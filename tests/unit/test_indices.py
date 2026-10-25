"""Tests for spectral indices (MNDWI, NDWI) with known mathematical values and NaN propagation."""

import numpy as np
import pytest

from satellite_analyst.analysis.indices import compute_mndwi, compute_ndwi


def test_compute_mndwi_known_values() -> None:
    # Green = 0.3, SWIR1 = 0.1 -> (0.3 - 0.1) / (0.3 + 0.1) = 0.2 / 0.4 = 0.50
    green = np.array([[0.3, 0.1]], dtype=np.float32)
    swir1 = np.array([[0.1, 0.3]], dtype=np.float32)

    mndwi = compute_mndwi(green, swir1)
    assert pytest.approx(mndwi[0, 0], rel=1e-5) == 0.50
    assert pytest.approx(mndwi[0, 1], rel=1e-5) == -0.50


def test_compute_mndwi_nan_propagation() -> None:
    green = np.array([[0.3, np.nan], [0.4, 0.5]], dtype=np.float32)
    swir1 = np.array([[0.1, 0.2], [np.nan, 0.1]], dtype=np.float32)

    mndwi = compute_mndwi(green, swir1)
    assert np.isnan(mndwi[0, 1])
    assert np.isnan(mndwi[1, 0])
    assert not np.isnan(mndwi[0, 0])
    assert not np.isnan(mndwi[1, 1])


def test_compute_mndwi_zero_division_and_bounds() -> None:
    green = np.array([[0.0, 1.0]], dtype=np.float32)
    swir1 = np.array([[0.0, 0.0]], dtype=np.float32)

    mndwi = compute_mndwi(green, swir1)
    # 0/0 indeterminate is assigned NaN
    assert np.isnan(mndwi[0, 0])
    # 1.0 / 1.0 = 1.0
    assert pytest.approx(mndwi[0, 1], rel=1e-5) == 1.0
    assert np.nanmin(mndwi) >= -1.0
    assert np.nanmax(mndwi) <= 1.0


def test_compute_ndwi_known_values_and_nan() -> None:
    green = np.array([[0.4, np.nan]], dtype=np.float32)
    nir = np.array([[0.1, 0.2]], dtype=np.float32)

    ndwi = compute_ndwi(green, nir)
    # (0.4 - 0.1) / (0.4 + 0.1) = 0.3 / 0.5 = 0.6
    assert pytest.approx(ndwi[0, 0], rel=1e-5) == 0.60
    assert np.isnan(ndwi[0, 1])
