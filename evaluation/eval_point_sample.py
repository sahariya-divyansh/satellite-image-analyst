"""Evaluation harness for independent manual point-sample validation.

Reads evaluation/point_sample_template.csv and computes:
- Stratified Precision, Recall, Overall Accuracy
- 95% Wilson Score Confidence Intervals
- Boundary vs. Interior error breakdown

If `human_label` is unpopulated, reports status: "pending_manual_labels".
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from typing import Any


def wilson_score_interval(
    successes: int,
    total: int,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Calculate Wilson score interval for a binomial proportion."""
    if total == 0:
        return (0.0, 0.0)

    # z = 1.96 for 95% confidence
    z = 1.95996 if confidence == 0.95 else 1.64485
    p_hat = successes / total

    denom = 1 + (z**2) / total
    centre = (p_hat + (z**2) / (2 * total)) / denom
    spread = (z * math.sqrt((p_hat * (1 - p_hat) + (z**2) / (4 * total)) / total)) / denom

    lower = max(0.0, centre - spread)
    upper = min(1.0, centre + spread)
    return (round(lower, 4), round(upper, 4))


def evaluate_point_sample(
    csv_path: Path | None = None,
) -> dict[str, Any]:
    """Evaluate point sample validation results."""
    if csv_path is None:
        csv_path = Path(__file__).parent / "point_sample_template.csv"

    if not csv_path.exists():
        raise FileNotFoundError(f"Point sample file not found: {csv_path}")

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    total_points = len(rows)
    labeled_rows = [r for r in rows if r.get("human_label", "").strip() in ("0", "1")]
    unlabeled_rows = [r for r in rows if not r.get("human_label", "").strip()]
    unsure_rows = [r for r in rows if r.get("human_label", "").strip().lower() == "unsure"]

    if len(labeled_rows) == 0:
        summary = {
            "status": "pending_manual_labels",
            "total_points": total_points,
            "labeled_count": 0,
            "unlabeled_count": len(unlabeled_rows),
            "unsure_count": len(unsure_rows),
            "instructions": (
                "To evaluate: Open evaluation/point_sample_template.csv. For each point, "
                "inspect the coordinates in Google Earth / high-resolution satellite imagery "
                "corresponding to October-November 2023. Set human_label to '1' (water), "
                "'0' (non-water), or 'unsure'. Then re-run this script."
            ),
        }
        print(
            f"\n[*] Point Sample Status: PENDING MANUAL LABELS ({len(unlabeled_rows)}/{total_points} unlabeled)"
        )
        print(f"    Instructions: {summary['instructions']}\n")
        return summary

    # Compute metrics across labeled subset
    tp = sum(1 for r in labeled_rows if r["our_label"] == "1" and r["human_label"] == "1")
    fp = sum(1 for r in labeled_rows if r["our_label"] == "1" and r["human_label"] == "0")
    fn = sum(1 for r in labeled_rows if r["our_label"] == "0" and r["human_label"] == "1")
    tn = sum(1 for r in labeled_rows if r["our_label"] == "0" and r["human_label"] == "0")

    correct = tp + tn
    total_eval = len(labeled_rows)

    accuracy = correct / total_eval if total_eval > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    acc_ci = wilson_score_interval(correct, total_eval)
    prec_ci = wilson_score_interval(tp, tp + fp)
    rec_ci = wilson_score_interval(tp, tp + fn)

    # Stratified breakdown
    by_stratum: dict[str, Any] = {}
    for st in ("water", "non_water", "boundary"):
        s_rows = [r for r in labeled_rows if r.get("stratum") == st]
        s_correct = sum(1 for r in s_rows if r["our_label"] == r["human_label"])
        s_tot = len(s_rows)
        s_acc = s_correct / s_tot if s_tot > 0 else 0.0
        by_stratum[st] = {
            "total": s_tot,
            "correct": s_correct,
            "accuracy": round(s_acc, 4),
            "ci_95": wilson_score_interval(s_correct, s_tot),
        }

    summary = {
        "status": "evaluated",
        "total_points": total_points,
        "labeled_count": total_eval,
        "unsure_count": len(unsure_rows),
        "overall_accuracy": round(accuracy, 4),
        "accuracy_ci_95": acc_ci,
        "precision": round(precision, 4),
        "precision_ci_95": prec_ci,
        "recall": round(recall, 4),
        "recall_ci_95": rec_ci,
        "f1": round(f1, 4),
        "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "by_stratum": by_stratum,
    }

    print("\n================ INDEPENDENT POINT-SAMPLE EVALUATION ================")
    print(f" Labeled Points:     {total_eval}/{total_points} (Unsure: {len(unsure_rows)})")
    print(
        f" Overall Accuracy:   {accuracy * 100:.2f}% (95% CI: [{acc_ci[0] * 100:.1f}%, {acc_ci[1] * 100:.1f}%])"
    )
    print(
        f" Precision (Water):  {precision * 100:.2f}% (95% CI: [{prec_ci[0] * 100:.1f}%, {prec_ci[1] * 100:.1f}%])"
    )
    print(
        f" Recall (Water):     {recall * 100:.2f}% (95% CI: [{rec_ci[0] * 100:.1f}%, {rec_ci[1] * 100:.1f}%])"
    )
    print(f" F1 Score:           {f1:.4f}")
    print("=====================================================================\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate point sample validation dataset.")
    parser.add_argument("--csv", type=Path, default=None, help="Path to point sample CSV.")
    args = parser.parse_args()
    evaluate_point_sample(args.csv)
