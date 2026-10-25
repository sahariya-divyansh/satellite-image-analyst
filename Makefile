.PHONY: help install lint format typecheck test evaluate run docker-build clean

help:
	@echo "Available commands:"
	@echo "  make install      - Install package and dev dependencies with uv"
	@echo "  make lint         - Run ruff linter and format checking"
	@echo "  make format       - Format code using ruff"
	@echo "  make typecheck    - Run mypy strict type checking"
	@echo "  make test         - Run unit & offline integration tests with coverage"
	@echo "  make evaluate     - Run golden planner & water validation evaluations"
	@echo "  make run          - Launch the FastAPI development server"
	@echo "  make docker-build - Build production Docker image"
	@echo "  make clean        - Remove caches, build artifacts, and test reports"

install:
	uv pip install -e ".[dev]"

lint:
	ruff check .
	ruff format --check .

format:
	ruff format .
	ruff check --fix .

typecheck:
	mypy src tests

test:
	pytest -v --cov=src/satellite_analyst --cov-report=term-missing --cov-report=xml:coverage.xml tests/unit

evaluate:
	python evaluation/run_planner_eval.py
	python evaluation/run_water_eval.py

run:
	uvicorn satellite_analyst.api.main:app --host 0.0.0.0 --port 8000 --reload

docker-build:
	docker build -t satellite-image-analyst:latest .

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov coverage.xml dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
