"""FastAPI route handlers for natural-language EO analysis, job polling, and vector streaming."""

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse

from satellite_analyst.api.jobs import WHITELISTED_LAYERS, job_manager
from satellite_analyst.api.models import (
    ExampleItem,
    ExamplesResponse,
    JobCreatedResponse,
    JobStatusResponse,
    LayerListResponse,
    QueryClarificationResponse,
    QueryRequest,
)
from satellite_analyst.errors import (
    InvalidLayerError,
)
from satellite_analyst.logging import get_logger
from satellite_analyst.planner.rule_based import RuleBasedPlanner
from satellite_analyst.planner.schema import QueryPlan

logger = get_logger(__name__)

__all__ = ["router", "job_manager"]

router = APIRouter(prefix="/v1", tags=["Earth Observation Analysis"])


@router.post(
    "/query",
    summary="Submit Natural-Language Query",
    response_model=JobCreatedResponse | QueryClarificationResponse,
    status_code=202,
    responses={
        200: {
            "model": QueryClarificationResponse,
            "description": "Clarification required or query out of archive bounds",
        },
        202: {"model": JobCreatedResponse, "description": "Analysis job accepted for execution"},
        400: {"description": "Invalid query payload"},
        429: {"description": "Rate limit or queue capacity exceeded"},
    },
)
async def submit_query(
    request: QueryRequest,
    http_request: Request,
) -> Response:
    """Parse natural-language query and either request clarification or queue an analysis job."""
    req_id = getattr(http_request.state, "request_id", "unknown")
    logger.info("Received query submission (request_id=%s): '%s'", req_id, request.query)

    # 1. Plan query
    planner = RuleBasedPlanner()
    try:
        plan: QueryPlan = planner.parse_query(request.query)
    except Exception as e:
        logger.warning("Planning failed: %s", e)
        raise HTTPException(status_code=422, detail=f"Query interpretation failed: {e}") from e

    # 2. Check if clarification or typed refusal is required
    if plan.needs_clarification:
        logger.info("Query requires clarification: %s", plan.clarification_question)
        clarification_body = QueryClarificationResponse(
            status="clarification_required",
            clarification_question=plan.clarification_question
            or "Please clarify your analysis timeframe and target location.",
            assumptions=plan.assumptions,
            plan=plan,
        )
        return JSONResponse(
            status_code=200,
            content=clarification_body.model_dump(mode="json"),
        )

    # 3. Create and enqueue asynchronous job
    job_id = job_manager.create_job(query=request.query, plan=plan)
    job_url = f"/v1/jobs/{job_id}"

    created_body = JobCreatedResponse(
        status="accepted",
        job_id=job_id,
        job_url=job_url,
        state="queued",
        plan=plan,
    )
    return JSONResponse(
        status_code=202,
        content=created_body.model_dump(mode="json"),
        headers={"Location": job_url},
    )


@router.get(
    "/jobs/{job_id}",
    summary="Get Job Execution Status",
    response_model=JobStatusResponse,
    responses={
        404: {"description": "Job not found"},
    },
)
async def get_job_status(job_id: str) -> JobStatusResponse:
    """Poll pipeline execution progress, status, and summary statistics."""
    job = job_manager.get_job(job_id)
    return JobStatusResponse(
        job_id=job["job_id"],
        status=job["status"],
        stage=job.get("stage", "Processing"),
        progress_percent=job.get("progress_percent", 0),
        created_at=job["created_at"],
        started_at=job.get("started_at"),
        completed_at=job.get("completed_at"),
        query=job["query"],
        plan=job.get("plan"),
        error=job.get("error"),
        stats=job.get("stats"),
        is_demo=job.get("is_demo", False),
        artifacts=job.get("artifacts", {}),
    )


@router.get(
    "/jobs/{job_id}/plan",
    summary="Get Parsed Query Plan",
    response_model=QueryPlan,
    responses={
        404: {"description": "Job not found"},
    },
)
async def get_job_plan(job_id: str) -> Any:
    """Retrieve the validated QueryPlan JSON generated for this job."""
    job = job_manager.get_job(job_id)
    plan = job.get("plan")
    if not plan:
        raise HTTPException(status_code=404, detail=f"No plan found for job {job_id}")
    if isinstance(plan, QueryPlan):
        return plan
    return QueryPlan.model_validate(plan)


@router.get(
    "/jobs/{job_id}/layers",
    summary="List Available Vector Layers",
    response_model=LayerListResponse,
    responses={
        404: {"description": "Job not found or layers not yet generated"},
    },
)
async def get_job_layers(job_id: str) -> LayerListResponse:
    """List vectorized layer names available for map visualization."""
    job = job_manager.get_job(job_id)
    layers_dir = job_manager.jobs_dir / job_id / "layers"

    if not layers_dir.exists():
        if job.get("status") == "failed":
            raise HTTPException(
                status_code=404, detail="Analysis failed; no vector layers generated."
            )
        return LayerListResponse(job_id=job_id, layers=[])

    available: list[str] = []
    for layer in sorted(WHITELISTED_LAYERS):
        if (layers_dir / f"{layer}.geojson").exists():
            available.append(layer)

    return LayerListResponse(job_id=job_id, layers=available)


@router.get(
    "/jobs/{job_id}/layers/{layer_name}.geojson",
    summary="Get Vector GeoJSON Layer",
    responses={
        200: {"content": {"application/geo+json": {}}},
        400: {"description": "Invalid or unwhitelisted layer name"},
        404: {"description": "Job or layer not found"},
    },
)
async def get_job_layer_geojson(job_id: str, layer_name: str) -> Response:
    """Stream a whitelisted GeoJSON layer for web map rendering with path-traversal defense."""
    sanitized_name = layer_name.strip().lower()
    if sanitized_name not in WHITELISTED_LAYERS:
        raise InvalidLayerError(
            layer_name=layer_name,
            allowed=sorted(WHITELISTED_LAYERS),
        )

    job_manager.get_job(job_id)  # Validate job exists
    layer_file = job_manager.jobs_dir / job_id / "layers" / f"{sanitized_name}.geojson"

    if not layer_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Layer '{sanitized_name}' not available for job {job_id} (pipeline may still be running)",
        )

    content = layer_file.read_text(encoding="utf-8")
    return Response(content=content, media_type="application/geo+json")


@router.get(
    "/jobs/{job_id}/report",
    summary="Get Grounded Analysis Report",
    responses={
        200: {"description": "Markdown or HTML grounded report"},
        404: {"description": "Report not found or job still running"},
    },
)
async def get_job_report(
    job_id: str,
    format: Literal["md", "html", "markdown"] = Query(default="html", description="Report format"),
) -> Response:
    """Retrieve grounded scientific report in Markdown or rendered HTML format."""
    job_manager.get_job(job_id)
    job_dir = job_manager.jobs_dir / job_id

    fmt = format.lower()
    if fmt == "html":
        report_file = job_dir / "report.html"
        media_type = "text/html"
    else:
        report_file = job_dir / "report.md"
        media_type = "text/markdown"

    if not report_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Report format '{format}' not available for job {job_id} (still processing or failed)",
        )

    content = report_file.read_text(encoding="utf-8")
    return Response(content=content, media_type=media_type)


@router.get(
    "/jobs/{job_id}/download/{download_format}",
    summary="Download Analysis Deliverables",
    responses={
        200: {"description": "File download (CSV, GeoTIFF, or GeoJSON)"},
        400: {"description": "Unsupported download format"},
        404: {"description": "File not found"},
    },
)
async def download_job_artifact(
    job_id: str,
    download_format: Literal["csv", "geotiff", "tif", "geojson"],
) -> FileResponse:
    """Download full-resolution geospatial artifacts (CSV attribute table, GeoTIFF, or GeoJSON)."""
    job_manager.get_job(job_id)
    layers_dir = job_manager.jobs_dir / job_id / "layers"

    fmt = download_format.lower()
    if fmt == "csv":
        target = layers_dir / "waterbodies.csv"
        media = "text/csv"
        fname = f"{job_id}_waterbodies.csv"
    elif fmt in ["geotiff", "tif"]:
        target = layers_dir / "change_mask.tif"
        media = "image/tiff"
        fname = f"{job_id}_change_mask.tif"
    elif fmt == "geojson":
        target = layers_dir / "waterbodies.geojson"
        if not target.exists():
            target = layers_dir / "all.geojson"
        media = "application/geo+json"
        fname = f"{job_id}_waterbodies.geojson"
    else:
        raise HTTPException(
            status_code=400, detail=f"Unsupported download format '{download_format}'"
        )

    if not target.exists():
        raise HTTPException(
            status_code=404, detail=f"Deliverable '{download_format}' not found for job {job_id}"
        )

    return FileResponse(
        path=target,
        filename=fname,
        media_type=media,
    )


@router.get(
    "/examples",
    summary="List Pre-Configured Query Examples",
    response_model=ExamplesResponse,
)
async def get_examples() -> ExamplesResponse:
    """Return pre-configured query examples including cached demo runs."""
    return ExamplesResponse(
        examples=[
            ExampleItem(
                id="raipur_2023_2025",
                title="Raipur Surface Water Dynamics (2023 vs 2025)",
                query="Show all water bodies that expanded near Raipur between 2023 and 2025",
                description="Verified Sentinel-2 L2A real analysis over Chhattisgarh. Demonstrates Otsu bimodality check, churn ratio thresholding, and conservative scientific labeling.",
                is_cached_demo=True,
            ),
            ExampleItem(
                id="sambhar_pre_monsoon",
                title="Sambhar Salt Lake Extent (Pre-Monsoon 2024)",
                query="Analyze water body extent near Sambhar during pre-monsoon 2024",
                description="Single-year surface water inventory over India's largest inland saline wetland during peak dry season.",
                is_cached_demo=False,
            ),
            ExampleItem(
                id="bhopal_recent_shrinkage",
                title="Bhopal Upper Lake Dynamics (Recent Years)",
                query="Show water bodies that shrunk recently near Bhopal",
                description="Evaluates relative date extraction ('recently' -> 2024 to 2026) and contraction vectorization.",
                is_cached_demo=False,
            ),
            ExampleItem(
                id="coord_nagpur",
                title="Point Coordinate Buffer (21.15°N, 79.08°E)",
                query="Show water body change near 21.15N, 79.08E from 2021 to 2024",
                description="Demonstrates decimal-degree coordinate literal parsing and local UTM projected radial buffer generation.",
                is_cached_demo=False,
            ),
        ]
    )
