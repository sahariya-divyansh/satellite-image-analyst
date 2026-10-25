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


def test_rule_based_planner_hindi_seasons() -> None:
    planner = RuleBasedPlanner()

    # "baarish ke baad" -> post-monsoon
    plan_post = planner.parse_query("Raipur me baarish ke baad 2023 se 2025 tak paani kitna badha")
    assert plan_post.task_type == "water_change"
    assert plan_post.season_policy == "post_monsoon"
    assert plan_post.period_a.year == 2023
    assert plan_post.period_b is not None and plan_post.period_b.year == 2025

    # "garmi" -> pre-monsoon
    plan_pre = planner.parse_query("Garmi me Sambhar lake ka paani 2024")
    assert plan_pre.season_policy == "pre_monsoon"
    assert plan_pre.period_a.year == 2024


def test_rule_based_planner_relative_time_and_radius() -> None:
    planner = RuleBasedPlanner()

    # "last 3 years" relative to reference year (2026)
    plan_rel = planner.parse_query(
        "Show water expansion within 20 km of Raipur over the last 3 years"
    )
    assert plan_rel.aoi.radius_km == 20.0
    assert plan_rel.period_a.year == 2023
    assert plan_rel.period_b is not None and plan_rel.period_b.year == 2026

    # "recently" -> 2024 to 2026
    plan_rec = planner.parse_query("Show water bodies that shrunk recently near Bhopal")
    assert plan_rec.period_a.year == 2024
    assert plan_rec.period_b is not None and plan_rec.period_b.year == 2026


def test_rule_based_planner_out_of_scope_and_archive_boundaries() -> None:
    planner = RuleBasedPlanner()

    # Out of scope: predictive modeling
    plan_pred = planner.parse_query("Predict next year's flood extent near Raipur")
    assert plan_pred.task_type == "out_of_scope"
    assert plan_pred.needs_clarification is True
    assert "outside supported capabilities" in (plan_pred.clarification_question or "")

    # Archive boundary: Sentinel-2 L2A starts in 2017
    plan_early = planner.parse_query("Water change near Raipur between 2015 and 2018")
    assert plan_early.needs_clarification is True
    assert "2017 onwards" in (plan_early.clarification_question or "")
