"""Evaluation harness for water mask segmentation against JRC Global Surface Water."""

import json
from pathlib import Path
from typing import Any

import numpy as np


def compute_binary_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """Calculate IoU, Precision, Recall, and F1 score for binary water masks."""
    tp = float(np.sum((y_true == 1) & (y_pred == 1)))
    fp = float(np.sum((y_true == 0) & (y_pred == 1)))
    fn = float(np.sum((y_true == 1) & (y_pred == 0)))

    iou = tp / (tp + fp + fn) if (tp + fp + fn) > 0 else 1.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "iou": round(iou, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def run_water_eval() -> dict[str, Any]:
    """Run water mask validation benchmark across 3 contrasting evaluation regions."""
    eval_dir = Path(__file__).parent
    regions = [
        {"name": "Raipur, CG", "type": "Inland Agricultural & Rivers", "season": "Post-Monsoon"},
        {"name": "Vembanad, KL", "type": "Coastal Backwaters & Wetlands", "season": "Post-Monsoon"},
        {"name": "Sambhar, RJ", "type": "Arid Saline Playa", "season": "Post-Monsoon"},
    ]

    results: list[dict[str, Any]] = []

    for reg in regions:
        # In Phase 5, live JRC GSW rasters and Sentinel-2 composites will be matched
        # Here we provide the validated metrics runner structure
        results.append(
            {
                "region": reg["name"],
                "characteristic": reg["type"],
                "season": reg["season"],
                "metrics": {
                    "status": "not_run",
                },
            }
        )

    summary = {"regions": results}
    out_file = eval_dir / "results" / "water_eval_results.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("Water Mask Evaluation Harness initialized.")
    return summary


if __name__ == "__main__":
    run_water_eval()
