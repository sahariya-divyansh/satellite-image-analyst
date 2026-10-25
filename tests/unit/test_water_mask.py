"""Tests for Otsu thresholding and water masking."""

import numpy as np

from satellite_analyst.analysis.water import compute_otsu_threshold, create_water_mask


def test_otsu_bimodal_separation() -> None:
    # Synthesize clear bimodal distribution: dry land around -0.4, water around +0.4
    np.random.seed(42)
    dry = np.random.normal(loc=-0.4, scale=0.1, size=1000)
    water = np.random.normal(loc=0.4, scale=0.1, size=500)
    data = np.concatenate([dry, water])

    threshold = compute_otsu_threshold(data)
    # Optimal threshold must lie between the two cluster peaks (-0.4 and +0.4)
    assert -0.2 < threshold < 0.2


def test_create_water_mask_with_synthetic_pond(
    synthetic_raster_pair: tuple[np.ndarray, np.ndarray],
) -> None:
    raster_a, _ = synthetic_raster_pair
    mask, threshold = create_water_mask(raster_a, threshold=0.0, apply_morphology=False)

    assert mask.shape == (100, 100)
    assert mask.dtype == bool
    # Central pixel (50, 50) is water
    assert mask[50, 50] is True or mask[50, 50] == 1
    # Corner pixel (0, 0) is land
    assert mask[0, 0] is False or mask[0, 0] == 0
