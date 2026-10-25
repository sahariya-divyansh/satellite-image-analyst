"""Geospatial analysis package: indices, water masking, change detection, and statistics."""

from satellite_analyst.analysis.change import WaterChangeClass, detect_water_change
from satellite_analyst.analysis.indices import compute_mndwi, compute_ndwi
from satellite_analyst.analysis.stats import (
    AreaSummaryStats,
    WaterBodyRecord,
    compute_summary_stats,
)
from satellite_analyst.analysis.vectorize import estimate_utm_epsg, vectorize_change_raster
from satellite_analyst.analysis.water import compute_otsu_threshold, create_water_mask

__all__ = [
    "compute_mndwi",
    "compute_ndwi",
    "compute_otsu_threshold",
    "create_water_mask",
    "WaterChangeClass",
    "detect_water_change",
    "estimate_utm_epsg",
    "vectorize_change_raster",
    "WaterBodyRecord",
    "AreaSummaryStats",
    "compute_summary_stats",
]
