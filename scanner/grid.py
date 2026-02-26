"""Grid calculator — snake pattern, ceil-based coverage, overlap."""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class GridPosition:
    """Single capture position in the grid."""
    col: int
    row: int
    x_mm: float
    y_mm: float
    index: int  # Sequential index in snake order


@dataclass
class GridPlan:
    """Complete grid scan plan."""
    cols: int
    rows: int
    total_frames: int
    positions: list[GridPosition]
    fov_x_mm: float
    fov_y_mm: float
    overlap_pct: float
    step_x_mm: float
    step_y_mm: float
    area_width_mm: float
    area_height_mm: float


class GridCalculator:
    """Calculate grid positions for scanning with overlap.

    Uses ceil() for grid dimensions to ensure full area coverage.
    Generates snake (boustrophedon) pattern to minimise travel.
    """

    @staticmethod
    def calculate(
        area_width_mm: float,
        area_height_mm: float,
        fov_x_mm: float,
        fov_y_mm: float,
        overlap_pct: float = 20.0,
        origin_x_mm: float = 0.0,
        origin_y_mm: float = 0.0,
    ) -> GridPlan:
        """Calculate grid plan.

        Args:
            area_width_mm: Total area width to scan.
            area_height_mm: Total area height to scan.
            fov_x_mm: Camera field-of-view width at current Z.
            fov_y_mm: Camera field-of-view height at current Z.
            overlap_pct: Overlap percentage between adjacent frames.
            origin_x_mm: X offset of scan area origin.
            origin_y_mm: Y offset of scan area origin.

        Returns:
            GridPlan with snake-ordered positions.
        """
        if fov_x_mm <= 0 or fov_y_mm <= 0:
            raise ValueError("FOV must be positive")
        if overlap_pct < 0 or overlap_pct >= 100:
            raise ValueError("Overlap must be in [0, 100)")

        overlap_frac = overlap_pct / 100.0
        step_x = fov_x_mm * (1.0 - overlap_frac)
        step_y = fov_y_mm * (1.0 - overlap_frac)

        if step_x <= 0 or step_y <= 0:
            raise ValueError("Overlap too large — step size is zero or negative")

        # Number of frames needed:
        # First frame covers [0, fov]. Each additional frame adds 'step' coverage.
        # After k frames, coverage = fov + (k-1)*step >= area
        # So k = ceil((area - fov) / step) + 1 when area > fov, else 1.
        if area_width_mm <= fov_x_mm:
            cols = 1
        else:
            cols = math.ceil((area_width_mm - fov_x_mm) / step_x) + 1

        if area_height_mm <= fov_y_mm:
            rows = 1
        else:
            rows = math.ceil((area_height_mm - fov_y_mm) / step_y) + 1

        positions: list[GridPosition] = []
        idx = 0
        for row in range(rows):
            col_range = range(cols) if row % 2 == 0 else range(cols - 1, -1, -1)
            for col in col_range:
                x = origin_x_mm + col * step_x
                y = origin_y_mm + row * step_y
                positions.append(GridPosition(
                    col=col, row=row,
                    x_mm=round(x, 3),
                    y_mm=round(y, 3),
                    index=idx,
                ))
                idx += 1

        return GridPlan(
            cols=cols,
            rows=rows,
            total_frames=len(positions),
            positions=positions,
            fov_x_mm=fov_x_mm,
            fov_y_mm=fov_y_mm,
            overlap_pct=overlap_pct,
            step_x_mm=round(step_x, 3),
            step_y_mm=round(step_y, 3),
            area_width_mm=area_width_mm,
            area_height_mm=area_height_mm,
        )
