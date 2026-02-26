"""Time estimator — measure snap/write times, predict total scan duration."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class TimeEstimate:
    """Scan time estimation results."""
    total_frames: int
    estimated_seconds: float
    t_move_avg: float       # Average move time (seconds)
    t_capture_avg: float    # Average capture time (seconds)
    t_settle: float         # Settle delay per frame


class TimeEstimator:
    """Measure and predict scan timing."""

    def __init__(self) -> None:
        self._move_times: list[float] = []
        self._capture_times: list[float] = []
        self._settle_delay: float = 0.3

    def set_settle_delay(self, delay_s: float) -> None:
        self._settle_delay = delay_s

    def record_move(self, duration_s: float) -> None:
        self._move_times.append(duration_s)

    def record_capture(self, duration_s: float) -> None:
        self._capture_times.append(duration_s)

    def estimate(self, total_frames: int) -> TimeEstimate:
        """Estimate total scan time based on measured averages."""
        t_move = _median(self._move_times) if self._move_times else 0.5
        t_capture = _median(self._capture_times) if self._capture_times else 0.3
        per_frame = t_move + self._settle_delay + t_capture
        total = per_frame * total_frames
        return TimeEstimate(
            total_frames=total_frames,
            estimated_seconds=round(total, 1),
            t_move_avg=round(t_move, 3),
            t_capture_avg=round(t_capture, 3),
            t_settle=self._settle_delay,
        )

    def remaining(self, frames_left: int) -> float:
        """Estimate remaining seconds."""
        est = self.estimate(frames_left)
        return est.estimated_seconds


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2.0
