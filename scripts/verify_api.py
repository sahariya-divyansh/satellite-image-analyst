"""Verification script to submit live query, poll status, and fetch artifacts."""

import json
import time

import httpx

client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=30.0)

# 1. Submit Query
query_payload = {"query": "Show all water bodies that expanded near Raipur between 2023 and 2025."}
resp = client.post("/v1/query", json=query_payload)
print("POST /v1/query status:", resp.status_code)
data = resp.json()
print("Response JSON:", json.dumps(data, indent=2))

job_id = data.get("job_id")
assert job_id, f"No job_id returned! Response was {data}"

# 2. Poll /v1/jobs/{id}
for _ in range(30):
    time.sleep(0.5)
    job_status = client.get(f"/v1/jobs/{job_id}").json()
    print(
        f"Job {job_id}: status={job_status['status']} "
        f"progress={job_status['progress_percent']}% stage={job_status['stage']}"
    )
    if job_status["status"] in ("succeeded", "failed"):
        break

# 3. Fetch plan
plan_resp = client.get(f"/v1/jobs/{job_id}/plan")
print("GET /plan status:", plan_resp.status_code)
print("Plan summary:", json.dumps(plan_resp.json(), indent=2)[:400], "...")

# 4. Fetch layers
layers_resp = client.get(f"/v1/jobs/{job_id}/layers")
print("GET /layers status:", layers_resp.status_code)
print("Layers list:", json.dumps(layers_resp.json(), indent=2))

# 5. Fetch report extract
report_resp = client.get(f"/v1/jobs/{job_id}/report")
print("GET /report status:", report_resp.status_code)
print("Report Preview (first 500 chars):\n", report_resp.text[:500])
