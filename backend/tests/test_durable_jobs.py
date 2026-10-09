import pytest
from atlas.api import app
from atlas.evaluation.network_v3 import SimulationCancelled
from atlas.operations import (
    cancellation_requested,
    job_status,
    persist_job,
    recover_jobs,
    run_job,
    worker_owner,
)
from fastapi.testclient import TestClient


def test_worker_restart_keeps_completed_records_and_marks_unfinished_as_interrupted(database):
    for identity, state in [("a", "complete"), ("b", "running"), ("c", "queued")]:
        persist_job(
            {
                "id": identity,
                "state": state,
                "worker_session": "older-worker",
                "request": {"city": "toronto"},
            }
        )
    recover_jobs()
    assert job_status("a")["state"] == "complete"
    assert job_status("b")["state"] == "interrupted" and job_status("c")["state"] == "interrupted"
    assert job_status("b")["request"]["city"] == "toronto"


def test_cancel_requires_operator_and_cannot_reanimate_a_completed_job(database, monkeypatch):
    monkeypatch.setenv("ATLAS_OPERATOR_KEY", "test-only")
    identity = "1" * 32
    persist_job({"id": identity, "state": "queued", "worker_session": worker_owner})
    with TestClient(app) as client:
        assert client.post(f"/api/operations/jobs/{identity}/cancel").status_code == 401
        r = client.post(
            f"/api/operations/jobs/{identity}/cancel", headers={"Authorization": "Bearer test-only"}
        )
        assert r.json()["state"] == "cancel_requested" and cancellation_requested(identity)
        with pytest.raises(SimulationCancelled):
            run_job(identity, None, ())
        persist_job({"id": identity, "state": "complete", "result_path": "actual-output"})
        persist_job({"id": identity, "state": "cancel_requested"})
        assert job_status(identity)["state"] == "complete"
