"""FastAPI application entrypoint, RFC 7807 problem details, rate limiting, and request tracing."""

import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from satellite_analyst import __version__
from satellite_analyst.api.models import HealthCheckResponse, ProblemDetail
from satellite_analyst.api.routes import router as api_router
from satellite_analyst.config import get_settings
from satellite_analyst.errors import SatelliteAnalystError
from satellite_analyst.logging import get_logger, setup_logging

setup_logging()
logger = get_logger("satellite_analyst.api")
settings = get_settings()

app = FastAPI(
    title="Natural-Language Satellite Image Analyst API",
    description=(
        "Translates natural-language Earth observation queries into defensible, "
        "reproducible remote sensing pipelines with grounded statistical verification."
    ),
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS configuration from Settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory per-IP sliding window rate limiter
_rate_limit_history: dict[str, list[float]] = defaultdict(list)


@app.middleware("http")
async def production_hygiene_middleware(request: Request, call_next: Any) -> Response:
    """Injects X-Request-ID, logs execution latency, and enforces per-IP rate limiting."""
    # 1. Request tracing
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    request.state.request_id = request_id

    # 2. Per-IP Rate Limiting (exclude static web UI assets)
    path = request.url.path
    if path.startswith("/v1/"):
        client_ip = request.client.host if request.client else "127.0.0.1"
        now = time.time()
        window_start = now - 60.0

        # Filter timestamps within last 60 seconds
        timestamps = [t for t in _rate_limit_history[client_ip] if t > window_start]
        timestamps.append(now)
        _rate_limit_history[client_ip] = timestamps

        if len(timestamps) > settings.rate_limit_per_minute:
            problem = ProblemDetail(
                type="https://tools.ietf.org/html/rfc7807",
                title="Rate Limit Exceeded",
                status=429,
                detail=f"Exceeded client rate limit of {settings.rate_limit_per_minute} requests per minute.",
                instance=str(request.url),
                code="RATE_LIMIT_EXCEEDED",
            )
            resp = JSONResponse(
                status_code=429,
                content=problem.model_dump(),
                media_type="application/problem+json",
            )
            resp.headers["X-Request-ID"] = request_id
            return resp

    # 3. Process Request
    start_time = time.time()
    try:
        response: Response = await call_next(request)
    except Exception as exc:
        logger.exception("Unhandled error processing %s: %s", path, exc)
        problem = ProblemDetail(
            type="https://tools.ietf.org/html/rfc7807",
            title="Internal Server Error",
            status=500,
            detail=str(exc) if settings.debug else "An unexpected internal server error occurred.",
            instance=str(request.url),
            code="INTERNAL_ERROR",
        )
        response = JSONResponse(
            status_code=500,
            content=problem.model_dump(),
            media_type="application/problem+json",
        )

    # 4. Attach X-Request-ID and response latency header
    duration_ms = (time.time() - start_time) * 1000.0
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"
    return response


# --- RFC 7807 Problem Details Error Handlers ---


@app.exception_handler(SatelliteAnalystError)
async def handle_satellite_analyst_error(
    request: Request, exc: SatelliteAnalystError
) -> JSONResponse:
    """Convert domain exceptions to RFC 7807 problem details."""
    problem = ProblemDetail(
        type="https://satellite-analyst.local/errors/" + exc.code.lower(),
        title=exc.code.replace("_", " ").title(),
        status=exc.status_code,
        detail=exc.message,
        instance=str(request.url),
        code=exc.code,
    )
    req_id = getattr(request.state, "request_id", None)
    headers = {"X-Request-ID": req_id} if req_id else {}
    return JSONResponse(
        status_code=exc.status_code,
        content=problem.model_dump(),
        media_type="application/problem+json",
        headers=headers,
    )


@app.exception_handler(HTTPException)
async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    """Convert FastAPI HTTP exceptions to RFC 7807 problem details."""
    detail_str = str(exc.detail) if exc.detail else "HTTP Exception"
    problem = ProblemDetail(
        type="about:blank",
        title=detail_str[:60],
        status=exc.status_code,
        detail=detail_str,
        instance=str(request.url),
        code="HTTP_ERROR",
    )
    req_id = getattr(request.state, "request_id", None)
    headers = {"X-Request-ID": req_id} if req_id else {}
    return JSONResponse(
        status_code=exc.status_code,
        content=problem.model_dump(),
        media_type="application/problem+json",
        headers=headers,
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Convert Pydantic validation errors to RFC 7807 problem details."""
    problem = ProblemDetail(
        type="https://satellite-analyst.local/errors/validation-error",
        title="Invalid Request Payload",
        status=422,
        detail="One or more fields failed validation checks.",
        instance=str(request.url),
        code="VALIDATION_FAILED",
        errors=list(exc.errors()),
    )
    req_id = getattr(request.state, "request_id", None)
    headers = {"X-Request-ID": req_id} if req_id else {}
    return JSONResponse(
        status_code=422,
        content=problem.model_dump(),
        media_type="application/problem+json",
        headers=headers,
    )


# --- Root Health and Route Mounts ---


@app.get(
    "/healthz",
    summary="Health Check",
    response_model=HealthCheckResponse,
    tags=["Health"],
)
async def healthz() -> HealthCheckResponse:
    """Kubernetes / Docker container readiness and liveness probe."""
    return HealthCheckResponse(
        status="ok",
        version=__version__,
        demo_mode=settings.demo_mode,
        timestamp=datetime.now(UTC),
    )


# Mount API Router
app.include_router(api_router)

# Mount Static Web UI
web_dir = Path("web")
if web_dir.exists():
    app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")
