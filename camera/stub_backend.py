"""Stub camera backend — generates synthetic frames with ArUco markers for dev/testing."""
from __future__ import annotations

import logging
import time
from typing import Optional

import cv2
import numpy as np

from ..config.schema import Resolution
from .base import CameraBackend

log = logging.getLogger(__name__)


class StubBackend(CameraBackend):
    """Generates synthetic frames with ArUco markers for development and testing."""

    def __init__(
        self,
        marker_size_px: int = 80,
        marker_id: int = 0,
        aruco_dict_name: str = "DICT_4X4_50",
        noise_level: int = 10,
    ) -> None:
        self._resolution: Resolution | None = None
        self._marker_size_px = marker_size_px
        self._marker_id = marker_id
        self._noise_level = noise_level
        self._opened = False
        self._frame_count = 0
        self._aruco_dict = cv2.aruco.getPredefinedDictionary(
            getattr(cv2.aruco, aruco_dict_name)
        )

    def open(self, resolution: Resolution) -> None:
        self._resolution = resolution
        self._opened = True
        self._frame_count = 0
        log.info("StubBackend opened at %s", resolution.value)

    def close(self) -> None:
        self._opened = False
        self._resolution = None
        log.info("StubBackend closed")

    def capture(self) -> np.ndarray:
        if not self._opened or not self._resolution:
            raise RuntimeError("StubBackend is not open")
        w, h = self._resolution.size
        frame = np.full((h, w, 3), 200, dtype=np.uint8)  # Light gray background

        # Add subtle grid pattern
        for y in range(0, h, 50):
            cv2.line(frame, (0, y), (w, y), (190, 190, 190), 1)
        for x in range(0, w, 50):
            cv2.line(frame, (x, 0), (x, h), (190, 190, 190), 1)

        # Render ArUco marker in centre
        marker_img = cv2.aruco.generateImageMarker(
            self._aruco_dict, self._marker_id, self._marker_size_px
        )
        marker_bgr = cv2.cvtColor(marker_img, cv2.COLOR_GRAY2BGR)
        my = (h - self._marker_size_px) // 2
        mx = (w - self._marker_size_px) // 2
        frame[my : my + self._marker_size_px, mx : mx + self._marker_size_px] = marker_bgr

        # Add some noise for realism
        if self._noise_level > 0:
            noise = np.random.randint(
                -self._noise_level, self._noise_level + 1,
                frame.shape, dtype=np.int16,
            )
            frame = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)

        # Add frame counter overlay
        self._frame_count += 1
        cv2.putText(
            frame, f"STUB #{self._frame_count}", (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2,
        )
        cv2.putText(
            frame, f"{self._resolution.value}", (10, 60),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 100, 100), 1,
        )

        return frame

    def is_open(self) -> bool:
        return self._opened

    @property
    def resolution(self) -> Resolution | None:
        return self._resolution

    @property
    def backend_name(self) -> str:
        return "stub"
