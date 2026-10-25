"""3-Class water change detection routines with strict nodata and confidence masking."""

from enum import IntEnum
from pathlib import Path

import numpy as np
from affine import Affine

from satellite_analyst.analysis.water import WaterMask


class WaterChangeClass(IntEnum):
    """Categorical raster classification values for 3-class change detection."""

    DRY = 0  # No water in either period (0, 0)
    GAINED = 1  # Water gained in period B (0, 1)
    LOST = 2  # Water lost from period A (1, 0)
    PERSISTENT = 3  # Permanent / persistent water in both periods (1, 1)
    NODATA = 255  # Invalid or low observation confidence in either period


def detect_water_change(
    mask_a: np.ndarray | WaterMask,
    mask_b: np.ndarray | WaterMask,
    valid_count_a: np.ndarray | None = None,
    valid_count_b: np.ndarray | None = None,
    min_valid_obs: int = 2,
) -> np.ndarray:
    """Classify pixel transitions between two temporal periods.

    Change is NEVER classified for pixels that are invalid (NaN / cloud / shadow)
    or low confidence (valid clear observation count < min_valid_obs) in either period.

    Args:
        mask_a: Binary water mask or WaterMask dataclass for Period A.
        mask_b: Binary water mask or WaterMask dataclass for Period B.
        valid_count_a: Optional clear-sky observation count raster for Period A.
        valid_count_b: Optional clear-sky observation count raster for Period B.
        min_valid_obs: Minimum required observations to consider a pixel confident (default 2).

    Returns:
        np.ndarray: Categorical uint8 raster with classes 0 (DRY), 1 (GAINED), 2 (LOST),
                   3 (PERSISTENT), and 255 (NODATA).
    """
    arr_a = mask_a.mask if isinstance(mask_a, WaterMask) else mask_a
    arr_b = mask_b.mask if isinstance(mask_b, WaterMask) else mask_b

    if arr_a.shape != arr_b.shape:
        raise ValueError(
            f"Shape mismatch: Period A shape {arr_a.shape} != Period B shape {arr_b.shape}"
        )

    # Determine validity mask
    if isinstance(mask_a, WaterMask) and isinstance(mask_b, WaterMask):
        valid = mask_a.valid_mask & mask_b.valid_mask
    else:
        valid = np.ones(arr_a.shape, dtype=bool)

    # Exclude low observation counts
    if valid_count_a is not None:
        valid = valid & (valid_count_a >= min_valid_obs)
    if valid_count_b is not None:
        valid = valid & (valid_count_b >= min_valid_obs)

    # Initialize raster to NODATA (255)
    change_raster = np.full(arr_a.shape, WaterChangeClass.NODATA, dtype=np.uint8)

    # Class 0: DRY (no water in either period)
    dry_mask = valid & (~arr_a) & (~arr_b)
    change_raster[dry_mask] = WaterChangeClass.DRY

    # Class 1: GAINED (dry in A, water in B)
    gained_mask = valid & (~arr_a) & arr_b
    change_raster[gained_mask] = WaterChangeClass.GAINED

    # Class 2: LOST (water in A, dry in B)
    lost_mask = valid & arr_a & (~arr_b)
    change_raster[lost_mask] = WaterChangeClass.LOST

    # Class 3: PERSISTENT (water in both periods)
    persistent_mask = valid & arr_a & arr_b
    change_raster[persistent_mask] = WaterChangeClass.PERSISTENT

    return change_raster


def save_change_raster_to_geotiff(
    change_raster: np.ndarray,
    output_path: Path,
    transform: Affine,
    crs: str,
) -> Path:
    """Save 3-class change raster to a compressed GeoTIFF."""
    import rasterio

    output_path.parent.mkdir(parents=True, exist_ok=True)
    height, width = change_raster.shape

    with rasterio.open(
        output_path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=np.uint8,
        crs=crs,
        transform=transform,
        nodata=int(WaterChangeClass.NODATA),
        compress="deflate",
    ) as dst:
        dst.write(change_raster, 1)

    return output_path
