"""Abstract interface for LLM planning and reporting backends."""

from abc import ABC, abstractmethod
from typing import Any

from satellite_analyst.planner.schema import AnalysisPlan


class BaseLLMProvider(ABC):
    """Abstract base class for all pluggable LLM backends."""

    def __init__(self, model_name: str, **kwargs: Any) -> None:
        self.model_name = model_name
        self.extra_config = kwargs

    @abstractmethod
    async def generate_plan(self, query: str) -> AnalysisPlan:
        """Parse natural language query into a validated AnalysisPlan."""
        pass

    @abstractmethod
    async def generate_narrative(
        self,
        plan: AnalysisPlan,
        stats: dict[str, Any],
        provenance: dict[str, Any],
    ) -> str:
        """Synthesize a grounded narrative summary strictly from computed stats."""
        pass
