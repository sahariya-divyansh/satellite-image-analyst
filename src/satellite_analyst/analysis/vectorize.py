"""Raster to vector polygonization, connected-component waterbody tracking, and GeoJSON export."""

import hashlib
from typing import Any

import geopandas as gpd
import numpy as np
import rasterio.features
from affine import Affine
from scipy.ndimage import label  # type: ignore[import-untyped]
from shapely.geometry import shape
from shapely.ops import unary_union

from satellite_analyst.analysis.change import WaterChangeClass
from satellite_analyst.analysis.stats import WaterBodyRecord


def estimate_utm_epsg(lon: float, lat: float) -> int:
    """Calculate appropriate UTM EPSG code for a given WGS84 coordinate."""
    zone = int((lon + 180) // 6) + 1
    if lat >= 0:
        return 32600 + zone
    return 32700 + zone


def vectorize_change_classes(
    change_raster: np.ndarray,
    transform: Affine,
    crs: str,
    min_area_ha: float = 0.05,
) -> gpd.GeoDataFrame:
    """Polygonize 3-class change raster into GeoDataFrame with equal-area metrics.

    Excludes DRY (0) and NODATA (255) pixels.
    Geometries are extracted in native projected coordinates, filtered by area,
    and transformed to EPSG:4326 for Leaflet/GeoJSON visualization.
    """
    # Valid change mask (GAINED=1, LOST=2, PERSISTENT=3)
    valid_change = np.isin(
        change_raster,
        [WaterChangeClass.GAINED, WaterChangeClass.LOST, WaterChangeClass.PERSISTENT],
    )

    if not np.any(valid_change):
        return gpd.GeoDataFrame(
            columns=["change_class", "class_name", "area_ha", "geometry"],
            crs="EPSG:4326",
        )

    class_names = {
        WaterChangeClass.GAINED: "gained",
        WaterChangeClass.LOST: "lost",
        WaterChangeClass.PERSISTENT: "persistent",
    }

    records: list[dict[str, Any]] = []

    # Extract polygon shapes using rasterio
    for geom_dict, val in rasterio.features.shapes(
        change_raster,
        mask=valid_change,
        transform=transform,
    ):
        try:
            val_cls = WaterChangeClass(int(val))
        except ValueError:
            continue
        if val_cls not in class_names:
            continue

        poly = shape(geom_dict)
        if poly.is_empty or not poly.is_valid:
            poly = poly.buffer(0)
            if poly.is_empty:
                continue

        # Native CRS is projected (e.g. UTM), so area is in m²
        # 1 ha = 10,000 m²
        area_ha = float(poly.area / 10000.0)
        if area_ha < min_area_ha:
            continue

        records.append(
            {
                "change_class": int(val_cls),
                "class_name": class_names[val_cls],
                "area_ha": round(area_ha, 3),
                "geometry": poly,
            }
        )

    if not records:
        return gpd.GeoDataFrame(
            columns=["change_class", "class_name", "area_ha", "geometry"],
            crs="EPSG:4326",
        )

    gdf = gpd.GeoDataFrame(records, geometry="geometry", crs=crs)

    # Reproject to WGS84 for GeoJSON/Leaflet
    if crs != "EPSG:4326":
        gdf = gdf.to_crs("EPSG:4326")

    return gdf


def extract_waterbody_records(
    mask_a: np.ndarray,
    mask_b: np.ndarray,
    transform: Affine,
    crs: str,
    min_area_ha: float = 0.1,
    pixel_size_m: float = 10.0,
) -> tuple[list[WaterBodyRecord], gpd.GeoDataFrame]:
    """Segment individual waterbodies by connected components of union(water_a, water_b).

    Assigns deterministic IDs hashed from geographic centroids, tracks before/after areas,
    calculates delta, and classifies dynamics into expanded, shrunk, persistent, new, or disappeared.
    """
    pixel_ha = (pixel_size_m**2) / 10000.0
    water_union = (mask_a | mask_b).astype(np.uint8)

    # 8-connectivity structural element
    struct = np.ones((3, 3), dtype=np.uint8)
    labeled_arr, num_features = label(water_union, structure=struct)

    records: list[WaterBodyRecord] = []

    if num_features == 0:
        empty_gdf = gpd.GeoDataFrame(
            columns=[
                "waterbody_id",
                "status",
                "area_period_a_ha",
                "area_period_b_ha",
                "net_change_ha",
                "percent_change",
                "geometry",
            ],
            crs="EPSG:4326",
        )
        return records, empty_gdf

    counts_a = np.bincount(labeled_arr[mask_a], minlength=num_features + 1)
    counts_b = np.bincount(labeled_arr[mask_b], minlength=num_features + 1)

    min_pixels = int(np.ceil((min_area_ha * 10000.0) / (pixel_size_m**2)))
    valid_cids = [
        cid for cid in range(1, num_features + 1) if max(counts_a[cid], counts_b[cid]) >= min_pixels
    ]

    if not valid_cids:
        empty_gdf = gpd.GeoDataFrame(
            columns=[
                "waterbody_id",
                "status",
                "area_period_a_ha",
                "area_period_b_ha",
                "net_change_ha",
                "percent_change",
                "geometry",
            ],
            crs="EPSG:4326",
        )
        return records, empty_gdf

    # Extract all component shapes in a single rasterio pass
    valid_mask = np.isin(labeled_arr, valid_cids)
    comp_polys: dict[int, list[Any]] = {cid: [] for cid in valid_cids}

    for geom_dict, val in rasterio.features.shapes(
        labeled_arr, mask=valid_mask, transform=transform
    ):
        cid = int(val)
        if cid in comp_polys:
            poly = shape(geom_dict)
            if not poly.is_empty:
                comp_polys[cid].append(poly)

    temp_rows: list[dict[str, Any]] = []

    for comp_id in valid_cids:
        count_a = int(counts_a[comp_id])
        count_b = int(counts_b[comp_id])
        area_a = count_a * pixel_ha
        area_b = count_b * pixel_ha

        net_change = area_b - area_a
        pct_change = (
            (net_change / area_a * 100.0) if area_a > 0.0 else (100.0 if area_b > 0 else 0.0)
        )

        # Classify status
        if area_a == 0.0 and area_b > 0.0:
            status = "new"
        elif area_a > 0.0 and area_b == 0.0:
            status = "disappeared"
        elif net_change > (0.05 * area_a):
            status = "expanded"
        elif net_change < (-0.05 * area_a):
            status = "shrunk"
        else:
            status = "persistent"

        polys = comp_polys.get(comp_id, [])
        if not polys:
            continue
        geom_union = unary_union(polys)

        temp_rows.append(
            {
                "status": status,
                "area_period_a_ha": round(area_a, 2),
                "area_period_b_ha": round(area_b, 2),
                "net_change_ha": round(net_change, 2),
                "percent_change": round(pct_change, 2),
                "geometry": geom_union,
            }
        )

    if not temp_rows:
        empty_gdf = gpd.GeoDataFrame(
            columns=[
                "waterbody_id",
                "status",
                "area_period_a_ha",
                "area_period_b_ha",
                "net_change_ha",
                "percent_change",
                "geometry",
            ],
            crs="EPSG:4326",
        )
        return records, empty_gdf

    # Reproject native geometries to WGS84 via GeoPandas
    gdf_native = gpd.GeoDataFrame(temp_rows, geometry="geometry", crs=crs)
    gdf_wgs84 = gdf_native.to_crs("EPSG:4326") if crs != "EPSG:4326" else gdf_native

    # Extract centroids and stable IDs in WGS84
    wb_ids: list[str] = []

    for _idx, row in gdf_wgs84.iterrows():
        c_pt = row.geometry.centroid
        lon = float(c_pt.x)
        lat = float(c_pt.y)

        loc_str = f"{round(lon, 4)}_{round(lat, 4)}"
        hash_id = hashlib.sha256(loc_str.encode("utf-8")).hexdigest()[:8]
        wb_id = f"wb_{hash_id}"
        wb_ids.append(wb_id)

        rec = WaterBodyRecord(
            waterbody_id=wb_id,
            centroid_lon=round(lon, 5),
            centroid_lat=round(lat, 5),
            area_period_a_ha=row["area_period_a_ha"],
            area_period_b_ha=row["area_period_b_ha"],
            net_change_ha=row["net_change_ha"],
            percent_change=row["percent_change"],
            status=row["status"],
        )
        records.append(rec)

    gdf_wgs84["waterbody_id"] = wb_ids

    # Sort deterministically by net_change absolute magnitude descending, then ID
    records.sort(key=lambda r: (-abs(r.net_change_ha), r.waterbody_id))

    gdf_wgs84["abs_delta"] = gdf_wgs84["net_change_ha"].abs()
    gdf_sorted = (
        gdf_wgs84.sort_values(by=["abs_delta", "waterbody_id"], ascending=[False, True])
        .drop(columns=["abs_delta"])
        .reset_index(drop=True)
    )

    return records, gdf_sorted
