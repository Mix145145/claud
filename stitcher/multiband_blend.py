"""MultiBand blending using OpenCV's MultiBandBlender."""
from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

from .base import GridFrame, StitcherBackend, StitchResult

log = logging.getLogger(__name__)


class MultiBandStitcher(StitcherBackend):
    """Grid placement with OpenCV MultiBandBlender for high-quality seams."""

    def __init__(self, num_bands: int = 5) -> None:
        self._num_bands = num_bands

    def stitch(
        self,
        frames: list[GridFrame],
        cols: int,
        rows: int,
        output_dir: str | Path,
        overlap_pct: float = 20.0,
    ) -> StitchResult:
        if not frames:
            return StitchResult(success=False, error="No frames to stitch")

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        h_frame, w_frame = frames[0].image.shape[:2]
        overlap_frac = overlap_pct / 100.0
        step_x = int(w_frame * (1.0 - overlap_frac))
        step_y = int(h_frame * (1.0 - overlap_frac))

        canvas_w = step_x * (cols - 1) + w_frame
        canvas_h = step_y * (rows - 1) + h_frame

        log.info("MultiBand stitching %d frames into %dx%d", len(frames), canvas_w, canvas_h)

        blender = cv2.detail.MultiBandBlender_create(
            try_gpu=False, num_bands=self._num_bands
        )
        blender.prepare((0, 0, canvas_w, canvas_h))

        for gf in frames:
            x_off = gf.col * step_x
            y_off = gf.row * step_y
            mask = np.full((h_frame, w_frame), 255, dtype=np.uint8)
            img_s = gf.image.astype(np.int16)
            blender.feed(img_s, mask, (x_off, y_off))

        result, result_mask = blender.blend(None, None)
        result = np.clip(result, 0, 255).astype(np.uint8)

        output_path = out / "stitched.png"
        cv2.imwrite(str(output_path), result)

        preview_path = out / "preview.png"
        scale = min(1.0, 2000 / max(canvas_w, canvas_h))
        if scale < 1.0:
            preview = cv2.resize(result, None, fx=scale, fy=scale)
        else:
            preview = result
        cv2.imwrite(str(preview_path), preview)

        return StitchResult(
            success=True,
            output_path=str(output_path),
            preview_path=str(preview_path),
            width=canvas_w,
            height=canvas_h,
        )

    @property
    def algorithm_name(self) -> str:
        return "multiband_blend"
