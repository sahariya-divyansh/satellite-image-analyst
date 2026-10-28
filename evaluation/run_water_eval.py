"""Evaluation harness validating Sentinel-2 water masks against JRC Global Surface Water.

Reference:
    Pekel, J.-F., Cottam, A., Gorelick, N., Belward, A. S. (2016).
    High-resolution mapping of global surface water and its long-term changes.
    Nature 540, 418-422. https://doi.org/10.1038/nature20584

Methodological Ground Rules:
    1. Agreement vs. Accuracy: Disagreements with JRC GSW reflect sensor resolution
       differences (Landsat 30m vs. Sentinel-2 10m), acquisition date offsets, and
       seasonal phenology. We report 'agreement with JRC GSW', never 'accuracy'.
    2. Spatial Aggregation: 10m Sentinel-2 water masks are aggregated to the 30m JRC
       grid using a 50% majority rule (water if >= 5 of 9 sub-pixels are water).
    3. Boundary Buffer Exclusion: A 1-pixel boundary zone around water edges is
       optionally masked to quantify and remove boundary co-registration penalties.
    4. Stratification: Agreement metrics are stratified by water body area
       (<1 ha, 1-10 ha, >10 ha).
    5. Uncertainty: 95% confidence intervals are computed via spatial block-bootstrapping
       to account for spatial autocorrelation.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import planetary_computer
import pystac_client
import rasterio  # type: ignore[import-untyped]
from rasterio.enums import Resampling  # type: ignore[import-untyped]
from rasterio.windows import from_bounds  # type: ignore[import-untyped]
from scipy.ndimage import binary_dilation, label  # type: ignore[import-untyped]

from satellite_analyst.analysis.indices import compute_mndwi
from satellite_analyst.analysis.water import compute_otsu_threshold, create_water_mask
from satellite_analyst.data.composites import CompositeBuilder
from satellite_analyst.planner.schema import BoundingBox, TimeInterval

# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class ValidationMetrics:
    """Agreement metrics between prediction and reference binary masks."""

    iou: float
    precision: float
    recall: float
    f1: float
    tp_pixels: int
    fp_pixels: int
    fn_pixels: int
    tn_pixels: int
    water_pixels_ref: int
    water_pixels_pred: int
    total_valid_pixels: int

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return asdict(self)


# ---------------------------------------------------------------------------
# Pure Metric Functions
# ---------------------------------------------------------------------------


def aggregate_10m_to_30m(
    mask_10m: np.ndarray,
    threshold_fraction: float = 0.5,
) -> np.ndarray:
    """Aggregate a 10m binary mask to a 30m grid using majority rule.

    Each 3x3 block of 10m pixels forms one 30m pixel.
    A 30m pixel is classified as True (water) if the fraction of active
    10m sub-pixels is >= threshold_fraction (e.g. >= 5 of 9 for 0.5).

    Args:
        mask_10m: 2D boolean or uint8 array with dimensions divisible by 3.
        threshold_fraction: Fraction of sub-pixels required to mark water.

    Returns:
        np.ndarray: 2D boolean array on 30m grid.
    """
    h, w = mask_10m.shape
    h_trim = h - (h % 3)
    w_trim = w - (w % 3)
    trimmed = mask_10m[:h_trim, :w_trim].astype(np.float32)

    blocks = trimmed.reshape(h_trim // 3, 3, w_trim // 3, 3)
    subpixel_mean = blocks.mean(axis=(1, 3))
    return np.asarray(subpixel_mean >= threshold_fraction, dtype=bool)


def extract_water_edge_boundary(
    water_mask: np.ndarray,
    width_px: int = 1,
) -> np.ndarray:
    """Extract a 1-pixel boundary transition band around water edges."""
    struct = np.ones((3, 3), dtype=bool)
    dilated = binary_dilation(water_mask, structure=struct, iterations=width_px)
    eroded = ~binary_dilation(~water_mask, structure=struct, iterations=width_px)
    return np.asarray(dilated ^ eroded, dtype=bool)


def compute_binary_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    valid_mask: np.ndarray | None = None,
) -> ValidationMetrics:
    """Calculate IoU, Precision, Recall, and F1 score for binary water masks."""
    if valid_mask is not None:
        t = y_true[valid_mask] > 0
        p = y_pred[valid_mask] > 0
    else:
        t = y_true.flatten() > 0
        p = y_pred.flatten() > 0

    tp = int(np.sum(t & p))
    fp = int(np.sum(~t & p))
    fn = int(np.sum(t & ~p))
    tn = int(np.sum(~t & ~p))

    denom_iou = tp + fp + fn
    iou = (
        float(tp / denom_iou)
        if denom_iou > 0
        else (1.0 if (tp == 0 and fp == 0 and fn == 0) else 0.0)
    )

    denom_prec = tp + fp
    precision = float(tp / denom_prec) if denom_prec > 0 else (1.0 if tp == 0 and fp == 0 else 0.0)

    denom_rec = tp + fn
    recall = float(tp / denom_rec) if denom_rec > 0 else (1.0 if tp == 0 and fn == 0 else 0.0)

    denom_f1 = precision + recall
    f1 = float(2 * precision * recall / denom_f1) if denom_f1 > 0 else 0.0

    return ValidationMetrics(
        iou=round(iou, 4),
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        tp_pixels=tp,
        fp_pixels=fp,
        fn_pixels=fn,
        tn_pixels=tn,
        water_pixels_ref=int(np.sum(t)),
        water_pixels_pred=int(np.sum(p)),
        total_valid_pixels=len(t),
    )


def compute_block_bootstrap_ci(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    valid_mask: np.ndarray | None = None,
    block_size: int = 10,
    n_bootstraps: int = 200,
    random_state: int = 42,
) -> dict[str, tuple[float, float]]:
    """Compute 95% confidence intervals for IoU and F1 via spatial block-bootstrap."""
    rng = np.random.default_rng(random_state)
    h, w = y_true.shape
    h_blocks = max(1, h // block_size)
    w_blocks = max(1, w // block_size)

    blocks_true: list[np.ndarray] = []
    blocks_pred: list[np.ndarray] = []
    blocks_valid: list[np.ndarray] = []

    for r in range(h_blocks):
        r_start = r * block_size
        r_end = h if r == h_blocks - 1 else (r + 1) * block_size
        for c in range(w_blocks):
            c_start = c * block_size
            c_end = w if c == w_blocks - 1 else (c + 1) * block_size
            blocks_true.append(y_true[r_start:r_end, c_start:c_end].flatten())
            blocks_pred.append(y_pred[r_start:r_end, c_start:c_end].flatten())
            if valid_mask is not None:
                blocks_valid.append(valid_mask[r_start:r_end, c_start:c_end].flatten())

    n_total_blocks = len(blocks_true)
    ious: list[float] = []
    f1s: list[float] = []

    for _ in range(n_bootstraps):
        idx = rng.integers(0, n_total_blocks, size=n_total_blocks)
        sample_t = np.concatenate([blocks_true[i] for i in idx])
        sample_p = np.concatenate([blocks_pred[i] for i in idx])
        sample_v = (
            np.concatenate([blocks_valid[i] for i in idx]) if valid_mask is not None else None
        )

        m = compute_binary_metrics(sample_t, sample_p, valid_mask=sample_v)
        ious.append(m.iou)
        f1s.append(m.f1)

    ci_iou = (float(np.percentile(ious, 2.5)), float(np.percentile(ious, 97.5)))
    ci_f1 = (float(np.percentile(f1s, 2.5)), float(np.percentile(f1s, 97.5)))

    return {
        "iou_ci_95": (round(ci_iou[0], 4), round(ci_iou[1], 4)),
        "f1_ci_95": (round(ci_f1[0], 4), round(ci_f1[1], 4)),
    }


def stratify_by_waterbody_size(
    water_mask_pred: np.ndarray,
    y_true: np.ndarray,
    pixel_size_m: float = 30.0,
) -> dict[str, dict[str, float]]:
    """Compute agreement metrics stratified by water body size in reference mask."""
    pixel_ha = (pixel_size_m**2) / 10000.0
    struct = np.ones((3, 3), dtype=np.uint8)
    labeled, n_features = label(y_true.astype(np.uint8), structure=struct)

    if n_features == 0:
        return {}

    counts = np.bincount(labeled.flatten())
    areas_ha = counts * pixel_ha

    small_mask = np.zeros_like(y_true, dtype=bool)
    med_mask = np.zeros_like(y_true, dtype=bool)
    large_mask = np.zeros_like(y_true, dtype=bool)

    for cid in range(1, n_features + 1):
        a = areas_ha[cid]
        if a < 1.0:
            small_mask[labeled == cid] = True
        elif a <= 10.0:
            med_mask[labeled == cid] = True
        else:
            large_mask[labeled == cid] = True

    results: dict[str, dict[str, float]] = {}
    for name, smask in [
        ("< 1 ha", small_mask),
        ("1-10 ha", med_mask),
        ("> 10 ha", large_mask),
    ]:
        if np.any(smask):
            m = compute_binary_metrics(smask.astype(np.uint8), water_mask_pred.astype(np.uint8))
            results[name] = {
                "iou": m.iou,
                "precision": m.precision,
                "recall": m.recall,
                "f1": m.f1,
                "ref_pixels": m.water_pixels_ref,
            }
        else:
            results[name] = {
                "iou": 0.0,
                "precision": 0.0,
                "recall": 0.0,
                "f1": 0.0,
                "ref_pixels": 0,
            }

    return results


# ---------------------------------------------------------------------------
# Evaluation Pipeline Runner
# ---------------------------------------------------------------------------

EVALUATION_AOIS: list[dict[str, Any]] = [
    {
        "id": "raipur",
        "name": "Raipur, Chhattisgarh",
        "hydrological_regime": "Inland alluvial plains & agricultural dendritic drainage",
        "centroid": [21.2381, 81.6337],
        "radius_km": 15.0,
    },
    {
        "id": "bhopal",
        "name": "Bhopal, Madhya Pradesh",
        "hydrological_regime": "Lake-heavy urban & peri-urban plateau (Bhojtal / Halali)",
        "centroid": [23.2599, 77.4126],
        "radius_km": 15.0,
    },
    {
        "id": "jodhpur",
        "name": "Jodhpur, Rajasthan",
        "hydrological_regime": "Arid desert fringe with small ephemeral impoundments (Kaylana)",
        "centroid": [26.2894, 73.0243],
        "radius_km": 15.0,
    },
]


def bbox_from_centroid(lat: float, lon: float, radius_km: float = 15.0) -> BoundingBox:
    """Calculate geographic bounding box from centroid and radius."""
    lat_deg = radius_km / 111.0
    lon_deg = radius_km / (111.0 * math.cos(math.radians(lat)))
    return BoundingBox(
        min_lon=lon - lon_deg,
        min_lat=lat - lat_deg,
        max_lon=lon + lon_deg,
        max_lat=lat + lat_deg,
    )


def fetch_jrc_occurrence_raster(
    bbox: BoundingBox,
    target_shape: tuple[int, int],
) -> np.ndarray:
    """Fetch JRC GSW Water Occurrence raster directly from Planetary Computer COG."""
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


def run_water_eval() -> dict[str, Any]:
    """Execute water mask validation benchmark against JRC Global Surface Water."""
    eval_dir = Path(__file__).parent
    results_dir = eval_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    print("\n================ JRC GLOBAL SURFACE WATER VALIDATION ================")
    print(" Reference Dataset: JRC GSW Water Occurrence (Pekel et al. Nature 2016)")
    print(" Source Access:     Microsoft Planetary Computer STAC ('jrc-gsw')")
    print(" Target Period:     Post-Monsoon (October-November) 2020")
    print(" Spatial Scheme:    Sentinel-2 10m aggregated to Landsat 30m (50% majority)")
    print(" Boundary Filter:   1-pixel transition band evaluated with and without")
    print(" Metric Rule:       Reported strictly as 'agreement with JRC GSW'")
    print("======================================================================\n")

    builder = CompositeBuilder()
    aoi_results: list[dict[str, Any]] = []

    for aoi in EVALUATION_AOIS:
        aoi_id = str(aoi["id"])
        aoi_name = str(aoi["name"])
        regime = str(aoi["hydrological_regime"])
        centroid_raw = aoi["centroid"]
        assert isinstance(centroid_raw, list)
        lat = float(centroid_raw[0])
        lon = float(centroid_raw[1])
        radius = float(aoi["radius_km"])

        print(f"[*] Processing AOI: {aoi_name} ({regime})...")
        bbox = bbox_from_centroid(lat, lon, radius)

        # 1. Build Sentinel-2 10m composite for Post-Monsoon 2020
        t_range = TimeInterval(
            start_date=date(2020, 10, 1),
            end_date=date(2020, 11, 30),
            label="Post-Monsoon 2020",
        )
        comp = builder.build_composite(
            bbox=bbox,
            time_range=t_range,
            max_cloud_cover=25.0,
            min_valid_obs=2,
        )

        green = comp.green.values
        swir1 = comp.swir1.values
        valid_obs = comp.valid_count.values >= 2
        mndwi = np.where(valid_obs, compute_mndwi(green, swir1), np.nan)

        # Candidate thresholds
        thresholds = [0.0, 0.05, -0.05]
        otsu_val, is_bimodal, _ = compute_otsu_threshold(mndwi[valid_obs])
        if is_bimodal:
            thresholds.append(round(otsu_val, 2))

        # Main evaluation uses default threshold = 0.0
        mask_10m = create_water_mask(
            mndwi=mndwi, threshold=0.0, min_area_ha=0.1, pixel_size_m=10.0
        ).mask
        mask_30m = aggregate_10m_to_30m(mask_10m, threshold_fraction=5 / 9)

        # 2. Fetch JRC GSW occurrence raster
        jrc_raw = fetch_jrc_occurrence_raster(bbox, mask_30m.shape)

        # JRC occurrence: 0-100%, 255 = no data
        jrc_valid = (jrc_raw <= 100) & (jrc_raw >= 0)
        jrc_perm = (jrc_raw >= 50) & jrc_valid  # Permanent water (>= 50% occurrence)
        jrc_seasonal = (jrc_raw >= 10) & jrc_valid  # Seasonal + Permanent (>= 10% occurrence)

        # 3. Metrics calculation
        # Baseline: All pixels vs Permanent Water
        m_perm_all = compute_binary_metrics(jrc_perm, mask_30m, valid_mask=jrc_valid)

        # Boundary-excluded
        edge_perm = extract_water_edge_boundary(jrc_perm, width_px=1)
        m_perm_interior = compute_binary_metrics(
            jrc_perm, mask_30m, valid_mask=(jrc_valid & ~edge_perm)
        )

        # Agreement vs Seasonal Water (>= 10%)
        m_seasonal_all = compute_binary_metrics(jrc_seasonal, mask_30m, valid_mask=jrc_valid)

        # Block-bootstrap CIs
        boot_ci = compute_block_bootstrap_ci(
            jrc_perm, mask_30m, valid_mask=jrc_valid, block_size=10, n_bootstraps=200
        )

        # Size strata
        strata = stratify_by_waterbody_size(mask_30m, jrc_perm, pixel_size_m=30.0)

        # Threshold sensitivity comparison
        thresh_comparison: dict[str, dict[str, float]] = {}
        for t_val in thresholds:
            t_mask_10m = create_water_mask(
                mndwi=mndwi, threshold=t_val, min_area_ha=0.1, pixel_size_m=10.0
            ).mask
            t_mask_30m = aggregate_10m_to_30m(t_mask_10m, threshold_fraction=5 / 9)
            m_t = compute_binary_metrics(jrc_perm, t_mask_30m, valid_mask=jrc_valid)
            thresh_comparison[f"MNDWI > {t_val}"] = {
                "iou": m_t.iou,
                "precision": m_t.precision,
                "recall": m_t.recall,
                "f1": m_t.f1,
            }

        rec = {
            "aoi_id": aoi_id,
            "aoi_name": aoi_name,
            "hydrological_regime": regime,
            "scenes_used": len(comp.scene_ids),
            "pred_water_pixels_30m": int(np.sum(mask_30m)),
            "ref_permanent_pixels_30m": int(np.sum(jrc_perm)),
            "ref_seasonal_pixels_30m": int(np.sum(jrc_seasonal)),
            "agreement_permanent_water": {
                "all_pixels": m_perm_all.to_dict(),
                "boundary_excluded": m_perm_interior.to_dict(),
                "block_bootstrap_ci_95": boot_ci,
                "size_strata": strata,
            },
            "agreement_seasonal_water_ge10": m_seasonal_all.to_dict(),
            "threshold_sensitivity": thresh_comparison,
        }
        aoi_results.append(rec)
        print(
            f"  [+] {aoi_name} evaluated | Perm Water IoU: {m_perm_all.iou:.4f} (F1: {m_perm_all.f1:.4f}) | "
            f"Seasonal Water IoU: {m_seasonal_all.iou:.4f} (F1: {m_seasonal_all.f1:.4f})"
        )

    summary: dict[str, Any] = {
        "status": "completed",
        "methodology": {
            "reference_dataset": "JRC Global Surface Water Occurrence v1.3",
            "citation": "Pekel et al., Nature 540, 418-422 (2016)",
            "validation_period": "Post-Monsoon (Oct 1 - Nov 30) 2020",
            "spatial_aggregation": "10m to 30m grid with 50% majority rule (5 of 9 subpixels)",
            "boundary_exclusion": "1-pixel transition band evaluated with and without",
            "stratification": "Size categories (<1 ha, 1-10 ha, >10 ha)",
            "uncertainty": "Block-bootstrap 95% confidence intervals (10x10 px blocks, B=200)",
            "reporting_standard": "Reported strictly as 'agreement with JRC GSW', never 'accuracy'",
            "seasonal_ephemeral_note": (
                "Post-monsoon composite observes surface water directly after seasonal rains. "
                "Agreement with JRC permanent water (occurrence >= 50%) is inherently constrained "
                "by seasonal and ephemeral water bodies that naturally recede during dry months."
            ),
        },
        "aois": aoi_results,
    }

    out_file = results_dir / "water_eval_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\n[+] Validation completed for all {len(aoi_results)} AOIs.")
    print(f"    Summary results saved to: {out_file}\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run JRC GSW water mask validation.")
    parser.parse_args()
    run_water_eval()
