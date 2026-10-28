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


def compute_ndvi(nir: np.ndarray, red: np.ndarray, eps: float = 1e-7) -> np.ndarray:
    """Compute Normalized Difference Vegetation Index (Rouse et al., 1974).

    Formula: NDVI = (NIR - Red) / (NIR + Red)
    NIR: Sentinel-2 Band 8 (10m)
    Red: Sentinel-2 Band 4 (10m)
    """
    n = nir.astype(np.float32)
    r = red.astype(np.float32)

    invalid = np.isnan(n) | np.isnan(r)
    denominator = n + r
    zero_denom = np.abs(denominator) < eps

    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = (n - r) / denominator

    ndvi[invalid | zero_denom] = np.nan
    finite_mask = np.isfinite(ndvi)
    ndvi[finite_mask] = np.clip(ndvi[finite_mask], -1.0, 1.0)
    return cast(np.ndarray, ndvi)


def compute_awei_nsh(
    green: np.ndarray,
    swir1: np.ndarray,
    nir: np.ndarray,
    swir2: np.ndarray,
) -> np.ndarray:
    """Compute Automated Water Extraction Index Non-Shadow (Feyisa et al., 2014).

    Formula: AWEInsh = 4 * (Green - SWIR1) - (0.25 * NIR + 2.75 * SWIR2)
    """
    g = green.astype(np.float32)
    s1 = swir1.astype(np.float32)
    n = nir.astype(np.float32)
    s2 = swir2.astype(np.float32)

    invalid = np.isnan(g) | np.isnan(s1) | np.isnan(n) | np.isnan(s2)
    awei = 4.0 * (g - s1) - (0.25 * n + 2.75 * s2)
    awei[invalid] = np.nan
    return awei


def compute_awei_sh(
    blue: np.ndarray,
    green: np.ndarray,
    nir: np.ndarray,
    swir1: np.ndarray,
    swir2: np.ndarray,
) -> np.ndarray:
    """Compute Automated Water Extraction Index Shadow (Feyisa et al., 2014).

    Formula: AWEIsh = Blue + 2.5 * Green - 1.5 * (NIR + SWIR1) - 0.25 * SWIR2
    """
    b = blue.astype(np.float32)
    g = green.astype(np.float32)
    n = nir.astype(np.float32)
    s1 = swir1.astype(np.float32)
    s2 = swir2.astype(np.float32)

    invalid = np.isnan(b) | np.isnan(g) | np.isnan(n) | np.isnan(s1) | np.isnan(s2)
    awei = b + 2.5 * g - 1.5 * (n + s1) - 0.25 * s2
    awei[invalid] = np.nan
    return awei
