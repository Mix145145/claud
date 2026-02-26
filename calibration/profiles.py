"""FOV profile storage — keyed by Z height and resolution."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class FOVProfile:
    """Calibrated field-of-view profile for a specific Z + resolution."""
    z_mm: float
    resolution: str          # e.g. "1920x1080"
    mm_per_px: float
    fov_x_mm: float          # resolution_w * mm_per_px
    fov_y_mm: float          # resolution_h * mm_per_px
    num_samples: int = 0
    std_dev: float = 0.0


class ProfileStore:
    """JSON-backed FOV profile storage keyed by 'z_mm → resolution'."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._profiles: dict[str, FOVProfile] = {}
        if self._path.exists():
            self.load()

    @staticmethod
    def _key(z_mm: float, resolution: str) -> str:
        return f"{z_mm:.1f}_{resolution}"

    def get(self, z_mm: float, resolution: str) -> FOVProfile | None:
        return self._profiles.get(self._key(z_mm, resolution))

    def put(self, profile: FOVProfile) -> None:
        key = self._key(profile.z_mm, profile.resolution)
        self._profiles[key] = profile
        self.save()
        log.info("Stored FOV profile: z=%.1f res=%s mm/px=%.5f",
                 profile.z_mm, profile.resolution, profile.mm_per_px)

    def get_all(self) -> list[FOVProfile]:
        return list(self._profiles.values())

    def get_for_z(self, z_mm: float) -> list[FOVProfile]:
        return [p for p in self._profiles.values() if abs(p.z_mm - z_mm) < 0.1]

    def load(self) -> None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._profiles = {}
            for key, val in data.items():
                self._profiles[key] = FOVProfile(**val)
            log.info("Loaded %d FOV profiles from %s", len(self._profiles), self._path)
        except Exception:
            log.exception("Failed to load FOV profiles")
            self._profiles = {}

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {k: asdict(v) for k, v in self._profiles.items()}
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")
