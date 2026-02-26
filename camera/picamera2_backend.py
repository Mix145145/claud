"""Picamera2 (libcamera) camera backend for Raspberry Pi."""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from ..config.schema import Resolution
from .base import CameraBackend

log = logging.getLogger(__name__)


class Picamera2Backend(CameraBackend):
    """Camera backend using Picamera2 (libcamera) on Raspberry Pi."""

    def __init__(self) -> None:
        self._picam = None
        self._resolution: Resolution | None = None

    def open(self, resolution: Resolution) -> None:
        from picamera2 import Picamera2

        self._picam = Picamera2()
        w, h = resolution.size
        config = self._picam.create_still_configuration(
            main={"size": (w, h), "format": "BGR888"},
        )
        self._picam.configure(config)
        self._picam.start()
        self._resolution = resolution
        log.info("Picamera2 opened at %s", resolution.value)

    def close(self) -> None:
        if self._picam:
            self._picam.stop()
            self._picam.close()
            self._picam = None
        self._resolution = None
        log.info("Picamera2 closed")

    def capture(self) -> np.ndarray:
        if not self._picam:
            raise RuntimeError("Picamera2 not open")
        frame = self._picam.capture_array("main")
        return frame

    def is_open(self) -> bool:
        return self._picam is not None

    @property
    def resolution(self) -> Resolution | None:
        return self._resolution

    @property
    def backend_name(self) -> str:
        return "picamera2"

    def set_exposure(self, exposure_us: int) -> None:
        if not self._picam:
            return
        if exposure_us == 0:
            self._picam.set_controls({"AeEnable": True})
        else:
            self._picam.set_controls({
                "AeEnable": False,
                "ExposureTime": exposure_us,
            })

    def set_gain(self, gain: float) -> None:
        if not self._picam:
            return
        if gain == 0:
            self._picam.set_controls({"AeEnable": True})
        else:
            self._picam.set_controls({
                "AeEnable": False,
                "AnalogueGain": gain,
            })
