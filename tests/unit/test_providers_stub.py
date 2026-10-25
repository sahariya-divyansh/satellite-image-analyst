"""Tests for LLM provider stubs and async rule-based planning."""

import pytest
from satellite_analyst.errors import PlanGenerationError
from satellite_analyst.planner.providers.gemini import GeminiProvider
from satellite_analyst.planner.providers.ollama import OllamaProvider
from satellite_analyst.planner.providers.openai import OpenAIProvider
from satellite_analyst.planner.rule_based import RuleBasedPlanner


@pytest.mark.asyncio
async def test_rule_based_async_methods() -> None:
    planner = RuleBasedPlanner()
    plan = await planner.generate_plan("Show water change in Raipur between 2023 and 2025")
    assert plan.task_type == "water_change"

    narrative = await planner.generate_narrative(
        plan=plan,
        stats={
            "net_change_ha": 500.0,
            "percent_change": 12.5,
            "persistent_water_ha": 4000.0,
            "gained_water_ha": 600.0,
            "lost_water_ha": 100.0,
        },
        _provenance={},
    )
    assert "Raipur" in narrative
    assert "500.00 hectares" in narrative


@pytest.mark.asyncio
async def test_gemini_provider_unconfigured() -> None:
    provider = GeminiProvider(api_key=None)
    with pytest.raises(PlanGenerationError):
        await provider.generate_plan("Show water in Raipur")


@pytest.mark.asyncio
async def test_openai_provider_unconfigured() -> None:
    provider = OpenAIProvider(api_key=None)
    with pytest.raises(PlanGenerationError):
        await provider.generate_plan("Show water in Raipur")


@pytest.mark.asyncio
async def test_ollama_provider_stub() -> None:
    provider = OllamaProvider()
    with pytest.raises(NotImplementedError):
        await provider.generate_plan("Show water in Raipur")
