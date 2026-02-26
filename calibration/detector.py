"""ArUco/AprilTag marker detector with preprocessing pipeline."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from ..utils.imaging import apply_clahe, adaptive_threshold

log = logging.getLogger(__name__)


@dataclass
class DetectionResult:
    """Result of marker detection on a single frame."""
    found: bool
    marker_id: int = -1
    corners: np.ndarray | None = None  # 4x2 float array of corner coords
    marker_size_px: float = 0.0        # Measured marker size in pixels
    dict_name: str = ""
    preprocessing: str = ""            # Which preprocessing found it


# ArUco dictionary name → OpenCV constant
_ARUCO_DICTS = {
    "DICT_4X4_50": cv2.aruco.DICT_4X4_50,
    "DICT_4X4_100": cv2.aruco.DICT_4X4_100,
    "DICT_5X5_50": cv2.aruco.DICT_5X5_50,
    "DICT_5X5_100": cv2.aruco.DICT_5X5_100,
    "DICT_6X6_50": cv2.aruco.DICT_6X6_50,
    "DICT_6X6_100": cv2.aruco.DICT_6X6_100,
    "DICT_APRILTAG_36h11": cv2.aruco.DICT_APRILTAG_36h11,
}


class MarkerDetector:
    """Detect ArUco/AprilTag markers with multi-dict and preprocessing pipeline."""

    def __init__(
        self,
        dict_names: list[str] | None = None,
        use_clahe: bool = True,
        clahe_clip: float = 2.0,
        clahe_grid: int = 8,
        use_threshold: bool = True,
        threshold_block_size: int = 11,
        threshold_c: int = 2,
    ) -> None:
        self._dict_names = dict_names or ["DICT_4X4_50"]
        self._use_clahe = use_clahe
        self._clahe_clip = clahe_clip
        self._clahe_grid = clahe_grid
        self._use_threshold = use_threshold
        self._threshold_block_size = threshold_block_size
        self._threshold_c = threshold_c
        self._detector_params = cv2.aruco.DetectorParameters()

    def detect(self, frame: np.ndarray) -> DetectionResult:
        """Try to detect a marker using all dicts and preprocessing variants.

        Preprocessing pipeline:
        1. Raw frame
        2. CLAHE enhanced
        3. Adaptive threshold
        """
        if frame.ndim == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame

        # Build preprocessing variants
        variants: list[tuple[str, np.ndarray]] = [("raw", gray)]
        if self._use_clahe:
            clahe_img = apply_clahe(gray, self._clahe_clip, self._clahe_grid)
            variants.append(("clahe", clahe_img))
        if self._use_threshold:
            thresh_img = adaptive_threshold(
                gray, self._threshold_block_size, self._threshold_c
            )
            variants.append(("threshold", thresh_img))

        # Try each dict × each preprocessing
        for dict_name in self._dict_names:
            aruco_id = _ARUCO_DICTS.get(dict_name)
            if aruco_id is None:
                log.warning("Unknown ArUco dict: %s", dict_name)
                continue
            dictionary = cv2.aruco.getPredefinedDictionary(aruco_id)
            detector = cv2.aruco.ArucoDetector(dictionary, self._detector_params)

            for preproc_name, img in variants:
                corners_list, ids, _ = detector.detectMarkers(img)
                if ids is not None and len(ids) > 0:
                    # Take first detected marker
                    corners = corners_list[0][0]  # shape (4, 2)
                    marker_id = int(ids[0][0])
                    size_px = _marker_size_from_corners(corners)
                    log.debug(
                        "Detected marker %d (%s) via %s, size=%.1f px",
                        marker_id, dict_name, preproc_name, size_px,
                    )
                    return DetectionResult(
                        found=True,
                        marker_id=marker_id,
                        corners=corners,
                        marker_size_px=size_px,
                        dict_name=dict_name,
                        preprocessing=preproc_name,
                    )

        return DetectionResult(found=False)


def _marker_size_from_corners(corners: np.ndarray) -> float:
    """Estimate marker size in pixels from 4 corner points."""
    # Average of the four side lengths
    sides = []
    for i in range(4):
        p1 = corners[i]
        p2 = corners[(i + 1) % 4]
        sides.append(float(np.linalg.norm(p2 - p1)))
    return sum(sides) / len(sides)
