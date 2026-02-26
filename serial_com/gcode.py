"""G-code builder helpers."""
from __future__ import annotations


class GCodeBuilder:
    """Fluent builder for G-code command sequences."""

    def __init__(self) -> None:
        self._commands: list[str] = []

    def absolute_mode(self) -> GCodeBuilder:
        self._commands.append("G90")
        return self

    def relative_mode(self) -> GCodeBuilder:
        self._commands.append("G91")
        return self

    def home(self, axes: str = "") -> GCodeBuilder:
        """Home axes. Empty string = all axes."""
        cmd = "G28"
        if axes:
            cmd += " " + " ".join(axes.upper())
        self._commands.append(cmd)
        return self

    def move(self, x: float | None = None, y: float | None = None,
             z: float | None = None, feed: int | None = None) -> GCodeBuilder:
        parts = ["G1"]
        if x is not None:
            parts.append(f"X{x:.2f}")
        if y is not None:
            parts.append(f"Y{y:.2f}")
        if z is not None:
            parts.append(f"Z{z:.2f}")
        if feed is not None:
            parts.append(f"F{feed}")
        self._commands.append(" ".join(parts))
        return self

    def wait(self) -> GCodeBuilder:
        self._commands.append("M400")
        return self

    def get_position(self) -> GCodeBuilder:
        self._commands.append("M114")
        return self

    def emergency_stop(self) -> GCodeBuilder:
        self._commands.append("M112")
        return self

    def set_units_mm(self) -> GCodeBuilder:
        self._commands.append("G21")
        return self

    def disable_steppers(self) -> GCodeBuilder:
        self._commands.append("M84")
        return self

    def custom(self, gcode: str) -> GCodeBuilder:
        self._commands.append(gcode)
        return self

    def build(self) -> list[str]:
        return list(self._commands)

    def clear(self) -> GCodeBuilder:
        self._commands.clear()
        return self
