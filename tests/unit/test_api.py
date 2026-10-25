"""Tests for FastAPI endpoints, asynchronous job manager, and RFC 7807 problem details."""

import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from satellite_analyst.api.jobs import FakePipelineRunner, JobManager
from satellite_analyst.api.main import app
from satellite_analyst.config import Settings


def test_healthz_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "timestamp" in data


def test_examples_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/v1/examples")
    assert response.status_code == 200
    data = response.json()
    assert "examples" in data
    assert len(data["examples"]) >= 3
    assert any(e["id"] == "raipur_2023_2025" and e["is_cached_demo"] for e in data["examples"])


def test_submit_query_clarification_flow() -> None:
    client = TestClient(app)
    # Single year water change query requires clarification
    res = client.post(
        "/v1/query",
        json={"query": "Show water change near Raipur in 2023"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "clarification_required"
    assert "clarification_question" in data
    assert len(data["clarification_question"]) > 5


def test_submit_query_out_of_archive_bounds() -> None:
    client = TestClient(app)
    # 2014 precedes 2017 Sentinel-2 L2A archive bounds
    res = client.post(
        "/v1/query",
        json={"query": "Water change near Raipur between 2014 and 2018"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "clarification_required"
    assert "2017 onwards" in data["clarification_question"]


def test_submit_query_validation_errors() -> None:
    client = TestClient(app)

    # Empty / too short
    res_short = client.post("/v1/query", json={"query": "ab"})
    assert res_short.status_code == 422
    assert res_short.headers["content-type"] == "application/problem+json"
    p_short = res_short.json()
    assert p_short["code"] == "VALIDATION_FAILED"

    # Too long (>500 chars)
    long_query = "water change " * 50
    res_long = client.post("/v1/query", json={"query": long_query})
    assert res_long.status_code == 422
    assert res_long.headers["content-type"] == "application/problem+json"

    # Control characters
    ctrl_query = "water change\x00\x01\x02 near Raipur"
    res_ctrl = client.post("/v1/query", json={"query": ctrl_query})
    # Control chars should be stripped, so if enough printable chars remain it succeeds or requires clarification
    assert res_ctrl.status_code in [200, 202]


def test_job_lifecycle_with_fake_runner(tmp_path: Path) -> None:
    # Configure test job manager with FakePipelineRunner and tmp jobs_dir
    test_settings = Settings(
        app_env="testing",
        jobs_dir=tmp_path / "jobs",
        max_concurrent_jobs=2,
        job_queue_limit=5,
        rate_limit_per_minute=200,
    )
    test_manager = JobManager(settings=test_settings, runner=FakePipelineRunner())

    # Monkeypatch global job_manager in routes and main
    from satellite_analyst.api import jobs, routes

    orig_mgr = jobs.job_manager
    jobs.job_manager = test_manager
    routes.job_manager = test_manager

    try:
        client = TestClient(app)
        res = client.post(
            "/v1/query",
            json={"query": "Show all water bodies that expanded near Raipur between 2023 and 2025"},
        )
        assert res.status_code == 202
        data = res.json()
        assert data["status"] == "accepted"
        job_id = data["job_id"]
        assert "job_url" in data

        # Poll until complete
        for _ in range(20):
            res_status = client.get(f"/v1/jobs/{job_id}")
            assert res_status.status_code == 200
            status_data = res_status.json()
            if status_data["status"] == "succeeded":
                break
            time.sleep(0.05)

        assert status_data["status"] == "succeeded"
        assert status_data["progress_percent"] == 100
        assert status_data["stats"]["net_change_ha"] == 50.0

        # Plan endpoint
        res_plan = client.get(f"/v1/jobs/{job_id}/plan")
        assert res_plan.status_code == 200
        assert res_plan.json()["aoi"]["place"].lower() == "raipur"

        # Layers list
        res_layers = client.get(f"/v1/jobs/{job_id}/layers")
        assert res_layers.status_code == 200
        layers_list = res_layers.json()["layers"]
        assert "gained" in layers_list
        assert "persistent" in layers_list

        # GeoJSON layer stream
        res_geo = client.get(f"/v1/jobs/{job_id}/layers/gained.geojson")
        assert res_geo.status_code == 200
        assert res_geo.headers["content-type"] == "application/geo+json"
        geo_data = res_geo.json()
        assert geo_data["type"] == "FeatureCollection"
        assert len(geo_data["features"]) > 0

        # Report markdown & html
        res_rep_md = client.get(f"/v1/jobs/{job_id}/report?format=md")
        assert res_rep_md.status_code == 200
        assert "# Analysis Report" in res_rep_md.text

        res_rep_html = client.get(f"/v1/jobs/{job_id}/report?format=html")
        assert res_rep_html.status_code == 200
        assert "<!DOCTYPE html>" in res_rep_html.text

        # Deliverable download endpoints
        res_dl_csv = client.get(f"/v1/jobs/{job_id}/download/csv")
        assert res_dl_csv.status_code == 200
        assert "waterbody_id" in res_dl_csv.text

        res_dl_geo = client.get(f"/v1/jobs/{job_id}/download/geojson")
        assert res_dl_geo.status_code == 200

        res_dl_tif = client.get(f"/v1/jobs/{job_id}/download/geotiff")
        assert res_dl_tif.status_code == 200

    finally:
        jobs.job_manager = orig_mgr
        routes.job_manager = orig_mgr


def test_path_traversal_protection() -> None:
    client = TestClient(app)
    # Attempt path traversal in layer name
    res = client.get("/v1/jobs/test-id/layers/../../etc/passwd.geojson")
    assert res.status_code in [400, 404]
    p = res.json()
    assert "INVALID_LAYER" in p.get("code", "") or res.status_code == 404


def test_job_not_found_problem_details() -> None:
    client = TestClient(app)
    res = client.get("/v1/jobs/nonexistent-uuid-12345")
    assert res.status_code == 404
    assert res.headers["content-type"] == "application/problem+json"
    problem = res.json()
    assert problem["status"] == 404
    assert problem["code"] == "JOB_NOT_FOUND"
    assert "nonexistent-uuid-12345" in problem["detail"]


def test_queue_concurrency_limit(tmp_path: Path) -> None:
    test_settings = Settings(
        app_env="testing",
        jobs_dir=tmp_path / "jobs",
        max_concurrent_jobs=1,
        job_queue_limit=2,
    )

    class BlockingRunner(FakePipelineRunner):
        def run(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            time.sleep(0.5)
            return super().run(*args, **kwargs)

    test_mgr = JobManager(settings=test_settings, runner=BlockingRunner())
    from satellite_analyst.planner.rule_based import RuleBasedPlanner

    planner = RuleBasedPlanner()
    plan = planner.parse_query(
        "Show all water bodies that expanded near Raipur between 2023 and 2025"
    )

    # Fill queue to limit (2 jobs)
    test_mgr.create_job("query 1", plan)
    test_mgr.create_job("query 2", plan)

    # 3rd job exceeds queue limit
    import pytest

    from satellite_analyst.errors import QueueLimitExceededError

    with pytest.raises(QueueLimitExceededError):
        test_mgr.create_job("query 3", plan)


def test_disk_persistence_and_recovery(tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    test_settings = Settings(app_env="testing", jobs_dir=jobs_dir)
    mgr1 = JobManager(settings=test_settings, runner=FakePipelineRunner())

    from satellite_analyst.planner.rule_based import RuleBasedPlanner

    plan = RuleBasedPlanner().parse_query(
        "Show all water bodies that expanded near Raipur between 2023 and 2025"
    )
    job_id = mgr1.create_job("persistence test", plan)

    # Wait for execution
    for _ in range(20):
        if mgr1.get_job(job_id)["status"] == "succeeded":
            break
        time.sleep(0.05)

    assert (jobs_dir / job_id / "job_state.json").exists()

    # Create new JobManager simulating server restart
    mgr2 = JobManager(settings=test_settings, runner=FakePipelineRunner())
    recovered_job = mgr2.get_job(job_id)
    assert recovered_job["job_id"] == job_id
    assert recovered_job["status"] == "succeeded"
    assert recovered_job["stats"]["net_change_ha"] == 50.0


def test_x_request_id_tracing_and_latency_headers() -> None:
    client = TestClient(app)
    custom_id = "trace-custom-uuid-999"
    res = client.get("/healthz", headers={"X-Request-ID": custom_id})
    assert res.status_code == 200
    assert res.headers.get("X-Request-ID") == custom_id
    assert "X-Response-Time-Ms" in res.headers


def test_real_pipeline_runner_demo_mode(tmp_path: Path) -> None:
    from satellite_analyst.api.jobs import RealPipelineRunner
    from satellite_analyst.planner.rule_based import RuleBasedPlanner

    plan = RuleBasedPlanner().parse_query(
        "Show all water bodies that expanded near Raipur between 2023 and 2025"
    )
    runner = RealPipelineRunner(demo_mode=True)
    job_dir = tmp_path / "raipur_demo_job"
    stages = []

    res = runner.run(
        job_id="demo-job-1",
        query="test query",
        plan=plan,
        job_dir=job_dir,
        update_stage=lambda msg, pct: stages.append((msg, pct)),
    )
    assert res["is_demo"] is True
    assert "stats" in res
    assert (job_dir / "report.md").exists()
    assert (job_dir / "report.html").exists()
    assert (job_dir / "layers" / "gained.geojson").exists()


def test_rate_limit_middleware() -> None:
    from satellite_analyst.api import main

    main._rate_limit_history.clear()
    orig_limit = main.settings.rate_limit_per_minute
    main.settings.rate_limit_per_minute = 5
    client = TestClient(app)

    try:
        # 5 fast requests ok
        for _ in range(5):
            r = client.get("/v1/examples")
            assert r.status_code == 200

        # 6th request triggers rate limit
        r_over = client.get("/v1/examples")
        assert r_over.status_code == 429
        assert r_over.headers["content-type"] == "application/problem+json"
        assert r_over.json()["code"] == "RATE_LIMIT_EXCEEDED"
    finally:
        main.settings.rate_limit_per_minute = orig_limit


def test_coordinate_literal_geocoding() -> None:
    from satellite_analyst.planner.geocode import GeocodeService

    geocoder = GeocodeService()
    res = geocoder.geocode("21.1500°N, 79.0800°E", radius_km=10.0)
    assert res.source == "coordinate_literal"
    assert abs(res.lat - 21.15) < 0.001
    assert abs(res.lon - 79.08) < 0.001
    assert res.bbox is not None


def test_prune_stale_jobs(tmp_path: Path) -> None:
    from datetime import UTC, datetime, timedelta

    jobs_dir = tmp_path / "prune_jobs"
    test_settings = Settings(app_env="testing", jobs_dir=jobs_dir, job_ttl_hours=1)
    mgr = JobManager(settings=test_settings, runner=FakePipelineRunner())

    from satellite_analyst.planner.rule_based import RuleBasedPlanner

    plan = RuleBasedPlanner().parse_query(
        "Show all water bodies that expanded near Raipur between 2023 and 2025"
    )
    jid = mgr.create_job("stale test", plan)

    # Artificially age the job
    mgr._jobs[jid]["created_at"] = datetime.now(UTC) - timedelta(hours=2)
    mgr.prune_stale_jobs()
    assert jid not in mgr._jobs
