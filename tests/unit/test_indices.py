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


def test_compute_ndvi_known_values() -> None:
    from satellite_analyst.analysis.indices import compute_ndvi

    nir = np.array([[0.6, np.nan]], dtype=np.float32)
    red = np.array([[0.2, 0.2]], dtype=np.float32)
    ndvi = compute_ndvi(nir, red)
    assert pytest.approx(ndvi[0, 0], rel=1e-5) == 0.50
    assert np.isnan(ndvi[0, 1])


def test_compute_awei_variants() -> None:
    from satellite_analyst.analysis.indices import compute_awei_nsh, compute_awei_sh

    blue = np.array([[0.15]], dtype=np.float32)
    green = np.array([[0.20]], dtype=np.float32)
    red = np.array([[0.10]], dtype=np.float32)  # noqa: F841
    nir = np.array([[0.05]], dtype=np.float32)
    swir1 = np.array([[0.08]], dtype=np.float32)
    swir2 = np.array([[0.04]], dtype=np.float32)

    # AWEInsh = 4 * (0.20 - 0.08) - (0.25 * 0.05 + 2.75 * 0.04) = 4 * 0.12 - (0.0125 + 0.11) = 0.48 - 0.1225 = 0.3575
    awei_nsh = compute_awei_nsh(green, swir1, nir, swir2)
    assert pytest.approx(awei_nsh[0, 0], rel=1e-4) == 0.3575

    # AWEIsh = 0.15 + 2.5 * 0.20 - 1.5 * (0.05 + 0.08) - 0.25 * 0.04 = 0.15 + 0.50 - 0.195 - 0.01 = 0.445
    awei_sh = compute_awei_sh(blue, green, nir, swir1, swir2)
    assert pytest.approx(awei_sh[0, 0], rel=1e-4) == 0.445
