# Documentation Index

Welcome to the documentation for **Natural-Language Satellite Image Analyst**.

This index provides links and summaries for all technical specifications, architectural designs, methodology notes, and reproducible evaluation benchmarks.

---

## Core Documentation

- **[System Architecture](architecture.md)**
  Detailed system architecture, boundary contracts between the probabilistic LLM planner and deterministic geospatial pipeline, dataflow pipelines, and claim grounding verification.

- **[Remote Sensing Methodology](methodology.md)**
  Comprehensive explanation of Earth observation algorithms: Sentinel-2 Level-2A surface reflectance, same-season median compositing, per-item BOA offset calibration across baseline changes, MNDWI calculation, Otsu adaptive thresholding, equal-area spatial reprojection, and 3-class polygon vectorization.

- **[Evaluation & Benchmarks](evaluation.md)**
  Reproducible benchmark protocols and real execution results:
  - Natural-language query planner generalization (Dev set $n=42$, Held-out v1 $n=30$, Held-out v2 $n=20$)
  - Reference ground truth validation against JRC Global Surface Water across 3 hydrological regimes (Raipur, Bhopal, Jodhpur)
  - Multi-year inter-annual trajectory for Raipur (2018–2025) with leave-one-out noise analysis
  - Stable-pixel radiometric continuity audit across the January 2022 ESA baseline transition

- **[Limitations & What We Do Not Claim](limitations.md)**
  Clear definitions of engineering boundaries, minimum mapping units ($0.1\,\text{ha}$), monsoon cloud obscuration, turbidity caveats, non-regulatory status, and experimental CLIP/SAM architectural stubs.

- **[Architecture Decision Records (ADRs)](adr/0001-llm-never-computes-numbers.md)**
  - [ADR 0001: The LLM Never Computes Numbers](adr/0001-llm-never-computes-numbers.md) — Fundamental design decision establishing a hard boundary between probabilistic natural language understanding and deterministic scientific geocomputation.

- **[Release Notes v0.1.0](release_notes_v0.1.0.md)**
  Release notes, new capabilities, and benchmark highlights for the v0.1.0 release.
