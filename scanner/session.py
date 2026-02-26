"""Scan session — move->wait->capture loop with pause/resume support."""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import numpy as np

from ..camera.base import CameraBackend
from ..config.schema import ScanConfig, SerialConfig
from ..engine.events import EventBus, EventType
from ..serial_com.base import MarlinConnection
from ..utils.imaging import safe_imwrite
from .estimator import TimeEstimator
from .grid import GridCalculator, GridPlan, GridPosition
from .project import ScanProject, ShotRecord

log = logging.getLogger(__name__)


class ScanSession:
    """Execute a grid scan: move -> wait -> capture -> save for each position."""

    def __init__(
        self,
        camera: CameraBackend,
        serial: MarlinConnection,
        project: ScanProject,
        event_bus: EventBus,
        scan_config: ScanConfig,
        serial_config: SerialConfig,
    ) -> None:
        self._camera = camera
        self._serial = serial
        self._project = project
        self._bus = event_bus
        self._scan_cfg = scan_config
        self._serial_cfg = serial_config
        self._estimator = TimeEstimator()
        self._estimator.set_settle_delay(serial_config.settle_delay_s)
        self._paused = threading.Event()
        self._paused.set()  # Not paused initially
        self._stop_requested = False
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def pause(self) -> None:
        self._paused.clear()
        self._bus.emit(EventType.SCAN_PAUSED)
        log.info("Scan paused")

    def resume(self) -> None:
        self._paused.set()
        self._bus.emit(EventType.SCAN_RESUMED)
        log.info("Scan resumed")

    def stop(self) -> None:
        self._stop_requested = True
        self._paused.set()  # Unblock if paused so the loop can exit
        log.info("Scan stop requested")

    def run(self, grid_plan: GridPlan) -> bool:
        """Execute the scan. Returns True if completed, False if stopped/error."""
        self._running = True
        self._stop_requested = False
        pending = self._project.get_pending_shots()
        total = grid_plan.total_frames
        captured_so_far = total - len(pending)

        self._bus.emit(EventType.SCAN_STARTED, {
            "total_frames": total,
            "pending_frames": len(pending),
            "grid_cols": grid_plan.cols,
            "grid_rows": grid_plan.rows,
        })

        for shot in pending:
            # Check pause
            self._paused.wait()

            # Check stop
            if self._stop_requested:
                log.info("Scan stopped by user at frame %d/%d", captured_so_far, total)
                self._running = False
                return False

            # Move
            t_move_start = time.monotonic()
            try:
                self._serial.move_to(
                    x=shot.x_mm, y=shot.y_mm,
                    feed_rate=self._serial_cfg.feed_rate_xy,
                )
                self._serial.wait_for_move()
            except Exception as e:
                log.error("Move failed at frame %d: %s", shot.index, e)
                self._project.mark_failed(shot.index, str(e))
                self._bus.emit(EventType.SCAN_ERROR, {
                    "frame_index": shot.index, "error": str(e),
                })
                continue
            t_move = time.monotonic() - t_move_start
            self._estimator.record_move(t_move)

            # Settle delay
            time.sleep(self._serial_cfg.settle_delay_s)

            # Capture
            t_cap_start = time.monotonic()
            try:
                frame = self._camera.capture()
                frame_path = self._project.frame_path(shot)
                safe_imwrite(frame_path, frame)
                self._project.mark_captured(shot.index)
                captured_so_far += 1
            except Exception as e:
                log.error("Capture failed at frame %d: %s", shot.index, e)
                self._project.mark_failed(shot.index, str(e))
                self._bus.emit(EventType.SCAN_ERROR, {
                    "frame_index": shot.index, "error": str(e),
                })
                continue
            t_cap = time.monotonic() - t_cap_start
            self._estimator.record_capture(t_cap)

            # Progress event
            remaining_s = self._estimator.remaining(total - captured_so_far)
            self._bus.emit(EventType.SCAN_PROGRESS, {
                "frame_index": shot.index,
                "captured": captured_so_far,
                "total": total,
                "progress_pct": round(captured_so_far / total * 100, 1),
                "remaining_seconds": remaining_s,
                "x_mm": shot.x_mm,
                "y_mm": shot.y_mm,
            })
            self._bus.emit(EventType.SCAN_FRAME_CAPTURED, {
                "frame_index": shot.index,
                "col": shot.col,
                "row": shot.row,
                "filename": shot.filename,
            })

        self._running = False
        self._bus.emit(EventType.SCAN_COMPLETE, {
            "total_captured": captured_so_far,
            "total_frames": total,
        })
        log.info("Scan complete: %d/%d frames", captured_so_far, total)
        return True
