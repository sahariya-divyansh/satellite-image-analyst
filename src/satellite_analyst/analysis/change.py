"""3-Class water change detection routines."""

from enum import IntEnum

import numpy as np


class WaterChangeClass(IntEnum):
    """Categorical raster classification values."""

    DRY = 0
    GAINED = 1
    LOST = 2
    PERSISTENT = 3


def detect_water_change(mask_a: np.ndarray, mask_b: np.ndarray) -> np.ndarray:
    """Classify pixel transitions between two binary water masks.

    Args:
        mask_a: Binary water mask for baseline period (True = Water)
        mask_b: Binary water mask for comparison period (True = Water)

    Returns:
        np.ndarray: Categorical array with values 0, 1, 2, 3 (uint8)
    """
    if mask_a.shape != mask_b.shape:
        raise ValueError(
            f"Shape mismatch: mask_a shape {mask_a.shape} != mask_b shape {mask_b.shape}"
        )

    change_raster = np.zeros(mask_a.shape, dtype=np.uint8)

    # Class 1: Gained (dry in A, water in B)
    change_raster[(~mask_a) & mask_b] = WaterChangeClass.GAINED

    # Class 2: Lost (water in A, dry in B)
    change_raster[mask_a & (~mask_b)] = WaterChangeClass.LOST

    # Class 3: Persistent (water in both A and B)
    change_raster[mask_a & mask_b] = WaterChangeClass.PERSISTENT

    return change_raster
