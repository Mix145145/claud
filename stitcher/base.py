"""Abstract base class for stitching backends."""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass
class StitchResult:
    """Result of a stitching operation."""
    success: bool
    output_path: str = ""
    preview_path: str = ""
    width: int = 0
    height: int = 0
    error: str = ""
    tiles: list[str] = field(default_factory=list)  # Tile paths if tiled output


@dataclass
class GridFrame:
    """A frame with its grid position for stitching."""
    image: np.ndarray
    col: int
    row: int
    x_mm: float
    y_mm: float


class StitcherBackend(abc.ABC):
    """Interface for all stitching algorithms."""

    @abc.abstractmethod
    def stitch(
        self,
        frames: list[GridFrame],
        cols: int,
        rows: int,
        output_dir: str | Path,
        overlap_pct: float = 20.0,
    ) -> StitchResult:
        """Stitch grid frames into a panorama."""

    @property
    @abc.abstractmethod
    def algorithm_name(self) -> str:
        """Human-readable algorithm name."""
