"""OpenCV GStreamer (libcamerasrc) camera backend."""
from __future__ import annotations

import logging
from typing import Optional

import cv2
import numpy as np

from ..config.schema import Resolution
from .base import CameraBackend

log = logging.getLogger(__name__)


class GStreamerBackend(CameraBackend):
    """Camera backend using OpenCV with GStreamer pipeline (libcamerasrc)."""

    def __init__(self) -> None:
        self._cap: cv2.VideoCapture | None = None
        self._resolution: Resolution | None = None

    def open(self, resolution: Resolution) -> None:
        w, h = resolution.size
        pipeline = (
            f"libcamerasrc ! "
            f"video/x-raw,width={w},height={h},format=BGR ! "
            f"videoconvert ! "
            f"appsink drop=true sync=false"
        )
        self._cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        if not self._cap.isOpened():
            self._cap = None
            raise RuntimeError("Cannot open GStreamer pipeline")
        self._resolution = resolution
        # Warmup
        for _ in range(3):
            self._cap.read()
        log.info("GStreamer opened at %s", resolution.value)

    def close(self) -> None:
        if self._cap:
            self._cap.release()
            self._cap = None
        self._resolution = None
        log.info("GStreamer closed")

    def capture(self) -> np.ndarray:
        if not self._cap or not self._cap.isOpened():
            raise RuntimeError("GStreamer not open")
        ret, frame = self._cap.read()
        if not ret or frame is None:
            raise RuntimeError("GStreamer capture failed")
        return frame

    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    @property
    def resolution(self) -> Resolution | None:
        return self._resolution

    @property
    def backend_name(self) -> str:
        return "gstreamer"
