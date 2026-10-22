"""Correctly located Main Street turns in an oracle route diagnostic.

Only completed source turns whose first observed sideward state is within 50 m
of official GIS signal 89 may change route on the one-junction model. The
destination is still future information, so this remains diagnostic only.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from atlas.city_network import binary
from atlas.physical_metrics_v7 import physical_errors
from calibrate_physics_v7 import native_states, reference_states
from cv_driven_ngsim_v6 import evaluate_aggregate, geometry_mapper
from diagnose_ngsim_v7 import development_observations
from reconstruct_ngsim_v6 import checked, road_model

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/reality-v8/reference-demand-development"
TARGET = ROOT / "data/reality-v8/reference-main-turns-development"
LOCATION = ROOT / "data/reality-v8/turn-location-development-detail.json"
REJECTED = ROOT / "artifacts/reality/v8/reference-route-ablation-development.json"
PUBLIC = ROOT / "artifacts/reality/v8/main-turn-route-ablation-development.json"
START, END = 30, 300


def sha(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main() -> None:
    if PUBLIC.exists() or (TARGET / "simulation.fcd.xml.gz").exists():
        raise FileExistsError("Preserve completed Main Street route ablation")
    location = json.loads(LOCATION.read_text(encoding="utf-8"))
    supported = {int(row["reference_id"]) for row in location if row["supported_signal"] == 89}
    rejected = json.loads(REJECTED.read_text(encoding="utf-8"))
    corrected = {
        int(row["reference_id"]): row["oracle_route"]
        for row in rejected["changed_route_records"]
        if int(row["reference_id"]) in supported
    }
    if len(corrected) != len(supported):
        raise ValueError("Source-supported Main Street turns lack a route")
    routes = ET.parse(BASE / "routes.xml")
    changed = []
    for vehicle in routes.findall("vehicle"):
        identity = int(vehicle.get("id").removeprefix("ref_"))
        if identity not in corrected:
            continue
        movement = vehicle.find("route")
        before = movement.get("edges")
        after = corrected[identity]
        if before.split()[0] != after.split()[0]:
            raise ValueError("Oracle route changed the observed admission edge")
        movement.set("edges", after)
        changed.append(identity)
    if set(changed) != supported:
        raise ValueError("Not every source-supported Main Street turn was changed")
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
    source = development_observations(301)
    source = source[source.t < END]
    road, _ = road_model(source)
    _, scoring = reference_states(source, road)
    mapping = {
        vehicle.get("id").removeprefix("ref_"): {
            "native_id": vehicle.get("id"),
            "birth_s": float(vehicle.get("depart")),
        }
        for vehicle in routes.findall("vehicle")
    }

    def summarize(directory: Path) -> dict:
        errors = physical_errors(mapping, scoring, native_states(directory), START, END)
        aggregate = evaluate_aggregate(
            directory, source, geometry_mapper(road), window=(START, END)
        )
        return {
            "reference_states": errors["reference_observations"],
            "native_presence": errors["native_presence_coverage"],
            "within_4m_reference_coverage": errors["within_4m_reference_coverage"],
            "uncapped_position_mae_m": errors["uncapped_position_m"]["mae"],
            "count_mae_vehicles": aggregate["instantaneous_vehicle_count"]["mae"],
            "queue_mae_vehicles": aggregate["sb_queue_count"]["mae"],
        }

    report = {
        "schema": "atlas-v8-main-turn-route-ablation-1",
        "window_s": [START, END],
        "source_scope": "Previously exposed development 0-300 s; not an independent holdout",
        "oracle_future_route_information": True,
        "signal_state_independently_verified": False,
        "physical_twin_accepted": False,
        "changed_main_street_routes": len(changed),
        "excluded_other_intersection_turns": len(rejected["changed_route_records"]) - len(changed),
        "comparison": "Same first annotated states, unchanged network/signal/dynamics/seed/safety. Only destinations supported within 50 m of official Main Street signal marker 89 change.",
        "baseline_network_sha256": sha(BASE / "network.net.xml"),
        "trial_network_sha256": sha(TARGET / "network.net.xml"),
        "baseline_routes_sha256": sha(BASE / "routes.xml"),
        "trial_routes_sha256": sha(TARGET / "routes.xml"),
        "trial_native_fcd_sha256": sha(TARGET / "simulation.fcd.xml.gz"),
        "turn_location_detail_sha256": sha(LOCATION),
        "source_sha256": sha(Path(__file__)),
        "before": summarize(BASE),
        "correctly_located_oracle_main_turns": summarize(TARGET),
    }
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "changed_main_street_routes",
                    "excluded_other_intersection_turns",
                    "before",
                    "correctly_located_oracle_main_turns",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
