"""FOV calibrator — capture multiple frames, detect markers, compute median mm_per_px."""
from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass
from typing import Optional

import numpy as np

from ..camera.base import CameraBackend
from ..config.schema import Resolution, CalibrationConfig
from ..engine.events import EventBus, EventType
from .detector import MarkerDetector, DetectionResult
from .profiles import FOVProfile, ProfileStore

log = logging.getLogger(__name__)


@dataclass
class CalibrationResult:
    """Result of calibration for one resolution at one Z height."""
    z_mm: float
    resolution: str
    success: bool
    mm_per_px: float = 0.0
    fov_x_mm: float = 0.0
    fov_y_mm: float = 0.0
    num_detections: int = 0
    std_dev: float = 0.0
    error: str = ""


class FOVCalibrator:
    """Calibrate FOV by detecting a known-size marker across multiple frames.

    Captures num_frames images, detects the marker in each, computes
    mm_per_px = marker_size_mm / marker_size_px, and takes the median.
    """

    def __init__(
        self,
        camera: CameraBackend,
        detector: MarkerDetector,
        profile_store: ProfileStore,
        event_bus: EventBus,
        config: CalibrationConfig,
    ) -> None:
        self._camera = camera
        self._detector = detector
        self._store = profile_store
        self._bus = event_bus
        self._config = config

    def calibrate(self, z_mm: float, resolution: Resolution) -> CalibrationResult:
        """Calibrate a single resolution at a given Z height."""
        marker_mm = self._config.marker_size_mm
        num_frames = self._config.num_frames
        res_str = resolution.value
        w, h = resolution.size

        self._bus.emit(EventType.CALIBRATION_STARTED, {
            "z_mm": z_mm, "resolution": res_str,
        })

        mm_per_px_values: list[float] = []

        for i in range(num_frames):
            try:
                frame = self._camera.capture()
                result = self._detector.detect(frame)
                self._bus.emit(EventType.CALIBRATION_FRAME, {
                    "frame_index": i,
                    "total_frames": num_frames,
                    "detected": result.found,
                    "marker_size_px": result.marker_size_px,
                })
                if result.found and result.marker_size_px > 0:
                    mpp = marker_mm / result.marker_size_px
                    mm_per_px_values.append(mpp)
            except Exception as e:
                log.warning("Calibration frame %d failed: %s", i, e)

        if len(mm_per_px_values) < 3:
            err = f"Only {len(mm_per_px_values)} detections (need >=3)"
            log.error("Calibration failed for z=%.1f %s: %s", z_mm, res_str, err)
            self._bus.emit(EventType.CALIBRATION_ERROR, {
                "z_mm": z_mm, "resolution": res_str, "error": err,
            })
            return CalibrationResult(
                z_mm=z_mm, resolution=res_str, success=False, error=err,
                num_detections=len(mm_per_px_values),
            )

        median_mpp = statistics.median(mm_per_px_values)
        std_dev = statistics.stdev(mm_per_px_values) if len(mm_per_px_values) > 1 else 0.0
        fov_x = w * median_mpp
        fov_y = h * median_mpp

        profile = FOVProfile(
            z_mm=z_mm,
            resolution=res_str,
            mm_per_px=round(median_mpp, 6),
            fov_x_mm=round(fov_x, 2),
            fov_y_mm=round(fov_y, 2),
            num_samples=len(mm_per_px_values),
            std_dev=round(std_dev, 6),
        )
        self._store.put(profile)

        result = CalibrationResult(
            z_mm=z_mm,
            resolution=res_str,
            success=True,
            mm_per_px=profile.mm_per_px,
            fov_x_mm=profile.fov_x_mm,
            fov_y_mm=profile.fov_y_mm,
            num_detections=len(mm_per_px_values),
            std_dev=profile.std_dev,
        )
        self._bus.emit(EventType.CALIBRATION_RESULT, {
            "z_mm": z_mm, "resolution": res_str,
            "mm_per_px": profile.mm_per_px,
            "fov_x_mm": profile.fov_x_mm,
            "fov_y_mm": profile.fov_y_mm,
        })
        log.info(
            "Calibration OK: z=%.1f %s mm/px=%.5f fov=%.1fx%.1f mm",
            z_mm, res_str, median_mpp, fov_x, fov_y,
        )
        return result

    def calibrate_all_resolutions(
        self, z_mm: float, resolutions: list[Resolution] | None = None,
    ) -> list[CalibrationResult]:
        """Calibrate all resolutions at a given Z height."""
        if resolutions is None:
            resolutions = [Resolution.FHD, Resolution.QHD, Resolution.UHD]
        results = []
        for res in resolutions:
            self._camera.close()
            self._camera.open(res)
            r = self.calibrate(z_mm, res)
            results.append(r)
        self._bus.emit(EventType.CALIBRATION_COMPLETE, {
            "z_mm": z_mm,
            "results": [
                {"resolution": r.resolution, "success": r.success, "mm_per_px": r.mm_per_px}
                for r in results
            ],
        })
        return results
