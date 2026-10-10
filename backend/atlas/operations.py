"""Persisted, bounded advisory workflow. No real traffic hardware actuation."""

import base64
import hashlib
import json
import logging
import os
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from functools import partial

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from atlas import config
from atlas.cities import FeedClient, city_configs, inspect_city, now
from atlas.control_v2 import RiskConfig
from atlas.intelligence import DemandAssumptions
from atlas.scene import SceneRegion
from atlas.state import CountFilter

router = APIRouter(prefix="/api/operations", tags=["City advisory operations"])
ingestion_slots = threading.BoundedSemaphore(2)
refresh_lock = threading.Lock()
last_refresh = {}
worker_pool = None
simulation_slots = threading.BoundedSemaphore(2)
simulation_jobs = {}
job_futures = {}
worker_owner = secrets.token_hex(16)
log = logging.getLogger("atlas.operations")
perception_lock = threading.Lock()
perception_model = None
camera_refresh = {}


@contextmanager
def connection():
    conn = sqlite3.connect(config.DATA / "operations.db", timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS observations (id TEXT PRIMARY KEY, city TEXT, payload TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS approvals (id INTEGER PRIMARY KEY, run_id TEXT, decision TEXT, actor TEXT, created_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS city_reports (city TEXT PRIMARY KEY, payload TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS scene_regions (revision INTEGER PRIMARY KEY AUTOINCREMENT, city TEXT, camera TEXT, payload TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS simulation_job_records (id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def require_operator(request):
    token = os.getenv("ATLAS_OPERATOR_KEY")
    supplied = request.headers.get("authorization", "").removeprefix("Bearer ")
    if not token:
        raise HTTPException(
            503,
            "Operational writes disabled: configure ATLAS_OPERATOR_KEY; public browsing remains read-only",
        )
    if not secrets.compare_digest(token, supplied):
        raise HTTPException(401, "Operator authorization required")
    return "authorized_operator"


def evidence(filename):
    path = config.ARTIFACTS / "cities" / filename
    if not path.exists():
        raise HTTPException(409, "Run the city-source/network/benchmark preparation command first")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/cities")
def cities():
    value = evidence("source-health.json")
    with connection() as conn:
        reports = {
            city: json.loads(payload)
            for city, payload in conn.execute("SELECT city,payload FROM city_reports")
        }
    value["cities"] = [reports.get(c["city"], c) for c in value["cities"]]
    return value


@router.get("/networks")
def networks():
    return evidence("networks.json")


@router.get("/summary-v4")
def summary_v4():
    from atlas.evidence_v4 import benchmark_summary

    return benchmark_summary()


@router.get("/cities/{city}/evidence-v4")
def city_evidence_v4(city: str):
    from atlas.evidence_v4 import CITIES, city_summary

    if city not in CITIES:
        raise HTTPException(404, "Unknown supported city")
    return city_summary(city)


@router.get("/experiments")
def experiments():
    return evidence("experiments.json")


@router.get("/intelligence")
def intelligence():
    return evidence("toronto-golden-path.json")


@router.get("/intelligence/context")
def intelligence_context():
    return evidence("toronto-intelligence.json")


@router.get("/intelligence/smoke")
def city_intelligence_smoke():
    return evidence("city-intelligence-smoke.json")


@router.get("/intelligence/smoke-v4")
def city_intelligence_smoke_v4():
    return evidence("v4/intelligence-smoke.json")


@router.get("/intelligence/{experiment_id}")
def intelligence_result(experiment_id: str):
    import re

    if not re.fullmatch(r"[a-f0-9]{24}", experiment_id):
        raise HTTPException(404, "Unknown completed intelligence experiment")
    recorded = evidence("toronto-golden-path.json")
    if experiment_id == recorded["id"]:
        return recorded
    initial = evidence("toronto-golden-path-initial.json")
    if experiment_id == initial["id"]:
        return initial
    v4 = config.ARTIFACTS / "cities/v4/intelligence-smoke.json"
    if v4.exists():
        for record in json.loads(v4.read_text(encoding="utf-8"))["records"]:
            for attempt in record["attempts"]:
                result = attempt.get("experiment")
                if result and result["id"] == experiment_id:
                    return result
    for record in evidence("city-intelligence-smoke.json")["records"]:
        for attempt in record["attempts"]:
            result = attempt.get("experiment")
            if result and result["id"] == experiment_id:
                return result
    path = config.DATA / f"intelligence-{experiment_id}.json"
    if not path.exists():
        raise HTTPException(404, "Completed intelligence experiment unavailable on this server")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/counts/toronto")
def official_counts():
    return evidence("toronto-counts.json")


@router.get("/traffic-context")
def traffic_context():
    return evidence("traffic-context.json")


@router.get("/visual-flow")
def visual_flow_evidence():
    return evidence("visual-flow.json")


@router.get("/models/vision")
def vision_model_evidence():
    return evidence("vision-v3.json")


@router.get("/scenes/{city}/{camera_id}")
def scene_regions(city: str, camera_id: str):
    with connection() as conn:
        rows = conn.execute(
            "SELECT revision,payload FROM scene_regions WHERE city=? AND camera=? ORDER BY revision DESC LIMIT 50",
            (city, camera_id),
        ).fetchall()
    return {
        "regions": [{"revision": revision, **json.loads(payload)} for revision, payload in rows],
        "scope": "Operator-supplied image regions, not agency-validated lanes or physical surveys",
    }


@router.post("/scenes")
def save_scene_region(body: SceneRegion, request: Request):
    actor = require_operator(request)
    network = next(
        (n for n in evidence("networks.json")["networks"] if n["city"] == body.city), None
    )
    if network is None or body.road_id not in {r["id"] for r in network["roads"]}:
        raise HTTPException(422, "Choose a real road in the imported city corridor")
    with connection() as conn:
        row = conn.execute(
            "SELECT payload FROM observations WHERE city=? AND json_extract(payload,'$.id')=? LIMIT 1",
            (body.city, body.observation_id),
        ).fetchone()
        observation = json.loads(row[0]) if row else None
        published = evidence("toronto-intelligence.json")
        if (
            observation is None
            and body.city == published["city"]
            and body.observation_id == published["observation"]["id"]
        ):
            observation = published["observation"]
        if observation is None or observation["camera_id"] != body.camera_id:
            raise HTTPException(422, "A known processed observation from this camera is required")
        from atlas.scene import assign_detections

        detections = assign_detections(body, observation.get("detections", []))
        record = {
            **body.model_dump(),
            "actor": actor,
            "created_at": now(),
            "status": "operator_corrected_not_independently_validated",
            "visible_detections_in_region": len(detections),
            "queue_vehicles": None,
            "calibration": "Image region only; no physical calibration or snapshot motion inferred",
        }
        cursor = conn.execute(
            "INSERT INTO scene_regions(city,camera,payload) VALUES(?,?,?)",
            (body.city, body.camera_id, json.dumps(record, allow_nan=False)),
        )
        from atlas.intelligence import assimilate, count_forecast
        from atlas.scene import region_observation

        derived = region_observation(body, observation, cursor.lastrowid)
        state = assimilate(derived)
        return {
            "revision": cursor.lastrowid,
            **record,
            "derived_observation": derived,
            "estimated_state": state,
            "forecast": count_forecast(state),
        }


@router.get("/models/forecast")
def forecasting_model():
    return evidence("forecast-v3.json")


@router.get("/models/graph")
def graph_model_evidence():
    return evidence("graph-forecast.json")


@router.get("/models/city")
def city_forecast_evidence():
    return evidence("v4/city-forecast.json")


@router.get("/models/vision-v4")
def vision_v4_evidence():
    return evidence("v4/perception.json")


@router.get("/control-v4")
def control_v4_evidence():
    return evidence("v4/controller-replay.json")


@router.get("/control-v4/assessment")
def control_v4_assessment():
    return evidence("v4/controller-assessment.json")


@router.post("/models/city/infer")
def city_count_inference(body: dict, request: Request):
    require_operator(request)
    from pydantic import ValidationError

    from atlas.city_runtime_v4 import CityCountInput, predict_city_counts

    try:
        value = CityCountInput.model_validate(body)
        return predict_city_counts(value)
    except ValidationError as exc:
        raise HTTPException(422, exc.errors(include_url=False, include_input=False)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(503, "Trusted native city forecasting models unavailable") from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


class ForecastInput(BaseModel):
    history_mph: list[list[float | None]] = Field(min_length=207, max_length=207)
    last_observation_at: datetime
    horizon_minutes: int = Field(ge=5, le=30, default=5)


@router.post("/models/forecast/infer")
@router.post("/models/graph/infer")
def forecast_inference(body: ForecastInput, request: Request):
    require_operator(request)
    if body.last_observation_at.tzinfo is not None:
        raise HTTPException(
            422,
            "Supply a naive timestamp in the METR-LA dataset's native clock convention; timezone conversion is not validated",
        )
    if any(len(row) != 6 for row in body.history_mph):
        raise HTTPException(
            422, "Each sensor must supply six chronological samples at five-minute cadence"
        )
    import math

    if any(
        v is not None and (not math.isfinite(v) or not 0 <= v <= 100)
        for row in body.history_mph
        for v in row
    ):
        raise HTTPException(422, "History must contain finite speeds in 0–100 mph or null")
    from atlas.forecast_v3 import predict_evaluated
    from atlas.graph_runtime import predict_graph

    try:
        predictor = (
            predict_graph if request.url.path.endswith("/graph/infer") else predict_evaluated
        )
        return predictor(
            body.history_mph,
            body.last_observation_at.replace(tzinfo=None).isoformat(),
            body.horizon_minutes,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/cities/{city}/cameras/{camera_id}/observe")
def observe_camera(city: str, camera_id: str, request: Request):
    """Authorized immediate viewing. Image never enters the DB or source artifacts."""
    require_operator(request)
    report = next((r for r in cities()["cities"] if r["city"] == city), None)
    camera = next((c for c in report["cameras"] if c["id"] == camera_id), None) if report else None
    if camera is None:
        raise HTTPException(404, "Unknown official camera")
    if not perception_lock.acquire(blocking=False):
        raise HTTPException(429, "Perception worker busy; try again shortly")
    client = FeedClient()
    try:
        global perception_model
        identity = (city, camera_id)
        elapsed = time.monotonic() - camera_refresh.get(identity, 0)
        minimum = city_configs()[city]["refresh_seconds"]
        if elapsed < minimum:
            raise HTTPException(
                429,
                "Camera refresh interval has not elapsed",
                headers={"Retry-After": str(int(minimum - elapsed) + 1)},
            )
        camera_refresh[identity] = time.monotonic()
        import cv2

        from atlas.cities import Camera, CityAdapter, FeedError, SnapshotPerception
        from atlas.intelligence import assimilate, camera_alignment, count_forecast

        try:
            image, observation = CityAdapter(city, client).snapshot(Camera(**camera))
            if perception_model is None:
                perception_model = SnapshotPerception()
            observation = perception_model.process(image, observation)
        except (FeedError, ValueError) as exc:
            raise HTTPException(502, str(exc)) from exc
        state = assimilate(observation)
        with connection() as conn:
            observation_key = hashlib.sha256(
                (city + camera_id + observation["id"]).encode()
            ).hexdigest()
            conn.execute(
                "INSERT OR REPLACE INTO observations VALUES (?,?,?)",
                (observation_key, city, json.dumps(observation, allow_nan=False)),
            )
        network = next(
            (n for n in evidence("networks.json")["networks"] if n["city"] == city), None
        )
        height, width = image.shape[:2]
        if width > 1024:
            image = cv2.resize(image, (1024, max(1, round(height * 1024 / width))))
        ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            raise HTTPException(500, "Snapshot encoding failed")
        payload = {
            "city": city,
            "camera": camera,
            "observation": observation,
            "estimated_state": state,
            "forecast": count_forecast(state),
            "alignment": camera_alignment(camera, network) if network else None,
            "image_data_url": "data:image/jpeg;base64," + base64.b64encode(encoded).decode(),
            "mode": "new_official_snapshot",
            "retention": "Image returned for immediate operator viewing; not saved on server",
        }
        from fastapi.responses import JSONResponse

        return JSONResponse(payload, headers={"Cache-Control": "no-store", "Pragma": "no-cache"})
    finally:
        client.close()
        perception_lock.release()


@router.get("/health")
def health():
    with connection() as conn:
        rows = conn.execute("SELECT city, count(*) FROM observations GROUP BY city").fetchall()
    return {
        "status": "ok",
        "mode": "advisory_only",
        "operator_writes": bool(os.getenv("ATLAS_OPERATOR_KEY")),
        "ingestion_capacity": 2,
        "stored_aggregate_observations": dict(rows),
        "hardware_actuation": False,
    }


@router.post("/cities/{city}/refresh")
def refresh(city: str, request: Request):
    require_operator(request)
    if city not in city_configs():
        raise HTTPException(404, "Unknown city")
    with refresh_lock:
        elapsed = time.monotonic() - last_refresh.get(city, 0)
        minimum = city_configs()[city]["refresh_seconds"]
        with connection() as conn:
            saved = conn.execute(
                "SELECT payload FROM city_reports WHERE city=?", (city,)
            ).fetchone()
        if saved:
            from datetime import UTC

            elapsed = min(
                elapsed,
                (
                    datetime.now(UTC) - datetime.fromisoformat(json.loads(saved[0])["checked_at"])
                ).total_seconds(),
            )
        if elapsed < minimum:
            raise HTTPException(
                429,
                "Source refresh interval has not elapsed",
                headers={"Retry-After": str(int(minimum - elapsed) + 1)},
            )
        if not ingestion_slots.acquire(blocking=False):
            raise HTTPException(429, "Ingestion capacity exhausted")
        last_refresh[city] = time.monotonic()
    client = FeedClient()
    try:
        report = inspect_city(city, client, samples=1)
        with connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO city_reports VALUES (?,?)",
                (city, json.dumps(report, allow_nan=False)),
            )
            for observation in report["observations"]:
                # Same content digest + camera is idempotent across polling/restarts.
                identity = hashlib.sha256(
                    (city + observation["camera_id"] + observation["id"]).encode()
                ).hexdigest()
                conn.execute(
                    "INSERT OR IGNORE INTO observations VALUES (?,?,?)",
                    (identity, city, json.dumps(observation, allow_nan=False)),
                )
        return report
    finally:
        client.close()
        ingestion_slots.release()


@router.get("/cities/{city}/state")
def estimated_state(city: str):
    report = next((c for c in cities()["cities"] if c["city"] == city), None)
    if not report:
        raise HTTPException(404, "City not found")
    states = []
    for observation in report["observations"]:
        if "counts" not in observation:
            continue
        f = CountFilter()
        total = sum(v for k, v in observation["counts"].items() if k != "person")
        timestamp = datetime.fromisoformat(observation["retrieved_at"]).timestamp()
        states.append(
            {
                "camera_id": observation["camera_id"],
                "source_observation": observation["id"],
                **f.update(timestamp, total, measurement_variance=max(9, total)),
                "kind": "visible_vehicle_count",
                "calibrated": False,
            }
        )
    return {
        "city": city,
        "states": states,
        "limitations": "Single-image estimate; not lane queues, demand calibration or continuous tracking",
    }


class Approval(BaseModel):
    run_id: str = Field(min_length=1, max_length=150)
    decision: str = Field(pattern="^(approve|reject|rollback)$")


@router.post("/approvals")
def approval(body: Approval, request: Request):
    actor = require_operator(request)
    known = {f"{r['city']}:{r['policy']}:{r['seed']}" for r in evidence("experiments.json")["runs"]}
    if body.run_id not in known:
        raise HTTPException(404, "Unknown completed experiment")
    with connection() as conn:
        cursor = conn.execute(
            "INSERT INTO approvals (run_id,decision,actor,created_at) VALUES (?,?,?,?)",
            (body.run_id, body.decision, actor, now()),
        )
    return {
        "event_id": cursor.lastrowid,
        "decision": body.decision,
        "mode": "advisory_only",
        "applied_to_infrastructure": False,
    }


@router.get("/approvals")
def approval_events(request: Request):
    require_operator(request)
    with connection() as conn:
        rows = conn.execute(
            "SELECT id,run_id,decision,actor,created_at FROM approvals ORDER BY id DESC LIMIT 100"
        ).fetchall()
    return [
        {
            "id": r[0],
            "run_id": r[1],
            "decision": r[2],
            "actor": r[3],
            "created_at": r[4],
            "mode": "advisory_only",
        }
        for r in rows
    ]


class PilotInput(BaseModel):
    city: str
    baseline: str = "fixed"
    candidate: str = "risk_mpc"
    vehicles_per_day: float = Field(gt=0, le=10_000_000)
    occupancy: float = Field(ge=1, le=20, default=1.2)
    value_per_person_hour: float = Field(ge=0, le=500, default=20)
    days_per_year: int = Field(ge=1, le=366, default=250)
    compute_monthly: float = Field(ge=0, le=1_000_000, default=100)
    deployment_cost: float = Field(ge=0, le=100_000_000, default=5000)


def pilot_report(body, experiment):
    if body.baseline == body.candidate:
        raise ValueError("Pilot requires distinct baseline and candidate controllers")
    summaries = experiment["summaries"]
    a = next(
        (s for s in summaries if s["city"] == body.city and s["policy"] == body.baseline), None
    )
    b = next(
        (s for s in summaries if s["city"] == body.city and s["policy"] == body.candidate), None
    )
    if not a or not b:
        raise ValueError("Completed matched city/controller evidence required")
    pairs = {}
    for r in experiment["runs"]:
        if r["city"] == body.city and r["policy"] in {body.baseline, body.candidate}:
            pairs.setdefault(r["seed"], {})[r["policy"]] = r
    if not pairs or any(set(v) != {body.baseline, body.candidate} for v in pairs.values()):
        raise ValueError("Pilot requires all paired seeds")
    for pair in pairs.values():
        first, second = pair[body.baseline], pair[body.candidate]
        if any(
            first[k] != second[k]
            for k in ("network_sha256", "routes_sha256", "duration", "scenario")
        ):
            raise ValueError("Unmatched pilot evidence")
    delay = a["mean_delay_s"] - b["mean_delay_s"]
    hours = delay * body.vehicles_per_day * body.occupancy * body.days_per_year / 3600
    value = hours * body.value_per_person_hour
    paired = next(
        (
            p
            for p in experiment.get("paired", [])
            if p["city"] == body.city
            and p["baseline"] == body.baseline
            and body.candidate == "risk_mpc"
            and p["pairs"] == len(pairs)
        ),
        None,
    )
    interval = paired["paired_difference_ci95"] if paired else None
    projected_interval = (
        [
            d
            * body.vehicles_per_day
            * body.occupancy
            * body.days_per_year
            * body.value_per_person_hour
            / 3600
            for d in interval
        ]
        if interval
        else None
    )
    return {
        "city": body.city,
        "scope": "Uncalibrated exploratory SUMO evidence; annual benefits are user-assumption projections, not validated municipal ROI",
        "baseline": a,
        "candidate": b,
        "paired_seeds": len(pairs),
        "delay_difference_s": delay,
        "paired_delay_ci95_s": interval,
        "projected_value_ci95_from_simulation_seed_variation": projected_interval,
        "uncertainty_qualification": "Simulation seed variation only; field calibration and economic uncertainty are not quantified",
        "simulation_inputs": [
            {
                k: r[k]
                for k in (
                    "seed",
                    "policy",
                    "network_sha256",
                    "routes_sha256",
                    "duration",
                    "scenario",
                )
            }
            for pair in pairs.values()
            for r in pair.values()
        ],
        "projected_person_hours_per_year": hours,
        "projected_value_per_year": value,
        "projected_net_first_year": value - 12 * body.compute_monthly - body.deployment_cost,
        "assumptions": body.model_dump(),
        "requirements": [
            "Independent traffic counts and holdout validation",
            "Agency signal/pedestrian timing and conflict survey",
            "Camera data-use approval",
            "Operator oversight and shadow pilot",
            "Hardware integration and certification are not implemented",
        ],
        "field_validated": False,
    }


class ExperimentInput(BaseModel):
    city: str
    policy: str = Field(
        pattern="^(fixed|max_pressure|original_mpc|risk_mpc|network_mpc|actuated)$",
        default="risk_mpc",
    )
    seed: int = Field(ge=1, le=2_000_000_000, default=19001)
    duration: int = Field(ge=60, le=300, default=300)
    risk_weight: float = Field(ge=0, le=5, default=0.2)
    tail_weight: float = Field(ge=0, le=5, default=0.15)
    scenario: str = Field(pattern="^(nominal|sensor_outage|lane_closure)$", default="nominal")


@router.post("/experiments", status_code=202)
def execute_experiment(body: ExperimentInput, request: Request):
    require_operator(request)
    if body.city not in city_configs():
        raise HTTPException(404, "Unknown supported city")
    if worker_pool is None:
        raise HTTPException(503, "Simulation worker unavailable")
    if not simulation_slots.acquire(blocking=False):
        raise HTTPException(429, "Simulation queue is full")
    if body.policy in {"network_mpc", "actuated"}:
        from atlas.evaluation.network_v4_runtime import run_network
    else:
        from atlas.evaluation.network_v3 import run_network

    settings = RiskConfig(risk_weight=body.risk_weight, tail_weight=body.tail_weight)
    return enqueue(
        run_network,
        (
            body.city,
            body.policy,
            body.seed,
            body.duration,
            settings,
            True,
            None,
            None,
            body.scenario,
        ),
        body.model_dump(),
    )


class IntelligenceInput(BaseModel):
    city: str = "toronto"
    observation_id: str = Field(min_length=1, max_length=64)
    seed: int = Field(ge=1, le=2_000_000_000, default=21002)
    duration: int = Field(ge=60, le=300, default=300)
    baseline: str = Field(pattern="^(fixed|max_pressure|original_mpc)$", default="original_mpc")
    assumptions: DemandAssumptions
    region_revision: int | None = Field(default=None, ge=1)


def recorded_city_observation(city, observation_id):
    """Accept only exact city/id matches from trusted recorded processing evidence."""
    path = config.ARTIFACTS / "cities/v4/intelligence-smoke.json"
    if not path.exists():
        return None
    for record in json.loads(path.read_text(encoding="utf-8"))["records"]:
        if record["city"] != city:
            continue
        for attempt in record["attempts"]:
            observation = attempt.get("context", {}).get("observation")
            if observation and observation["id"] == observation_id and observation["city"] == city:
                return observation
    return None


@router.post("/intelligence/experiments", status_code=202)
def execute_intelligence(body: IntelligenceInput, request: Request):
    require_operator(request)
    context = evidence("toronto-intelligence.json")
    observation = (
        context["observation"]
        if body.city == context["city"] and body.observation_id == context["observation"]["id"]
        else None
    )
    if observation is None:
        observation = recorded_city_observation(body.city, body.observation_id)
    if observation is None:
        with connection() as conn:
            saved = conn.execute(
                "SELECT payload FROM observations WHERE city=? AND json_extract(payload,'$.id')=? LIMIT 1",
                (body.city, body.observation_id),
            ).fetchone()
        if saved:
            observation = json.loads(saved[0])
        else:
            raise HTTPException(404, "Unknown processed corridor observation")
    if not body.assumptions.acknowledge_exploratory:
        raise HTTPException(422, "Acknowledge uncalibrated demand assumptions")
    from atlas.intelligence import camera_alignment

    report = next((item for item in cities()["cities"] if item["city"] == body.city), None)
    camera = (
        next((item for item in report["cameras"] if item["id"] == observation["camera_id"]), None)
        if report
        else None
    )
    network = next(
        (item for item in evidence("networks.json")["networks"] if item["city"] == body.city), None
    )
    if camera is None or network is None or not network.get("roads"):
        raise HTTPException(422, "Known camera and imported corridor geometry are required")
    alignment = camera_alignment(camera, network)
    if not alignment["candidates"] or alignment["candidates"][0]["distance_m"] > 1000:
        raise HTTPException(
            422,
            "Camera exceeds the 1 km geographic screening limit; corridor demand cannot be conditioned on this source. Field-of-view calibration remains required even within this limit.",
        )
    if body.region_revision is not None:
        with connection() as conn:
            saved = conn.execute(
                "SELECT payload FROM scene_regions WHERE revision=? AND city=? AND camera=?",
                (body.region_revision, body.city, observation["camera_id"]),
            ).fetchone()
        if not saved:
            raise HTTPException(422, "Unknown operator region for this camera")
        region = json.loads(saved[0])
        if region["observation_id"] != observation["id"]:
            raise HTTPException(
                422, "Region belongs to an older observation; verify camera geometry before reuse"
            )
        from atlas.scene import region_observation

        observation = region_observation(SceneRegion(**region), observation, body.region_revision)
    if worker_pool is None:
        raise HTTPException(503, "Simulation worker unavailable")
    if not simulation_slots.acquire(blocking=False):
        raise HTTPException(429, "Simulation queue is full")
    from atlas.intelligence import execute_pair

    return enqueue(
        execute_pair,
        (
            body.city,
            observation,
            body.assumptions.model_dump(),
            body.seed,
            body.duration,
            body.baseline,
        ),
        body.model_dump(),
    )


def persist_job(job):
    with connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        prior = conn.execute(
            "SELECT payload FROM simulation_job_records WHERE id=?", (job["id"],)
        ).fetchone()
        if prior:
            previous = json.loads(prior[0])
            if previous["state"] in {"complete", "failed", "cancelled", "interrupted"} and job[
                "state"
            ] not in {"complete", "failed", "cancelled", "interrupted"}:
                return previous
            job = {**previous, **job}
        conn.execute(
            "INSERT INTO simulation_job_records(id,payload) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
            (job["id"], json.dumps(job, allow_nan=False)),
        )
    return job


def recover_jobs():
    """One API process per operations DB; interrupted jobs never rerun silently."""
    with connection() as conn:
        for identity, payload in conn.execute(
            "SELECT id,payload FROM simulation_job_records"
        ).fetchall():
            job = json.loads(payload)
            if (
                job["state"] in {"queued", "running", "cancel_requested"}
                and job.get("worker_session") != worker_owner
            ):
                job.update(
                    state="interrupted",
                    finished_at=now(),
                    error="Worker restarted before verified completion; resubmit explicitly",
                )
                conn.execute(
                    "UPDATE simulation_job_records SET payload=? WHERE id=?",
                    (json.dumps(job), identity),
                )


def cancellation_requested(identity):
    with connection() as conn:
        row = conn.execute(
            "SELECT payload FROM simulation_job_records WHERE id=?", (identity,)
        ).fetchone()
    return row is None or json.loads(row[0]).get("cancel_requested", False)


def run_job(identity, function, arguments):
    """Top-level, process-pool-compatible worker with shared durable cancellation."""
    from atlas.evaluation.network_v3 import SimulationCancelled

    with connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT payload FROM simulation_job_records WHERE id=?", (identity,)
        ).fetchone()
        job = json.loads(row[0])
        if job.get("cancel_requested"):
            raise SimulationCancelled("Cancelled before execution")
        job.update(state="running", started_at=now())
        conn.execute(
            "UPDATE simulation_job_records SET payload=? WHERE id=?", (json.dumps(job), identity)
        )
    return function(*arguments, cancel_check=partial(cancellation_requested, identity))


def enqueue(function, arguments, parameters):
    identity = secrets.token_hex(16)
    job = {
        "id": identity,
        "state": "queued",
        "mode": "new_simulation",
        "request": parameters,
        "submitted_at": now(),
        "worker_session": worker_owner,
    }
    simulation_jobs[identity] = job
    try:
        persist_job(job)
    except sqlite3.Error:
        simulation_slots.release()
        simulation_jobs.pop(identity, None)
        raise HTTPException(503, "Job storage unavailable; submission was not accepted") from None
    if len(simulation_jobs) > 100:
        for old_id in list(simulation_jobs):
            if len(simulation_jobs) <= 100:
                break
            if simulation_jobs[old_id]["state"] in {"complete", "failed"}:
                simulation_jobs.pop(old_id)
    try:
        future = worker_pool.submit(run_job, identity, function, arguments)
        job_futures[identity] = future
    except Exception:
        simulation_slots.release()
        simulation_jobs.pop(identity)
        job.update(state="failed", error="Worker rejected submission", finished_at=now())
        persist_job(job)
        raise HTTPException(503, "Worker rejected simulation") from None

    def completed(value):
        from concurrent.futures import CancelledError

        from atlas.evaluation.network_v3 import SimulationCancelled

        try:
            outcome = value.result()
            (config.DATA / f"experiment-{identity}.json").write_text(
                json.dumps(outcome, allow_nan=False), encoding="utf-8"
            )
            job.update(
                state="complete",
                result_path=f"/api/operations/jobs/{identity}/result",
                finished_at=now(),
            )
        except (SimulationCancelled, CancelledError):
            job.update(
                state="cancelled",
                finished_at=now(),
                error="Operator cancelled this simulated experiment",
            )
        except Exception:
            log.exception("simulation_job_failed", extra={"job_id": identity})
            job.update(
                state="failed",
                error="Simulation failed; inspect worker logs and scenario prerequisites",
                finished_at=now(),
            )
        finally:
            try:
                persist_job(job)
            finally:
                job_futures.pop(identity, None)
                simulation_slots.release()

    future.add_done_callback(completed)
    return job


@router.get("/jobs/{job_id}")
def job_status(job_id: str):
    with connection() as conn:
        row = conn.execute(
            "SELECT payload FROM simulation_job_records WHERE id=?", (job_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Unknown persisted simulation job")
    return json.loads(row[0])


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, request: Request):
    require_operator(request)
    job = job_status(job_id)
    if job["state"] in {"complete", "failed", "cancelled", "interrupted"}:
        return job
    job.update(cancel_requested=True, state="cancel_requested")
    persist_job(job)
    future = job_futures.get(job_id)
    if future is not None:
        future.cancel()
    return job_status(job_id)


@router.get("/jobs/{job_id}/result")
def job_result(job_id: str):
    if not job_id.isalnum() or len(job_id) != 32:
        raise HTTPException(404, "Unknown job")
    path = config.DATA / f"experiment-{job_id}.json"
    if not path.exists():
        raise HTTPException(409, "Completed output not yet available")
    return json.loads(path.read_text(encoding="utf-8"))


@router.post("/pilot")
def pilot(body: PilotInput):
    try:
        return pilot_report(body, evidence("experiments.json"))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
