"""Tests for summary stats, raster vectorization, equal-area accuracy, and waterbody tracking."""

import numpy as np
import pytest
from affine import Affine

from satellite_analyst.analysis.change import WaterChangeClass
from satellite_analyst.analysis.stats import (
    WaterBodyRecord,
    compute_summary_stats,
)
from satellite_analyst.analysis.vectorize import (
    estimate_utm_epsg,
    extract_waterbody_records,
    vectorize_change_classes,
)


def test_estimate_utm_epsg() -> None:
    # Raipur approx: lon 81.6, lat 21.2 -> UTM Zone 44N (EPSG:32644)
    epsg_raipur = estimate_utm_epsg(81.6, 21.2)
    assert epsg_raipur == 32644

    # Southern hemisphere coordinate
    epsg_south = estimate_utm_epsg(81.6, -21.2)
    assert epsg_south == 32744


def test_vectorize_change_classes_equal_area_accuracy() -> None:
    """Test that polygonized area in hectares matches pixel count * 0.01 ha within 0.1%."""
    # 50x50 raster with 10m pixels in UTM Zone 44N
    shape = (50, 50)
    change_raster = np.zeros(shape, dtype=np.uint8)

    # 10x10 block of GAINED pixels = 100 pixels * 100m² = 10,000 m² = 1.00 hectare
    change_raster[10:20, 10:20] = WaterChangeClass.GAINED

    # Affine transform for 10m pixels starting at UTM (200000, 2350000)
    transform = Affine.translation(200000, 2350000) @ Affine.scale(10.0, -10.0)

    gdf = vectorize_change_classes(
        change_raster,
        transform=transform,
        crs="EPSG:32644",
        min_area_ha=0.01,
    )

    assert len(gdf) == 1
    row = gdf.iloc[0]
    assert row["class_name"] == "gained"
    # Exact 1.00 ha within < 0.1% tolerance
    assert pytest.approx(row["area_ha"], abs=1e-3) == 1.00
    # Output CRS is EPSG:4326 for Leaflet compatibility
    assert gdf.crs.to_string() == "EPSG:4326"


def test_extract_waterbody_records_dynamics_and_stable_id() -> None:
    """Test connected components tracking, dynamic statuses, and deterministic IDs."""
    shape = (60, 60)
    mask_a = np.zeros(shape, dtype=bool)
    mask_b = np.zeros(shape, dtype=bool)

    # Waterbody 1: Expanding pond (10x10 -> 10x15)
    mask_a[10:20, 10:20] = True  # 100 px = 1.0 ha
    mask_b[10:20, 10:25] = True  # 150 px = 1.5 ha

    # Waterbody 2: Disappeared pond
    mask_a[30:40, 30:40] = True  # 100 px = 1.0 ha
    # mask_b remains False

    # Waterbody 3: Brand new pond
    mask_b[45:55, 45:55] = True  # 100 px = 1.0 ha

    transform = Affine.translation(200000, 2350000) @ Affine.scale(10.0, -10.0)

    records, gdf = extract_waterbody_records(
        mask_a=mask_a,
        mask_b=mask_b,
        transform=transform,
        crs="EPSG:32644",
        min_area_ha=0.1,
    )

    assert len(records) == 3
    statuses = {r.status for r in records}
    assert statuses == {"expanded", "disappeared", "new"}

    # Verify stable ID determinism: running extraction again on same data yields identical IDs
    records_repeat, _ = extract_waterbody_records(
        mask_a=mask_a,
        mask_b=mask_b,
        transform=transform,
        crs="EPSG:32644",
        min_area_ha=0.1,
    )
    assert [r.waterbody_id for r in records] == [r.waterbody_id for r in records_repeat]


def test_compute_summary_stats() -> None:
    shape = (100, 100)
    change_raster = np.zeros(shape, dtype=np.uint8)

    # 100 gained pixels = 1.0 ha
    change_raster[0:10, 0:10] = WaterChangeClass.GAINED
    # 50 lost pixels = 0.5 ha
    change_raster[20:25, 0:10] = WaterChangeClass.LOST
    # 200 persistent pixels = 2.0 ha
    change_raster[40:50, 0:20] = WaterChangeClass.PERSISTENT

    wb = WaterBodyRecord(
        waterbody_id="wb_test01",
        centroid_lon=81.65,
        centroid_lat=21.25,
        area_period_a_ha=2.5,
        area_period_b_ha=3.0,
        net_change_ha=0.5,
        percent_change=20.0,
        status="expanded",
    )

    stats = compute_summary_stats(change_raster, waterbodies=[wb], pixel_size_m=10.0)

    assert stats.gained_water_ha == 1.00
    assert stats.lost_water_ha == 0.50
    assert stats.persistent_water_ha == 2.00
    assert stats.total_water_period_a_ha == 2.50
    assert stats.total_water_period_b_ha == 3.00
    assert stats.net_change_ha == 0.50
    assert stats.percent_change == 20.00
    assert stats.net_change_pct == 20.00
    # churn_ratio = (1.0 + 0.5) / (2.0 + 1.0 + 0.5) = 1.5 / 3.5 = 0.4286 > 0.25 -> within noise
    assert stats.churn_ratio == pytest.approx(0.4286, abs=1e-3)
    assert stats.significance == "within noise / inconclusive"
    assert stats.waterbody_count == 1
    assert stats.valid_area_fraction == 1.00
    # wb >= 1.0 ha
    assert stats.headline_1ha["count"] == 1
    assert stats.headline_1ha["total_water_period_a_ha"] == 2.50
    assert stats.headline_1ha["total_water_period_b_ha"] == 3.00
    assert stats.headline_1ha["net_change_ha"] == 0.50


def test_significance_labels_expansion_and_noise() -> None:
    """Test that significant expansion requires >= 10% change AND churn <= 0.25."""
    shape = (100, 100)
    # Significant expansion case: persistent = 20.0 ha (2000 px), gained = 3.0 ha (300 px), lost = 0.5 ha (50 px)
    change_raster_exp = np.zeros(shape, dtype=np.uint8)
    change_raster_exp[0:20, 0:100] = WaterChangeClass.PERSISTENT
    change_raster_exp[20:23, 0:100] = WaterChangeClass.GAINED
    change_raster_exp[23:24, 0:50] = WaterChangeClass.LOST

    stats_exp = compute_summary_stats(change_raster_exp, waterbodies=[], pixel_size_m=10.0)
    # net_change = 3.0 - 0.5 = 2.5 ha (12.5% of persistent)
    # churn = 3.5 / 23.5 = 0.149 <= 0.25
    assert stats_exp.significance == "significant expansion"

    # Noise case: net change is large but churn is high (> 0.25)
    change_raster_noise = np.zeros(shape, dtype=np.uint8)
    change_raster_noise[0:10, 0:100] = WaterChangeClass.PERSISTENT  # 10.0 ha
    change_raster_noise[10:14, 0:100] = WaterChangeClass.GAINED  # 4.0 ha
    change_raster_noise[14:17, 0:100] = WaterChangeClass.LOST  # 3.0 ha
    # net = +1.0 ha (10% of persistent), churn = 7.0 / 17.0 = 0.412 > 0.25
    stats_noise = compute_summary_stats(change_raster_noise, waterbodies=[], pixel_size_m=10.0)
    assert stats_noise.significance == "within noise / inconclusive"


def test_threshold_sensitivity_evaluation() -> None:
    from satellite_analyst.analysis.stats import compute_threshold_sensitivity

    # 10x10 synthetic grid
    mndwi_a = np.full((10, 10), -0.05, dtype=np.float32)
    mndwi_b = np.full((10, 10), 0.05, dtype=np.float32)
    valid_mask = np.ones((10, 10), dtype=bool)

    # At threshold -0.1: both are water (net = 0)
    # At threshold 0.0: a is dry, b is water (b gained 100 px = 1.0 ha, net = +1.0 ha)
    # At threshold +0.1: both are dry (net = 0)
    sens = compute_threshold_sensitivity(
        mndwi_a=mndwi_a,
        mndwi_b=mndwi_b,
        valid_mask=valid_mask,
        mid_threshold=0.0,
        offset=0.1,
        pixel_size_m=10.0,
    )
    assert sens.threshold_low == -0.1
    assert sens.threshold_mid == 0.0
    assert sens.threshold_high == 0.1
    assert sens.net_change_low_ha == 0.0
    assert sens.net_change_mid_ha == 1.0
    assert sens.net_change_high_ha == 0.0
    assert sens.sign_flips is False  # Min is 0.0, not negative


def test_report_area_equals_analysed_valid_area() -> None:
    """Test that report area matches analysed valid bounding box area exactly."""
    # 200x200 raster with 10m pixels -> 40,000 pixels * 0.01 ha = 400.0 ha = 4.0 km²
    shape = (200, 200)
    change_raster = np.zeros(shape, dtype=np.uint8)
    # Set 500 pixels as NODATA (255)
    change_raster[0:25, 0:20] = WaterChangeClass.NODATA

    stats = compute_summary_stats(change_raster, waterbodies=[], pixel_size_m=10.0)

    assert stats.total_aoi_ha == 400.0
    assert stats.total_aoi_km2 == 4.0
    assert stats.valid_aoi_ha == 395.0
    assert stats.valid_aoi_km2 == 3.95
    assert stats.valid_area_fraction == 0.9875

    # Check that to_dict exports these fields
    d = stats.to_dict()
    assert d["total_aoi_km2"] == 4.0
    assert d["valid_aoi_km2"] == 3.95
    assert d["total_aoi_ha"] == 400.0
    assert d["valid_aoi_ha"] == 395.0
