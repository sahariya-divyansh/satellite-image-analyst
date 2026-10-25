"""OpenAI and OpenAI-compatible API provider implementation using REST API."""

import os
from typing import Any

import httpx

from satellite_analyst.errors import PlanGenerationError
from satellite_analyst.planner.llm_base import BaseLLMProvider


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
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = (
            base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        ).rstrip("/")

    async def generate_plan(self, query: str) -> Any:
        """Parse natural language query into a validated QueryPlan."""
        if not self.api_key:
            raise PlanGenerationError(
                query=query,
                reason="OPENAI_API_KEY is not configured. Falling back to rule-based planner.",
            )
        return await super().generate_plan(query)

    async def generate_chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        """Call OpenAI-compatible chat completions endpoint."""
        if not self.api_key:
            raise PlanGenerationError(
                query=user_prompt,
                reason="OPENAI_API_KEY is not configured. Falling back to rule-based planner.",
            )

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.0,
        }
        if json_schema:
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"OpenAI API returned HTTP {resp.status_code}: {resp.text}")
            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                raise RuntimeError("OpenAI API returned no choices")
            content = choices[0].get("message", {}).get("content", "")
            return str(content)
