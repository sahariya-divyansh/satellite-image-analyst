from typing import cast

import numpy as np
import pytest

from satellite_analyst.analysis.change import WaterChangeClass, detect_water_change
from satellite_analyst.analysis.water import WaterMask


def _create_circle_mask(shape: tuple[int, int], center: tuple[int, int], radius: int) -> np.ndarray:
    """Create boolean mask for a circle with given center and radius."""
    y, x = np.ogrid[: shape[0], : shape[1]]
    dist_sq = (x - center[0]) ** 2 + (y - center[1]) ** 2
    return cast(np.ndarray, dist_sq <= (radius**2))


def test_synthetic_circle_growing() -> None:
    """Circle of radius 5 in period A expands to radius 10 in period B."""
    shape = (50, 50)
    center = (25, 25)
    mask_a = _create_circle_mask(shape, center, radius=5)
    mask_b = _create_circle_mask(shape, center, radius=10)

    count_a = int(np.sum(mask_a))
    count_b = int(np.sum(mask_b))

    change = detect_water_change(mask_a, mask_b)

    persistent_pixels = int(np.sum(change == WaterChangeClass.PERSISTENT))
    gained_pixels = int(np.sum(change == WaterChangeClass.GAINED))
    lost_pixels = int(np.sum(change == WaterChangeClass.LOST))

    assert persistent_pixels == count_a
    assert gained_pixels == (count_b - count_a)
    assert lost_pixels == 0


def test_synthetic_circle_shrinking() -> None:
    """Circle of radius 10 in period A shrinks to radius 5 in period B."""
    shape = (50, 50)
    center = (25, 25)
    mask_a = _create_circle_mask(shape, center, radius=10)
    mask_b = _create_circle_mask(shape, center, radius=5)

    count_a = int(np.sum(mask_a))
    count_b = int(np.sum(mask_b))

    change = detect_water_change(mask_a, mask_b)

    persistent_pixels = int(np.sum(change == WaterChangeClass.PERSISTENT))
    gained_pixels = int(np.sum(change == WaterChangeClass.GAINED))
    lost_pixels = int(np.sum(change == WaterChangeClass.LOST))

    assert persistent_pixels == count_b
    assert lost_pixels == (count_a - count_b)
    assert gained_pixels == 0


def test_synthetic_circle_shifting() -> None:
    """Circle at (20, 20) shifts to (25, 25)."""
    shape = (60, 60)
    mask_a = _create_circle_mask(shape, (20, 20), radius=8)
    mask_b = _create_circle_mask(shape, (25, 25), radius=8)

    intersection = int(np.sum(mask_a & mask_b))
    expected_gained = int(np.sum((~mask_a) & mask_b))
    expected_lost = int(np.sum(mask_a & (~mask_b)))

    change = detect_water_change(mask_a, mask_b)

    assert int(np.sum(change == WaterChangeClass.PERSISTENT)) == intersection
    assert int(np.sum(change == WaterChangeClass.GAINED)) == expected_gained
    assert int(np.sum(change == WaterChangeClass.LOST)) == expected_lost


def test_nodata_propagation() -> None:
    """Pixels invalid in either period must strictly be assigned NODATA (255)."""
    shape = (10, 10)
    arr_a = np.ones(shape, dtype=bool)
    arr_b = np.ones(shape, dtype=bool)

    valid_a = np.ones(shape, dtype=bool)
    valid_b = np.ones(shape, dtype=bool)

    valid_a[0, 0] = False  # invalid in A
    valid_b[2, 2] = False  # invalid in B

    wm_a = WaterMask(arr_a, valid_a, 0.0, "otsu", 1.0, 0.8)
    wm_b = WaterMask(arr_b, valid_b, 0.0, "otsu", 1.0, 0.8)

    change = detect_water_change(wm_a, wm_b)

    assert change[0, 0] == WaterChangeClass.NODATA
    assert change[2, 2] == WaterChangeClass.NODATA
    # Normal persistent pixel elsewhere
    assert change[5, 5] == WaterChangeClass.PERSISTENT


def test_low_confidence_filtering() -> None:
    """Pixels with valid observation count below min_valid_obs are masked as NODATA."""
    shape = (5, 5)
    mask_a = np.ones(shape, dtype=bool)
    mask_b = np.ones(shape, dtype=bool)

    vc_a = np.full(shape, 5, dtype=np.int16)
    vc_b = np.full(shape, 5, dtype=np.int16)

    # Pixel (1, 1) has only 1 observation in period B
    vc_b[1, 1] = 1

    change = detect_water_change(
        mask_a, mask_b, valid_count_a=vc_a, valid_count_b=vc_b, min_valid_obs=2
    )

    assert change[1, 1] == WaterChangeClass.NODATA
    assert change[0, 0] == WaterChangeClass.PERSISTENT


def test_detect_water_change_shape_mismatch() -> None:
    mask_a = np.zeros((10, 10), dtype=bool)
    mask_b = np.zeros((12, 12), dtype=bool)

    with pytest.raises(ValueError, match="Shape mismatch"):
        detect_water_change(mask_a, mask_b)
