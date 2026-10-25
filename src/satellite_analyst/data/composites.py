"""Cloud-masked seasonal median composite engine for Sentinel-2 L2A imagery."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import xarray as xr
from rasterio.transform import Affine

from satellite_analyst import __version__
from satellite_analyst.analysis.vectorize import estimate_utm_epsg
from satellite_analyst.config import get_settings
from satellite_analyst.data.cache import RasterDataCache
from satellite_analyst.data.stac_client import SceneCollection, STACClient
from satellite_analyst.errors import InsufficientImageryError
from satellite_analyst.logging import get_logger
from satellite_analyst.planner.schema import BoundingBox, TimeInterval

logger = get_logger(__name__)

# Default SCL classes to mask (0=no data, 1=saturated, 3=shadow, 8=cloud med, 9=cloud high, 10=cirrus, 11=snow)
DEFAULT_SCL_MASK_CLASSES: frozenset[int] = frozenset([0, 1, 3, 8, 9, 10, 11])


@dataclass
class CompositeResult:
    """Represents a radiometric, cloud-masked temporal median composite."""

    green: xr.DataArray
    swir1: xr.DataArray
    valid_count: xr.DataArray
    scene_ids: list[str]
    date_range: tuple[str, str]
    per_scene_cloud: list[dict[str, Any]]
    bbox: list[float]
    crs: str
    valid_fraction: float
    software_version: str

    def to_provenance(self) -> dict[str, Any]:
        """Return provenance metadata dictionary."""
        return {
            "scene_ids": self.scene_ids,
            "scene_count": len(self.scene_ids),
            "date_range": list(self.date_range),
            "per_scene_cloud": self.per_scene_cloud,
            "bbox": self.bbox,
            "crs": self.crs,
            "valid_fraction": round(self.valid_fraction, 4),
            "software_version": self.software_version,
            "spatial_resolution_m": 10.0,
        }


def parse_processing_baseline(baseline_str: str) -> float:
    """Parse baseline string such as '04.00' or '05.00' into a float for comparison."""
    try:
        parts = baseline_str.strip().split(".")
        if len(parts) >= 2:
            return float(f"{parts[0]}.{parts[1]}")
        return float(baseline_str)
    except Exception:
        return 4.0  # Conservative default: assume modern baseline with offset


def convert_dn_to_reflectance(
    dn: np.ndarray,
    processing_baseline: str,
    offset: float = -1000.0,
    scale: float = 10000.0,
) -> np.ndarray:
    """Convert raw Digital Numbers (DN) to BOA surface reflectance [0.0, 1.0].

    Sentinel-2 L2A processing baseline >= 04.00 (since Jan 2022) introduces
    BOA_ADD_OFFSET = -1000 to prevent negative reflectance truncation.
    Formula:
      Baseline >= 04.00: reflectance = (DN + offset) / scale = (DN - 1000) / 10000
      Baseline < 04.00:  reflectance = DN / scale = DN / 10000
    """
    arr = dn.astype(np.float32)
    numeric_baseline = parse_processing_baseline(processing_baseline)
    reflectance = (arr + offset) / scale if numeric_baseline >= 4.0 else arr / scale
    return np.clip(reflectance, 0.0, 1.0)


def apply_scl_mask(
    data: np.ndarray,
    scl: np.ndarray,
    mask_classes: frozenset[int] = DEFAULT_SCL_MASK_CLASSES,
) -> np.ndarray:
    """Mask cloudy, shadow, defective, or cirrus pixels by setting them to NaN."""
    masked = data.copy()
    invalid_mask = np.isin(scl, list(mask_classes))
    masked[invalid_mask] = np.nan
    return masked


def compute_temporal_median(
    stack: np.ndarray,
    min_valid_obs: int = 2,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Compute temporal median across axis 0 with strict min_valid_obs threshold.

    Args:
        stack: 3D float array of shape (time, height, width) with NaNs for masked pixels.
        min_valid_obs: Minimum number of valid clear observations required per pixel.

    Returns:
        tuple[np.ndarray, np.ndarray, float]:
          - median composite (2D float32, NaN where valid_count < min_valid_obs)
          - valid_count (2D int16)
          - valid_fraction (float: ratio of pixels meeting min_valid_obs)
    """
    if stack.ndim != 3:
        raise ValueError(f"Expected 3D stack (time, height, width), got shape {stack.shape}")

    # Count non-NaN valid observations across time
    valid_count = np.sum(~np.isnan(stack), axis=0).astype(np.int16)

    # Compute nanmedian with warnings suppressed for all-NaN slices
    with np.errstate(all="ignore"):
        median = np.nanmedian(stack, axis=0).astype(np.float32)

    # Enforce min_valid_obs: pixels with fewer valid observations become NaN
    insufficient = valid_count < min_valid_obs
    median[insufficient] = np.nan

    total_pixels = float(valid_count.size)
    valid_pixels = float(np.sum(~insufficient))
    valid_fraction = (valid_pixels / total_pixels) if total_pixels > 0 else 0.0

    return median, valid_count, valid_fraction


class CompositeBuilder:
    """Orchestrates scene retrieval, radiometry normalization, and median compositing."""

    def __init__(
        self,
        stac_client: STACClient | None = None,
        cache: RasterDataCache | None = None,
    ) -> None:
        self.stac_client = stac_client or STACClient()
        self.cache = cache or RasterDataCache()

    def build_composite(
        self,
        bbox: BoundingBox,
        time_range: TimeInterval,
        max_cloud_cover: float = 40.0,
        min_valid_obs: int = 2,
        scl_mask_classes: frozenset[int] = DEFAULT_SCL_MASK_CLASSES,
        force_refresh: bool = False,
    ) -> CompositeResult:
        """Build cloud-masked seasonal median composite across target temporal window."""
        # Check on-disk cached composite
        cache_params = {
            "bbox": bbox.as_list(),
            "start": str(time_range.start_date),
            "end": str(time_range.end_date),
            "max_cloud": max_cloud_cover,
            "min_valid_obs": min_valid_obs,
            "mask_classes": sorted(scl_mask_classes),
            "version": __version__,
        }
        cache_hash = hashlib.sha256(json.dumps(cache_params, sort_keys=True).encode()).hexdigest()
        cache_dir = get_settings().cache_dir / f"composite_{cache_hash}"

        if not force_refresh and (cache_dir / "provenance.json").exists():
            try:
                cached_res = self._load_cached_composite(cache_dir)
                if cached_res is not None:
                    logger.info(f"Loaded cached seasonal composite from {cache_dir}")
                    return cached_res
            except Exception as e:
                logger.warning(f"Failed to read cached composite: {e}")

        # Search matching Sentinel-2 scenes
        collection = self.stac_client.search_scenes(
            bbox=bbox,
            time_range=time_range,
            max_cloud_cover=max_cloud_cover,
        )

        if not collection.items:
            raise InsufficientImageryError(
                period=time_range.label,
                total_scenes=0,
                valid_scenes=0,
            )

        # Centroid for equal-area UTM zone selection
        mid_lon = (bbox.min_lon + bbox.max_lon) / 2.0
        mid_lat = (bbox.min_lat + bbox.max_lat) / 2.0
        utm_code = estimate_utm_epsg(mid_lon, mid_lat)
        target_crs = f"EPSG:{utm_code}"

        # Load bands via odc-stac or fallback windowed loader
        composite = self._load_and_composite(
            collection=collection,
            bbox=bbox,
            target_crs=target_crs,
            min_valid_obs=min_valid_obs,
            scl_mask_classes=scl_mask_classes,
        )

        # Cache composite to disk
        try:
            self._save_cached_composite(composite, cache_dir, cache_params)
        except Exception as e:
            logger.warning(f"Could not persist composite to cache: {e}")

        return composite

    def _load_and_composite(
        self,
        collection: SceneCollection,
        bbox: BoundingBox,
        target_crs: str,
        min_valid_obs: int,
        scl_mask_classes: frozenset[int],
    ) -> CompositeResult:
        """Load band assets, calibrate radiometry, apply SCL mask, and compute median."""
        try:
            import odc.stac  # type: ignore[import-untyped]
            import planetary_computer  # type: ignore[import-untyped]
            from pystac_client import Client  # type: ignore[import-untyped]

            # Re-query raw pystac items for odc.stac loader
            client = Client.open(self.stac_client._get_endpoint(collection.provider))
            search = client.search(
                collections=["sentinel-2-l2a"],
                bbox=bbox.as_list(),
                ids=[item.id for item in collection.items],
            )
            raw_pystac_items = list(search.items())
            if collection.provider == "planetary_computer":
                for it in raw_pystac_items:
                    planetary_computer.sign_inplace(it)

            logger.info(
                f"Loading {len(raw_pystac_items)} Sentinel-2 scenes via odc-stac into {target_crs} at 10m"
            )

            # Define per-band resampling: bilinear for reflectance (B03, B11), nearest for SCL
            bbox_tuple: tuple[float, float, float, float] = (
                float(bbox.min_lon),
                float(bbox.min_lat),
                float(bbox.max_lon),
                float(bbox.max_lat),
            )
            ds: xr.Dataset = odc.stac.load(
                raw_pystac_items,
                bands=["B03", "B11", "SCL"],
                bbox=bbox_tuple,
                crs=target_crs,
                resolution=10,
                chunks={"x": 2048, "y": 2048},
                resampling={"B03": "bilinear", "B11": "bilinear", "SCL": "nearest"},
            )

            # Materialize computed chunks into memory
            ds = ds.compute()

            # Align band arrays
            b03_raw = ds["B03"].values.astype(np.float32)
            b11_raw = ds["B11"].values.astype(np.float32)
            scl_raw = ds["SCL"].values.astype(np.int32)

            # Number of time steps
            n_time = b03_raw.shape[0]
            b03_clean = np.zeros_like(b03_raw)
            b11_clean = np.zeros_like(b11_raw)

            # Apply per-scene baseline offset and SCL mask
            for t_idx in range(n_time):
                item_meta = (
                    collection.items[t_idx]
                    if t_idx < len(collection.items)
                    else collection.items[0]
                )
                baseline = item_meta.processing_baseline

                b03_refl = convert_dn_to_reflectance(b03_raw[t_idx], baseline)
                b11_refl = convert_dn_to_reflectance(b11_raw[t_idx], baseline)

                b03_clean[t_idx] = apply_scl_mask(b03_refl, scl_raw[t_idx], scl_mask_classes)
                b11_clean[t_idx] = apply_scl_mask(b11_refl, scl_raw[t_idx], scl_mask_classes)

            # Compute median composites
            green_med, valid_count, valid_fraction = compute_temporal_median(
                b03_clean, min_valid_obs
            )
            swir1_med, _, _ = compute_temporal_median(b11_clean, min_valid_obs)

            # Build xarray DataArrays with coordinates and spatial reference
            x_coords = ds["x"].values
            y_coords = ds["y"].values

            green_da = xr.DataArray(
                green_med,
                coords={"y": y_coords, "x": x_coords},
                dims=["y", "x"],
                attrs={
                    "crs": target_crs,
                    "long_name": "Sentinel-2 B03 Green 10m Median Reflectance",
                },
            )
            swir1_da = xr.DataArray(
                swir1_med,
                coords={"y": y_coords, "x": x_coords},
                dims=["y", "x"],
                attrs={
                    "crs": target_crs,
                    "long_name": "Sentinel-2 B11 SWIR1 10m Median Reflectance",
                },
            )
            valid_da = xr.DataArray(
                valid_count,
                coords={"y": y_coords, "x": x_coords},
                dims=["y", "x"],
                attrs={"crs": target_crs, "long_name": "Clear-Sky Valid Observation Count"},
            )

            per_scene_cloud = [
                {"id": it.id, "datetime": it.datetime, "cloud_cover": it.cloud_cover}
                for it in collection.items
            ]

            d_start = str(collection.items[0].datetime) if collection.items else ""
            d_end = str(collection.items[-1].datetime) if collection.items else ""

            return CompositeResult(
                green=green_da,
                swir1=swir1_da,
                valid_count=valid_da,
                scene_ids=collection.scene_ids(),
                date_range=(d_start, d_end),
                per_scene_cloud=per_scene_cloud,
                bbox=bbox.as_list(),
                crs=target_crs,
                valid_fraction=valid_fraction,
                software_version=__version__,
            )

        except Exception as e:
            logger.exception(f"odc-stac composite pipeline encountered error: {e}")
            raise

    def _save_cached_composite(
        self,
        composite: CompositeResult,
        cache_dir: Path,
        params: dict[str, Any],
    ) -> None:
        """Persist composite bands and metadata to disk."""
        cache_dir.mkdir(parents=True, exist_ok=True)
        save_composite_to_geotiff(composite, cache_dir, prefix="cached")

        meta = {
            "params": params,
            "provenance": composite.to_provenance(),
        }
        with open(cache_dir / "provenance.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

    def _load_cached_composite(self, cache_dir: Path) -> CompositeResult | None:
        """Load composite from disk cache."""
        prov_file = cache_dir / "provenance.json"
        green_file = cache_dir / "cached_green.tif"
        swir1_file = cache_dir / "cached_swir1.tif"
        valid_file = cache_dir / "cached_valid_count.tif"

        if not (prov_file.exists() and green_file.exists() and swir1_file.exists()):
            return None

        with open(prov_file, encoding="utf-8") as f:
            meta = json.load(f)
        prov = meta.get("provenance", {})

        with rasterio.open(green_file) as src_g:
            green_arr = src_g.read(1)
            bounds = src_g.bounds
            res_x, res_y = src_g.res
            xs = np.linspace(bounds.left + res_x / 2.0, bounds.right - res_x / 2.0, src_g.width)
            ys = np.linspace(bounds.top - res_y / 2.0, bounds.bottom + res_y / 2.0, src_g.height)

        with rasterio.open(swir1_file) as src_s:
            swir1_arr = src_s.read(1)

        with rasterio.open(valid_file) as src_v:
            valid_arr = src_v.read(1)

        crs_str = prov.get("crs", "EPSG:4326")
        green_da = xr.DataArray(
            green_arr, coords={"y": ys, "x": xs}, dims=["y", "x"], attrs={"crs": crs_str}
        )
        swir1_da = xr.DataArray(
            swir1_arr, coords={"y": ys, "x": xs}, dims=["y", "x"], attrs={"crs": crs_str}
        )
        valid_da = xr.DataArray(
            valid_arr, coords={"y": ys, "x": xs}, dims=["y", "x"], attrs={"crs": crs_str}
        )

        date_tuple = tuple(prov.get("date_range", ["", ""]))
        dr = (str(date_tuple[0]), str(date_tuple[1])) if len(date_tuple) == 2 else ("", "")

        return CompositeResult(
            green=green_da,
            swir1=swir1_da,
            valid_count=valid_da,
            scene_ids=prov.get("scene_ids", []),
            date_range=dr,
            per_scene_cloud=prov.get("per_scene_cloud", []),
            bbox=prov.get("bbox", []),
            crs=crs_str,
            valid_fraction=float(prov.get("valid_fraction", 0.0)),
            software_version=prov.get("software_version", __version__),
        )


def save_composite_to_geotiff(
    composite: CompositeResult,
    output_dir: Path,
    prefix: str = "composite",
) -> dict[str, Path]:
    """Save composite bands (green, swir1, valid_count) as Cloud-Optimized GeoTIFFs."""
    output_dir.mkdir(parents=True, exist_ok=True)

    height, width = composite.green.shape
    xs = composite.green.coords["x"].values
    ys = composite.green.coords["y"].values

    res_x = float(abs(xs[1] - xs[0])) if len(xs) > 1 else 10.0
    res_y = float(abs(ys[1] - ys[0])) if len(ys) > 1 else 10.0

    top_left_x = float(xs[0] - res_x / 2.0)
    top_left_y = float(ys[0] + res_y / 2.0)

    transform = Affine.translation(top_left_x, top_left_y) @ Affine.scale(res_x, -res_y)

    out_paths: dict[str, Path] = {}

    # 1. Green band GeoTIFF
    p_green = output_dir / f"{prefix}_green.tif"
    with rasterio.open(
        p_green,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=np.float32,
        crs=composite.crs,
        transform=transform,
        nodata=np.nan,
        compress="deflate",
    ) as dst:
        dst.write(composite.green.values.astype(np.float32), 1)
    out_paths["green"] = p_green

    # 2. SWIR1 band GeoTIFF
    p_swir1 = output_dir / f"{prefix}_swir1.tif"
    with rasterio.open(
        p_swir1,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=np.float32,
        crs=composite.crs,
        transform=transform,
        nodata=np.nan,
        compress="deflate",
    ) as dst:
        dst.write(composite.swir1.values.astype(np.float32), 1)
    out_paths["swir1"] = p_swir1

    # 3. Valid observation count GeoTIFF
    p_valid = output_dir / f"{prefix}_valid_count.tif"
    with rasterio.open(
        p_valid,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=np.int16,
        crs=composite.crs,
        transform=transform,
        nodata=-1,
        compress="deflate",
    ) as dst:
        dst.write(composite.valid_count.values.astype(np.int16), 1)
    out_paths["valid_count"] = p_valid

    # 4. Provenance JSON
    p_prov = output_dir / f"{prefix}_provenance.json"
    with open(p_prov, "w", encoding="utf-8") as f:
        json.dump(composite.to_provenance(), f, indent=2)
    out_paths["provenance"] = p_prov

    return out_paths
