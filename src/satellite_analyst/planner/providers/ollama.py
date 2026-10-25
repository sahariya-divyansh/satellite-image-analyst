"""Ollama local LLM provider implementation."""

from typing import Any

from satellite_analyst.planner.llm_base import BaseLLMProvider
from satellite_analyst.planner.schema import AnalysisPlan


class OllamaProvider(BaseLLMProvider):
    """Planner and reporter powered by a local Ollama instance."""

    def __init__(
        self,
        model_name: str = "llama3.2",
        base_url: str = "http://localhost:11434",
        **kwargs: Any,
    ) -> None:
        super().__init__(model_name=model_name, **kwargs)
        self.base_url = base_url

    async def generate_plan(self, query: str) -> AnalysisPlan:
        """Call Ollama /api/generate with JSON schema format."""
        raise NotImplementedError("OllamaProvider live execution enabled in Phase 3.")

    async def generate_narrative(
        self,
        plan: AnalysisPlan,
        stats: dict[str, Any],
        provenance: dict[str, Any],
    ) -> str:
        """Synthesize narrative using local model."""
        raise NotImplementedError("Ollama narrative generation enabled in Phase 3.")
