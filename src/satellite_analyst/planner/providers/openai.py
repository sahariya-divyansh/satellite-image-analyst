"""OpenAI and OpenAI-compatible API provider implementation."""

from typing import Any

from satellite_analyst.errors import PlanGenerationError
from satellite_analyst.planner.llm_base import BaseLLMProvider
from satellite_analyst.planner.schema import AnalysisPlan


class OpenAIProvider(BaseLLMProvider):
    """Planner and reporter powered by OpenAI-compatible APIs."""

    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        **kwargs: Any,
    ) -> None:
        super().__init__(model_name=model_name, **kwargs)
        self.api_key = api_key
        self.base_url = base_url

    async def generate_plan(self, query: str) -> AnalysisPlan:
        """Call OpenAI-compatible chat completion with structured JSON output."""
        if not self.api_key:
            raise PlanGenerationError(
                query=query,
                reason="OPENAI_API_KEY is not configured. Falling back to rule-based planner.",
            )
        raise NotImplementedError("OpenAIProvider live execution enabled in Phase 3.")

    async def generate_narrative(
        self,
        _plan: AnalysisPlan,
        _stats: dict[str, Any],
        _provenance: dict[str, Any],
    ) -> str:
        """Generate narrative grounded strictly in computed statistics."""
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured.")
        raise NotImplementedError("OpenAI narrative generation enabled in Phase 3.")
