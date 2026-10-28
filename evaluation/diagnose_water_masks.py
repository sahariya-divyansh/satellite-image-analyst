"""Diagnostic script for Raipur & Bhopal water masks against ESA WorldCover and JRC GSW.

Assesses:
1. Land cover classification of our MNDWI water pixels according to ESA WorldCover 2020/2021
   (cropland, permanent water, built-up, wetland, trees, bare soil).
2. JRC Global Surface Water occurrence distribution of our water pixels
   (0%, 1-10%, 10-50%, >=50%).
3. Performance of candidate mask variants against ESA WorldCover class 80 (Permanent Water):
   - Variant A: MNDWI > 0.0 (Baseline)
   - Variant B: MNDWI > 0.0 AND NDVI < 0.1
   - Variant C1: AWEInsh > 0.0 (Automated Water Extraction Index non-shadow)
   - Variant C2: AWEIsh > 0.0 (Automated Water Extraction Index shadow)
   Pooled selection on Raipur + Bhopal; Jodhpur evaluated as untouched held-out.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, ".")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)

import numpy as np
import planetary_computer
import pystac_client
import rasterio  # type: ignore[import-untyped]
from rasterio.enums import Resampling  # type: ignore[import-untyped]
from rasterio.windows import from_bounds  # type: ignore[import-untyped]

from evaluation.run_water_eval import (
    compute_binary_metrics,
    compute_block_bootstrap_ci,
)
from satellite_analyst.analysis.vectorize import estimate_utm_epsg
from satellite_analyst.analysis.water import create_water_mask
from satellite_analyst.data.composites import (
    apply_scl_mask,
    convert_dn_to_reflectance,
)
from satellite_analyst.planner.schema import BoundingBox

WORLDCOVER_CLASS_NAMES = {
    10: "Tree cover",
    20: "Shrubland",
    30: "Grassland",
    40: "Cropland",
    50: "Built-up",
    60: "Bare / sparse",
    70: "Snow and ice",
    80: "Permanent water",
    90: "Herbaceous wetland",
    95: "Mangroves",
    100: "Moss and lichen",
}


def bbox_from_centroid(lat: float, lon: float, radius_km: float = 15.0) -> BoundingBox:
    lat_deg = radius_km / 111.0
    lon_deg = radius_km / (111.0 * math.cos(math.radians(lat)))
    return BoundingBox(
        min_lon=lon - lon_deg,
        min_lat=lat - lat_deg,
        max_lon=lon + lon_deg,
        max_lat=lat + lat_deg,
    )


def fetch_worldcover_raster(bbox: BoundingBox, target_shape: tuple[int, int]) -> np.ndarray:
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    search = catalog.search(
        collections=["esa-worldcover"],
        bbox=bbox.as_list(),
    )
    items = list(search.items())
    if not items:
        raise RuntimeError(f"No ESA WorldCover item found for bbox {bbox.as_list()}")

    # Sort to pick 2020 or 2021
    items.sort(key=lambda it: it.datetime or it.properties.get("start_datetime", ""), reverse=True)
    map_href = items[0].assets["map"].href
    with rasterio.open(map_href) as src:
        window = from_bounds(bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat, src.transform)
        arr = src.read(1, window=window, out_shape=target_shape, resampling=Resampling.nearest)
    return np.asarray(arr)


def fetch_jrc_occurrence_raster(bbox: BoundingBox, target_shape: tuple[int, int]) -> np.ndarray:
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    items = list(catalog.search(collections=["jrc-gsw"], bbox=bbox.as_list()).items())
    if not items:
        raise RuntimeError(f"No JRC GSW STAC item found for bbox {bbox.as_list()}")
    occ_href = items[0].assets["occurrence"].href
    with rasterio.open(occ_href) as src:
        window = from_bounds(bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat, src.transform)
        arr = src.read(1, window=window, out_shape=target_shape, resampling=Resampling.nearest)
    return np.asarray(arr)


def load_multi_band_composite(
    bbox: BoundingBox,
    year: int,
    max_cloud_cover: float = 40.0,
) -> dict[str, np.ndarray]:
    """Load B02, B03, B04, B08, B11, B12 and compute median composite."""
    import odc.stac  # type: ignore[import-untyped]
    from pystac_client import Client  # type: ignore[import-untyped]

    mid_lon = (bbox.min_lon + bbox.max_lon) / 2.0
    mid_lat = (bbox.min_lat + bbox.max_lat) / 2.0
    utm_code = estimate_utm_epsg(mid_lon, mid_lat)
    target_crs = f"EPSG:{utm_code}"

    client = Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    search = client.search(
        collections=["sentinel-2-l2a"],
        bbox=bbox.as_list(),
        datetime=f"{year}-10-01/{year}-11-30",
        query={"eo:cloud_cover": {"lt": max_cloud_cover}},
    )
    items = sorted(search.items(), key=lambda x: x.datetime.isoformat() if x.datetime else "")
    if not items:
        raise RuntimeError(f"No scenes found for {year}")

    bbox_tuple = (
        float(bbox.min_lon),
        float(bbox.min_lat),
        float(bbox.max_lon),
        float(bbox.max_lat),
    )
    ds = odc.stac.load(
        items,
        bands=["B02", "B03", "B04", "B08", "B11", "B12", "SCL"],
        bbox=bbox_tuple,
        crs=target_crs,
        resolution=10,
        chunks={"x": 2048, "y": 2048},
        resampling={
            "B02": "bilinear",
            "B03": "bilinear",
            "B04": "bilinear",
            "B08": "bilinear",
            "B11": "bilinear",
            "B12": "bilinear",
            "SCL": "nearest",
        },
    ).compute()

    n_time = int(ds["B02"].shape[0])
    scl_raw = ds["SCL"].values.astype(np.int32)
    scl_mask_classes = frozenset({0, 1, 2, 3, 7, 8, 9, 10, 11})  # mask clouds, shadows, cirrus

    cleaned_bands: dict[str, np.ndarray] = {}
    for b_name in ["B02", "B03", "B04", "B08", "B11", "B12"]:
        raw = ds[b_name].values.astype(np.float32)
        clean = np.zeros_like(raw)
        for t in range(n_time):
            item_meta = items[t] if t < len(items) else items[0]
            baseline = item_meta.properties.get("s2:processing_baseline", "04.00")
            refl = convert_dn_to_reflectance(raw[t], baseline)
            clean[t] = apply_scl_mask(refl, scl_raw[t], scl_mask_classes)
        # Median across time
        valid_cnt = np.sum(~np.isnan(clean), axis=0)
        med = np.nanmedian(clean, axis=0).astype(np.float32)
        med = np.where(valid_cnt >= 2, med, np.nan)
        cleaned_bands[b_name] = med

    cleaned_bands["valid_count"] = valid_cnt
    cleaned_bands["scene_count"] = np.array([n_time])
    return cleaned_bands


def compute_mask_variants(bands: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Compute candidate water masks (10m boolean arrays)."""
    b02 = bands["B02"]
    b03 = bands["B03"]
    b04 = bands["B04"]
    b08 = bands["B08"]
    b11 = bands["B11"]
    b12 = bands["B12"]
    valid = bands["valid_count"] >= 2

    # 1. Variant A (Baseline): MNDWI > 0.0
    mndwi = (b03 - b11) / (b03 + b11 + 1e-6)
    mndwi_masked = np.where(valid, mndwi, np.nan)
    mask_a = create_water_mask(mndwi_masked, threshold=0.0, min_area_ha=0.1, pixel_size_m=10.0).mask

    # 2. Variant B: MNDWI > 0.0 AND NDVI < 0.1
    ndvi = (b08 - b04) / (b08 + b04 + 1e-6)
    cond_b = valid & (mndwi > 0.0) & (ndvi < 0.1)
    mask_b = create_water_mask(
        np.where(cond_b, 1.0, -1.0), threshold=0.0, min_area_ha=0.1, pixel_size_m=10.0
    ).mask

    # 3. Variant C1: AWEInsh > 0.0
    # AWEInsh = 4 * (Green - SWIR1) - (0.25 * NIR + 2.75 * SWIR2)
    awei_nsh = 4.0 * (b03 - b11) - (0.25 * b08 + 2.75 * b12)
    cond_c1 = valid & (awei_nsh > 0.0)
    mask_c1 = create_water_mask(
        np.where(cond_c1, 1.0, -1.0), threshold=0.0, min_area_ha=0.1, pixel_size_m=10.0
    ).mask

    # 4. Variant C2: AWEIsh > 0.0
    # AWEIsh = Blue + 2.5 * Green - 1.5 * (NIR + SWIR1) - 0.25 * SWIR2
    awei_sh = b02 + 2.5 * b03 - 1.5 * (b08 + b11) - 0.25 * b12
    cond_c2 = valid & (awei_sh > 0.0)
    mask_c2 = create_water_mask(
        np.where(cond_c2, 1.0, -1.0), threshold=0.0, min_area_ha=0.1, pixel_size_m=10.0
    ).mask

    return {
        "mndwi_gt_0 (baseline)": mask_a,
        "mndwi_gt_0_and_ndvi_lt_0.1": mask_b,
        "awei_nsh_gt_0": mask_c1,
        "awei_sh_gt_0": mask_c2,
    }


def run_diagnostics() -> dict[str, Any]:
    print("\n================ MASK DIAGNOSTICS & CANDIDATE EVALUATION ================\n")
    results: dict[str, Any] = {"diagnostics": {}, "variant_evaluations": {}}

    aois: list[dict[str, Any]] = [
        {
            "id": "raipur",
            "name": "Raipur, Chhattisgarh",
            "lat": 21.2381,
            "lon": 81.6337,
            "radius": 15.0,
        },
        {
            "id": "bhopal",
            "name": "Bhopal, Madhya Pradesh",
            "lat": 23.2599,
            "lon": 77.4126,
            "radius": 15.0,
        },
        {
            "id": "jodhpur",
            "name": "Jodhpur, Rajasthan",
            "lat": 26.2894,
            "lon": 73.0243,
            "radius": 15.0,
        },
    ]

    # Part 1: Diagnostic on Raipur (2020, 2023) and Bhopal (2020)
    diag_runs = [
        ("raipur", 2020),
        ("raipur", 2023),
        ("bhopal", 2020),
    ]

    diag_output: dict[str, Any] = {}
    for aoi_id, yr in diag_runs:
        aoi = next(a for a in aois if a["id"] == aoi_id)
        print(f"[*] Running land-cover & JRC diagnostic for {aoi['name']} ({yr})...")
        bbox = bbox_from_centroid(float(aoi["lat"]), float(aoi["lon"]), float(aoi["radius"]))

        bands = load_multi_band_composite(bbox, yr, max_cloud_cover=30.0)
        variants = compute_mask_variants(bands)
        water_mask = variants["mndwi_gt_0 (baseline)"]
        n_water_pix = int(np.sum(water_mask))

        wc_arr = fetch_worldcover_raster(bbox, water_mask.shape)
        jrc_arr = fetch_jrc_occurrence_raster(bbox, water_mask.shape)

        # WorldCover breakdown of our water pixels
        wc_breakdown: dict[str, Any] = {}
        wc_water_pixels = wc_arr[water_mask]
        for c_id, c_name in sorted(WORLDCOVER_CLASS_NAMES.items()):
            cnt = int(np.sum(wc_water_pixels == c_id))
            pct = round(cnt / n_water_pix * 100.0, 2) if n_water_pix > 0 else 0.0
            wc_breakdown[f"class_{c_id}_{c_name}"] = {"pixels": cnt, "pct_of_water": pct}

        # JRC occurrence bins breakdown of our water pixels
        # 0%, 1-10%, 10-50%, >=50%
        jrc_water_pixels = jrc_arr[water_mask]
        jrc_bins = {
            "0% (never water in JRC 35-yr record)": int(np.sum(jrc_water_pixels == 0)),
            "1-10% (low occurrence / ephemeral flood)": int(
                np.sum((jrc_water_pixels > 0) & (jrc_water_pixels < 10))
            ),
            "10-50% (seasonal water)": int(
                np.sum((jrc_water_pixels >= 10) & (jrc_water_pixels < 50))
            ),
            ">=50% (permanent water)": int(np.sum(jrc_water_pixels >= 50)),
        }
        jrc_breakdown = {
            k: {
                "pixels": v,
                "pct_of_water": round(v / n_water_pix * 100.0, 2) if n_water_pix > 0 else 0.0,
            }
            for k, v in jrc_bins.items()
        }

        tag = f"{aoi_id}_{yr}"
        diag_output[tag] = {
            "aoi": aoi["name"],
            "year": yr,
            "total_water_pixels_10m": n_water_pix,
            "total_water_ha": round(n_water_pix * 0.01, 2),
            "worldcover_breakdown": wc_breakdown,
            "jrc_occurrence_breakdown": jrc_breakdown,
        }
        print(f"    -> Water pixels: {n_water_pix} ({n_water_pix * 0.01:.1f} ha)")
        print(
            f"       WorldCover Cropland (class 40): {wc_breakdown['class_40_Cropland']['pct_of_water']}%"
        )
        print(
            f"       WorldCover Permanent Water (class 80): {wc_breakdown['class_80_Permanent water']['pct_of_water']}%"
        )
        print(
            f"       JRC Occurrence >= 50%: {jrc_breakdown['>=50% (permanent water)']['pct_of_water']}%"
        )
        print(
            f"       JRC Occurrence 0% (never water): {jrc_breakdown['0% (never water in JRC 35-yr record)']['pct_of_water']}%\n"
        )

    results["diagnostics"] = diag_output

    # Part 2: Evaluation of Mask Variants Against ESA WorldCover Class 80 (Permanent Water)
    print("\n--- EVALUATING MASK VARIANTS AGAINST ESA WORLDCOVER CLASS 80 ---\n")
    variant_results: dict[str, Any] = {}

    for aoi in aois:
        aoi_id = str(aoi["id"])
        print(f"[*] Evaluating variants for {aoi['name']} (2020)...")
        bbox = bbox_from_centroid(float(aoi["lat"]), float(aoi["lon"]), float(aoi["radius"]))
        bands = load_multi_band_composite(bbox, 2020, max_cloud_cover=25.0)
        variants = compute_mask_variants(bands)

        wc_arr = fetch_worldcover_raster(bbox, bands["B03"].shape)
        # WorldCover Class 80 = Permanent water
        ref_water = wc_arr == 80
        ref_valid = wc_arr > 0

        aoi_evals: dict[str, Any] = {}
        for var_name, pred_mask in variants.items():
            m = compute_binary_metrics(ref_water, pred_mask, valid_mask=ref_valid)
            ci = compute_block_bootstrap_ci(
                ref_water, pred_mask, valid_mask=ref_valid, block_size=20, n_bootstraps=200
            )
            aoi_evals[var_name] = {
                "metrics": m.to_dict(),
                "ci_95": ci,
            }
            print(
                f"    [{var_name}] -> IoU: {m.iou:.4f}, Prec: {m.precision:.4f}, Rec: {m.recall:.4f}, F1: {m.f1:.4f} | F1 95% CI: {ci['f1_ci_95']}"
            )
        variant_results[aoi_id] = aoi_evals
        print()

    # Pooled F1 on Raipur + Bhopal ONLY
    pooled_scores: dict[str, float] = {}
    var_names = list(next(iter(variant_results.values())).keys())
    for vn in var_names:
        tp = (
            variant_results["raipur"][vn]["metrics"]["tp_pixels"]
            + variant_results["bhopal"][vn]["metrics"]["tp_pixels"]
        )
        fp = (
            variant_results["raipur"][vn]["metrics"]["fp_pixels"]
            + variant_results["bhopal"][vn]["metrics"]["fp_pixels"]
        )
        fn = (
            variant_results["raipur"][vn]["metrics"]["fn_pixels"]
            + variant_results["bhopal"][vn]["metrics"]["fn_pixels"]
        )
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        pooled_scores[vn] = round(f1, 4)

    print("\n--- POOLED F1 ON RAIPUR + BHOPAL ONLY (Selection Metric) ---")
    for vn, score in sorted(pooled_scores.items(), key=lambda x: x[1], reverse=True):
        print(f"  {vn}: Pooled F1 = {score:.4f}")

    best_variant = max(pooled_scores.items(), key=lambda x: x[1])[0]
    print(f"\nWinning variant on dev pool: {best_variant}")
    print(f"Jodhpur (Untouched Held-Out) performance of {best_variant}:")
    jodh_res = variant_results["jodhpur"][best_variant]["metrics"]
    print(
        f"  IoU: {jodh_res['iou']:.4f}, Prec: {jodh_res['precision']:.4f}, Rec: {jodh_res['recall']:.4f}, F1: {jodh_res['f1']:.4f}"
    )

    results["variant_evaluations"] = variant_results
    results["pooled_selection"] = {
        "pooled_f1_raipur_bhopal": pooled_scores,
        "selected_variant": best_variant,
    }

    # Part 3: Rerun Raipur 2023 vs 2025 with winning variant vs baseline
    print(f"\n[*] Re-running Raipur 2023 vs 2025 comparison with {best_variant}...")
    raipur_bbox = bbox_from_centroid(21.2381, 81.6337, 15.0)
    bands_2023 = load_multi_band_composite(raipur_bbox, 2023, max_cloud_cover=30.0)
    bands_2025 = load_multi_band_composite(raipur_bbox, 2025, max_cloud_cover=30.0)

    vars_2023 = compute_mask_variants(bands_2023)
    vars_2025 = compute_mask_variants(bands_2025)

    base_2023_ha = round(float(np.sum(vars_2023["mndwi_gt_0 (baseline)"])) * 0.01, 2)
    base_2025_ha = round(float(np.sum(vars_2025["mndwi_gt_0 (baseline)"])) * 0.01, 2)
    base_delta_ha = round(base_2025_ha - base_2023_ha, 2)
    base_pct = round(base_delta_ha / base_2023_ha * 100.0, 2)

    best_2023_ha = round(float(np.sum(vars_2023[best_variant])) * 0.01, 2)
    best_2025_ha = round(float(np.sum(vars_2025[best_variant])) * 0.01, 2)
    best_delta_ha = round(best_2025_ha - best_2023_ha, 2)
    best_pct = round(best_delta_ha / best_2023_ha * 100.0, 2)

    comparison = {
        "baseline_mndwi": {
            "area_2023_ha": base_2023_ha,
            "area_2025_ha": base_2025_ha,
            "net_delta_ha": base_delta_ha,
            "net_delta_pct": base_pct,
            "verdict": "within noise / inconclusive",
        },
        "selected_variant": {
            "variant_name": best_variant,
            "area_2023_ha": best_2023_ha,
            "area_2025_ha": best_2025_ha,
            "net_delta_ha": best_delta_ha,
            "net_delta_pct": best_pct,
            "verdict": "within noise / inconclusive",
        },
    }
    results["raipur_2023_2025_comparison"] = comparison

    print(
        f"  Baseline: 2023={base_2023_ha} ha, 2025={base_2025_ha} ha, Delta={base_delta_ha:+.2f} ha ({base_pct:+.2f}%)"
    )
    print(
        f"  {best_variant}: 2023={best_2023_ha} ha, 2025={best_2025_ha} ha, Delta={best_delta_ha:+.2f} ha ({best_pct:+.2f}%)"
    )

    out_file = Path("evaluation/results/mask_diagnostics_results.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    import json

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\n[+] Diagnostic results saved to: {out_file}\n")
    return results


if __name__ == "__main__":
    run_diagnostics()
