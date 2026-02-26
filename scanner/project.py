"""Scan project — directory structure, shots.json, resume support."""
from __future__ import annotations

import json
import logging
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)


@dataclass
class ShotRecord:
    """Single frame record in shots.json."""
    index: int
    col: int
    row: int
    x_mm: float
    y_mm: float
    z_mm: float
    filename: str
    status: str = "pending"  # pending | captured | failed
    timestamp: str = ""
    mm_per_px: float = 0.0


@dataclass
class ScanManifest:
    """Scan session manifest."""
    project_name: str
    created: str
    grid_cols: int = 0
    grid_rows: int = 0
    total_frames: int = 0
    captured_count: int = 0
    overlap_pct: float = 20.0
    z_height_mm: float = 50.0
    resolution: str = "1920x1080"
    stitch_algorithm: str = "feather_blend"
    shots: list[ShotRecord] = field(default_factory=list)


class ScanProject:
    """Manages a scan project directory and shots.json for resume."""

    def __init__(self, base_dir: str | Path, project_name: str | None = None) -> None:
        if project_name is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            project_name = f"scan_{ts}"
        self._name = project_name
        self._root = Path(base_dir) / project_name
        self._frames_dir = self._root / "frames"
        self._stitched_dir = self._root / "stitched"
        self._logs_dir = self._root / "logs"
        self._manifest_path = self._root / "shots.json"
        self._config_snapshot_path = self._root / "config_snapshot.json"
        self._manifest: ScanManifest | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def root(self) -> Path:
        return self._root

    @property
    def frames_dir(self) -> Path:
        return self._frames_dir

    @property
    def stitched_dir(self) -> Path:
        return self._stitched_dir

    @property
    def logs_dir(self) -> Path:
        return self._logs_dir

    @property
    def manifest(self) -> ScanManifest | None:
        return self._manifest

    def create(self) -> None:
        """Create project directory structure."""
        self._frames_dir.mkdir(parents=True, exist_ok=True)
        self._stitched_dir.mkdir(parents=True, exist_ok=True)
        self._logs_dir.mkdir(parents=True, exist_ok=True)
        log.info("Created scan project: %s", self._root)

    def save_config_snapshot(self, config_dict: dict) -> None:
        """Save a frozen copy of the configuration."""
        self._config_snapshot_path.write_text(
            json.dumps(config_dict, indent=2), encoding="utf-8"
        )

    def init_manifest(
        self,
        grid_cols: int,
        grid_rows: int,
        positions: list[dict],
        z_mm: float,
        overlap_pct: float,
        resolution: str,
        stitch_algorithm: str,
    ) -> ScanManifest:
        """Initialise manifest with pending shots."""
        shots = []
        for pos in positions:
            filename = f"frame_{pos['row']:03d}_{pos['col']:03d}.png"
            shots.append(ShotRecord(
                index=pos["index"],
                col=pos["col"],
                row=pos["row"],
                x_mm=pos["x_mm"],
                y_mm=pos["y_mm"],
                z_mm=z_mm,
                filename=filename,
            ))
        self._manifest = ScanManifest(
            project_name=self._name,
            created=datetime.now().isoformat(),
            grid_cols=grid_cols,
            grid_rows=grid_rows,
            total_frames=len(shots),
            overlap_pct=overlap_pct,
            z_height_mm=z_mm,
            resolution=resolution,
            stitch_algorithm=stitch_algorithm,
            shots=shots,
        )
        self._save_manifest()
        return self._manifest

    def mark_captured(self, index: int, mm_per_px: float = 0.0) -> None:
        """Mark a shot as captured and save immediately."""
        if not self._manifest:
            raise RuntimeError("Manifest not initialised")
        for shot in self._manifest.shots:
            if shot.index == index:
                shot.status = "captured"
                shot.timestamp = datetime.now().isoformat()
                shot.mm_per_px = mm_per_px
                self._manifest.captured_count += 1
                break
        self._save_manifest()

    def mark_failed(self, index: int, reason: str = "") -> None:
        """Mark a shot as failed."""
        if not self._manifest:
            raise RuntimeError("Manifest not initialised")
        for shot in self._manifest.shots:
            if shot.index == index:
                shot.status = "failed"
                shot.timestamp = datetime.now().isoformat()
                break
        self._save_manifest()

    def get_pending_shots(self) -> list[ShotRecord]:
        """Return shots that haven't been captured yet."""
        if not self._manifest:
            return []
        return [s for s in self._manifest.shots if s.status == "pending"]

    def load_manifest(self) -> ScanManifest | None:
        """Load manifest from disk (for resume)."""
        if not self._manifest_path.exists():
            return None
        try:
            data = json.loads(self._manifest_path.read_text(encoding="utf-8"))
            shots = [ShotRecord(**s) for s in data.pop("shots", [])]
            self._manifest = ScanManifest(**data, shots=shots)
            log.info(
                "Loaded manifest: %d/%d captured",
                self._manifest.captured_count, self._manifest.total_frames,
            )
            return self._manifest
        except Exception:
            log.exception("Failed to load manifest")
            return None

    def frame_path(self, shot: ShotRecord) -> Path:
        return self._frames_dir / shot.filename

    def _save_manifest(self) -> None:
        if not self._manifest:
            return
        data = {
            "project_name": self._manifest.project_name,
            "created": self._manifest.created,
            "grid_cols": self._manifest.grid_cols,
            "grid_rows": self._manifest.grid_rows,
            "total_frames": self._manifest.total_frames,
            "captured_count": self._manifest.captured_count,
            "overlap_pct": self._manifest.overlap_pct,
            "z_height_mm": self._manifest.z_height_mm,
            "resolution": self._manifest.resolution,
            "stitch_algorithm": self._manifest.stitch_algorithm,
            "shots": [asdict(s) for s in self._manifest.shots],
        }
        self._manifest_path.write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )
