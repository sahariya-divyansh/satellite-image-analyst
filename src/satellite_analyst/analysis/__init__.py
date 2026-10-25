"""Geospatial analysis package: indices, water masking, change detection, and statistics."""

from satellite_analyst.analysis.change import (
    WaterChangeClass,
    detect_water_change,
    save_change_raster_to_geotiff,
)
from satellite_analyst.analysis.indices import compute_mndwi, compute_ndwi
from satellite_analyst.analysis.stats import (
    AreaSummaryStats,
    ThresholdSensitivity,
    WaterBodyRecord,
    compute_summary_stats,
    compute_threshold_sensitivity,
)
from satellite_analyst.analysis.vectorize import (
    estimate_utm_epsg,
    extract_waterbody_records,
    vectorize_change_classes,
)
from satellite_analyst.analysis.water import (
    WaterMask,
    compute_otsu_threshold,
    create_water_mask,
    segment_dual_period_water,
)

# Backwards compatibility alias
vectorize_change_raster = vectorize_change_classes

__all__ = [
    "compute_mndwi",
    "compute_ndwi",
    "compute_otsu_threshold",
    "create_water_mask",
    "segment_dual_period_water",
    "WaterMask",
    "WaterChangeClass",
    "detect_water_change",
    "save_change_raster_to_geotiff",
    "estimate_utm_epsg",
    "vectorize_change_classes",
    "vectorize_change_raster",
    "extract_waterbody_records",
    "WaterBodyRecord",
    "AreaSummaryStats",
    "ThresholdSensitivity",
    "compute_summary_stats",
    "compute_threshold_sensitivity",
]
