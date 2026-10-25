FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

# Install geospatial runtime libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast, reliable package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Create non-root user
RUN groupadd -g 10001 appuser && \
    useradd -u 10001 -g appuser -m -s /bin/bash appuser

WORKDIR /app

# Copy dependency configuration first to leverage Docker layer caching
COPY pyproject.toml /app/
RUN uv pip install --system -e .

# Copy application source code and web assets
COPY src/ /app/src/
COPY web/ /app/web/
COPY evaluation/ /app/evaluation/

# Reinstall package in editable/system mode to register CLI and metadata
RUN uv pip install --system --no-deps -e .

# Create cache and data directories with proper permissions
RUN mkdir -p /app/data/cache && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/healthz || exit 1

ENTRYPOINT ["uvicorn", "satellite_analyst.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
