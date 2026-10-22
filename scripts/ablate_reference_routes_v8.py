"""Oracle route ablation on the exposed 0-300 s Lankershim development clip.

This uses a vehicle's *future final observed direction* to isolate route error.
It is a diagnostic intervention on the native simulation, never a causal
predictor or independently validated control result.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from atlas.city_network import binary
from atlas.physical_metrics_v7 import physical_errors
from atlas.reference_routes_v8 import destination
from calibrate_physics_v7 import native_states, reference_states
from cv_driven_ngsim_v6 import evaluate_aggregate, geometry_mapper
from diagnose_ngsim_v7 import development_observations
from reconstruct_ngsim_v6 import checked, road_model

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/reality-v8/reference-demand-development"
TARGET = ROOT / "data/reality-v8/reference-routes-development"
PUBLIC = ROOT / "artifacts/reality/v8/reference-route-ablation-development.json"
START, END = 30, 300


def sha(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main() -> None:
    if PUBLIC.exists() or (TARGET / "simulation.fcd.xml.gz").exists():
        raise FileExistsError("Preserve completed route ablation")
    source = development_observations(301)
    source = source[source.t < END]
    last = source.sort_values("t").groupby("vehicle_id").last()
    road, _ = road_model(source)
    _, scoring = reference_states(source, road)
    routes = ET.parse(BASE / "routes.xml")
    changed = []
    skipped = Counter()
    for vehicle in routes.findall("vehicle"):
        identity = int(vehicle.get("id").removeprefix("ref_"))
        movement = vehicle.find("route")
        if movement is None:
            raise ValueError("Reference route has no edges")
        inbound = movement.get("edges").split()[0]
        if identity not in last.index:
            skipped["no_reference_final_state"] += 1
            continue
        row = last.loc[identity]
        side = destination(int(row.direction), float(row.local_x), float(row.t), inbound)
        if side is None:
            skipped["no_complete_corrobated_side_exit"] += 1
            continue
        previous = movement.get("edges")
        movement.set("edges", f"{inbound} {side}")
        changed.append(
            {
                "reference_id": identity,
                "previous": previous,
                "oracle_route": movement.get("edges"),
                "last_observed_s": float(row.t),
                "last_direction": int(row.direction),
            }
        )
    TARGET.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(BASE / "network.net.xml", TARGET / "network.net.xml")
    routes.write(TARGET / "routes.xml", encoding="utf-8")
    checked(
        [
            binary("sumo"),
            "-n",
            str(TARGET / "network.net.xml"),
            "-r",
            str(TARGET / "routes.xml"),
            "--begin",
            "0",
            "--end",
            str(END),
            "--step-length",
            ".1",
            "--seed",
            "77001",
            "--eager-insert",
            "true",
            "--fcd-output",
            str(TARGET / "simulation.fcd.xml.gz"),
            "--device.fcd.period",
            "1",
            "--tripinfo-output",
            str(TARGET / "tripinfo.xml"),
            "--no-step-log",
            "true",
            "--duration-log.disable",
            "true",
            "--time-to-teleport",
            "-1",
        ],
        TARGET / "sumo.log",
    )
    mapping = {
        vehicle.get("id").removeprefix("ref_"): {
            "native_id": vehicle.get("id"),
            "birth_s": float(vehicle.get("depart")),
        }
        for vehicle in routes.findall("vehicle")
    }
    before = physical_errors(mapping, scoring, native_states(BASE), START, END)
    after = physical_errors(mapping, scoring, native_states(TARGET), START, END)
    local = geometry_mapper(road)
    aggregate_before = evaluate_aggregate(BASE, source, local, window=(START, END))
    aggregate_after = evaluate_aggregate(TARGET, source, local, window=(START, END))

    def brief(errors: dict, aggregate: dict) -> dict:
        return {
            "reference_states": errors["reference_observations"],
            "native_presence": errors["native_presence_coverage"],
            "within_4m_reference_coverage": errors["within_4m_reference_coverage"],
            "uncapped_position_mae_m": errors["uncapped_position_m"]["mae"],
            "count_mae_vehicles": aggregate["instantaneous_vehicle_count"]["mae"],
            "queue_mae_vehicles": aggregate["sb_queue_count"]["mae"],
        }

    report = {
        "schema": "atlas-v8-reference-route-ablation-1",
        "window_s": [START, END],
        "source_scope": "Previously exposed development data; no new holdout validation",
        "experiment": "Only destination route changes for vehicles with a completed observed side exit. Identical first observed poses, network, approximate signals, driving behavior, seed and SUMO safety.",
        "oracle_future_route_information": True,
        "changed_routes": len(changed),
        "reference_births": len(routes.findall("vehicle")),
        "skipped": dict(skipped),
        "changed_route_records": changed,
        "baseline_network_sha256": sha(BASE / "network.net.xml"),
        "trial_network_sha256": sha(TARGET / "network.net.xml"),
        "baseline_routes_sha256": sha(BASE / "routes.xml"),
        "trial_routes_sha256": sha(TARGET / "routes.xml"),
        "native_fcd_sha256": sha(TARGET / "simulation.fcd.xml.gz"),
        "source_sha256": sha(Path(__file__)),
        "before": brief(before, aggregate_before),
        "oracle_routes": brief(after, aggregate_after),
        "signal_state_independently_verified": False,
        "validated_physical_twin": False,
    }
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {key: report[key] for key in ("changed_routes", "skipped", "before", "oracle_routes")},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
