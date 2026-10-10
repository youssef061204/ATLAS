"""Disabled-by-default, authenticated and bounded native experiment execution.

One supervisor process owns an execution database. A restart marks active jobs
interrupted instead of silently replaying them. Each experiment uses an isolated
child process, allowing timeout/cancellation without killing unrelated work.
"""

import hashlib
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import psutil
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from atlas import config

router = APIRouter(prefix="/api/execution", tags=["Bounded native experiments"])
TERMINAL = {"complete", "failed", "cancelled", "timed_out", "interrupted"}


def execution_sources():
    """Fingerprint the actual policy, safety, simulation and frozen parameters."""
    paths = (
        "backend/atlas/execution_v5.py",
        "backend/atlas/control.py",
        "backend/atlas/control_v2.py",
        "backend/atlas/control_v4.py",
        "backend/atlas/evaluation/network_v4.py",
        "backend/atlas/evaluation/network_v2.py",
        "backend/atlas/evaluation/network_v4_runtime.py",
        "backend/atlas/evaluation/signal_lab.py",
        "docs/signal-controller-frozen.json",
    )
    return {path: hashlib.sha256((config.ROOT / path).read_bytes()).hexdigest() for path in paths}


class ExperimentRequest(BaseModel):
    city: Literal["toronto", "london", "seattle", "austin", "calgary"]
    seed: int = Field(default=56001, ge=0, le=2147483647)
    duration_seconds: int = Field(default=120, ge=60, le=300)
    scenario: Literal["nominal", "lane_closure", "sensor_outage"] = "nominal"
    baseline: Literal["fixed", "max_pressure"] = "max_pressure"
    candidate: Literal["original_mpc", "network_mpc"] = "network_mpc"


class ExecutionStore:
    def __init__(
        self,
        root,
        daily_quota=5,
        user_active_limit=2,
        global_queue_limit=8,
        minimum_interval_seconds=5,
    ):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = self.root / "jobs.db"
        self.daily_quota, self.user_active_limit = daily_quota, user_active_limit
        self.global_queue_limit, self.minimum_interval_seconds = (
            global_queue_limit,
            minimum_interval_seconds,
        )
        with self.connection() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, owner TEXT NOT NULL, payload TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS quota (owner TEXT, day TEXT, used INTEGER, PRIMARY KEY(owner,day))"
            )

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.database, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def submit(self, owner, parameters, *, clock=None):
        clock = time.time() if clock is None else clock
        day = datetime.fromtimestamp(clock, UTC).date().isoformat()
        raw = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
        # Reproducibility identity includes immutable execution source and network.
        source = config.ROOT / "datasets/cities" / parameters["city"] / "manifest.json"
        source_digest = (
            hashlib.sha256(source.read_bytes()).hexdigest()
            if source.exists()
            else "scenario-not-restored"
        )
        sources = execution_sources()
        executable_digest = sources["backend/atlas/execution_v5.py"]
        identity = secrets.token_hex(16)
        job = {
            "id": identity,
            "state": "queued",
            "request": parameters,
            "submitted_epoch": clock,
            "progress": 0,
            "experiment_id": hashlib.sha256(
                (raw + source_digest + json.dumps(sources, sort_keys=True)).encode()
            ).hexdigest(),
            "network_manifest_sha256": source_digest,
            "execution_source_sha256": executable_digest,
            "source_sha256": sources,
            "cancel_requested": False,
            "error": None,
        }
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = [
                (account, json.loads(payload))
                for account, payload in conn.execute("SELECT owner,payload FROM jobs")
            ]
            active = [(account, value) for account, value in rows if value["state"] not in TERMINAL]
            if (
                len(active) >= self.global_queue_limit
                or sum(account == owner for account, _ in active) >= self.user_active_limit
            ):
                raise HTTPException(429, "Native experiment queue limit reached")
            previous = [value["submitted_epoch"] for account, value in rows if account == owner]
            if previous and clock - max(previous) < self.minimum_interval_seconds:
                raise HTTPException(429, "Submission rate limit reached")
            used = conn.execute(
                "SELECT used FROM quota WHERE owner=? AND day=?", (owner, day)
            ).fetchone()
            if used and used[0] >= self.daily_quota:
                raise HTTPException(429, "Daily native experiment quota reached")
            conn.execute(
                "INSERT INTO quota(owner,day,used) VALUES(?,?,1) ON CONFLICT(owner,day) DO UPDATE SET used=used+1",
                (owner, day),
            )
            conn.execute(
                "INSERT INTO jobs(id,owner,payload) VALUES(?,?,?)",
                (identity, owner, json.dumps(job)),
            )
        return job

    def get(self, identity, owner=None):
        with self.connection() as conn:
            row = conn.execute("SELECT owner,payload FROM jobs WHERE id=?", (identity,)).fetchone()
        if row is None or owner is not None and row[0] != owner:
            raise HTTPException(404, "Experiment not found")
        return json.loads(row[1])

    def update(self, identity, **changes):
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT payload FROM jobs WHERE id=?", (identity,)).fetchone()
            if row is None:
                raise ValueError("Unknown durable job")
            value = json.loads(row[0])
            if value["state"] in TERMINAL:
                return value
            value.update(changes)
            conn.execute("UPDATE jobs SET payload=? WHERE id=?", (json.dumps(value), identity))
        return value

    def recover(self):
        with self.connection() as conn:
            for identity, payload in conn.execute("SELECT id,payload FROM jobs").fetchall():
                job = json.loads(payload)
                if job["state"] not in TERMINAL:
                    job.update(
                        state="interrupted",
                        error="Supervisor restarted; resubmit explicitly",
                        finished_epoch=time.time(),
                    )
                    conn.execute(
                        "UPDATE jobs SET payload=? WHERE id=?", (json.dumps(job), identity)
                    )

    def pending(self):
        with self.connection() as conn:
            jobs = [json.loads(p) for (p,) in conn.execute("SELECT payload FROM jobs")]
        return sorted(
            (j for j in jobs if j["state"] == "queued"), key=lambda j: j["submitted_epoch"]
        )


def terminate_owned(child):
    """Terminate only the process launched for this job and its descendants."""
    try:
        parent = psutil.Process(child.pid)
        processes = parent.children(recursive=True) + [parent]
        for process in processes:
            try:
                process.terminate()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(processes, timeout=2)
        for process in alive:
            try:
                process.kill()
            except psutil.NoSuchProcess:
                pass
    except psutil.NoSuchProcess:
        pass


class ExecutionSupervisor:
    def __init__(self, store, timeout_seconds=60, memory_limit_mb=2048):
        self.store, self.timeout_seconds, self.memory_limit_mb = (
            store,
            timeout_seconds,
            memory_limit_mb,
        )
        self.stop_event = threading.Event()
        self.thread = None
        self.last_heartbeat_epoch = None

    def start(self):
        self.store.recover()
        self.thread = threading.Thread(target=self.run, daemon=True, name="atlas-bounded-execution")
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=4)

    def run(self):
        while not self.stop_event.is_set():
            self.last_heartbeat_epoch = time.time()
            pending = self.store.pending()
            if pending:
                self.execute(pending[0])
            else:
                self.stop_event.wait(0.2)

    def execute(self, job):
        identity = job["id"]
        current = self.store.update(identity, state="running", started_epoch=time.time())
        if current["state"] in TERMINAL:
            return
        environment = dict(os.environ)
        for key in ("ATLAS_EXECUTION_KEYS", "ATLAS_OPERATOR_KEY"):
            environment.pop(key, None)
        environment.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
        child = None
        started = time.monotonic()
        try:
            with (self.store.root / f"{identity}.log").open("wb") as log:
                child = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "atlas.execution_v5",
                        "--root",
                        str(self.store.root),
                        "--job",
                        identity,
                    ],
                    stdout=log,
                    stderr=log,
                    env=environment,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                while child.poll() is None:
                    self.last_heartbeat_epoch = time.time()
                    current = self.store.get(identity)
                    memory_mb = 0
                    try:
                        process = psutil.Process(child.pid)
                        for p in [process, *process.children(recursive=True)]:
                            try:
                                memory_mb += p.memory_info().rss / 1048576
                            except psutil.NoSuchProcess:
                                pass
                    except psutil.NoSuchProcess:
                        pass
                    if current["cancel_requested"] or self.stop_event.is_set():
                        terminate_owned(child)
                        self.store.update(
                            identity,
                            state="cancelled",
                            error="Native experiment cancelled",
                            finished_epoch=time.time(),
                        )
                        return
                    if (
                        time.monotonic() - started > self.timeout_seconds
                        or memory_mb > self.memory_limit_mb
                    ):
                        terminate_owned(child)
                        self.store.update(
                            identity,
                            state="timed_out" if memory_mb <= self.memory_limit_mb else "failed",
                            error="Native worker resource limit reached",
                            finished_epoch=time.time(),
                        )
                        return
                    self.stop_event.wait(0.2)
            if self.store.get(identity)["state"] not in TERMINAL:
                self.store.update(
                    identity,
                    state="failed",
                    error="Native simulation failed; inspect private worker logs",
                    finished_epoch=time.time(),
                )
        except Exception:
            if child:
                terminate_owned(child)
            self.store.update(
                identity,
                state="failed",
                error="Native worker unavailable",
                finished_epoch=time.time(),
            )


supervisor = None


def enabled():
    return os.getenv("ATLAS_EXECUTION_ENABLED", "false").lower() == "true"


def start():
    global supervisor
    if enabled():
        supervisor = ExecutionSupervisor(ExecutionStore(config.DATA / "execution-v5"))
        supervisor.start()


def stop():
    global supervisor
    if supervisor:
        supervisor.stop()
        supervisor = None


def account(request):
    if not enabled() or supervisor is None:
        raise HTTPException(
            503, "Hosted execution is disabled; genuine recorded experiments remain available"
        )
    try:
        keys = json.loads(os.getenv("ATLAS_EXECUTION_KEYS", "{}"))
    except (ValueError, TypeError):
        raise HTTPException(503, "Native execution authentication is not configured") from None
    supplied = request.headers.get("authorization", "").removeprefix("Bearer ")
    for owner, token in keys.items() if isinstance(keys, dict) else []:
        if (
            isinstance(token, str)
            and len(token) >= 16
            and secrets.compare_digest(token.encode(), supplied.encode())
        ):
            return owner
    raise HTTPException(401, "Native experiment account authorization required")


@router.get("/health")
def health():
    return {
        "enabled": enabled() and supervisor is not None,
        "public_execution_verified": False,
        "worker_heartbeat_epoch": supervisor.last_heartbeat_epoch if supervisor else None,
        "maximum_duration_seconds": 300,
        "maximum_paired_episodes": 2,
        "daily_quota_per_account": 5,
        "timeout_seconds": 60,
        "memory_limit_mb": 2048,
        "status": "native worker only" if supervisor else "disabled publicly",
    }


@router.post("/jobs", status_code=202)
def submit(value: ExperimentRequest, request: Request):
    owner = account(request)
    return supervisor.store.submit(owner, value.model_dump())


@router.get("/jobs/{identity}")
def status(identity: str, request: Request):
    owner = account(request)
    return supervisor.store.get(identity, owner)


@router.post("/jobs/{identity}/cancel")
def cancel(identity: str, request: Request):
    owner = account(request)
    job = supervisor.store.get(identity, owner)
    return supervisor.store.update(
        identity,
        cancel_requested=True,
        state="cancelled" if job["state"] == "queued" else job["state"],
        error="Native experiment cancelled" if job["state"] == "queued" else None,
    )


@router.get("/jobs/{identity}/result")
def result(identity: str, request: Request):
    owner = account(request)
    job = supervisor.store.get(identity, owner)
    if job["state"] != "complete":
        raise HTTPException(409, "Native experiment is not complete")
    path = supervisor.store.root / f"{job['id']}.json"
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != job["result_sha256"]:
        raise HTTPException(503, "Stored native result failed integrity verification")
    return json.loads(raw)


def worker(root, identity):
    from atlas.evaluation.network_v4_runtime import run_network

    store = ExecutionStore(root)
    job = store.get(identity)
    if execution_sources() != job["source_sha256"]:
        raise ValueError("Execution sources changed after submission; resubmit explicitly")
    value = ExperimentRequest(**job["request"])

    def cancelled():
        return store.get(identity)["cancel_requested"]

    runs = []
    for index, policy in enumerate((value.baseline, value.candidate)):
        runs.append(
            run_network(
                value.city,
                policy,
                value.seed,
                value.duration_seconds,
                scenario=value.scenario,
                cancel_check=cancelled,
            )
        )
        store.update(identity, progress=(index + 1) * 45)
    outcome = {
        "experiment_id": job["experiment_id"],
        "request": job["request"],
        "runs": runs,
        "scope": "New native SUMO processing on exploratory, uncalibrated city networks; no field actuation",
        "source_sha256": job["execution_source_sha256"],
        "execution_sources_sha256": job["source_sha256"],
    }
    raw = json.dumps(outcome, separators=(",", ":"), allow_nan=False).encode()
    if len(raw) > 20_000_000:
        raise ValueError("Native result exceeds storage budget")
    path = store.root / f"{identity}.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(raw)
    temporary.replace(path)
    store.update(
        identity,
        state="complete",
        progress=100,
        result_sha256=hashlib.sha256(raw).hexdigest(),
        result_bytes=len(raw),
        finished_epoch=time.time(),
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--job", required=True)
    args = parser.parse_args()
    worker(args.root, args.job)
