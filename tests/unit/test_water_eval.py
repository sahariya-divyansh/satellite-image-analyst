"""Unit tests for water mask validation metrics, aggregation, boundary exclusion, and CIs."""

import numpy as np
import pytest

from evaluation.eval_point_sample import wilson_score_interval
from evaluation.run_water_eval import (
    aggregate_10m_to_30m,
    compute_binary_metrics,
    compute_block_bootstrap_ci,
    extract_water_edge_boundary,
    stratify_by_waterbody_size,
)


def test_compute_binary_metrics_known_confusion_matrix() -> None:
    """Verify IoU, Precision, Recall, and F1 on known confusion matrix values."""
    # 10 pixels:
    # 4 True Positive (1, 1)
    # 2 False Positive (0, 1)
    # 1 False Negative (1, 0)
    # 3 True Negative (0, 0)
    y_true = np.array([1, 1, 1, 1, 0, 0, 1, 0, 0, 0], dtype=np.uint8)
    y_pred = np.array([1, 1, 1, 1, 1, 1, 0, 0, 0, 0], dtype=np.uint8)

    m = compute_binary_metrics(y_true, y_pred)

    assert m.tp_pixels == 4
    assert m.fp_pixels == 2
    assert m.fn_pixels == 1
    assert m.tn_pixels == 3

    # TP / (TP + FP + FN) = 4 / (4 + 2 + 1) = 4/7 ~ 0.5714
    assert m.iou == round(4.0 / 7.0, 4)
    # TP / (TP + FP) = 4 / 6 ~ 0.6667
    assert m.precision == round(4.0 / 6.0, 4)
    # TP / (TP + FN) = 4 / 5 = 0.8000
    assert m.recall == 0.8000
    # 2 * P * R / (P + R) = 2 * (4/6) * (4/5) / (4/6 + 4/5) = 8/11 ~ 0.7273
    assert m.f1 == round(8.0 / 11.0, 4)


def test_aggregate_10m_to_30m_majority_rule() -> None:
    """Verify 3x3 block aggregation with 50% majority threshold."""
    # 6x6 10m grid -> 2x2 30m grid
    mask_10m = np.zeros((6, 6), dtype=bool)

    # Block 0,0: 5 active sub-pixels (>= 50% of 9) -> True
    mask_10m[0:3, 0:2] = True
    mask_10m[2, 2] = False  # 6 - 1 = 5 True

    # Block 0,1: 4 active sub-pixels (< 50% of 9) -> False
    mask_10m[0:2, 3:5] = True  # 4 True

    # Block 1,0: 0 active sub-pixels -> False
    # (remains all False)

    # Block 1,1: 9 active sub-pixels (100%) -> True
    mask_10m[3:6, 3:6] = True

    agg_30m = aggregate_10m_to_30m(mask_10m, threshold_fraction=0.5)

    assert agg_30m.shape == (2, 2)
    assert agg_30m[0, 0] is np.True_  # 5 of 9
    assert agg_30m[0, 1] is np.False_  # 4 of 9
    assert agg_30m[1, 0] is np.False_  # 0 of 9
    assert agg_30m[1, 1] is np.True_  # 9 of 9


def test_extract_water_edge_boundary() -> None:
    """Verify extraction of 1-pixel morphological transition boundary."""
    grid = np.zeros((10, 10), dtype=bool)
    # Center 4x4 square of water: rows 3:7, cols 3:7
    grid[3:7, 3:7] = True

    boundary = extract_water_edge_boundary(grid, width_px=1)

    # The outer boundary ring (rows 2, 7 and cols 2, 7 around the water)
    # and inner perimeter should be captured
    assert np.any(boundary)
    # Center interior water (4,4) should NOT be in the 1-pixel boundary
    assert boundary[4, 4] is np.False_
    assert boundary[5, 5] is np.False_
    # Edge pixels should be True
    assert boundary[2, 3] is np.True_
    assert boundary[3, 3] is np.True_


def test_compute_block_bootstrap_ci() -> None:
    """Verify block bootstrap produces sensible 95% confidence bounds."""
    rng = np.random.default_rng(12345)
    y_true = rng.choice([0, 1], size=(40, 40), p=[0.8, 0.2]).astype(np.uint8)
    # Create prediction with ~80% correlation
    noise = rng.choice([0, 1], size=(40, 40), p=[0.9, 0.1]).astype(np.uint8)
    y_pred = y_true ^ noise

    base_metrics = compute_binary_metrics(y_true, y_pred)
    ci = compute_block_bootstrap_ci(
        y_true, y_pred, block_size=10, n_bootstraps=200, random_state=42
    )

    iou_low, iou_high = ci["iou_ci_95"]
    f1_low, f1_high = ci["f1_ci_95"]

    assert iou_low <= base_metrics.iou <= iou_high
    assert f1_low <= base_metrics.f1 <= f1_high
    assert 0.0 <= iou_low < iou_high <= 1.0


def test_stratify_by_waterbody_size() -> None:
    """Verify size stratification into <1ha, 1-10ha, and >10ha bins."""
    grid_true = np.zeros((100, 100), dtype=np.uint8)
    # 30m pixel = 900 m² = 0.09 ha
    # Body 1: 5 pixels * 0.09 ha = 0.45 ha (< 1 ha)
    grid_true[5:10, 5] = 1

    # Body 2: 50 pixels * 0.09 ha = 4.5 ha (1-10 ha)
    grid_true[20:25, 20:30] = 1

    # Body 3: 200 pixels * 0.09 ha = 18.0 ha (> 10 ha)
    grid_true[50:60, 50:70] = 1

    grid_pred = grid_true.copy()
    # Add a small false positive
    grid_pred[90:92, 90:92] = 1

    strat = stratify_by_waterbody_size(grid_pred, grid_true, pixel_size_m=30.0)

    assert "< 1 ha" in strat
    assert "1-10 ha" in strat
    assert "> 10 ha" in strat

    assert strat["< 1 ha"]["ref_pixels"] == 5
    assert strat["1-10 ha"]["ref_pixels"] == 50
    assert strat["> 10 ha"]["ref_pixels"] == 200
    assert strat["> 10 ha"]["recall"] == 1.0


def test_wilson_score_interval() -> None:
    """Verify Wilson score confidence interval calculation."""
    # 0 out of 10
    low_0, high_0 = wilson_score_interval(0, 10)
    assert low_0 == 0.0
    assert 0.0 < high_0 < 0.35

    # 10 out of 10
    low_10, high_10 = wilson_score_interval(10, 10)
    assert 0.65 < low_10 < 1.0
    assert high_10 == 1.0

    # 50 out of 100 (symmetric around 0.5)
    low_50, high_50 = wilson_score_interval(50, 100)
    assert pytest.approx(0.5 - low_50, abs=1e-3) == high_50 - 0.5
