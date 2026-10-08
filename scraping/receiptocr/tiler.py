from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .schemas import ReceiptOcrError


def make_tiles(
    image: str | Path | np.ndarray,
    n_tiles: int = 3,
    overlap: float = 0.10,
    zoom: float = 2.0,
) -> list[np.ndarray]:
    """Split the receipt image into overlapping horizontal bands, upscaled by zoom."""
    if isinstance(image, (str, Path)):
        img = cv2.imread(str(image))
        if img is None:
            raise ReceiptOcrError(f"Unreadable image: {image}")
    else:
        img = image

    H, W = img.shape[:2]
    step = 1.0 / n_tiles
    span = step + overlap
    tiles: list[np.ndarray] = []

    for i in range(n_tiles):
        y0 = int(H * (i * step - (overlap / 2 if 0 < i < n_tiles - 1 else 0)))
        y1 = int(H * (i * step + span + (overlap / 2 if 0 < i < n_tiles - 1 else 0)))
        y0 = max(0, y0)
        y1 = min(H, y1)
        crop = img[y0:y1, :]
        if zoom != 1.0:
            crop = cv2.resize(
                crop,
                (int(crop.shape[1] * zoom), int(crop.shape[0] * zoom)),
                interpolation=cv2.INTER_LANCZOS4,
            )
        tiles.append(crop)

    return tiles
