"""OpenCV V4L2 camera backend."""
from __future__ import annotations

import logging
from typing import Optional

import cv2
import numpy as np

from ..config.schema import Resolution
from .base import CameraBackend

log = logging.getLogger(__name__)


class V4L2Backend(CameraBackend):
    """Camera backend using OpenCV with V4L2."""

    def __init__(self, device_path: str = "/dev/video0") -> None:
        self._device_path = device_path
        self._cap: cv2.VideoCapture | None = None
        self._resolution: Resolution | None = None

    def open(self, resolution: Resolution) -> None:
        w, h = resolution.size
        self._cap = cv2.VideoCapture(self._device_path, cv2.CAP_V4L2)
        if not self._cap.isOpened():
            self._cap = None
            raise RuntimeError(f"Cannot open V4L2 device: {self._device_path}")
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        self._resolution = resolution
        # Read and discard a few warmup frames
        for _ in range(3):
            self._cap.read()
        log.info("V4L2 opened %s at %s", self._device_path, resolution.value)

    def close(self) -> None:
        if self._cap:
            self._cap.release()
            self._cap = None
        self._resolution = None
        log.info("V4L2 closed")

    def capture(self) -> np.ndarray:
        if not self._cap or not self._cap.isOpened():
            raise RuntimeError("V4L2 not open")
        ret, frame = self._cap.read()
        if not ret or frame is None:
            raise RuntimeError("V4L2 capture failed")
        return frame

    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    @property
    def resolution(self) -> Resolution | None:
        return self._resolution

    @property
    def backend_name(self) -> str:
        return "v4l2"
