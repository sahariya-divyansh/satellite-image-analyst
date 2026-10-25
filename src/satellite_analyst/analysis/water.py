"""Water masking via adaptive thresholding and morphological cleanup."""

import numpy as np


def compute_otsu_threshold(values: np.ndarray) -> float:
    """Compute optimal Otsu threshold for 1D float array of index values."""
    valid = values[np.isfinite(values)]
    if len(valid) == 0:
        return 0.0

    # Discretize into 256 bins between -1.0 and 1.0
    hist, bin_edges = np.histogram(valid, bins=256, range=(-1.0, 1.0))
    hist = hist.astype(np.float64) / (hist.sum() + 1e-12)

    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2.0
    weight1 = np.cumsum(hist)
    weight2 = 1.0 - weight1

    total_mean = np.sum(hist * bin_centers)
    cum_mean = np.cumsum(hist * bin_centers)

    mean1 = cum_mean / (weight1 + 1e-12)
    mean2 = (total_mean - cum_mean) / (weight2 + 1e-12)

    variance = weight1 * weight2 * ((mean1 - mean2) ** 2)
    idx = int(np.argmax(variance))
    return float(bin_centers[idx])


def create_water_mask(
    mndwi: np.ndarray,
    threshold: float | None = None,
    min_pixels: int = 10,
    apply_morphology: bool = True,
) -> tuple[np.ndarray, float]:
    """Segment water bodies from MNDWI array.

    Returns:
        tuple[np.ndarray, float]: Binary boolean mask (True=Water) and applied threshold.
    """
    if threshold is None:
        threshold = compute_otsu_threshold(mndwi)

    binary_mask = (mndwi > threshold) & np.isfinite(mndwi)

    if apply_morphology and np.any(binary_mask):
        try:
            from scipy.ndimage import binary_opening, label  # type: ignore[import-untyped]

            # 3x3 structuring element for noise reduction
            structure = np.ones((3, 3), dtype=bool)
            cleaned = binary_opening(binary_mask, structure=structure)

            # Filter small connected components below min_pixels
            labeled_array, num_features = label(cleaned)
            if num_features > 0:
                component_sizes = np.bincount(labeled_array.ravel())
                too_small = component_sizes < min_pixels
                too_small_mask = too_small[labeled_array]
                cleaned[too_small_mask] = False

            return cleaned.astype(bool), threshold
        except ImportError:
            # Fallback if scipy not yet available
            return binary_mask.astype(bool), threshold

    return binary_mask.astype(bool), threshold
