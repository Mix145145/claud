"""Engine state machine with valid transitions."""
from __future__ import annotations

import logging
import threading
from typing import Optional, Callable

from ..config.schema import EngineState
from .events import EventBus, EventType

log = logging.getLogger(__name__)

# Valid state transitions: from_state -> set of allowed to_states
_TRANSITIONS: dict[EngineState, set[EngineState]] = {
    EngineState.UNINITIALIZED: {EngineState.IDLE, EngineState.ERROR},
    EngineState.IDLE: {
        EngineState.HOMING, EngineState.JOGGING, EngineState.CALIBRATING,
        EngineState.SCANNING, EngineState.STITCHING, EngineState.ERROR,
        EngineState.SHUTTING_DOWN,
    },
    EngineState.HOMING: {EngineState.IDLE, EngineState.ERROR},
    EngineState.JOGGING: {EngineState.IDLE, EngineState.ERROR},
    EngineState.CALIBRATING: {EngineState.IDLE, EngineState.ERROR},
    EngineState.SCANNING: {EngineState.PAUSED, EngineState.IDLE, EngineState.ERROR},
    EngineState.PAUSED: {EngineState.SCANNING, EngineState.IDLE, EngineState.ERROR},
    EngineState.STITCHING: {EngineState.IDLE, EngineState.ERROR},
    EngineState.ERROR: {EngineState.IDLE, EngineState.SHUTTING_DOWN},
    EngineState.SHUTTING_DOWN: {EngineState.UNINITIALIZED},
}


class StateMachine:
    """Thread-safe state machine that emits state change events."""

    def __init__(self, event_bus: EventBus) -> None:
        self._state = EngineState.UNINITIALIZED
        self._lock = threading.Lock()
        self._event_bus = event_bus

    @property
    def state(self) -> EngineState:
        with self._lock:
            return self._state

    def transition(self, new_state: EngineState) -> bool:
        """Attempt a state transition. Returns True if successful."""
        with self._lock:
            allowed = _TRANSITIONS.get(self._state, set())
            if new_state not in allowed:
                log.warning(
                    "Invalid state transition: %s -> %s (allowed: %s)",
                    self._state.value, new_state.value,
                    [s.value for s in allowed],
                )
                return False
            old = self._state
            self._state = new_state
        log.info("State: %s -> %s", old.value, new_state.value)
        self._event_bus.emit(EventType.STATE_CHANGED, {
            "old_state": old.value,
            "new_state": new_state.value,
        })
        return True

    def is_in(self, *states: EngineState) -> bool:
        with self._lock:
            return self._state in states

    def force_state(self, state: EngineState) -> None:
        """Force state without transition validation (for error recovery)."""
        with self._lock:
            old = self._state
            self._state = state
        log.warning("Forced state: %s -> %s", old.value, state.value)
        self._event_bus.emit(EventType.STATE_CHANGED, {
            "old_state": old.value,
            "new_state": state.value,
            "forced": True,
        })
