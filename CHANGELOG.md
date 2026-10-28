# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-10-28

### Added
- Natural language query planner supporting regex/keyword parsing and LLM backends (Gemini, OpenAI, Ollama) with strict Pydantic plan validation.
- STAC client querying Microsoft Planetary Computer for Sentinel-2 Level-2A surface reflectance data.
- Temporal median compositing with SCL cloud/shadow filtering and automatic per-scene BOA offset correction (`-1000 DN`) for ESA baseline $\ge 04.00$.
- Modified Normalized Difference Water Index (MNDWI) calculation with 10m spatial resampling.
- Adaptive thresholding (Otsu bimodality diagnostics) and 3-class change categorization (Persistent, Expansion, Contraction).
- Local equal-area UTM spatial reprojection and contiguous vector polygon extraction with $0.1\,\text{ha}$ minimum mapping unit.
- Claim Grounding Verifier cross-checking LLM narrative reports against deterministic pipeline outputs with numeric tolerance checks.
- Interactive Leaflet-based Web UI and FastAPI backend supporting layer toggles, statistical drawers, and offline `DEMO_MODE`.
- JRC Global Surface Water validation harness supporting automated Planetary Computer STAC retrieval, 50% majority aggregation, boundary exclusion, block-bootstrap 95% CIs, and size stratification across Raipur, Bhopal, and Jodhpur.
- Multi-year inter-annual time-series analysis (Raipur 2018–2025) and stable-pixel radiometric continuity audit.
- Independent stratified 150-point sample validation template for expert ground truth verification.
- Comprehensive documentation suite: Architecture, Methodology, Evaluation & Benchmarks, Limitations, ADR 0001, Documentation Index, and Release Notes.
- Dockerfile, docker-compose orchestration, and GitHub Actions CI.
