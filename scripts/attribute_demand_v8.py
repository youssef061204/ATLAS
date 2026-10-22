"""Development-only CV demand audit and reference-initialized SUMO diagnostic.

The reference run is an oracle diagnostic: it supplies independently annotated
first observed poses, speeds, and lengths at their observation time. It uses no
future interior state corrections and retains the v7 approximate road, signals,
straight routes, vehicle dynamics, random seed, and collision checks. It cannot
be reported as deployable predictive accuracy or a fresh holdout result.
"""

import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import numpy as np
from atlas.attribution_v8 import admission_lifecycle, state_attribution
from atlas.city_network import binary
from atlas.physical_metrics_v7 import birth_correspondence, physical_errors
from calibrate_physics_v7 import native_states, reference_states
from cv_driven_ngsim_v6 import evaluate_aggregate, geometry_mapper
from diagnose_ngsim_v7 import development_observations
from reconstruct_births_v7 import lane_project
from reconstruct_ngsim_v6 import METRES, checked, road_model

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/reality-v7/eager-insertion/duration-300"
FULL_INPUT = ROOT / "data/reality-v7/eager-insertion/duration-1122/inputs.json"
OUT = ROOT / "data/reality-v8/reference-demand-development"
PUBLISHED = ROOT / "artifacts/reality/v8/demand-attribution-development.json"
START, END = 30, 300


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def lanes_from_network(network):
    lanes = []
    for edge in network.findall("edge"):
        edge_id = edge.get("id")
        if edge_id not in {"N_in", "S_in", "N_out", "S_out"}:
            continue
        for lane in edge.findall("lane"):
            lanes.append(
                {
                    "edge": edge_id,
                    "id": lane.get("id"),
                    "index": int(lane.get("index")),
                    "length": float(lane.get("length")),
                    "shape": np.array(
                        [[float(v) for v in pair.split(",")] for pair in lane.get("shape").split()]
                    ),
                }
            )
    return lanes


def reference_first_states(source, all_states, network):
    """Convert each first eligible annotated state into an oracle initial birth."""
    lookup = {
        (tick, str(state["id"])): state for tick, states in all_states.items() for state in states
    }
    lanes = lanes_from_network(network)
    seen, entries = set(), []
    discarded = Counter()
    for row in source.itertuples():
        identity = str(row.vehicle_id)
        if identity in seen or not 0 <= row.t < END:
            continue
        if (
            not 970 < row.local_y < 1400
            or abs(row.local_x) * METRES > 16
            or row.direction not in (2, 4)
            or not 1 <= row.lane_id <= 4
        ):
            continue
        seen.add(identity)
        point = np.asarray(lookup[round(row.t * 10), identity]["point"])
        eligible = {"S_in", "N_out"} if row.direction == 2 else {"N_in", "S_out"}
        candidates = [
            (distance, lane, position)
            for lane in lanes
            if lane["edge"] in eligible
            for distance, position, _ in [lane_project(point, lane["shape"])]
        ]
        if not candidates:
            discarded["no_directionally_eligible_lane"] += 1
            continue
        distance, lane, position = min(candidates, key=lambda item: item[0])
        if distance > 6:
            discarded["outside_6m_lane_projection_gate"] += 1
            continue
        length = float(row.v_length * METRES)
        front = float(np.clip(position + length / 2, length / 2, lane["length"] - 0.2))
        remaining = max(0, lane["length"] - front)
        safe_speed = max(0, np.sqrt(4.5**2 + 2 * 4.5 * remaining) - 4.5)
        entries.append(
            {
                "id": f"ref_{identity}",
                "reference_id": identity,
                "t": float(row.t),
                "edge": lane["edge"],
                "lane": lane["index"],
                "position_m": front,
                "speed_mps": float(min(row.v_vel * METRES, 15.65, safe_speed)),
                "length_m": length,
                "observed_world_m": point.tolist(),
                "projection_residual_m": float(distance),
            }
        )
    return sorted(entries, key=lambda item: (item["t"], item["id"])), dict(discarded)


def build_reference_routes(entries, source_routes, target):
    original = ET.parse(source_routes)
    root = ET.Element("routes")
    template = original.find("vType")
    if template is None:
        raise ValueError("Missing baseline vehicle type")
    for entry in entries:
        kind = ET.SubElement(root, "vType", attrib=dict(template.attrib))
        kind.set("id", entry["id"])
        kind.set("length", f"{entry['length_m']:.3f}")
        vehicle = ET.SubElement(
            root,
            "vehicle",
            id=entry["id"],
            type=entry["id"],
            depart=f"{entry['t']:.1f}",
            departLane=str(entry["lane"]),
            departPos=f"{entry['position_m']:.2f}",
            departSpeed=f"{entry['speed_mps']:.2f}",
        )
        route = {
            "N_in": "N_in S_out",
            "S_in": "S_in N_out",
            "N_out": "N_out",
            "S_out": "S_out",
        }[entry["edge"]]
        ET.SubElement(vehicle, "route", edges=route)
    ET.ElementTree(root).write(target, encoding="utf-8")


def run_reference(entries):
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / "simulation.fcd.xml.gz").exists():
        raise FileExistsError("Preserve completed reference diagnostic")
    shutil.copyfile(BASE / "network.net.xml", OUT / "network.net.xml")
    build_reference_routes(entries, BASE / "routes.xml", OUT / "routes.xml")
    checked(
        [
            binary("sumo"),
            "-n",
            str(OUT / "network.net.xml"),
            "-r",
            str(OUT / "routes.xml"),
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
            str(OUT / "simulation.fcd.xml.gz"),
            "--device.fcd.period",
            "1",
            "--tripinfo-output",
            str(OUT / "tripinfo.xml"),
            "--no-step-log",
            "true",
            "--duration-log.disable",
            "true",
            "--time-to-teleport",
            "-1",
        ],
        OUT / "sumo.log",
    )


def main():
    if PUBLISHED.exists():
        raise FileExistsError("Preserve measured v8 development report")
    source = development_observations(301)
    source = source[source.t < END]
    road, _ = road_model(source)
    all_states, scoring = reference_states(source, road)
    full_entries = json.loads(FULL_INPUT.read_text(encoding="utf-8"))["entries"]
    cv_entries = [entry for entry in full_entries if entry["t"] < END]
    cv_mapping, diagnostics = birth_correspondence(cv_entries, all_states)
    cv_native = native_states(BASE)
    cv_errors = physical_errors(cv_mapping, scoring, cv_native, START, END)
    cv_attribution = state_attribution(cv_mapping, scoring, cv_native, START, END)
    cv_lifecycle = admission_lifecycle(cv_entries, cv_mapping, cv_native, END)

    reference_entries, rejects = reference_first_states(
        source, all_states, ET.parse(BASE / "network.net.xml").getroot()
    )
    protocol = {
        "window_s": [START, END],
        "source_scope": "Previously inspected 0-300 s development recording; not independent test",
        "reference_run": "Oracle first annotated pose/speed/length at observation time; no future trajectory corrections; straight routes remain estimated",
        "cv_run": "Frozen ATLAS 7 CV births; native eager-insertion output unchanged",
        "shared": "Exact baseline network and signal phases, tau 0.7, maxSpeed 15.65, seed 77001, SUMO safety and 0.1 s step",
        "selection": "No parameter selection from this diagnostic; compare same reference cohort and publish regressions",
        "baseline_network_sha256": sha(BASE / "network.net.xml"),
        "baseline_routes_sha256": sha(BASE / "routes.xml"),
        "baseline_native_fcd_sha256": sha(BASE / "simulation.fcd.xml.gz"),
        "source_sha256": sha(Path(__file__)),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    run_reference(reference_entries)
    native = native_states(OUT)
    mapping = {
        entry["reference_id"]: {"native_id": entry["id"], "birth_s": entry["t"]}
        for entry in reference_entries
    }
    reference_errors = physical_errors(mapping, scoring, native, START, END)
    reference_attribution = state_attribution(mapping, scoring, native, START, END)
    reference_lifecycle = admission_lifecycle(reference_entries, mapping, native, END)
    local = geometry_mapper(road)
    cv_aggregate = evaluate_aggregate(BASE, source, local, window=(START, END))
    ref_aggregate = evaluate_aggregate(OUT, source, local, window=(START, END))
    report = {
        "protocol": protocol,
        "split": "Known development 30-300 s; oracle-assisted diagnostic, not deployable or independent",
        "cv": {
            "physical_errors": cv_errors,
            "state_attribution": cv_attribution,
            "admission": cv_lifecycle,
            "birth_association_diagnostics": diagnostics,
            "aggregate": cv_aggregate,
        },
        "reference_initialized": {
            "physical_errors": reference_errors,
            "state_attribution": reference_attribution,
            "admission": reference_lifecycle,
            "first_state_projection_rejections": rejects,
            "aggregate": ref_aggregate,
        },
        "reference_native_fcd_sha256": sha(OUT / "simulation.fcd.xml.gz"),
        "reference_routes_sha256": sha(OUT / "routes.xml"),
        "validated_physical_twin": False,
        "limitations": [
            "Signals remain unverified against observed lamp states",
            "Current road omits turn bays, side approaches, and driveways",
            "The reference run sees oracle first states unavailable to a deployable CV model",
            "SUMO first appearance is sampled at 1 Hz; exact admission delays require tripinfo/log review",
        ],
    }
    PUBLISHED.parent.mkdir(parents=True, exist_ok=True)
    PUBLISHED.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "cv_births": len(cv_entries),
                "reference_births": len(reference_entries),
                "cv_state_categories": cv_attribution["exclusive_state_categories"],
                "reference_state_categories": reference_attribution["exclusive_state_categories"],
                "cv_count_mae": cv_aggregate["instantaneous_vehicle_count"]["mae"],
                "reference_count_mae": ref_aggregate["instantaneous_vehicle_count"]["mae"],
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
