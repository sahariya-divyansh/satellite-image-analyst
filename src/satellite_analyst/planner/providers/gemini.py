"""Google Gemini LLM provider implementation."""

from typing import Any

from satellite_analyst.errors import PlanGenerationError
from satellite_analyst.logging import get_logger
from satellite_analyst.planner.llm_base import BaseLLMProvider
from satellite_analyst.planner.schema import AnalysisPlan

logger = get_logger(__name__)


class GeminiProvider(BaseLLMProvider):
    """Planner and narrative reporter powered by Google Gemini API."""

    def __init__(
        self, model_name: str = "gemini-1.5-flash", api_key: str | None = None, **kwargs: Any
    ) -> None:
        super().__init__(model_name=model_name, **kwargs)
        self.api_key = api_key

    async def generate_plan(self, query: str) -> AnalysisPlan:
        """Call Gemini to output validated AnalysisPlan JSON schema."""
        if not self.api_key:
            raise PlanGenerationError(
                query=query,
                reason="GEMINI_API_KEY is not configured. Falling back to rule-based planner.",
            )
        # Concrete implementation with google-genai or httpx will be wired in Phase 3
        raise NotImplementedError("GeminiProvider live execution enabled in Phase 3.")

    async def generate_narrative(
        self,
        _plan: AnalysisPlan,
        _stats: dict[str, Any],
        _provenance: dict[str, Any],
    ) -> str:
        """Call Gemini to generate report narrative strictly grounded in stats."""
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured.")
        raise NotImplementedError("Gemini narrative generation enabled in Phase 3.")
