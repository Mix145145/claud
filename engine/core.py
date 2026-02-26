"""TuposcanEngine — top-level orchestrator composing all subsystems."""
from __future__ import annotations

import logging
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from ..calibration.calibrator import FOVCalibrator
from ..calibration.detector import MarkerDetector
from ..calibration.profiles import ProfileStore
from ..camera.base import CameraBackend
from ..camera.factory import create_camera
from ..camera.mjpeg_streamer import MJPEGStreamer
from ..config.manager import ConfigManager
from ..config.schema import (
    CameraBackendType, EngineState, Resolution, TuposcanConfig,
)
from ..scanner.estimator import TimeEstimator
from ..scanner.grid import GridCalculator, GridPlan
from ..scanner.project import ScanProject
from ..scanner.session import ScanSession
from ..serial_com.base import MarlinConnection
from ..serial_com.safety import SafetyGuard
from ..serial_com.stub import StubMarlinConnection
from .events import EventBus, EventType
from .state import StateMachine

log = logging.getLogger(__name__)


class TuposcanEngine:
    """Top-level facade that both UIs interact with.

    Composes camera, serial, calibration, scanner, and stitcher subsystems.
    UIs communicate via the EventBus — they never import subsystem modules directly.
    """

    def __init__(self, config_manager: ConfigManager) -> None:
        self._cm = config_manager
        self._bus = EventBus()
        self._state = StateMachine(self._bus)
        self._camera: CameraBackend | None = None
        self._serial: MarlinConnection | None = None
        self._safety: SafetyGuard | None = None
        self._profile_store: ProfileStore | None = None
        self._calibrator: FOVCalibrator | None = None
        self._scan_session: ScanSession | None = None
        self._scan_thread: threading.Thread | None = None
        self._mjpeg: MJPEGStreamer | None = None
        self._preview_running = False

    @property
    def event_bus(self) -> EventBus:
        return self._bus

    @property
    def state(self) -> EngineState:
        return self._state.state

    @property
    def config(self) -> TuposcanConfig:
        return self._cm.config

    @property
    def profile_store(self) -> ProfileStore | None:
        return self._profile_store

    @property
    def serial(self) -> MarlinConnection | None:
        return self._serial

    def save_config(self) -> None:
        """Save current configuration to disk."""
        self._cm.save()

    def config_snapshot(self) -> dict:
        """Return a serialisable dict copy of current config."""
        return self._cm.snapshot()

    def initialize(self) -> None:
        """Initialize all subsystems."""
        cfg = self._cm.config

        # Camera
        self._camera = create_camera(
            backend_type=cfg.camera.backend,
            resolution=cfg.camera.resolution,
            device_path=cfg.camera.device_path,
        )
        log.info("Camera: %s", self._camera.backend_name)

        # Serial
        if cfg.serial.port == "stub":
            self._serial = StubMarlinConnection(
                feed_rate_xy=cfg.serial.feed_rate_xy,
                feed_rate_z=cfg.serial.feed_rate_z,
            )
        else:
            # Try real serial, fallback to stub
            try:
                from ..serial_com.marlin import RealMarlinConnection
                self._serial = RealMarlinConnection(
                    port=cfg.serial.port,
                    baudrate=cfg.serial.baudrate,
                    timeout=cfg.serial.timeout_s,
                )
            except Exception as e:
                log.warning("Real serial not available (%s), using stub", e)
                self._serial = StubMarlinConnection(
                    feed_rate_xy=cfg.serial.feed_rate_xy,
                    feed_rate_z=cfg.serial.feed_rate_z,
                )
        self._serial.connect()
        log.info("Serial: %s", self._serial.connection_name)

        # Safety guard
        self._safety = SafetyGuard(self._serial)
        self._safety.set_estop_callback(self._on_estop)

        # Profile store
        profiles_path = Path(cfg.paths.fov_profiles_file)
        self._profile_store = ProfileStore(profiles_path)

        # Calibrator
        detector = MarkerDetector(
            dict_names=cfg.calibration.aruco_dicts,
            use_clahe=cfg.calibration.use_clahe,
            clahe_clip=cfg.calibration.clahe_clip,
            clahe_grid=cfg.calibration.clahe_grid,
            use_threshold=cfg.calibration.use_threshold,
            threshold_block_size=cfg.calibration.threshold_block_size,
            threshold_c=cfg.calibration.threshold_c,
        )
        self._calibrator = FOVCalibrator(
            camera=self._camera,
            detector=detector,
            profile_store=self._profile_store,
            event_bus=self._bus,
            config=cfg.calibration,
        )

        self._state.transition(EngineState.IDLE)
        self._bus.emit(EventType.ENGINE_INITIALIZED, {
            "camera_backend": self._camera.backend_name,
            "serial_backend": self._serial.connection_name,
        })
        log.info("Engine initialized")

    def shutdown(self) -> None:
        """Shut down all subsystems."""
        self._state.transition(EngineState.SHUTTING_DOWN)
        self.stop_preview()
        if self._scan_session and self._scan_session.is_running:
            self._scan_session.stop()
            if self._scan_thread:
                self._scan_thread.join(timeout=5.0)
        if self._camera:
            self._camera.close()
        if self._serial and self._serial.is_connected():
            self._serial.disconnect()
        self._state.force_state(EngineState.UNINITIALIZED)
        self._bus.emit(EventType.ENGINE_SHUTDOWN)
        log.info("Engine shut down")

    # -- Motion ------------------------------------------------------

    def home(self) -> None:
        """Home all axes."""
        if not self._state.transition(EngineState.HOMING):
            return
        try:
            self._serial.home()
            self._safety.set_homed()
            self._bus.emit(EventType.HOME_COMPLETE)
            pos = self._serial.get_position()
            self._bus.emit(EventType.POSITION_CHANGED, {
                "x": pos.x, "y": pos.y, "z": pos.z,
            })
        except Exception as e:
            self._bus.emit(EventType.SERIAL_ERROR, {"error": str(e)})
            self._state.transition(EngineState.ERROR)
            return
        self._state.transition(EngineState.IDLE)

    def jog(self, dx: float = 0, dy: float = 0, dz: float = 0) -> None:
        """Relative jog move."""
        if not self._state.is_in(EngineState.IDLE):
            return
        pos = self._serial.get_position()
        new_x = pos.x + dx
        new_y = pos.y + dy
        new_z = pos.z + dz
        err = self._safety.validate_move(new_x, new_y, new_z)
        if err:
            self._bus.emit(EventType.SERIAL_ERROR, {"error": err})
            return
        self._state.transition(EngineState.JOGGING)
        try:
            feed = self._cm.config.serial.feed_rate_xy if (dx or dy) else self._cm.config.serial.feed_rate_z
            self._serial.move_to(x=new_x, y=new_y, z=new_z, feed_rate=feed)
            self._serial.wait_for_move()
            pos = self._serial.get_position()
            self._bus.emit(EventType.POSITION_CHANGED, {
                "x": pos.x, "y": pos.y, "z": pos.z,
            })
        except Exception as e:
            self._bus.emit(EventType.SERIAL_ERROR, {"error": str(e)})
            self._state.transition(EngineState.ERROR)
            return
        self._state.transition(EngineState.IDLE)

    def move_to(self, x: float, y: float, z: float | None = None) -> None:
        """Absolute move."""
        if not self._state.is_in(EngineState.IDLE):
            return
        err = self._safety.validate_move(x, y, z)
        if err:
            self._bus.emit(EventType.SERIAL_ERROR, {"error": err})
            return
        self._state.transition(EngineState.JOGGING)
        try:
            self._serial.move_to(x=x, y=y, z=z, feed_rate=self._cm.config.serial.feed_rate_xy)
            self._serial.wait_for_move()
            pos = self._serial.get_position()
            self._bus.emit(EventType.POSITION_CHANGED, {
                "x": pos.x, "y": pos.y, "z": pos.z,
            })
        except Exception as e:
            self._bus.emit(EventType.SERIAL_ERROR, {"error": str(e)})
            self._state.transition(EngineState.ERROR)
            return
        self._state.transition(EngineState.IDLE)

    def emergency_stop(self) -> None:
        """Emergency stop — immediately halt all motion."""
        if self._safety:
            self._safety.trigger_estop()
        self._state.force_state(EngineState.ERROR)
        self._bus.emit(EventType.EMERGENCY_STOP)

    # -- Calibration -------------------------------------------------

    def calibrate(
        self, z_mm: float, resolutions: list[Resolution] | None = None,
    ) -> None:
        """Run calibration at given Z for specified resolutions."""
        if not self._state.transition(EngineState.CALIBRATING):
            return
        try:
            # Move to Z height first
            self._serial.move_to(z=z_mm, feed_rate=self._cm.config.serial.feed_rate_z)
            self._serial.wait_for_move()
            self._calibrator.calibrate_all_resolutions(z_mm, resolutions)
            # Re-open camera at the configured resolution
            self._camera.close()
            self._camera.open(self._cm.config.camera.resolution)
        except Exception as e:
            self._bus.emit(EventType.CALIBRATION_ERROR, {"error": str(e)})
            self._state.transition(EngineState.ERROR)
            return
        self._state.transition(EngineState.IDLE)

    # -- Scanning ----------------------------------------------------

    def start_scan(self) -> None:
        """Start a new scan based on current config."""
        if not self._state.transition(EngineState.SCANNING):
            return
        cfg = self._cm.config
        # Look up FOV profile
        profile = self._profile_store.get(cfg.scan.z_height_mm, cfg.camera.resolution.value)
        if not profile:
            self._bus.emit(EventType.SCAN_ERROR, {
                "error": f"No FOV profile for z={cfg.scan.z_height_mm} "
                         f"res={cfg.camera.resolution.value}. Calibrate first.",
            })
            self._state.transition(EngineState.IDLE)
            return

        # Calculate grid
        grid = GridCalculator.calculate(
            area_width_mm=cfg.scan.area_width_mm,
            area_height_mm=cfg.scan.area_height_mm,
            fov_x_mm=profile.fov_x_mm,
            fov_y_mm=profile.fov_y_mm,
            overlap_pct=cfg.scan.overlap_pct,
            origin_x_mm=cfg.scan.origin_x_mm,
            origin_y_mm=cfg.scan.origin_y_mm,
        )

        # Create project
        project = ScanProject(cfg.paths.scans_dir)
        project.create()
        project.save_config_snapshot(self._cm.snapshot())
        project.init_manifest(
            grid_cols=grid.cols,
            grid_rows=grid.rows,
            positions=[asdict(p) for p in grid.positions],
            z_mm=cfg.scan.z_height_mm,
            overlap_pct=cfg.scan.overlap_pct,
            resolution=cfg.camera.resolution.value,
            stitch_algorithm=cfg.scan.stitch_algorithm.value,
        )

        # Set Z height
        self._serial.move_to(z=cfg.scan.z_height_mm, feed_rate=cfg.serial.feed_rate_z)
        self._serial.wait_for_move()

        # Create session and run in thread
        self._scan_session = ScanSession(
            camera=self._camera,
            serial=self._serial,
            project=project,
            event_bus=self._bus,
            scan_config=cfg.scan,
            serial_config=cfg.serial,
        )
        self._scan_thread = threading.Thread(
            target=self._run_scan, args=(grid,), daemon=True,
        )
        self._scan_thread.start()

    def _run_scan(self, grid: GridPlan) -> None:
        try:
            completed = self._scan_session.run(grid)
            if completed:
                self._state.transition(EngineState.IDLE)
            else:
                self._state.transition(EngineState.IDLE)
        except Exception as e:
            log.exception("Scan thread error")
            self._bus.emit(EventType.SCAN_ERROR, {"error": str(e)})
            self._state.force_state(EngineState.ERROR)

    def pause_scan(self) -> None:
        if self._scan_session and self._state.is_in(EngineState.SCANNING):
            self._scan_session.pause()
            self._state.transition(EngineState.PAUSED)

    def resume_scan(self) -> None:
        if self._scan_session and self._state.is_in(EngineState.PAUSED):
            self._state.transition(EngineState.SCANNING)
            self._scan_session.resume()

    def stop_scan(self) -> None:
        if self._scan_session:
            self._scan_session.stop()
            if self._scan_thread:
                self._scan_thread.join(timeout=10.0)
            if not self._state.is_in(EngineState.IDLE):
                self._state.force_state(EngineState.IDLE)

    def resume_project(self, project_dir: str | Path) -> None:
        """Resume a previously interrupted scan."""
        if not self._state.transition(EngineState.SCANNING):
            return
        cfg = self._cm.config
        project = ScanProject(Path(project_dir).parent, Path(project_dir).name)
        manifest = project.load_manifest()
        if not manifest:
            self._bus.emit(EventType.SCAN_ERROR, {"error": "No manifest found"})
            self._state.transition(EngineState.IDLE)
            return

        profile = self._profile_store.get(manifest.z_height_mm, manifest.resolution)
        if not profile:
            self._bus.emit(EventType.SCAN_ERROR, {"error": "No FOV profile for resumed scan"})
            self._state.transition(EngineState.IDLE)
            return

        grid = GridCalculator.calculate(
            area_width_mm=cfg.scan.area_width_mm,
            area_height_mm=cfg.scan.area_height_mm,
            fov_x_mm=profile.fov_x_mm,
            fov_y_mm=profile.fov_y_mm,
            overlap_pct=manifest.overlap_pct,
            origin_x_mm=cfg.scan.origin_x_mm,
            origin_y_mm=cfg.scan.origin_y_mm,
        )

        self._serial.move_to(z=manifest.z_height_mm, feed_rate=cfg.serial.feed_rate_z)
        self._serial.wait_for_move()

        self._scan_session = ScanSession(
            camera=self._camera,
            serial=self._serial,
            project=project,
            event_bus=self._bus,
            scan_config=cfg.scan,
            serial_config=cfg.serial,
        )
        self._scan_thread = threading.Thread(
            target=self._run_scan, args=(grid,), daemon=True,
        )
        self._scan_thread.start()

    # -- Estimation --------------------------------------------------

    def estimate_scan_time(self) -> dict:
        """Estimate scan time based on current config and profiles."""
        cfg = self._cm.config
        profile = self._profile_store.get(cfg.scan.z_height_mm, cfg.camera.resolution.value)
        if not profile:
            return {"error": "No FOV profile — calibrate first"}
        grid = GridCalculator.calculate(
            area_width_mm=cfg.scan.area_width_mm,
            area_height_mm=cfg.scan.area_height_mm,
            fov_x_mm=profile.fov_x_mm,
            fov_y_mm=profile.fov_y_mm,
            overlap_pct=cfg.scan.overlap_pct,
        )
        estimator = TimeEstimator()
        estimator.set_settle_delay(cfg.serial.settle_delay_s)
        est = estimator.estimate(grid.total_frames)
        return {
            "cols": grid.cols,
            "rows": grid.rows,
            "total_frames": grid.total_frames,
            "estimated_seconds": est.estimated_seconds,
        }

    # -- Preview -----------------------------------------------------

    def start_preview(self, fps: int | None = None) -> None:
        if not self._camera or not self._camera.is_open():
            return
        if self._mjpeg:
            self._mjpeg.stop()
        f = fps or self._cm.config.camera.preview_fps
        self._mjpeg = MJPEGStreamer(self._camera, fps=f)
        self._mjpeg.start()
        self._preview_running = True

    def stop_preview(self) -> None:
        if self._mjpeg:
            self._mjpeg.stop()
            self._mjpeg = None
        self._preview_running = False

    def get_mjpeg_streamer(self) -> MJPEGStreamer | None:
        return self._mjpeg

    def capture_snapshot(self):
        """Capture a single frame."""
        if self._camera and self._camera.is_open():
            return self._camera.capture()
        return None

    # -- Internals ---------------------------------------------------

    def _on_estop(self) -> None:
        if self._scan_session:
            self._scan_session.stop()
        self._state.force_state(EngineState.ERROR)
