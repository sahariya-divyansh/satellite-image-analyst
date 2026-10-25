"""Google Gemini LLM provider implementation using REST API."""

import os
from typing import Any

import httpx

from satellite_analyst.errors import PlanGenerationError
from satellite_analyst.logging import get_logger
from satellite_analyst.planner.llm_base import BaseLLMProvider

logger = get_logger(__name__)


class GeminiProvider(BaseLLMProvider):
    """Planner and narrative reporter powered by Google Gemini API."""

    def __init__(
        self,
        model_name: str = "gemini-1.5-flash",
        api_key: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(model_name=model_name, **kwargs)
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")

    async def generate_plan(self, query: str) -> Any:
        """Parse natural language query into a validated QueryPlan."""
        if not self.api_key:
            raise PlanGenerationError(
                query=query,
                reason="GEMINI_API_KEY is not configured. Falling back to rule-based planner.",
            )
        return await super().generate_plan(query)

    async def generate_chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        """Call Gemini REST API for structured chat completion."""
        if not self.api_key:
            raise PlanGenerationError(
                query=user_prompt,
                reason="GEMINI_API_KEY is not configured. Falling back to rule-based planner.",
            )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"
        payload: dict[str, Any] = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}],
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
            },
        }
        if json_schema:
            payload["generationConfig"]["response_mime_type"] = "application/json"

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"Gemini API returned HTTP {resp.status_code}: {resp.text}")
            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise RuntimeError("Gemini API returned no candidates")
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                raise RuntimeError("Gemini API response contained no content")
            return str(parts[0].get("text", ""))
