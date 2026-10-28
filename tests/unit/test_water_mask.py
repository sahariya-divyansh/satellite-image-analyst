"""Tests for Otsu thresholding, bimodality checks, morphology, and water masking."""

import numpy as np
import pytest

from satellite_analyst.analysis.water import (
    compute_otsu_threshold,
    create_water_mask,
    segment_dual_period_water,
)


def test_otsu_bimodal_separation() -> None:
    # Synthesize clear bimodal distribution: dry land around -0.4, water around +0.4
    np.random.seed(42)
    dry = np.random.normal(loc=-0.4, scale=0.08, size=2000)
    water = np.random.normal(loc=0.4, scale=0.08, size=1000)
    data = np.concatenate([dry, water])

    threshold, is_bimodal, eta = compute_otsu_threshold(data, bimodality_min_ratio=0.40)
    assert is_bimodal is True
    assert eta >= 0.40
    # Threshold must separate the two clusters
    assert -0.2 < threshold < 0.2


def test_otsu_unimodal_fallback() -> None:
    # Unimodal dry land with no water: single Gaussian around -0.4
    np.random.seed(42)
    dry_only = np.random.normal(loc=-0.4, scale=0.08, size=3000)

    threshold, is_bimodal, eta = compute_otsu_threshold(dry_only, bimodality_min_ratio=0.70)
    assert is_bimodal is False
    assert eta < 0.70

    # In create_water_mask, should trigger fallback
    mndwi_unimodal = dry_only.reshape((50, 60))
    wm = create_water_mask(mndwi_unimodal, fixed_fallback_threshold=0.0)
    assert wm.method == "otsu_fallback_unimodal"
    assert wm.threshold == 0.0
    assert wm.water_fraction == 0.0


def test_manual_override_threshold() -> None:
    data = np.full((20, 20), 0.1, dtype=np.float32)
    wm = create_water_mask(data, threshold=0.15)
    assert wm.method == "manual_override"
    assert wm.threshold == 0.15
    assert wm.water_fraction == 0.0


def test_morphological_cleanup_noise_and_holes() -> None:
    # 50x50 grid of dry land (-0.5)
    arr = np.full((50, 50), -0.5, dtype=np.float32)

    # 1. Add single isolated noise pixel
    arr[5, 5] = 0.5

    # 2. Add solid 10x10 water body with a single-pixel hole in the center
    arr[20:30, 20:30] = 0.5
    arr[25, 25] = -0.5  # hole

    wm = create_water_mask(
        arr,
        threshold=0.0,
        apply_morphology=True,
        fill_holes=True,
        min_area_ha=0.05,
    )

    # Isolated noise pixel at (5, 5) must be removed by opening
    assert wm.mask[5, 5] == False  # noqa: E712

    # Hole at (25, 25) must be filled
    assert wm.mask[25, 25] == True  # noqa: E712

    # Surrounding water body preserved
    assert wm.mask[22, 22] == True  # noqa: E712


def test_min_area_filter() -> None:
    arr = np.full((30, 30), -0.5, dtype=np.float32)
    # 2x2 water blob = 4 pixels (0.04 ha at 10m)
    arr[2:4, 2:4] = 0.5

    # min_area_ha = 0.10 ha (= 10 pixels), so 4-pixel blob must be filtered out
    wm = create_water_mask(arr, threshold=0.0, min_area_ha=0.10, pixel_size_m=10.0)
    assert np.all(wm.mask == False)  # noqa: E712


def test_nan_propagation_in_water_mask() -> None:
    arr = np.full((10, 10), 0.5, dtype=np.float32)
    arr[0, 0] = np.nan
    arr[1, 1] = np.nan

    wm = create_water_mask(arr, threshold=0.0)
    assert wm.valid_mask[0, 0] == False  # noqa: E712
    assert wm.valid_mask[1, 1] == False  # noqa: E712
    assert wm.mask[0, 0] == False  # noqa: E712
    assert wm.mask[1, 1] == False  # noqa: E712
    assert wm.valid_mask[5, 5] == True  # noqa: E712
    assert wm.mask[5, 5] == True  # noqa: E712


def test_segment_dual_period_shared_policy() -> None:
    np.random.seed(42)
    mndwi_a = np.concatenate(
        [np.random.normal(-0.4, 0.05, 500), np.random.normal(0.4, 0.05, 500)]
    ).reshape((25, 40))
    mndwi_b = np.concatenate(
        [np.random.normal(-0.4, 0.05, 500), np.random.normal(0.4, 0.05, 500)]
    ).reshape((25, 40))

    mask_a, mask_b = segment_dual_period_water(mndwi_a, mndwi_b, policy="shared")
    assert mask_a.method == "shared_otsu"
    assert mask_b.method == "shared_otsu"
    assert mask_a.threshold == pytest.approx(mask_b.threshold, rel=1e-5)


def test_segment_dual_period_unimodal_fallback() -> None:
    # Unimodal data in both periods forces fallback to fixed_fallback_threshold
    mndwi_a = np.full((20, 20), -0.3, dtype=np.float32)
    mndwi_b = np.full((20, 20), -0.4, dtype=np.float32)

    mask_a, mask_b = segment_dual_period_water(
        mndwi_a, mndwi_b, policy="shared", fixed_fallback_threshold=0.0
    )
    assert mask_a.method == "shared_otsu_fallback"
    assert mask_b.method == "shared_otsu_fallback"
    assert mask_a.threshold == 0.0
    assert mask_b.threshold == 0.0


def test_segment_dual_period_per_period_policy() -> None:
    mndwi_a = np.full((20, 20), 0.1, dtype=np.float32)
    mndwi_b = np.full((20, 20), -0.2, dtype=np.float32)

    mask_a, mask_b = segment_dual_period_water(
        mndwi_a, mndwi_b, policy="per_period", override_threshold=0.0
    )
    assert mask_a.method == "manual_override"
    assert mask_b.method == "manual_override"
    assert mask_a.water_fraction == 1.0
    assert mask_b.water_fraction == 0.0


def test_create_water_mask_all_nan() -> None:
    arr = np.full((10, 10), np.nan, dtype=np.float32)
    wm = create_water_mask(arr, fixed_fallback_threshold=0.0)
    assert wm.water_fraction == 0.0
    assert np.all(~wm.valid_mask)
    assert np.all(~wm.mask)
