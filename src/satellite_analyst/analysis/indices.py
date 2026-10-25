"""Spectral index calculation functions for optical Earth observation."""

from typing import cast

import numpy as np


def compute_mndwi(green: np.ndarray, swir1: np.ndarray, eps: float = 1e-7) -> np.ndarray:
    """Compute Modified Normalized Difference Water Index (Xu, 2006).

    Formula: MNDWI = (Green - SWIR1) / (Green + SWIR1)
    Green: Sentinel-2 Band 3 (10m)
    SWIR1: Sentinel-2 Band 11 (resampled to 10m)

    Output is strictly bounded to [-1.0, 1.0] with NaN propagated for invalid pixels.
    """
    g = green.astype(np.float32)
    s = swir1.astype(np.float32)

    invalid = np.isnan(g) | np.isnan(s)
    denominator = g + s
    zero_denom = np.abs(denominator) < eps

    with np.errstate(divide="ignore", invalid="ignore"):
        mndwi = (g - s) / denominator

    # Propagate NaNs and assign NaN to indeterminate zero-reflectance pixels
    mndwi[invalid | zero_denom] = np.nan

    # Clip finite values to valid theoretical radiometric bounds [-1.0, 1.0]
    finite_mask = np.isfinite(mndwi)
    mndwi[finite_mask] = np.clip(mndwi[finite_mask], -1.0, 1.0)
    return cast(np.ndarray, mndwi)


def compute_ndwi(green: np.ndarray, nir: np.ndarray, eps: float = 1e-7) -> np.ndarray:
    """Compute Normalized Difference Water Index (McFeeters, 1996).

    Formula: NDWI = (Green - NIR) / (Green + NIR)
    Green: Sentinel-2 Band 3 (10m)
    NIR: Sentinel-2 Band 8 (10m)

    Output is strictly bounded to [-1.0, 1.0] with NaN propagated for invalid pixels.
    """
    g = green.astype(np.float32)
    n = nir.astype(np.float32)

    invalid = np.isnan(g) | np.isnan(n)
    denominator = g + n
    zero_denom = np.abs(denominator) < eps

    with np.errstate(divide="ignore", invalid="ignore"):
        ndwi = (g - n) / denominator

    ndwi[invalid | zero_denom] = np.nan

    finite_mask = np.isfinite(ndwi)
    ndwi[finite_mask] = np.clip(ndwi[finite_mask], -1.0, 1.0)
    return cast(np.ndarray, ndwi)
