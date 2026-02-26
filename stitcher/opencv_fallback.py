"""OpenCV Stitcher fallback — uses cv2.Stitcher for emergency use."""
from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

from .base import GridFrame, StitcherBackend, StitchResult

log = logging.getLogger(__name__)


class OpenCVFallbackStitcher(StitcherBackend):
    """Emergency fallback using cv2.Stitcher (feature-based, not grid-aware)."""

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

        images = [gf.image for gf in frames]
        stitcher = cv2.Stitcher.create(cv2.Stitcher_SCANS)
        status, result = stitcher.stitch(images)

        if status != cv2.Stitcher_OK:
            err_map = {
                cv2.Stitcher_ERR_NEED_MORE_IMG: "Need more images",
                cv2.Stitcher_ERR_HOMOGRAPHY_EST_FAIL: "Homography estimation failed",
                cv2.Stitcher_ERR_CAMERA_PARAMS_ADJUST_FAIL: "Camera params adjustment failed",
            }
            err = err_map.get(status, f"Unknown error (code {status})")
            log.error("OpenCV Stitcher failed: %s", err)
            return StitchResult(success=False, error=err)

        output_path = out / "stitched.png"
        cv2.imwrite(str(output_path), result)

        h, w = result.shape[:2]
        preview_path = out / "preview.png"
        scale = min(1.0, 2000 / max(w, h))
        if scale < 1.0:
            preview = cv2.resize(result, None, fx=scale, fy=scale)
        else:
            preview = result
        cv2.imwrite(str(preview_path), preview)

        return StitchResult(
            success=True,
            output_path=str(output_path),
            preview_path=str(preview_path),
            width=w,
            height=h,
        )

    @property
    def algorithm_name(self) -> str:
        return "opencv_fallback"
