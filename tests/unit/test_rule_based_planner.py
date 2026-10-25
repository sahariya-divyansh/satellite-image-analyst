"""Tests for rule-based fallback planner."""

import pytest

from satellite_analyst.errors import PlanGenerationError
from satellite_analyst.planner.rule_based import RuleBasedPlanner


def test_rule_based_planner_standard_query() -> None:
    planner = RuleBasedPlanner()
    query = "Show all water bodies that expanded near Raipur between 2023 and 2025"
    plan = planner.parse_query(query)

    assert plan.task_type == "water_change"
    assert plan.aoi.place_name.lower() == "raipur"
    assert plan.time_range_a.start_date.year == 2023
    assert plan.time_range_b is not None
    assert plan.time_range_b.start_date.year == 2025
    assert plan.season_policy == "post_monsoon"


def test_rule_based_planner_pre_monsoon_detection() -> None:
    planner = RuleBasedPlanner()
    query = "Analyze water body extent near Sambhar during pre-monsoon 2024"
    plan = planner.parse_query(query)

    assert plan.season_policy == "pre_monsoon"
    assert plan.time_range_a.start_date.month == 3
    assert plan.time_range_a.end_date.month == 5
    assert plan.aoi.place_name.lower() == "sambhar"


def test_rule_based_planner_empty_query() -> None:
    planner = RuleBasedPlanner()
    with pytest.raises(PlanGenerationError):
        planner.parse_query("   ")
