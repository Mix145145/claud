"""Platform detection and dependency checking."""
from __future__ import annotations

import importlib
import platform
import shutil
import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class PlatformInfo:
    system: str
    machine: str
    is_raspberry_pi: bool
    python_version: str
    hostname: str


def get_platform_info() -> PlatformInfo:
    """Detect current platform."""
    system = platform.system()
    machine = platform.machine()
    is_rpi = False
    if system == "Linux" and machine.startswith("aarch64"):
        try:
            with open("/proc/device-tree/model", "r") as f:
                model = f.read().lower()
            is_rpi = "raspberry pi" in model
        except (FileNotFoundError, PermissionError):
            pass
    return PlatformInfo(
        system=system,
        machine=machine,
        is_raspberry_pi=is_rpi,
        python_version=platform.python_version(),
        hostname=platform.node(),
    )


@dataclass
class DepStatus:
    name: str
    available: bool
    version: str = ""
    error: str = ""


def check_dependencies() -> list[DepStatus]:
    """Check availability of key dependencies."""
    deps = []
    for mod_name, display in [
        ("cv2", "OpenCV"),
        ("numpy", "NumPy"),
        ("picamera2", "Picamera2"),
        ("serial", "pyserial"),
        ("PyQt6", "PyQt6"),
        ("fastapi", "FastAPI"),
        ("uvicorn", "uvicorn"),
    ]:
        try:
            mod = importlib.import_module(mod_name)
            ver = getattr(mod, "__version__", getattr(mod, "VERSION", "unknown"))
            deps.append(DepStatus(name=display, available=True, version=str(ver)))
        except ImportError as e:
            deps.append(DepStatus(name=display, available=False, error=str(e)))

    # Check libcamera CLI
    if shutil.which("libcamera-still"):
        deps.append(DepStatus(name="libcamera-cli", available=True))
    else:
        deps.append(DepStatus(name="libcamera-cli", available=False, error="not in PATH"))

    return deps
