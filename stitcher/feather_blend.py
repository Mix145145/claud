"""Grid placement with linear feather blending — fast, good for aligned grids."""
from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

from .base import GridFrame, StitcherBackend, StitchResult
from .tile_writer import TileWriter

log = logging.getLogger(__name__)

# Threshold for switching to tiled output (~200 megapixels)
_MAX_PIXELS = 200_000_000


class FeatherBlendStitcher(StitcherBackend):
    """Place frames on a grid canvas with linear feather blending in overlap zones."""

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

        total_pixels = canvas_w * canvas_h
        if total_pixels > _MAX_PIXELS:
            log.info("Canvas too large (%d px), using tile writer", total_pixels)
            return self._stitch_tiled(frames, cols, rows, step_x, step_y,
                                       w_frame, h_frame, canvas_w, canvas_h, out)

        log.info("Stitching %d frames into %dx%d canvas", len(frames), canvas_w, canvas_h)
        canvas = np.zeros((canvas_h, canvas_w, 3), dtype=np.float32)
        weight_map = np.zeros((canvas_h, canvas_w), dtype=np.float32)

        # Pre-compute per-frame feather weight mask
        feather = _create_feather_mask(w_frame, h_frame, overlap_frac)

        for gf in frames:
            x_off = gf.col * step_x
            y_off = gf.row * step_y
            roi = canvas[y_off:y_off + h_frame, x_off:x_off + w_frame]
            w_roi = weight_map[y_off:y_off + h_frame, x_off:x_off + w_frame]

            img_f = gf.image.astype(np.float32)
            roi += img_f * feather[:, :, np.newaxis]
            w_roi += feather

        # Normalise
        mask = weight_map > 0
        for c in range(3):
            canvas[:, :, c][mask] /= weight_map[mask]

        result_img = np.clip(canvas, 0, 255).astype(np.uint8)
        output_path = out / "stitched.png"
        cv2.imwrite(str(output_path), result_img)

        # Preview
        preview_path = out / "preview.png"
        scale = min(1.0, 2000 / max(canvas_w, canvas_h))
        if scale < 1.0:
            preview = cv2.resize(result_img, None, fx=scale, fy=scale)
        else:
            preview = result_img
        cv2.imwrite(str(preview_path), preview)

        return StitchResult(
            success=True,
            output_path=str(output_path),
            preview_path=str(preview_path),
            width=canvas_w,
            height=canvas_h,
        )

    def _stitch_tiled(self, frames, cols, rows, step_x, step_y,
                       w_frame, h_frame, canvas_w, canvas_h, out):
        tw = TileWriter(out, canvas_w, canvas_h)
        for gf in frames:
            x_off = gf.col * step_x
            y_off = gf.row * step_y
            tw.place_frame(gf.image, x_off, y_off)
        tile_paths = tw.finalize()
        preview_path = tw.write_preview(max_dim=2000)
        return StitchResult(
            success=True,
            output_path=str(out),
            preview_path=str(preview_path) if preview_path else "",
            width=canvas_w,
            height=canvas_h,
            tiles=tile_paths,
        )

    @property
    def algorithm_name(self) -> str:
        return "feather_blend"


def _create_feather_mask(w: int, h: int, overlap_frac: float) -> np.ndarray:
    """Create a 2D feather weight mask that ramps in the overlap zones."""
    mask = np.ones((h, w), dtype=np.float32)
    border_x = int(w * overlap_frac / 2)
    border_y = int(h * overlap_frac / 2)
    if border_x > 0:
        ramp = np.linspace(0, 1, border_x, dtype=np.float32)
        mask[:, :border_x] *= ramp[np.newaxis, :]
        mask[:, -border_x:] *= ramp[np.newaxis, ::-1]
    if border_y > 0:
        ramp = np.linspace(0, 1, border_y, dtype=np.float32)
        mask[:border_y, :] *= ramp[:, np.newaxis]
        mask[-border_y:, :] *= ramp[::-1, np.newaxis]
    return mask
