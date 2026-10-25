"""Tests for spectral indices (MNDWI, NDWI)."""

import numpy as np

from satellite_analyst.analysis.indices import compute_mndwi, compute_ndwi


def test_compute_mndwi_values() -> None:
    # Pure water: high green, low swir
    green = np.array([[0.3, 0.4], [0.5, 0.6]], dtype=np.float32)
    swir1 = np.array([[0.05, 0.05], [0.1, 0.1]], dtype=np.float32)

    mndwi = compute_mndwi(green, swir1)
    # Check that water values are strongly positive
    assert np.all(mndwi > 0.5)
    assert np.all(mndwi <= 1.0)


def test_compute_mndwi_dry_soil() -> None:
    # Bare dry soil / urban: lower green, higher swir
    green = np.array([[0.1, 0.15]], dtype=np.float32)
    swir1 = np.array([[0.35, 0.45]], dtype=np.float32)

    mndwi = compute_mndwi(green, swir1)
    # Check that dry soil is negative
    assert np.all(mndwi < 0.0)
    assert np.all(mndwi >= -1.0)


def test_compute_ndwi_zero_division() -> None:
    # Zero arrays should not crash with ZeroDivisionError
    green = np.zeros((2, 2), dtype=np.float32)
    nir = np.zeros((2, 2), dtype=np.float32)

    ndwi = compute_ndwi(green, nir)
    assert ndwi.shape == (2, 2)
    assert np.all(np.isfinite(ndwi))
