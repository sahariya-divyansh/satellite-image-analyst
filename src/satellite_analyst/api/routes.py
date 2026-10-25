"""FastAPI API routes definition."""

from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response

from satellite_analyst.api.jobs import job_manager
from satellite_analyst.api.models import JobResponse, QueryRequest
from satellite_analyst.errors import JobNotFoundError
from satellite_analyst.logging import get_logger
from satellite_analyst.planner.rule_based import RuleBasedPlanner

logger = get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["Analysis"])


async def _run_analysis_pipeline(job_id: str, query: str) -> None:
    """Async background worker executing analysis pipeline."""
    try:
        job_manager.update_job(job_id, status="running", progress=10)
        planner = RuleBasedPlanner()
        plan = planner.parse_query(query)
        job_manager.update_job(job_id, plan=plan, progress=30)

        # In Phase 4, full pipeline will be triggered here
        job_manager.update_job(job_id, status="completed", progress=100)
    except Exception as e:
        logger.exception(f"Job {job_id} failed: {e}")
        job_manager.update_job(job_id, status="failed", error=str(e))


@router.post("/query", response_model=JobResponse, status_code=202)
async def submit_query(request: QueryRequest, background_tasks: BackgroundTasks) -> JobResponse:
    """Submit a natural-language Earth observation query for async execution."""
    job_id = job_manager.create_job(request.query)
    background_tasks.add_task(_run_analysis_pipeline, job_id, request.query)
    return job_manager.to_response(job_id)


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job_status(job_id: str) -> JobResponse:
    """Retrieve execution status and summary stats for a job."""
    try:
        return job_manager.to_response(job_id)
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message) from e


@router.get("/jobs/{job_id}/layers/{layer_name}.geojson")
async def get_job_geojson_layer(job_id: str, layer_name: str) -> Any:
    """Download a specific GeoJSON vector layer (e.g. 'water_change', 'gained_water')."""
    try:
        job = job_manager.get_job(job_id)
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message) from e

    layers = job.get("layers", {})
    if layer_name not in layers:
        raise HTTPException(
            status_code=404,
            detail=f"Layer '{layer_name}' not available for job {job_id}.",
        )
    return layers[layer_name]


@router.get("/jobs/{job_id}/report")
async def get_job_report(job_id: str, format: str = "markdown") -> Response:
    """Retrieve grounded Markdown or HTML report for a completed job."""
    try:
        job = job_manager.get_job(job_id)
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message) from e

    if format.lower() == "html":
        content = job.get("report_html") or "<h1>Report Pending</h1>"
        return Response(content=content, media_type="text/html")

    content = job.get("report_markdown") or "# Report Pending\n"
    return Response(content=content, media_type="text/markdown")
