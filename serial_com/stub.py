"""Stub Marlin connection — virtual XYZ tracking for dev/testing."""
from __future__ import annotations

import logging
import time
from typing import Optional

from .base import MarlinConnection, Position

log = logging.getLogger(__name__)


class StubMarlinConnection(MarlinConnection):
    """Virtual CNC for development. Tracks position, simulates move timing."""

    def __init__(self, feed_rate_xy: int = 3000, feed_rate_z: int = 600) -> None:
        self._position = Position(0, 0, 0)
        self._connected = False
        self._feed_rate_xy = feed_rate_xy
        self._feed_rate_z = feed_rate_z
        self._homed = False
        self._command_history: list[str] = []
        self._simulate_timing = True

    def connect(self) -> None:
        self._connected = True
        log.info("StubMarlin connected")

    def disconnect(self) -> None:
        self._connected = False
        log.info("StubMarlin disconnected")

    def is_connected(self) -> bool:
        return self._connected

    def send_command(self, gcode: str, wait_ok: bool = True) -> str:
        if not self._connected:
            raise RuntimeError("StubMarlin not connected")
        self._command_history.append(gcode)
        log.debug("STUB TX: %s", gcode)
        return "ok"

    def home(self) -> None:
        self.send_command("G28")
        self._position = Position(0, 0, 0)
        self._homed = True
        if self._simulate_timing:
            time.sleep(0.1)  # Simulate homing time (shortened for dev)
        log.info("StubMarlin homed")

    def move_to(self, x: float | None = None, y: float | None = None,
                z: float | None = None, feed_rate: int | None = None) -> None:
        parts = ["G1"]
        target_x = x if x is not None else self._position.x
        target_y = y if y is not None else self._position.y
        target_z = z if z is not None else self._position.z

        if x is not None:
            parts.append(f"X{x:.2f}")
        if y is not None:
            parts.append(f"Y{y:.2f}")
        if z is not None:
            parts.append(f"Z{z:.2f}")
        if feed_rate:
            parts.append(f"F{feed_rate}")

        self.send_command("G90")  # Absolute positioning
        self.send_command(" ".join(parts))

        # Simulate move time
        if self._simulate_timing:
            dx = target_x - self._position.x
            dy = target_y - self._position.y
            dz = target_z - self._position.z
            dist_xy = (dx ** 2 + dy ** 2) ** 0.5
            fr = feed_rate or self._feed_rate_xy
            move_time = (dist_xy / fr * 60) if dist_xy > 0 else 0
            z_time = (abs(dz) / self._feed_rate_z * 60) if dz != 0 else 0
            delay = min(max(move_time, z_time), 0.5)  # Cap at 0.5s for dev
            if delay > 0:
                time.sleep(delay)

        self._position = Position(target_x, target_y, target_z)

    def wait_for_move(self) -> None:
        self.send_command("M400")
        # No extra delay needed — move_to already simulated timing

    def get_position(self) -> Position:
        return Position(self._position.x, self._position.y, self._position.z)

    def emergency_stop(self) -> None:
        self.send_command("M112")
        self._connected = False
        log.warning("StubMarlin EMERGENCY STOP")

    @property
    def connection_name(self) -> str:
        return "stub"

    @property
    def command_history(self) -> list[str]:
        """Access command history for test assertions."""
        return list(self._command_history)

    def clear_history(self) -> None:
        self._command_history.clear()
