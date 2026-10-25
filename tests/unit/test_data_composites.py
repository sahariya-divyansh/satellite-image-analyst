"""Unit tests for Sentinel-2 L2A radiometry, SCL masking, and compositing."""

from pathlib import Path

import numpy as np
import pytest
import rasterio
import xarray as xr

from satellite_analyst.analysis.vectorize import estimate_utm_epsg
from satellite_analyst.data.composites import (
    CompositeResult,
    apply_scl_mask,
    compute_temporal_median,
    convert_dn_to_reflectance,
    save_composite_to_geotiff,
)


def test_utm_zone_selection_raipur() -> None:
    """Raipur coordinates (lon 81.63, lat 21.25) must deterministically resolve to UTM Zone 44N (EPSG:32644)."""
    raipur_lon = 81.6296
    raipur_lat = 21.2514
    epsg = estimate_utm_epsg(raipur_lon, raipur_lat)
    assert epsg == 32644


def test_dn_to_reflectance_modern_baseline() -> None:
    """Baseline >= 04.00 includes BOA_ADD_OFFSET = -1000."""
    # DN = 2000 -> (2000 - 1000) / 10000 = 0.1000
    # DN = 900  -> (900 - 1000) / 10000 = -0.01 -> clipped to 0.0
    # DN = 12000 -> (12000 - 1000) / 10000 = 1.1 -> clipped to 1.0
    dn = np.array([900, 2000, 5000, 12000], dtype=np.int32)
    refl = convert_dn_to_reflectance(dn, processing_baseline="04.00")

    assert pytest.approx(refl[0]) == 0.0
    assert pytest.approx(refl[1]) == 0.1000
    assert pytest.approx(refl[2]) == 0.4000
    assert pytest.approx(refl[3]) == 1.0000


def test_dn_to_reflectance_legacy_baseline() -> None:
    """Baseline < 04.00 (e.g. 02.04) has NO offset."""
    # DN = 2000 -> 2000 / 10000 = 0.2000
    dn = np.array([0, 2000, 10000, 15000], dtype=np.int32)
    refl = convert_dn_to_reflectance(dn, processing_baseline="02.04")

    assert pytest.approx(refl[0]) == 0.0
    assert pytest.approx(refl[1]) == 0.2000
    assert pytest.approx(refl[2]) == 1.0000
    assert pytest.approx(refl[3]) == 1.0000


def test_scl_mask_logic() -> None:
    """Mask 0 (no data), 1 (saturated), 3 (shadow), 8/9 (cloud), 10 (cirrus), 11 (snow).

    Keep 4 (veg), 5 (bare), 6 (water), 7 (unclassified).
    """
    data = np.full((12,), 0.5, dtype=np.float32)
    scl = np.array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], dtype=np.int32)

    masked = apply_scl_mask(data, scl)

    # Invalid classes (should be NaN)
    for idx in [0, 1, 3, 8, 9, 10, 11]:
        assert np.isnan(masked[idx]), f"Class {idx} should be masked"

    # Valid classes (should remain 0.5)
    for idx in [4, 5, 6, 7]:
        assert pytest.approx(masked[idx]) == 0.5, f"Class {idx} should be kept"


def test_compute_temporal_median_cloudy_stack() -> None:
    """Verify temporal nanmedian across cloudy observations with min_valid_obs enforcement."""
    # Stack: 4 scenes over 2x2 AOI
    # Pixel (0,0): 4 valid obs [0.1, 0.2, 0.3, 0.4] -> median 0.25, valid_count = 4
    # Pixel (0,1): 2 valid obs [0.2, NaN, 0.4, NaN] -> median 0.30, valid_count = 2
    # Pixel (1,0): 1 valid obs [NaN, 0.5, NaN, NaN] -> < 2 valid obs -> NaN!
    # Pixel (1,1): 0 valid obs [NaN, NaN, NaN, NaN] -> < 2 valid obs -> NaN!
    stack = np.array(
        [
            [[0.1, 0.2], [np.nan, np.nan]],
            [[0.2, np.nan], [0.5, np.nan]],
            [[0.3, 0.4], [np.nan, np.nan]],
            [[0.4, np.nan], [np.nan, np.nan]],
        ],
        dtype=np.float32,
    )

    median, valid_count, valid_fraction = compute_temporal_median(stack, min_valid_obs=2)

    assert pytest.approx(median[0, 0]) == 0.25
    assert valid_count[0, 0] == 4

    assert pytest.approx(median[0, 1]) == 0.30
    assert valid_count[0, 1] == 2

    # Pixels with fewer than min_valid_obs MUST be NaN
    assert np.isnan(median[1, 0])
    assert valid_count[1, 0] == 1

    assert np.isnan(median[1, 1])
    assert valid_count[1, 1] == 0

    # 2 out of 4 pixels meet threshold -> 50%
    assert pytest.approx(valid_fraction) == 0.50


def test_save_composite_to_geotiff(tmp_path: Path) -> None:
    """Verify GeoTIFF generation, coordinates, nodata, and transform."""
    xs = np.array([100.0, 110.0, 120.0])
    ys = np.array([200.0, 190.0])

    green_arr = np.array([[0.1, 0.2, 0.3], [0.4, 0.5, np.nan]], dtype=np.float32)
    swir1_arr = np.array([[0.05, 0.06, 0.07], [0.08, 0.09, np.nan]], dtype=np.float32)
    valid_arr = np.array([[3, 3, 3], [2, 2, 0]], dtype=np.int16)

    comp = CompositeResult(
        green=xr.DataArray(green_arr, coords={"y": ys, "x": xs}, dims=["y", "x"]),
        swir1=xr.DataArray(swir1_arr, coords={"y": ys, "x": xs}, dims=["y", "x"]),
        valid_count=xr.DataArray(valid_arr, coords={"y": ys, "x": xs}, dims=["y", "x"]),
        scene_ids=["S2A_TEST_01", "S2B_TEST_02"],
        date_range=("2023-10-01", "2023-11-30"),
        per_scene_cloud=[{"id": "S2A_TEST_01", "cloud": 5.0}],
        bbox=[81.5, 21.1, 81.8, 21.3],
        crs="EPSG:32644",
        valid_fraction=0.8333,
        software_version="0.1.0",
    )

    out_paths = save_composite_to_geotiff(comp, output_dir=tmp_path, prefix="test_comp")

    assert out_paths["green"].exists()
    assert out_paths["swir1"].exists()
    assert out_paths["valid_count"].exists()
    assert out_paths["provenance"].exists()

    with rasterio.open(out_paths["green"]) as src:
        assert src.count == 1
        assert src.crs.to_string() == "EPSG:32644"
        assert src.shape == (2, 3)
        read_arr = src.read(1)
        assert pytest.approx(read_arr[0, 0]) == 0.1
        assert np.isnan(read_arr[1, 2])
