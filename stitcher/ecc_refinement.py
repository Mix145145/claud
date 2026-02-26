"""Grid placement + ECC/phase correlation refinement for sub-pixel alignment."""
from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

from .base import GridFrame, StitcherBackend, StitchResult
from .feather_blend import FeatherBlendStitcher, _create_feather_mask

log = logging.getLogger(__name__)


class ECCRefinementStitcher(StitcherBackend):
    """Grid placement with ECC/phase correlation refinement for better alignment.

    For each pair of overlapping neighbours, computes a sub-pixel dx/dy correction
    using phase correlation or ECC, then applies the corrections before feather blending.
    """

    def __init__(self, max_shift_px: int = 50) -> None:
        self._max_shift = max_shift_px

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

        # Index frames by (col, row)
        frame_map: dict[tuple[int, int], GridFrame] = {}
        for gf in frames:
            frame_map[(gf.col, gf.row)] = gf

        # Compute refinement offsets via phase correlation
        offsets: dict[tuple[int, int], tuple[float, float]] = {}
        offsets[(0, 0)] = (0.0, 0.0)

        for row in range(rows):
            for col in range(cols):
                if (col, row) in offsets:
                    continue
                # Try left neighbour
                if col > 0 and (col - 1, row) in frame_map and (col, row) in frame_map:
                    dx, dy = self._phase_shift(
                        frame_map[(col - 1, row)].image,
                        frame_map[(col, row)].image,
                        step_x, 0, w_frame, h_frame,
                    )
                    parent = offsets.get((col - 1, row), (0, 0))
                    offsets[(col, row)] = (parent[0] + dx, parent[1] + dy)
                # Try top neighbour
                elif row > 0 and (col, row - 1) in frame_map and (col, row) in frame_map:
                    dx, dy = self._phase_shift(
                        frame_map[(col, row - 1)].image,
                        frame_map[(col, row)].image,
                        0, step_y, w_frame, h_frame,
                    )
                    parent = offsets.get((col, row - 1), (0, 0))
                    offsets[(col, row)] = (parent[0] + dx, parent[1] + dy)
                else:
                    offsets[(col, row)] = (0.0, 0.0)

        # Determine canvas size with offsets
        all_x = []
        all_y = []
        for (c, r), (ox, oy) in offsets.items():
            px = c * step_x + ox
            py = r * step_y + oy
            all_x.extend([px, px + w_frame])
            all_y.extend([py, py + h_frame])

        min_x, max_x = min(all_x), max(all_x)
        min_y, max_y = min(all_y), max(all_y)
        canvas_w = int(np.ceil(max_x - min_x))
        canvas_h = int(np.ceil(max_y - min_y))

        log.info("ECC stitching %d frames into %dx%d", len(frames), canvas_w, canvas_h)

        canvas = np.zeros((canvas_h, canvas_w, 3), dtype=np.float32)
        weight_map = np.zeros((canvas_h, canvas_w), dtype=np.float32)
        feather = _create_feather_mask(w_frame, h_frame, overlap_frac)

        for (c, r), (ox, oy) in offsets.items():
            if (c, r) not in frame_map:
                continue
            gf = frame_map[(c, r)]
            x_off = int(round(c * step_x + ox - min_x))
            y_off = int(round(r * step_y + oy - min_y))

            # Clip to canvas bounds
            x_end = min(x_off + w_frame, canvas_w)
            y_end = min(y_off + h_frame, canvas_h)
            x_start = max(x_off, 0)
            y_start = max(y_off, 0)
            fx_start = x_start - x_off
            fy_start = y_start - y_off
            fw = x_end - x_start
            fh = y_end - y_start

            if fw <= 0 or fh <= 0:
                continue

            img_f = gf.image[fy_start:fy_start + fh, fx_start:fx_start + fw].astype(np.float32)
            f_w = feather[fy_start:fy_start + fh, fx_start:fx_start + fw]
            canvas[y_start:y_end, x_start:x_end] += img_f * f_w[:, :, np.newaxis]
            weight_map[y_start:y_end, x_start:x_end] += f_w

        mask = weight_map > 0
        for ch in range(3):
            canvas[:, :, ch][mask] /= weight_map[mask]

        result_img = np.clip(canvas, 0, 255).astype(np.uint8)
        output_path = out / "stitched.png"
        cv2.imwrite(str(output_path), result_img)

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

    def _phase_shift(
        self, img1: np.ndarray, img2: np.ndarray,
        nominal_dx: int, nominal_dy: int,
        w: int, h: int,
    ) -> tuple[float, float]:
        """Compute sub-pixel shift between overlapping regions via phase correlation."""
        try:
            gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY) if img1.ndim == 3 else img1
            gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY) if img2.ndim == 3 else img2

            # Extract overlap region
            if nominal_dx > 0:  # Horizontal neighbour
                overlap_w = w - nominal_dx
                roi1 = gray1[:, nominal_dx:nominal_dx + overlap_w]
                roi2 = gray2[:, :overlap_w]
            else:  # Vertical neighbour
                overlap_h = h - nominal_dy
                roi1 = gray1[nominal_dy:nominal_dy + overlap_h, :]
                roi2 = gray2[:overlap_h, :]

            shift, _ = cv2.phaseCorrelate(
                roi1.astype(np.float64),
                roi2.astype(np.float64),
            )
            dx, dy = shift
            # Clamp to max shift
            dx = max(-self._max_shift, min(self._max_shift, dx))
            dy = max(-self._max_shift, min(self._max_shift, dy))
            # Return only the sub-pixel correction, not the nominal shift.
            # The caller accumulates corrections separately from nominal grid positions.
            return (dx, dy)
        except Exception as e:
            log.debug("Phase correlation failed: %s", e)
            return (0.0, 0.0)

    @property
    def algorithm_name(self) -> str:
        return "ecc_refinement"
