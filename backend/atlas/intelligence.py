"""Explicit observation-to-SUMO exploratory pipeline; no field calibration claim."""

import copy
import hashlib
import json
import math
import shutil
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from atlas import config
from atlas.cities import now
from atlas.city_network import sha
from atlas.control_v2 import RiskConfig
from atlas.state import CountFilter


class DemandAssumptions(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    residence_seconds: float = Field(ge=10, le=600, default=60)
    corridor_multiplier: float = Field(ge=0.1, le=10, default=1)
    acknowledge_exploratory: bool = False


def camera_alignment(camera, network):
    """Point-to-segment distance in a local tangent plane; geolocation only."""
    scale = math.cos(math.radians(camera["lat"]))
    point = np.array([camera["lon"] * scale, camera["lat"]]) * 111_195
    candidates = []
    for road in network["roads"]:
        coords = np.array(road["coordinates"], dtype=float)
        coords[:, 0] *= scale
        coords *= 111_195
        distances = []
        for start, end in zip(coords[:-1], coords[1:], strict=True):
            delta = end - start
            length2 = float(delta @ delta)
            fraction = np.clip(float((point - start) @ delta) / length2, 0, 1) if length2 else 0
            distances.append(float(np.linalg.norm(point - (start + fraction * delta))))
        if distances:
            candidates.append({"road_id": road["id"], "distance_m": min(distances)})
    return {
        "status": "geographic_candidate_not_validated",
        "method": "nearest road polyline; heading/FOV and lane survey unavailable",
        "candidates": sorted(candidates, key=lambda r: r["distance_m"])[:5],
    }


def assimilate(observation):
    if "counts" not in observation:
        raise ValueError("A successfully processed observation is required")
    # Bicycles and people remain separate from passenger-car scenario demand.
    motor = sum(observation["counts"].get(c, 0) for c in ("car", "truck", "bus", "motorcycle"))
    timestamp = datetime.fromisoformat(observation["retrieved_at"]).timestamp()
    filter_ = CountFilter()
    state = filter_.update(timestamp, motor, measurement_variance=max(9, motor))
    return state | {
        "kind": "visible_motor_vehicle_count",
        "unit": "vehicles",
        "source_observation": observation["id"],
        "capture_timestamp_verified": False,
        "queue_vehicles": None,
        "flow_veh_hour": None,
    }


def count_forecast(state, horizons=(60, 180, 300)):
    """Random-walk prior pending enough repeated observations for a learned model."""
    radius0 = (state["interval95"][1] - state["mean"]) / 1.96
    return [
        {
            "horizon_seconds": h,
            "mean": state["mean"],
            "interval95": [
                max(0, state["mean"] - 1.96 * math.sqrt(radius0**2 + 0.2 * h)),
                state["mean"] + 1.96 * math.sqrt(radius0**2 + 0.2 * h),
            ],
            "unit": "visible vehicles",
            "model": "unvalidated Gaussian random-walk prior",
            "calibrated": False,
        }
        for h in horizons
    ]


def prepare_scenario(city, observation, assumptions, seed=21001, duration=300):
    if not assumptions.acknowledge_exploratory:
        raise ValueError("Explicit exploratory demand acknowledgement required")
    if city not in {"toronto", "london", "seattle", "austin", "calgary"}:
        raise ValueError("Unsupported city")
    state = assimilate(observation)
    forecast = count_forecast(state)
    source = config.ROOT / "datasets/cities" / city
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    template = next(
        (p for p in source.glob("routes-*.xml") if sha(p) == manifest["routes_sha256"]), None
    )
    if template is None or sha(source / "network.net.xml") != manifest["network_sha256"]:
        raise ValueError("Pinned source scenario mismatch")
    template_root = ET.parse(template).getroot()
    vehicles = template_root.findall("vehicle")
    if not vehicles:
        raise ValueError("No validated route templates")
    rate = state["mean"] / assumptions.residence_seconds * assumptions.corridor_multiplier
    expected = state["mean"] + duration * rate
    if expected > 1000:
        raise ValueError("Observation-conditioned scenario exceeds 1000-vehicle budget")
    rng = np.random.default_rng(seed)
    # Visible stock is an assumed network-wide initial stock, not measured OD.
    departures = [0.0] * int(round(state["mean"]))
    t = 0.0
    while rate > 0:
        t += float(rng.exponential(1 / rate))
        if t >= duration:
            break
        departures.append(t)
        if len(departures) > 1000:
            raise ValueError("Sampled scenario exceeds vehicle budget")
    if not departures:
        raise ValueError(
            "Zero observed motor vehicles; no supported demand scenario. Choose an observation with detections or independent detector data."
        )
    output = config.DATA / "intelligence-scenarios" / uuid.uuid4().hex
    output.mkdir(parents=True)
    shutil.copyfile(source / "network.net.xml", output / "network.net.xml")
    route_root = ET.Element("routes")
    for child in template_root:
        if child.tag in {"vType", "vTypeDistribution", "route", "routeDistribution"}:
            route_root.append(copy.deepcopy(child))
    for i, departure in enumerate(departures):
        vehicle = copy.deepcopy(vehicles[int(rng.integers(len(vehicles)))])
        vehicle.set("id", f"obs-{i}")
        vehicle.set("depart", f"{departure:.6f}")
        route_root.append(vehicle)
    routes = output / "conditioned-routes.xml"
    ET.ElementTree(route_root).write(routes, encoding="utf-8", xml_declaration=True)
    manifest.update(routes_sha256=sha(routes), duration=duration, scheduled=len(departures))
    manifest["calibration"] = {
        "status": "uncalibrated_observation_conditioned",
        "demand": "Visible count → user-assumed residence time → Poisson departures; OD sampled from pinned synthetic routes",
        "signal_timings": "Generated SUMO research phases; not municipal timings",
        "independent_validation": None,
    }
    output.joinpath("manifest.json").write_text(
        json.dumps(manifest, allow_nan=False), encoding="utf-8"
    )
    lineage = {
        "schema_version": "atlas-intelligence-3.0",
        "created_at": now(),
        "city": city,
        "seed": seed,
        "duration": duration,
        "observation": observation,
        "estimated_state": state,
        "forecast": forecast,
        "assumptions": assumptions.model_dump(),
        "demand": {
            "initial_stock_assumed": int(round(state["mean"])),
            "arrival_rate_assumed_veh_s": rate,
            "scheduled_vehicles": len(departures),
        },
        "calibration": manifest["calibration"],
        "network_sha256": manifest["network_sha256"],
        "routes_sha256": manifest["routes_sha256"],
        "limitations": [
            "Snapshot vehicle counts do not establish arrival rates or queues",
            "Count-to-flow conversion and network-wide stock are explicit assumptions",
            "Geographic proximity does not validate field of view or lane mapping",
            "Unknown capture time; retrieval time orders observations",
            "Conditional simulation effects are not realized field improvements",
        ],
        "hardware_actuation": False,
    }
    lineage["id"] = hashlib.sha256(json.dumps(lineage, sort_keys=True).encode()).hexdigest()[:24]
    return output, routes, lineage


def execute_pair(
    city,
    observation,
    assumptions,
    seed=21001,
    duration=300,
    baseline="original_mpc",
    cancel_check=None,
):
    from atlas.evaluation.network_v3 import run_network

    if baseline not in {"fixed", "max_pressure", "original_mpc"}:
        raise ValueError("Unsupported paired comparator")
    root, routes, lineage = prepare_scenario(
        city, observation, DemandAssumptions(**assumptions), seed, duration
    )
    results = [
        run_network(
            city, p, seed, duration, RiskConfig(), True, root, routes, cancel_check=cancel_check
        )
        for p in (baseline, "risk_mpc")
    ]
    if any(
        results[0][k] != results[1][k]
        for k in (
            "network_sha256",
            "routes_sha256",
            "initial_states",
            "duration",
            "seed",
            "scenario",
        )
    ):
        raise ValueError("Paired inputs changed; comparison rejected")
    a, b = results
    lineage.update(
        mode="completed_exploratory_simulation",
        runs=results,
        comparison={
            "baseline": baseline,
            "mean_delay_difference_s": a["metrics"]["mean_delay_s"] - b["metrics"]["mean_delay_s"],
            "recommendation": "Prototype reduced delay in this single assumed-demand run; independent calibration and replicated testing required"
            if b["metrics"]["mean_delay_s"] < a["metrics"]["mean_delay_s"]
            else "Retain baseline: prototype did not reduce mean delay in this run",
            "modeled_safety_violations": sum(
                r["metrics"]["modeled_safety_violations"] for r in results
            ),
        },
    )
    config.DATA.joinpath(f"intelligence-{lineage['id']}.json").write_text(
        json.dumps(lineage, allow_nan=False), encoding="utf-8"
    )
    return lineage
