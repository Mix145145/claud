"""Abstract base class for camera backends."""
from __future__ import annotations

import abc
from typing import Optional

import numpy as np

from ..config.schema import Resolution


class CameraBackend(abc.ABC):
    """Interface for all camera backends."""

    @abc.abstractmethod
    def open(self, resolution: Resolution) -> None:
        """Open and configure the camera."""

    @abc.abstractmethod
    def close(self) -> None:
        """Release camera resources."""

    @abc.abstractmethod
    def capture(self) -> np.ndarray:
        """Capture and return a single BGR frame."""

    @abc.abstractmethod
    def is_open(self) -> bool:
        """Check if camera is open and functional."""

    @property
    @abc.abstractmethod
    def resolution(self) -> Resolution | None:
        """Currently active resolution, or None if not open."""

    @property
    @abc.abstractmethod
    def backend_name(self) -> str:
        """Human-readable backend name."""

    def set_exposure(self, exposure_us: int) -> None:
        """Set exposure time in microseconds. 0 = auto. Override if supported."""
        pass

    def set_gain(self, gain: float) -> None:
        """Set analogue gain. 0 = auto. Override if supported."""
        pass
