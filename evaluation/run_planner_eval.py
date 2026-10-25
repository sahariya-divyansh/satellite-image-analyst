"""Evaluation harness for natural-language query planners on dev and held-out benchmark suites."""

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from satellite_analyst.planner.rule_based import RuleBasedPlanner


def run_planner_eval(
    dataset_name: str = "golden_queries.yaml",
) -> dict[str, Any]:
    """Run benchmark evaluation across specified query suite."""
    eval_dir = Path(__file__).parent
    golden_file = eval_dir / dataset_name

    with open(golden_file, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    queries: list[dict[str, Any]] = data.get("queries", [])
    planner = RuleBasedPlanner()

    total = len(queries)
    exact_match = 0
    task_match = 0
    place_match = 0
    season_match = 0
    year_match = 0
    clarification_match = 0

    results_detail: list[dict[str, Any]] = []

    for item in queries:
        qid = item["id"]
        q_str = item["query"]
        expected = item["expected"]

        try:
            plan = planner.parse_query(q_str)
            actual_task = plan.task_type
            actual_place = plan.aoi.place_name.lower()
            actual_season = plan.season_policy
            actual_year_a = plan.time_range_a.start_date.year
            actual_year_b = plan.time_range_b.start_date.year if plan.time_range_b else None
            actual_clarification = plan.needs_clarification

            # Out-of-scope / clarification handling
            if expected.get("needs_clarification") is True:
                is_clarification_ok = actual_clarification is True
                is_task_ok = actual_task == expected.get("task_type") or is_clarification_ok
                is_place_ok = True
                is_season_ok = True
                is_year_ok = True
            else:
                is_clarification_ok = actual_clarification is False
                is_task_ok = actual_task == expected["task_type"]
                is_place_ok = actual_place == expected["place_name"].lower()
                is_season_ok = actual_season == expected["season_policy"]
                is_year_ok = (actual_year_a == expected["year_a"]) and (
                    actual_year_b == expected["year_b"]
                )

            is_exact = (
                is_task_ok and is_place_ok and is_season_ok and is_year_ok and is_clarification_ok
            )

            if is_task_ok:
                task_match += 1
            if is_place_ok:
                place_match += 1
            if is_season_ok:
                season_match += 1
            if is_year_ok:
                year_match += 1
            if is_clarification_ok:
                clarification_match += 1
            if is_exact:
                exact_match += 1

            results_detail.append(
                {
                    "id": qid,
                    "query": q_str,
                    "exact": is_exact,
                    "task_ok": is_task_ok,
                    "place_ok": is_place_ok,
                    "season_ok": is_season_ok,
                    "year_ok": is_year_ok,
                    "clarification_ok": is_clarification_ok,
                    "actual": {
                        "task_type": actual_task,
                        "place": actual_place,
                        "season": actual_season,
                        "year_a": actual_year_a,
                        "year_b": actual_year_b,
                        "needs_clarification": actual_clarification,
                    },
                }
            )
        except Exception as e:
            results_detail.append(
                {
                    "id": qid,
                    "query": q_str,
                    "exact": False,
                    "error": str(e),
                }
            )

    summary = {
        "dataset": dataset_name,
        "total_queries": total,
        "exact_match_count": exact_match,
        "exact_match_pct": round(exact_match / total * 100.0, 2),
        "task_acc_pct": round(task_match / total * 100.0, 2),
        "place_acc_pct": round(place_match / total * 100.0, 2),
        "season_acc_pct": round(season_match / total * 100.0, 2),
        "year_acc_pct": round(year_match / total * 100.0, 2),
        "clarification_acc_pct": round(clarification_match / total * 100.0, 2),
        "results_detail": results_detail,
    }

    out_filename = (
        "planner_heldout_results.json" if "heldout" in dataset_name else "planner_eval_results.json"
    )
    out_file = eval_dir / "results" / out_filename
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\n================ PLANNER EVALUATION [{dataset_name}] ================")
    print(f" Total Evaluated Queries:       {total:>5} (Exact Matches: {exact_match})")
    print(f" Overall Exact Match Accuracy:  {summary['exact_match_pct']:>5.2f}%")
    print(f" Task Type Classification:      {summary['task_acc_pct']:>5.2f}%")
    print(f" AOI Place Name Resolution:     {summary['place_acc_pct']:>5.2f}%")
    print(f" Season Policy Extraction:      {summary['season_acc_pct']:>5.2f}%")
    print(f" Temporal Year Bounds:          {summary['year_acc_pct']:>5.2f}%")
    print(f" Clarification / Refusal Acc:   {summary['clarification_acc_pct']:>5.2f}%")
    print(f" Results Saved:                 {out_file}")
    print("=======================================================================\n")

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run query planner benchmark evaluation.")
    parser.add_argument(
        "--dataset",
        choices=["golden_queries.yaml", "golden_heldout.yaml", "golden_heldout_v2.yaml"],
        default="golden_heldout_v2.yaml",
        help="Evaluation dataset file (default: golden_heldout_v2.yaml).",
    )
    args = parser.parse_args()
    run_planner_eval(args.dataset)
