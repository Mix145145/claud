"""Stitcher factory — create stitcher by algorithm name."""
from __future__ import annotations

from ..config.schema import StitchAlgorithm
from .base import StitcherBackend
from .feather_blend import FeatherBlendStitcher
from .multiband_blend import MultiBandStitcher
from .ecc_refinement import ECCRefinementStitcher
from .opencv_fallback import OpenCVFallbackStitcher


def create_stitcher(algorithm: StitchAlgorithm | str = StitchAlgorithm.FEATHER_BLEND) -> StitcherBackend:
    """Create a stitcher backend by algorithm name or enum."""
    if isinstance(algorithm, str):
        algorithm = StitchAlgorithm(algorithm)

    if algorithm == StitchAlgorithm.FEATHER_BLEND:
        return FeatherBlendStitcher()
    elif algorithm == StitchAlgorithm.MULTIBAND_BLEND:
        return MultiBandStitcher()
    elif algorithm == StitchAlgorithm.ECC_REFINEMENT:
        return ECCRefinementStitcher()
    elif algorithm == StitchAlgorithm.OPENCV_FALLBACK:
        return OpenCVFallbackStitcher()
    else:
        raise ValueError(f"Unknown stitch algorithm: {algorithm}")
