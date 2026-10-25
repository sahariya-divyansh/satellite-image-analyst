"""Tests for summary stats and vectorization utilities."""

import numpy as np

from satellite_analyst.analysis.stats import (
    WaterBodyRecord,
    compute_summary_stats,
)
from satellite_analyst.analysis.vectorize import estimate_utm_epsg, vectorize_change_raster
from satellite_analyst.analysis.water import create_water_mask


def test_estimate_utm_epsg() -> None:
    # Raipur approx: lon 81.6, lat 21.2 -> UTM Zone 44N (EPSG:32644)
    epsg_raipur = estimate_utm_epsg(81.6, 21.2)
    assert epsg_raipur == 32644

    # Southern hemisphere coordinate
    epsg_south = estimate_utm_epsg(81.6, -21.2)
    assert epsg_south == 32744


def test_vectorize_change_raster_stub() -> None:
    raster = np.zeros((10, 10), dtype=np.uint8)
    geojson = vectorize_change_raster(raster, transform=None, crs="EPSG:32644")
    assert geojson["type"] == "FeatureCollection"
    assert "features" in geojson


def test_compute_summary_stats() -> None:
    wb = WaterBodyRecord(
        waterbody_id="WB_001",
        centroid_lon=81.65,
        centroid_lat=21.25,
        area_period_a_ha=100.0,
        area_period_b_ha=120.0,
        net_change_ha=20.0,
        percent_change=20.0,
        status="expanded",
    )
    summary = compute_summary_stats(
        waterbodies=[wb],
        pixel_gained_ha=25.0,
        pixel_lost_ha=5.0,
        pixel_persistent_ha=95.0,
    )

    assert summary.total_water_period_a_ha == 100.0
    assert summary.total_water_period_b_ha == 120.0
    assert summary.net_change_ha == 20.0
    assert summary.percent_change == 20.0
    assert summary.waterbody_count == 1

    d = summary.to_dict()
    assert isinstance(d, dict)
    assert d["net_change_ha"] == 20.0


def test_water_mask_with_morphology() -> None:
    # Create array with a small 1-pixel noise and a larger 4x4 block
    mndwi = np.full((20, 20), -0.5, dtype=np.float32)
    mndwi[2, 2] = 0.5  # 1-pixel noise
    mndwi[8:14, 8:14] = 0.6  # 36-pixel pond

    mask, threshold = create_water_mask(
        mndwi,
        threshold=0.0,
        min_pixels=10,
        apply_morphology=True,
    )
    # The 1-pixel noise should be removed by morphology / min_pixels
    assert mask[2, 2] is False or mask[2, 2] == 0
    # The pond center should be water
    assert mask[10, 10] is True or mask[10, 10] == 1
