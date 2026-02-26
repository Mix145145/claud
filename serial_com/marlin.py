"""Real Marlin serial connection via pyserial."""
from __future__ import annotations

import logging
import re
import time
from typing import Optional

import serial

from .base import MarlinConnection, Position

log = logging.getLogger(__name__)

_POS_RE = re.compile(r"X:([0-9.-]+)\s+Y:([0-9.-]+)\s+Z:([0-9.-]+)")


class RealMarlinConnection(MarlinConnection):
    """Real serial connection to Marlin firmware."""

    def __init__(self, port: str = "auto", baudrate: int = 250_000,
                 timeout: float = 10.0) -> None:
        self._port = port
        self._baudrate = baudrate
        self._timeout = timeout
        self._serial: serial.Serial | None = None
        self._position = Position(0, 0, 0)

    def connect(self) -> None:
        port = self._port
        if port == "auto":
            port = self._auto_detect_port()
        self._serial = serial.Serial(
            port=port,
            baudrate=self._baudrate,
            timeout=self._timeout,
        )
        # Wait for Marlin boot
        time.sleep(2.0)
        self._flush_input()
        # Set absolute mode and mm units
        self.send_command("G90")
        self.send_command("G21")
        log.info("Connected to Marlin on %s @ %d", port, self._baudrate)

    def disconnect(self) -> None:
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._serial = None
        log.info("Disconnected from Marlin")

    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def send_command(self, gcode: str, wait_ok: bool = True) -> str:
        if not self._serial or not self._serial.is_open:
            raise RuntimeError("Serial not connected")
        cmd = gcode.strip() + "\n"
        self._serial.write(cmd.encode("ascii"))
        log.debug("TX: %s", gcode.strip())

        if not wait_ok:
            return ""

        response_lines = []
        deadline = time.time() + self._timeout
        while time.time() < deadline:
            line = self._serial.readline().decode("ascii", errors="replace").strip()
            if not line:
                continue
            log.debug("RX: %s", line)
            response_lines.append(line)
            if line.startswith("ok"):
                break
            if line.startswith("Error") or line.startswith("!!"):
                raise RuntimeError(f"Marlin error: {line}")
        return "\n".join(response_lines)

    def home(self) -> None:
        self.send_command("G28")
        self._position = Position(0, 0, 0)

    def move_to(self, x: float | None = None, y: float | None = None,
                z: float | None = None, feed_rate: int | None = None) -> None:
        self.send_command("G90")
        parts = ["G1"]
        if x is not None:
            parts.append(f"X{x:.2f}")
        if y is not None:
            parts.append(f"Y{y:.2f}")
        if z is not None:
            parts.append(f"Z{z:.2f}")
        if feed_rate:
            parts.append(f"F{feed_rate}")
        self.send_command(" ".join(parts))

    def wait_for_move(self) -> None:
        self.send_command("M400")

    def get_position(self) -> Position:
        response = self.send_command("M114")
        match = _POS_RE.search(response)
        if match:
            self._position = Position(
                x=float(match.group(1)),
                y=float(match.group(2)),
                z=float(match.group(3)),
            )
        return Position(self._position.x, self._position.y, self._position.z)

    def emergency_stop(self) -> None:
        if self._serial and self._serial.is_open:
            self._serial.write(b"M112\n")
            log.critical("EMERGENCY STOP sent")

    @property
    def connection_name(self) -> str:
        port = self._serial.port if self._serial else self._port
        return f"marlin:{port}"

    def _auto_detect_port(self) -> str:
        """Try to find a Marlin device on common serial ports."""
        import serial.tools.list_ports
        candidates = []
        for info in serial.tools.list_ports.comports():
            desc = (info.description or "").lower()
            if any(kw in desc for kw in ["marlin", "arduino", "ch340", "cp210", "usb serial"]):
                candidates.append(info.device)
            elif info.device.startswith("/dev/ttyUSB") or info.device.startswith("/dev/ttyACM"):
                candidates.append(info.device)
        if not candidates:
            raise RuntimeError("No serial ports found. Specify port explicitly.")
        log.info("Auto-detected serial port: %s", candidates[0])
        return candidates[0]

    def _flush_input(self) -> None:
        if self._serial:
            self._serial.reset_input_buffer()
            time.sleep(0.1)
            while self._serial.in_waiting:
                self._serial.read(self._serial.in_waiting)
                time.sleep(0.05)
