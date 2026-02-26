"""MJPEG byte-stream generator for web preview."""
from __future__ import annotations

import logging
import threading
import time
from typing import Generator, Optional

import cv2
import numpy as np

from .base import CameraBackend

log = logging.getLogger(__name__)


class MJPEGStreamer:
    """Generates MJPEG byte stream from camera frames for HTTP streaming."""

    BOUNDARY = b"--frame"

    def __init__(self, camera: CameraBackend, fps: int = 15, quality: int = 70) -> None:
        self._camera = camera
        self._fps = fps
        self._quality = quality
        self._running = False
        self._lock = threading.Lock()
        self._latest_frame: bytes | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _capture_loop(self) -> None:
        interval = 1.0 / self._fps
        while self._running:
            t0 = time.monotonic()
            try:
                frame = self._camera.capture()
                _, buf = cv2.imencode(
                    ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self._quality]
                )
                with self._lock:
                    self._latest_frame = buf.tobytes()
            except Exception:
                log.exception("MJPEG capture error")
            elapsed = time.monotonic() - t0
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def generate(self) -> Generator[bytes, None, None]:
        """Yield MJPEG frames as multipart HTTP chunks."""
        interval = 1.0 / self._fps
        while self._running:
            with self._lock:
                jpeg = self._latest_frame
            if jpeg:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n"
                    b"\r\n" + jpeg + b"\r\n"
                )
            time.sleep(interval)

    @property
    def content_type(self) -> str:
        return "multipart/x-mixed-replace; boundary=frame"
