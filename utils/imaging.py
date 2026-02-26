"""Image utility functions."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

log = logging.getLogger(__name__)


def to_bgr(frame: np.ndarray) -> np.ndarray:
    """Ensure frame is BGR (3-channel uint8)."""
    if frame.ndim == 2:
        return cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    if frame.shape[2] == 4:
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
    if frame.shape[2] == 3:
        return frame
    raise ValueError(f"Unexpected frame shape: {frame.shape}")


def safe_imwrite(path: str | Path, image: np.ndarray, quality: int = 95) -> bool:
    """Write image with directory creation and error handling."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    params = []
    suffix = p.suffix.lower()
    if suffix in (".jpg", ".jpeg"):
        params = [cv2.IMWRITE_JPEG_QUALITY, quality]
    elif suffix == ".png":
        params = [cv2.IMWRITE_PNG_COMPRESSION, 3]
    ok = cv2.imwrite(str(p), image, params)
    if not ok:
        log.error("Failed to write image to %s", p)
    return ok


def apply_clahe(
    frame: np.ndarray,
    clip_limit: float = 2.0,
    grid_size: int = 8,
) -> np.ndarray:
    """Apply CLAHE to a BGR or grayscale image, returns same color space."""
    if frame.ndim == 3:
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(grid_size, grid_size))
        l_ch = clahe.apply(l_ch)
        lab = cv2.merge([l_ch, a_ch, b_ch])
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    else:
        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(grid_size, grid_size))
        return clahe.apply(frame)


def adaptive_threshold(
    frame: np.ndarray,
    block_size: int = 11,
    c: int = 2,
) -> np.ndarray:
    """Adaptive threshold for marker detection preprocessing."""
    if frame.ndim == 3:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    else:
        gray = frame
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, block_size, c,
    )
