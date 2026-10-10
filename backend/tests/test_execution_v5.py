import threading

import pytest
from atlas import execution_v5
from atlas.execution_v5 import ExecutionStore, ExecutionSupervisor, ExperimentRequest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


def parameters():
    return ExperimentRequest(city="toronto").model_dump()


def test_atomic_persistent_quota_and_account_isolation(tmp_path):
    store = ExecutionStore(tmp_path, daily_quota=2, user_active_limit=8, minimum_interval_seconds=0)
    a = store.submit("a", parameters(), clock=100)
    with pytest.raises(HTTPException) as error:
        store.get(a["id"], "b")
    assert error.value.status_code == 404
    store.submit("a", parameters(), clock=110)
    restored = ExecutionStore(
        tmp_path, daily_quota=2, user_active_limit=8, minimum_interval_seconds=0
    )
    with pytest.raises(HTTPException, match="Daily"):
        restored.submit("a", parameters(), clock=120)
    restored.recover()
    assert restored.get(a["id"])["state"] == "interrupted"
    assert restored.submit("b", parameters(), clock=130)["state"] == "queued"


def test_concurrent_submissions_cannot_exceed_global_queue(tmp_path):
    store = ExecutionStore(tmp_path, global_queue_limit=1, minimum_interval_seconds=0)
    accepted, rejected = [], []

    def submit(owner):
        try:
            accepted.append(store.submit(owner, parameters()))
        except HTTPException as exc:
            rejected.append(exc.status_code)

    threads = [threading.Thread(target=submit, args=(str(i),)) for i in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(accepted) == 1
    assert rejected == [429] * 5


def test_disabled_and_unauthorized_routes_fail_closed(tmp_path, monkeypatch):
    app = FastAPI()
    app.include_router(execution_v5.router)
    client = TestClient(app)
    monkeypatch.setenv("ATLAS_EXECUTION_ENABLED", "false")
    for url in ("/api/execution/jobs/x", "/api/execution/jobs/x/result"):
        assert client.get(url).status_code == 503
    assert client.post("/api/execution/jobs", json=parameters()).status_code == 503
    assert client.post("/api/execution/jobs/x/cancel").status_code == 503
    assert client.get("/api/execution/health").json()["enabled"] is False
    monkeypatch.setenv("ATLAS_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("ATLAS_EXECUTION_KEYS", '{"test-user":"local-v5-verification-only"}')
    supervisor = ExecutionSupervisor(ExecutionStore(tmp_path))
    monkeypatch.setattr(execution_v5, "supervisor", supervisor)
    assert client.post("/api/execution/jobs", json=parameters()).status_code == 401
    headers = {"Authorization": "Bearer local-v5-verification-only"}
    accepted = client.post("/api/execution/jobs", json=parameters(), headers=headers)
    assert accepted.status_code == 202
    identity = accepted.json()["id"]
    assert (
        client.post(f"/api/execution/jobs/{identity}/cancel", headers=headers).json()["state"]
        == "cancelled"
    )
    assert (
        client.post(
            "/api/execution/jobs", json={**parameters(), "duration_seconds": 301}, headers=headers
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/execution/jobs",
            json={**parameters(), "city": "unauthorized-network"},
            headers=headers,
        ).status_code
        == 422
    )


def test_timeout_terminates_only_owned_real_worker_process(tmp_path):
    store = ExecutionStore(tmp_path)
    job = store.submit("test", parameters())
    supervisor = ExecutionSupervisor(store, timeout_seconds=0.00001)
    supervisor.execute(job)
    result = store.get(job["id"])
    assert result["state"] == "timed_out"
    assert result["error"] == "Native worker resource limit reached"
