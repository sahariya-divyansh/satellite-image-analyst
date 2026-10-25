"""Ollama local LLM provider implementation using REST API."""

import os
from typing import Any

import httpx

from satellite_analyst.planner.llm_base import BaseLLMProvider


class OllamaProvider(BaseLLMProvider):
    """Planner and reporter powered by a local Ollama instance."""

    def __init__(
        self,
        model_name: str = "llama3.2",
        base_url: str = "http://localhost:11434",
        **kwargs: Any,
    ) -> None:
        super().__init__(model_name=model_name, **kwargs)
        self.base_url = (
            base_url or os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434"
        ).rstrip("/")

    async def generate_plan(self, query: str) -> Any:
        """Parse natural language query into a validated QueryPlan."""
        if not os.environ.get("OLLAMA_ENABLED"):
            raise NotImplementedError(
                "OllamaProvider live execution requires active Ollama daemon."
            )
        return await super().generate_plan(query)

    async def generate_chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        """Call Ollama /api/chat with JSON format."""
        url = f"{self.base_url}/api/chat"
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "format": "json" if json_schema else None,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"Ollama returned HTTP {resp.status_code}: {resp.text}")
            data = resp.json()
            return str(data.get("message", {}).get("content", ""))
