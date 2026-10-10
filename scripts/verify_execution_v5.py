"""Real local SUMO API lifecycle verification; synthetic verification credentials only."""

import hashlib
import json
import os
import time
from pathlib import Path

# This verification gets its own storage and never mutates another worker's jobs.
os.environ["ATLAS_DATA_DIR"] = str(Path("data/worker-v5-native-smoke").resolve())
os.environ["ATLAS_EXECUTION_ENABLED"] = "true"
os.environ["ATLAS_EXECUTION_KEYS"] = json.dumps(
    {"verification-a": "local-v5-verification-only", "verification-b": "local-v5-second-verifier"}
)

from atlas.api import app  # noqa: E402
from atlas.execution_v5 import ExperimentRequest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def main():
    headers = {"Authorization": "Bearer local-v5-verification-only"}
    other = {"Authorization": "Bearer local-v5-second-verifier"}
    began = time.perf_counter()
    with TestClient(app) as client:
        health = client.get("/api/execution/health").json()
        assert health["enabled"] and not health["public_execution_verified"]
        parameters = ExperimentRequest(city="toronto", seed=56001).model_dump()
        assert client.post("/api/execution/jobs", json=parameters).status_code == 401
        accepted = client.post("/api/execution/jobs", json=parameters, headers=headers)
        assert accepted.status_code == 202, accepted.status_code
        job = accepted.json()
        identity = job["id"]
        assert client.get(f"/api/execution/jobs/{identity}", headers=other).status_code == 404
        until = time.monotonic() + 65
        while time.monotonic() < until:
            status = client.get(f"/api/execution/jobs/{identity}", headers=headers).json()
            if status["state"] in {"complete", "failed", "timed_out", "cancelled"}:
                break
            time.sleep(0.1)
        assert status["state"] == "complete", status.get("error")
        result = client.get(f"/api/execution/jobs/{identity}/result", headers=headers)
        assert result.status_code == 200
        value = result.json()
        assert len(value["runs"]) == 2
        assert all(
            r["seed"] == 56001 and r["metrics"]["modeled_safety_violations"] == 0
            for r in value["runs"]
        )
        for key in ("network_sha256", "routes_sha256", "initial_states", "duration", "scenario"):
            assert value["runs"][0][key] == value["runs"][1][key]
        assert (
            client.post("/api/execution/jobs", json=parameters, headers=headers).status_code == 429
        )
        cancelled = client.post(
            "/api/execution/jobs", json={**parameters, "seed": 56002}, headers=other
        )
        assert cancelled.status_code == 202
        cid = cancelled.json()["id"]
        assert client.post(f"/api/execution/jobs/{cid}/cancel", headers=other).status_code == 200
        until = time.monotonic() + 10
        while time.monotonic() < until:
            cancelled_state = client.get(f"/api/execution/jobs/{cid}", headers=other).json()[
                "state"
            ]
            if cancelled_state == "cancelled":
                break
            time.sleep(0.1)
        assert cancelled_state == "cancelled"
    artifact = {
        "schema_version": "atlas-native-worker-verification-5.0",
        "verified_at": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat(),
        "new_native_processing": True,
        "public_execution_verified": False,
        "verification_wall_s": time.perf_counter() - began,
        "checks": {
            "unauthorized_rejected": True,
            "cross_account_read_rejected": True,
            "real_paired_sumo_completed": True,
            "rate_limit_enforced": True,
            "cancellation_verified": True,
            "result_integrity_verified": True,
            "modeled_safety_violations": 0,
        },
        "experiment_id": value["experiment_id"],
        "execution_sources_sha256": value["execution_sources_sha256"],
        "parameters": parameters,
        "runs": [
            {
                "policy": r["policy"],
                "seed": r["seed"],
                "metrics": r["metrics"],
                "network_sha256": r["network_sha256"],
                "routes_sha256": r["routes_sha256"],
            }
            for r in value["runs"]
        ],
        "worker_source_sha256": hashlib.sha256(
            Path("backend/atlas/execution_v5.py").read_bytes()
        ).hexdigest(),
        "verifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scope": "Private native verification with synthetic credentials; exploratory SUMO, not hosted public execution or field benefit",
    }
    output = Path("data/worker-v5-native-smoke/verification.json")
    output.write_text(json.dumps(artifact, indent=2, allow_nan=False), encoding="utf-8")
    print(
        "Verified actual bounded native SUMO worker, account isolation, quota and cancellation",
        flush=True,
    )


if __name__ == "__main__":
    main()
