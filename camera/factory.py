"""Camera backend factory — auto-detect with fallback chain."""
from __future__ import annotations

import logging
from typing import Optional

from ..config.schema import CameraBackendType, Resolution
from .base import CameraBackend
from .stub_backend import StubBackend

log = logging.getLogger(__name__)


def _try_picamera2(resolution: Resolution) -> CameraBackend | None:
    try:
        from .picamera2_backend import Picamera2Backend
        cam = Picamera2Backend()
        cam.open(resolution)
        return cam
    except Exception as e:
        log.debug("Picamera2 not available: %s", e)
        return None


def _try_v4l2(resolution: Resolution, device: str) -> CameraBackend | None:
    try:
        from .v4l2_backend import V4L2Backend
        cam = V4L2Backend(device_path=device)
        cam.open(resolution)
        return cam
    except Exception as e:
        log.debug("V4L2 not available: %s", e)
        return None


def _try_gstreamer(resolution: Resolution) -> CameraBackend | None:
    try:
        from .gstreamer_backend import GStreamerBackend
        cam = GStreamerBackend()
        cam.open(resolution)
        return cam
    except Exception as e:
        log.debug("GStreamer not available: %s", e)
        return None


def create_camera(
    backend_type: CameraBackendType = CameraBackendType.AUTO,
    resolution: Resolution = Resolution.FHD,
    device_path: str = "/dev/video0",
) -> CameraBackend:
    """Create and open a camera backend.

    AUTO mode tries: Picamera2 → V4L2 → GStreamer → Stub.
    """
    if backend_type == CameraBackendType.STUB:
        cam = StubBackend()
        cam.open(resolution)
        return cam

    if backend_type == CameraBackendType.PICAMERA2:
        from .picamera2_backend import Picamera2Backend
        cam = Picamera2Backend()
        cam.open(resolution)
        return cam

    if backend_type == CameraBackendType.V4L2:
        from .v4l2_backend import V4L2Backend
        cam = V4L2Backend(device_path=device_path)
        cam.open(resolution)
        return cam

    if backend_type == CameraBackendType.GSTREAMER:
        from .gstreamer_backend import GStreamerBackend
        cam = GStreamerBackend()
        cam.open(resolution)
        return cam

    # AUTO: try in priority order
    for name, try_fn in [
        ("Picamera2", lambda: _try_picamera2(resolution)),
        ("V4L2", lambda: _try_v4l2(resolution, device_path)),
        ("GStreamer", lambda: _try_gstreamer(resolution)),
    ]:
        cam = try_fn()
        if cam is not None:
            log.info("Auto-detected camera backend: %s", name)
            return cam

    log.warning("No real camera backend available, falling back to stub")
    cam = StubBackend()
    cam.open(resolution)
    return cam
