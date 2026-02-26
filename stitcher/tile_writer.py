"""Tile-based writer for very large panoramas that don't fit in RAM."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

log = logging.getLogger(__name__)

_TILE_SIZE = 4096  # px per tile dimension


class TileWriter:
    """Write large panoramas as tiles to avoid OOM."""

    def __init__(self, output_dir: Path, canvas_w: int, canvas_h: int,
                 tile_size: int = _TILE_SIZE) -> None:
        self._dir = output_dir / "tiles"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._canvas_w = canvas_w
        self._canvas_h = canvas_h
        self._tile_size = tile_size

        self._cols = (canvas_w + tile_size - 1) // tile_size
        self._rows = (canvas_h + tile_size - 1) // tile_size

        # Lazy-initialise tiles as needed
        self._tiles: dict[tuple[int, int], np.ndarray] = {}
        self._weights: dict[tuple[int, int], np.ndarray] = {}

    def place_frame(self, image: np.ndarray, x_off: int, y_off: int) -> None:
        """Place a frame on the canvas, distributing across tiles."""
        fh, fw = image.shape[:2]
        img_f = image.astype(np.float32)

        for ty in range(self._rows):
            for tx in range(self._cols):
                tile_x = tx * self._tile_size
                tile_y = ty * self._tile_size
                tile_w = min(self._tile_size, self._canvas_w - tile_x)
                tile_h = min(self._tile_size, self._canvas_h - tile_y)

                # Intersection
                ix0 = max(x_off, tile_x)
                iy0 = max(y_off, tile_y)
                ix1 = min(x_off + fw, tile_x + tile_w)
                iy1 = min(y_off + fh, tile_y + tile_h)

                if ix0 >= ix1 or iy0 >= iy1:
                    continue

                # Get or create tile
                key = (tx, ty)
                if key not in self._tiles:
                    self._tiles[key] = np.zeros((tile_h, tile_w, 3), dtype=np.float32)
                    self._weights[key] = np.zeros((tile_h, tile_w), dtype=np.float32)

                # Copy region
                src_x = ix0 - x_off
                src_y = iy0 - y_off
                dst_x = ix0 - tile_x
                dst_y = iy0 - tile_y
                rw = ix1 - ix0
                rh = iy1 - iy0

                self._tiles[key][dst_y:dst_y + rh, dst_x:dst_x + rw] += \
                    img_f[src_y:src_y + rh, src_x:src_x + rw]
                self._weights[key][dst_y:dst_y + rh, dst_x:dst_x + rw] += 1.0

    def finalize(self) -> list[str]:
        """Normalise and write all tiles. Returns list of tile file paths."""
        paths = []
        for (tx, ty), tile in self._tiles.items():
            w = self._weights[(tx, ty)]
            mask = w > 0
            for c in range(3):
                tile[:, :, c][mask] /= w[mask]
            result = np.clip(tile, 0, 255).astype(np.uint8)
            path = self._dir / f"tile_{ty:03d}_{tx:03d}.png"
            cv2.imwrite(str(path), result)
            paths.append(str(path))
        log.info("Wrote %d tiles to %s", len(paths), self._dir)
        return paths

    def write_preview(self, max_dim: int = 2000) -> Path | None:
        """Write a downscaled preview from tiles."""
        if not self._tiles:
            return None
        scale = min(1.0, max_dim / max(self._canvas_w, self._canvas_h))
        pw = int(self._canvas_w * scale)
        ph = int(self._canvas_h * scale)
        preview = np.zeros((ph, pw, 3), dtype=np.uint8)

        for (tx, ty), tile in self._tiles.items():
            # Normalise first
            w = self._weights[(tx, ty)]
            mask = w > 0
            tile_copy = tile.copy()
            for c in range(3):
                tile_copy[:, :, c][mask] /= w[mask]
            tile_uint8 = np.clip(tile_copy, 0, 255).astype(np.uint8)

            ox = int(tx * self._tile_size * scale)
            oy = int(ty * self._tile_size * scale)
            th, tw_t = tile_uint8.shape[:2]
            rw = int(tw_t * scale)
            rh = int(th * scale)
            if rw <= 0 or rh <= 0:
                continue
            resized = cv2.resize(tile_uint8, (rw, rh))
            # Clip to preview bounds
            ew = min(rw, pw - ox)
            eh = min(rh, ph - oy)
            if ew <= 0 or eh <= 0:
                continue
            preview[oy:oy + eh, ox:ox + ew] = resized[:eh, :ew]

        path = self._dir.parent / "preview.png"
        cv2.imwrite(str(path), preview)
        return path
