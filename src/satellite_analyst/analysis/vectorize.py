"""Raster to vector polygonization and equal-area CRS transformation."""

from typing import Any

import numpy as np


def estimate_utm_epsg(lon: float, lat: float) -> int:
    """Calculate appropriate UTM EPSG code for a given WGS84 coordinate."""
    zone = int((lon + 180) // 6) + 1
    if lat >= 0:
        return 32600 + zone
    return 32700 + zone


def vectorize_change_raster(
    change_raster: np.ndarray,
    transform: Any,
    crs: str = "EPSG:4326",
    min_area_ha: float = 0.1,
) -> dict[str, Any]:
    """Polygonize change raster into GeoJSON FeatureCollection with equal-area metrics."""
    # In Phase 2, rasterio.features.shapes and geopandas / shapely / pyproj
    # will implement the complete polygonization and UTM equal-area reprojection.
    _ = (change_raster, transform, min_area_ha)
    features: list[dict[str, Any]] = []

    # Placeholder skeleton structure
    return {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": crs}},
        "features": features,
    }
