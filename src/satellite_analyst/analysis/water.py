"""Water masking via adaptive thresholding, bimodality verification, and morphological filtering."""

from dataclasses import dataclass
from typing import Literal

import numpy as np
from scipy.ndimage import binary_fill_holes, binary_opening, label  # type: ignore[import-untyped]


@dataclass
class WaterMask:
    """Segmented binary water mask and associated diagnostic metadata."""

    mask: np.ndarray  # 2D boolean array: True = Water, False = Non-water
    valid_mask: np.ndarray  # 2D boolean array: True = Valid pixel, False = NaN / Nodata
    threshold: float  # Applied MNDWI threshold
    method: str  # "otsu" | "otsu_fallback_unimodal" | "manual_override" | "shared_otsu" | "shared_otsu_fallback"
    water_fraction: float  # Ratio of water pixels to valid pixels
    bimodality_metric: float  # Otsu between-class to total variance ratio eta in [0, 1]


def compute_otsu_threshold(
    values: np.ndarray,
    bimodality_min_ratio: float = 0.70,
    min_mean_separation: float = 0.25,
) -> tuple[float, bool, float]:
    """Compute optimal Otsu threshold for 1D float array of MNDWI values.

    Calculates Otsu between-class variance and verifies histogram bimodality via:
    1. Variance ratio eta = max(sigma_B^2) / sigma_T^2 (single Gaussian eta <= 0.65; bimodal >= 0.70)
    2. Class mean separation delta_mu = |mu2 - mu1| >= min_mean_separation

    Returns:
        tuple[float, bool, float]: (optimal_threshold, is_bimodal, eta_ratio)
    """
    valid = values[np.isfinite(values)]
    if len(valid) < 100:
        return 0.0, False, 0.0

    # Discretize into 256 bins between -1.0 and 1.0
    hist, bin_edges = np.histogram(valid, bins=256, range=(-1.0, 1.0))
    total_pixels = float(hist.sum())
    if total_pixels == 0.0:
        return 0.0, False, 0.0

    p = hist.astype(np.float64) / total_pixels
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2.0

    # Total mean and total variance
    mu_t = np.sum(p * bin_centers)
    sigma_t_sq = np.sum(p * ((bin_centers - mu_t) ** 2))

    if sigma_t_sq < 1e-10:
        return 0.0, False, 0.0

    # Cumulative probabilities and means
    omega1 = np.cumsum(p)
    omega2 = 1.0 - omega1

    cum_mu = np.cumsum(p * bin_centers)

    with np.errstate(divide="ignore", invalid="ignore"):
        mu1 = cum_mu / omega1
        mu2 = (mu_t - cum_mu) / omega2
        sigma_b_sq = omega1 * omega2 * ((mu1 - mu2) ** 2)

    sigma_b_sq = np.nan_to_num(sigma_b_sq, nan=0.0)
    max_idx = int(np.argmax(sigma_b_sq))
    max_sigma_b_sq = float(sigma_b_sq[max_idx])
    optimal_threshold = float(bin_centers[max_idx])

    # Bimodality separation ratio eta and mean separation
    eta = max_sigma_b_sq / sigma_t_sq
    delta_mu = float(abs(mu2[max_idx] - mu1[max_idx]))
    is_bimodal = bool(eta >= bimodality_min_ratio and delta_mu >= min_mean_separation)

    return optimal_threshold, is_bimodal, eta


def create_water_mask(
    mndwi: np.ndarray,
    threshold: float | None = None,
    fixed_fallback_threshold: float = 0.0,
    bimodality_min_ratio: float = 0.70,
    min_area_ha: float = 0.1,
    pixel_size_m: float = 10.0,
    apply_morphology: bool = True,
    fill_holes: bool = True,
) -> WaterMask:
    """Segment water bodies from MNDWI array with bimodality guard and morphological cleanup.

    Args:
        mndwi: 2D array of MNDWI surface reflectance index values [-1.0, 1.0]
        threshold: Explicit user-specified threshold override. If None, automated Otsu is run.
        fixed_fallback_threshold: Threshold to use when distribution is unimodal (default 0.0).
        bimodality_min_ratio: Minimum Otsu separation ratio eta required to accept adaptive threshold.
        min_area_ha: Minimum contiguous waterbody area in hectares to retain (default 0.1 ha).
        pixel_size_m: Spatial resolution in meters per pixel (default 10.0 m for Sentinel-2).
        apply_morphology: Whether to execute morphological opening and size filtering.
        fill_holes: Whether to fill interior isolated holes within detected water bodies.

    Returns:
        WaterMask: Typed segmentation object containing mask array and audit metadata.
    """
    valid_mask = np.isfinite(mndwi)
    valid_pixels = mndwi[valid_mask]

    if len(valid_pixels) == 0:
        return WaterMask(
            mask=np.zeros(mndwi.shape, dtype=bool),
            valid_mask=valid_mask,
            threshold=fixed_fallback_threshold,
            method="no_valid_data",
            water_fraction=0.0,
            bimodality_metric=0.0,
        )

    # 1. Determine threshold & method
    if threshold is not None:
        applied_threshold = float(threshold)
        method = "manual_override"
        eta = 1.0
    else:
        otsu_val, is_bimodal, eta = compute_otsu_threshold(
            valid_pixels, bimodality_min_ratio=bimodality_min_ratio
        )
        if is_bimodal:
            applied_threshold = otsu_val
            method = "otsu"
        else:
            applied_threshold = fixed_fallback_threshold
            method = "otsu_fallback_unimodal"

    # 2. Raw binary segmentation
    binary_mask = (mndwi > applied_threshold) & valid_mask

    # 3. Morphological filtering
    cleaned = binary_mask.copy()
    if apply_morphology and np.any(cleaned):
        # 3x3 structural element for morphological opening (removes 1-2 px salt noise)
        struct = np.ones((3, 3), dtype=bool)
        cleaned = binary_opening(cleaned, structure=struct)

        # Fill interior micro-holes within solid water bodies
        if fill_holes:
            cleaned = binary_fill_holes(cleaned)

        # Filter blobs below min_area_ha
        min_pixels = int(np.ceil((min_area_ha * 10000.0) / (pixel_size_m**2)))
        if min_pixels > 1:
            labeled_arr, num_features = label(cleaned)
            if num_features > 0:
                component_sizes = np.bincount(labeled_arr.ravel())
                too_small = component_sizes < min_pixels
                cleaned[too_small[labeled_arr]] = False

    # Mask must strictly be False wherever valid_mask is False
    cleaned = cleaned & valid_mask

    valid_count = int(np.sum(valid_mask))
    water_count = int(np.sum(cleaned))
    water_fraction = (water_count / valid_count) if valid_count > 0 else 0.0

    return WaterMask(
        mask=cleaned.astype(bool),
        valid_mask=valid_mask,
        threshold=applied_threshold,
        method=method,
        water_fraction=float(water_fraction),
        bimodality_metric=float(eta),
    )


def segment_dual_period_water(
    mndwi_a: np.ndarray,
    mndwi_b: np.ndarray,
    policy: Literal["shared", "per_period"] = "shared",
    override_threshold: float | None = None,
    fixed_fallback_threshold: float = 0.0,
    bimodality_min_ratio: float = 0.70,
    min_area_ha: float = 0.1,
    pixel_size_m: float = 10.0,
) -> tuple[WaterMask, WaterMask]:
    """Segment water for both baseline (A) and comparison (B) periods under a consistent threshold policy.

    Using policy='shared' (the default) pools valid MNDWI observations from both periods
    to derive a single shared threshold. This eliminates threshold-induced false change
    where identical MNDWI values would flip classification between years due to independent splits.
    """
    if policy == "shared" and override_threshold is None:
        valid_a = mndwi_a[np.isfinite(mndwi_a)]
        valid_b = mndwi_b[np.isfinite(mndwi_b)]
        pooled = (
            np.concatenate([valid_a, valid_b])
            if len(valid_a) and len(valid_b)
            else (valid_a if len(valid_a) else valid_b)
        )

        otsu_val, is_bimodal, eta = compute_otsu_threshold(
            pooled, bimodality_min_ratio=bimodality_min_ratio
        )
        if is_bimodal:
            shared_thresh = otsu_val
            shared_method = "shared_otsu"
        else:
            shared_thresh = fixed_fallback_threshold
            shared_method = "shared_otsu_fallback"

        mask_a = create_water_mask(
            mndwi_a,
            threshold=shared_thresh,
            min_area_ha=min_area_ha,
            pixel_size_m=pixel_size_m,
        )
        mask_b = create_water_mask(
            mndwi_b,
            threshold=shared_thresh,
            min_area_ha=min_area_ha,
            pixel_size_m=pixel_size_m,
        )
        mask_a.method = shared_method
        mask_a.bimodality_metric = float(eta)
        mask_b.method = shared_method
        mask_b.bimodality_metric = float(eta)
        return mask_a, mask_b

    # Otherwise: per_period or user override
    mask_a = create_water_mask(
        mndwi_a,
        threshold=override_threshold,
        fixed_fallback_threshold=fixed_fallback_threshold,
        bimodality_min_ratio=bimodality_min_ratio,
        min_area_ha=min_area_ha,
        pixel_size_m=pixel_size_m,
    )
    mask_b = create_water_mask(
        mndwi_b,
        threshold=override_threshold,
        fixed_fallback_threshold=fixed_fallback_threshold,
        bimodality_min_ratio=bimodality_min_ratio,
        min_area_ha=min_area_ha,
        pixel_size_m=pixel_size_m,
    )
    return mask_a, mask_b
