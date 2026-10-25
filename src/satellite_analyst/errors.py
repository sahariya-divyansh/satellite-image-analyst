"""Domain-specific exceptions and typed error hierarchies."""

from typing import Any


class SatelliteAnalystError(Exception):
    """Base exception for all satellite-analyst errors."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class GeocodingError(SatelliteAnalystError):
    """Raised when an Area of Interest cannot be geocoded or resolved."""

    def __init__(self, place: str, reason: str = "Location not found") -> None:
        super().__init__(
            message=f"Failed to geocode location '{place}': {reason}",
            code="GEOCODING_FAILED",
            status_code=404,
            details={"place": place, "reason": reason},
        )


class PlanGenerationError(SatelliteAnalystError):
    """Raised when natural-language query planning fails."""

    def __init__(self, query: str, reason: str) -> None:
        super().__init__(
            message=f"Failed to create execution plan for query: {reason}",
            code="PLAN_GENERATION_FAILED",
            status_code=422,
            details={"query": query, "reason": reason},
        )


class STACSearchError(SatelliteAnalystError):
    """Raised when STAC query returns no scenes or external API fails."""

    def __init__(self, reason: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=f"STAC search error: {reason}",
            code="STAC_SEARCH_FAILED",
            status_code=502,
            details=details or {},
        )


class InsufficientImageryError(SatelliteAnalystError):
    """Raised when cloud masking removes all valid observations in period."""

    def __init__(self, period: str, total_scenes: int, valid_scenes: int) -> None:
        super().__init__(
            message=(
                f"Insufficient clear observations for period '{period}'. "
                f"Total scenes: {total_scenes}, valid scenes post-masking: {valid_scenes}."
            ),
            code="INSUFFICIENT_IMAGERY",
            status_code=422,
            details={
                "period": period,
                "total_scenes": total_scenes,
                "valid_scenes": valid_scenes,
            },
        )


class GroundingViolationError(SatelliteAnalystError):
    """Raised when LLM reporter generates metrics not present in computed stats."""

    def __init__(self, ungrounded_numbers: list[str]) -> None:
        super().__init__(
            message=(
                "Grounding verification failed: Report contains ungrounded numeric claims "
                f"not present in pipeline statistics: {ungrounded_numbers}"
            ),
            code="GROUNDING_VIOLATION",
            status_code=500,
            details={"ungrounded_numbers": ungrounded_numbers},
        )


class JobNotFoundError(SatelliteAnalystError):
    """Raised when an asynchronous analysis job is not found."""

    def __init__(self, job_id: str) -> None:
        super().__init__(
            message=f"Analysis job '{job_id}' not found.",
            code="JOB_NOT_FOUND",
            status_code=404,
            details={"job_id": job_id},
        )
