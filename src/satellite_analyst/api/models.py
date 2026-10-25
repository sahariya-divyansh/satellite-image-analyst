"""Pydantic schemas for HTTP API requests and responses."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from satellite_analyst.planner.schema import AnalysisPlan


class QueryRequest(BaseModel):
    """Natural-language query submission."""

    query: str = Field(
        ...,
        min_length=3,
        max_length=500,
        examples=["Show all water bodies that expanded near Raipur between 2023 and 2025."],
    )
    llm_provider: Literal["rule_based", "gemini", "openai", "ollama"] | None = Field(
        default=None,
        description="Override default LLM provider for planning",
    )


class JobResponse(BaseModel):
    """Job status response."""

    job_id: str
    status: Literal["pending", "running", "completed", "failed"]
    created_at: datetime
    updated_at: datetime
    query: str
    plan: AnalysisPlan | None = None
    progress_percent: int = Field(default=0, ge=0, le=100)
    error: str | None = None
    stats: dict[str, Any] | None = None
    artifacts: dict[str, str] = Field(default_factory=dict)


class HealthCheckResponse(BaseModel):
    """Health check payload."""

    status: str = "ok"
    version: str
    timestamp: datetime
