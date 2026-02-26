"""Abstract base class for Marlin serial connections."""
from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass
class Position:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __str__(self) -> str:
        return f"X{self.x:.2f} Y{self.y:.2f} Z{self.z:.2f}"


class MarlinConnection(abc.ABC):
    """Interface for Marlin CNC communication."""

    @abc.abstractmethod
    def connect(self) -> None:
        """Establish connection."""

    @abc.abstractmethod
    def disconnect(self) -> None:
        """Close connection."""

    @abc.abstractmethod
    def is_connected(self) -> bool:
        """Check if connection is active."""

    @abc.abstractmethod
    def send_command(self, gcode: str, wait_ok: bool = True) -> str:
        """Send a G-code command and optionally wait for 'ok' response."""

    @abc.abstractmethod
    def home(self) -> None:
        """Home all axes (G28)."""

    @abc.abstractmethod
    def move_to(self, x: float | None = None, y: float | None = None,
                z: float | None = None, feed_rate: int | None = None) -> None:
        """Move to absolute position. None means don't change that axis."""

    @abc.abstractmethod
    def wait_for_move(self) -> None:
        """Wait for all moves to complete (M400)."""

    @abc.abstractmethod
    def get_position(self) -> Position:
        """Return current position."""

    @abc.abstractmethod
    def emergency_stop(self) -> None:
        """Emergency stop (M112)."""

    @property
    @abc.abstractmethod
    def connection_name(self) -> str:
        """Human-readable connection name."""
