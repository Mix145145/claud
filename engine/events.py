"""Thread-safe event bus for UI decoupling."""
from __future__ import annotations

import enum
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger(__name__)


class EventType(enum.Enum):
    # Engine lifecycle
    ENGINE_INITIALIZED = "engine_initialized"
    ENGINE_SHUTDOWN = "engine_shutdown"
    ENGINE_ERROR = "engine_error"
    STATE_CHANGED = "state_changed"

    # Camera
    PREVIEW_FRAME = "preview_frame"
    FRAME_CAPTURED = "frame_captured"
    CAMERA_CONNECTED = "camera_connected"
    CAMERA_ERROR = "camera_error"

    # Serial / Motion
    SERIAL_CONNECTED = "serial_connected"
    SERIAL_DISCONNECTED = "serial_disconnected"
    SERIAL_ERROR = "serial_error"
    POSITION_CHANGED = "position_changed"
    HOME_COMPLETE = "home_complete"
    MOVE_COMPLETE = "move_complete"
    EMERGENCY_STOP = "emergency_stop"

    # Calibration
    CALIBRATION_STARTED = "calibration_started"
    CALIBRATION_FRAME = "calibration_frame"
    CALIBRATION_RESULT = "calibration_result"
    CALIBRATION_COMPLETE = "calibration_complete"
    CALIBRATION_ERROR = "calibration_error"

    # Scanning
    SCAN_STARTED = "scan_started"
    SCAN_PROGRESS = "scan_progress"
    SCAN_FRAME_CAPTURED = "scan_frame_captured"
    SCAN_PAUSED = "scan_paused"
    SCAN_RESUMED = "scan_resumed"
    SCAN_COMPLETE = "scan_complete"
    SCAN_ERROR = "scan_error"

    # Stitching
    STITCH_STARTED = "stitch_started"
    STITCH_PROGRESS = "stitch_progress"
    STITCH_COMPLETE = "stitch_complete"
    STITCH_ERROR = "stitch_error"

    # Log
    LOG_MESSAGE = "log_message"


@dataclass
class Event:
    type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


# Subscriber callback type
Subscriber = Callable[[Event], None]


class EventBus:
    """Thread-safe publish/subscribe event bus."""

    def __init__(self) -> None:
        self._subscribers: dict[EventType, list[Subscriber]] = {}
        self._global_subscribers: list[Subscriber] = []
        self._lock = threading.Lock()

    def subscribe(self, event_type: EventType, callback: Subscriber) -> None:
        """Subscribe to a specific event type."""
        with self._lock:
            self._subscribers.setdefault(event_type, []).append(callback)

    def subscribe_all(self, callback: Subscriber) -> None:
        """Subscribe to all events."""
        with self._lock:
            self._global_subscribers.append(callback)

    def unsubscribe(self, event_type: EventType, callback: Subscriber) -> None:
        with self._lock:
            subs = self._subscribers.get(event_type, [])
            if callback in subs:
                subs.remove(callback)

    def unsubscribe_all(self, callback: Subscriber) -> None:
        with self._lock:
            if callback in self._global_subscribers:
                self._global_subscribers.remove(callback)

    def emit(self, event_type: EventType, data: dict[str, Any] | None = None) -> None:
        """Emit an event to all matching subscribers."""
        event = Event(type=event_type, data=data or {})
        with self._lock:
            callbacks = list(self._subscribers.get(event_type, []))
            globals_ = list(self._global_subscribers)
        for cb in callbacks + globals_:
            try:
                cb(event)
            except Exception:
                log.exception("Error in event subscriber for %s", event_type)
