# Contributing to Natural-Language Satellite Image Analyst

Thank you for your interest in contributing! This project is built for rigorous Earth-observation analysis and scientific transparency. Every PR must maintain defensible geospatial accuracy, clean software architecture, and verified tests.

## Core Principle: LLM Never Computes Numbers

Before contributing, please read [ADR 0001: LLM Never Computes Numbers](docs/adr/0001-llm-never-computes-numbers.md). All spatial calculations, indices, band math, areas in hectares, thresholds, and statistics must be computed deterministically. The LLM is used strictly as a structured planner and narrative synthesizer grounded in computed values.

## Development Setup

1. **Prerequisites**:
   - Python 3.11 or 3.12
   - `uv` package manager (`pip install uv`)
   - System geospatial libraries (GDAL, GEOS, PROJ)

2. **Environment Initialization**:
   ```bash
   git clone https://github.com/sahariya-divyansh/satellite-image-analyst.git
   cd satellite-image-analyst
   uv venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   make install
   ```

3. **Pre-commit Hooks**:
   ```bash
   pre-commit install
   ```

## Development Workflow

Before submitting a Pull Request, verify:
```bash
make lint       # Ruff linting and formatting check
make typecheck  # Mypy strict type checking
make test       # Pytest unit tests and coverage report (must remain >=80%)
make evaluate   # Golden set evaluations
```

## Commit Conventions

We follow [Conventional Commits](https://www.conventionalcommits.org/):
- `feat:` new user-facing functionality or pipeline stage
- `fix:` bug fixes
- `refactor:` code restructuring without external interface changes
- `test:` adding or refactoring test suites
- `docs:` documentation improvements
- `ci:` workflow or Docker updates

## Reporting Issues & Security

- Report functional bugs or feature ideas via [GitHub Issues](https://github.com/sahariya-divyansh/satellite-image-analyst/issues).
- Security concerns can be communicated directly via maintainer contact or GitHub Security Advisories.
