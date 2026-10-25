"""FastAPI application entrypoint and middleware configuration."""

from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from satellite_analyst import __version__
from satellite_analyst.api.models import HealthCheckResponse
from satellite_analyst.api.routes import router as api_router
from satellite_analyst.errors import SatelliteAnalystError
from satellite_analyst.logging import get_logger, setup_logging

setup_logging()
logger = get_logger("satellite_analyst.api")

app = FastAPI(
    title="Natural-Language Satellite Image Analyst",
    description=(
        "Translates natural-language Earth observation queries into defensible, "
        "reproducible remote sensing pipelines with grounded statistical verification."
    ),
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(SatelliteAnalystError)
async def satellite_error_handler(_request: Request, exc: SatelliteAnalystError) -> JSONResponse:
    """Standardized error responses for domain exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


# Include API v1 router
app.include_router(api_router)


@app.get("/healthz", response_model=HealthCheckResponse, tags=["Health"])
async def healthz() -> HealthCheckResponse:
    """Kubernetes / Docker health check endpoint."""
    return HealthCheckResponse(
        status="ok",
        version=__version__,
        timestamp=datetime.now(UTC),
    )


# Mount static web UI if available
web_dir = Path(__file__).parent.parent.parent.parent / "web"
if web_dir.exists():
    app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")
