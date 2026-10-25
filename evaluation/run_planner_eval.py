"""Evaluation harness for natural-language query planners."""

import json
from pathlib import Path
from typing import Any

import yaml

from satellite_analyst.planner.rule_based import RuleBasedPlanner


def run_planner_eval() -> dict[str, Any]:
    """Run benchmark evaluation across golden query suite."""
    eval_dir = Path(__file__).parent
    golden_file = eval_dir / "golden_queries.yaml"

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

            is_task_ok = actual_task == expected["task_type"]
            is_place_ok = actual_place == expected["place_name"].lower()
            is_season_ok = actual_season == expected["season_policy"]
            is_year_ok = (actual_year_a == expected["year_a"]) and (
                actual_year_b == expected["year_b"]
            )

            is_exact = is_task_ok and is_place_ok and is_season_ok and is_year_ok

            if is_task_ok:
                task_match += 1
            if is_place_ok:
                place_match += 1
            if is_season_ok:
                season_match += 1
            if is_year_ok:
                year_match += 1
            if is_exact:
                exact_match += 1

            results_detail.append(
                {
                    "id": qid,
                    "exact": is_exact,
                    "task_ok": is_task_ok,
                    "place_ok": is_place_ok,
                    "season_ok": is_season_ok,
                    "year_ok": is_year_ok,
                }
            )
        except Exception as e:
            results_detail.append(
                {
                    "id": qid,
                    "exact": False,
                    "error": str(e),
                }
            )

    summary = {
        "total_queries": total,
        "exact_match_count": exact_match,
        "exact_match_pct": round(exact_match / total * 100.0, 2),
        "task_acc_pct": round(task_match / total * 100.0, 2),
        "place_acc_pct": round(place_match / total * 100.0, 2),
        "season_acc_pct": round(season_match / total * 100.0, 2),
        "year_acc_pct": round(year_match / total * 100.0, 2),
        "results_detail": results_detail,
    }

    out_file = eval_dir / "results" / "planner_eval_results.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"Planner Evaluation Complete ({total} queries):")
    print(f"  Exact Match: {summary['exact_match_pct']}% ({exact_match}/{total})")
    print(f"  Task Type Accuracy: {summary['task_acc_pct']}%")
    print(f"  AOI Place Accuracy: {summary['place_acc_pct']}%")
    print(f"  Season Policy Accuracy: {summary['season_acc_pct']}%")
    print(f"  Temporal Window Accuracy: {summary['year_acc_pct']}%")

    return summary


if __name__ == "__main__":
    run_planner_eval()
