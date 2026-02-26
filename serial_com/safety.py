"""Safety guard — emergency stop, dead-man switch logic, home guard."""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Callable

from .base import MarlinConnection, Position

log = logging.getLogger(__name__)


class SafetyGuard:
    """Safety monitoring for CNC motion."""

    def __init__(
        self,
        connection: MarlinConnection,
        max_x: float = 300.0,
        max_y: float = 300.0,
        max_z: float = 100.0,
        require_home: bool = True,
    ) -> None:
        self._conn = connection
        self._max_x = max_x
        self._max_y = max_y
        self._max_z = max_z
        self._require_home = require_home
        self._homed = False
        self._estop_triggered = False
        self._on_estop: Callable[[], None] | None = None

    @property
    def is_homed(self) -> bool:
        return self._homed

    @property
    def estop_triggered(self) -> bool:
        return self._estop_triggered

    def set_homed(self) -> None:
        self._homed = True

    def set_estop_callback(self, callback: Callable[[], None]) -> None:
        self._on_estop = callback

    def validate_move(self, x: float | None, y: float | None, z: float | None) -> str | None:
        """Validate a proposed move. Returns error message or None if OK."""
        if self._estop_triggered:
            return "Emergency stop is active — reset required"
        if self._require_home and not self._homed:
            return "Machine must be homed before moving"
        if x is not None and (x < 0 or x > self._max_x):
            return f"X={x:.1f} out of range [0, {self._max_x}]"
        if y is not None and (y < 0 or y > self._max_y):
            return f"Y={y:.1f} out of range [0, {self._max_y}]"
        if z is not None and (z < 0 or z > self._max_z):
            return f"Z={z:.1f} out of range [0, {self._max_z}]"
        return None

    def trigger_estop(self) -> None:
        """Trigger emergency stop."""
        self._estop_triggered = True
        try:
            self._conn.emergency_stop()
        except Exception:
            log.exception("E-stop command failed")
        if self._on_estop:
            try:
                self._on_estop()
            except Exception:
                log.exception("E-stop callback failed")
        log.critical("EMERGENCY STOP triggered")

    def reset(self) -> None:
        """Reset after emergency stop. Machine must be re-homed."""
        self._estop_triggered = False
        self._homed = False
        log.info("Safety guard reset — re-homing required")
