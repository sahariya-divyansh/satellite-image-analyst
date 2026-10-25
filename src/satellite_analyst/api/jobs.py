"""Asynchronous job management and in-memory execution registry."""

import uuid
from datetime import UTC, datetime
from typing import Any

from satellite_analyst.api.models import JobResponse
from satellite_analyst.errors import JobNotFoundError
from satellite_analyst.planner.schema import AnalysisPlan


class JobManager:
    """Manages asynchronous query execution state and artifact registries."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}

    def create_job(self, query: str) -> str:
        """Create a new job entry."""
        job_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        self._jobs[job_id] = {
            "job_id": job_id,
            "status": "pending",
            "created_at": now,
            "updated_at": now,
            "query": query,
            "plan": None,
            "progress_percent": 0,
            "error": None,
            "stats": None,
            "artifacts": {},
            "layers": {},
            "report_markdown": None,
            "report_html": None,
        }
        return job_id

    def get_job(self, job_id: str) -> dict[str, Any]:
        """Retrieve job dictionary by id."""
        if job_id not in self._jobs:
            raise JobNotFoundError(job_id=job_id)
        return self._jobs[job_id]

    def update_job(
        self,
        job_id: str,
        status: str | None = None,
        plan: AnalysisPlan | None = None,
        progress: int | None = None,
        error: str | None = None,
        stats: dict[str, Any] | None = None,
        artifacts: dict[str, str] | None = None,
        layers: dict[str, Any] | None = None,
        report_markdown: str | None = None,
        report_html: str | None = None,
    ) -> None:
        """Update job fields."""
        job = self.get_job(job_id)
        job["updated_at"] = datetime.now(UTC)
        if status is not None:
            job["status"] = status
        if plan is not None:
            job["plan"] = plan
        if progress is not None:
            job["progress_percent"] = progress
        if error is not None:
            job["error"] = error
        if stats is not None:
            job["stats"] = stats
        if artifacts is not None:
            job["artifacts"].update(artifacts)
        if layers is not None:
            job["layers"].update(layers)
        if report_markdown is not None:
            job["report_markdown"] = report_markdown
        if report_html is not None:
            job["report_html"] = report_html

    def to_response(self, job_id: str) -> JobResponse:
        """Convert job dictionary to JobResponse model."""
        job = self.get_job(job_id)
        return JobResponse(
            job_id=job["job_id"],
            status=job["status"],
            created_at=job["created_at"],
            updated_at=job["updated_at"],
            query=job["query"],
            plan=job["plan"],
            progress_percent=job["progress_percent"],
            error=job["error"],
            stats=job["stats"],
            artifacts=job["artifacts"],
        )


# Global singleton job manager
job_manager = JobManager()
