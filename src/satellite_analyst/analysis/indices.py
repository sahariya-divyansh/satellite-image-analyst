"""Spectral index calculation functions."""

from typing import cast

import numpy as np


def compute_mndwi(green: np.ndarray, swir1: np.ndarray, eps: float = 1e-7) -> np.ndarray:
    """Compute Modified Normalized Difference Water Index (Xu, 2006).

    Formula: MNDWI = (Green - SWIR1) / (Green + SWIR1)
    Green: Sentinel-2 Band 3 (10m)
    SWIR1: Sentinel-2 Band 11 (resampled to 10m)
    """
    g = green.astype(np.float32)
    s = swir1.astype(np.float32)
    numerator = g - s
    denominator = g + s
    # Avoid zero division
    denominator = np.where(np.abs(denominator) < eps, eps, denominator)
    mndwi = numerator / denominator
    return cast(np.ndarray, np.clip(mndwi, -1.0, 1.0))


def compute_ndwi(green: np.ndarray, nir: np.ndarray, eps: float = 1e-7) -> np.ndarray:
    """Compute Normalized Difference Water Index (McFeeters, 1996).

    Formula: NDWI = (Green - NIR) / (Green + NIR)
    Green: Sentinel-2 Band 3 (10m)
    NIR: Sentinel-2 Band 8 (10m)
    """
    g = green.astype(np.float32)
    n = nir.astype(np.float32)
    numerator = g - n
    denominator = g + n
    denominator = np.where(np.abs(denominator) < eps, eps, denominator)
    ndwi = numerator / denominator
    return cast(np.ndarray, np.clip(ndwi, -1.0, 1.0))
