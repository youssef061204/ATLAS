"""Test the artificial edge-end speed clamp on observed CV births.

Development-only one-factor trial. The current birth adapter limits speed by
distance to the *end of an edge*, although the route may continue across J.
This trial requests the actual CV track speed (bounded by the unchanged vehicle
maxSpeed); SUMO keeps its ordinary insertion, car-following, signal and collision
rules. No future reference state is supplied to the trial.
"""

import gzip
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

from atlas.birth_speed_v8 import observed_cv_depart_speed
from atlas.city_network import binary
from atlas.physical_metrics_v7 import birth_correspondence, physical_errors
from calibrate_physics_v7 import native_states, reference_states
from cv_driven_ngsim_v6 import evaluate_aggregate, geometry_mapper
from diagnose_ngsim_v7 import development_observations
from reconstruct_ngsim_v6 import checked, road_model

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/reality-v7/eager-insertion/duration-300"
TARGET = ROOT / "data/reality-v8/no-edge-end-speed-cap-cv-development"
FULL_INPUT = ROOT / "data/reality-v7/eager-insertion/duration-1122/inputs.json"
PUBLIC = ROOT / "artifacts/reality/v8/edge-end-speed-cap-ablation-development.json"
START, END = 30, 300
RUN_END = 300
ALLOWED_EDGES = None
SOURCE_SCOPE = (
    "Already exposed development data; CV births only, independently annotated "
    "states used solely for post-run scoring; no fresh holdout"
)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def summary(errors, aggregate=None):
    result = {
        "reference_states": errors["reference_observations"],
        "native_presence": errors["native_presence_coverage"],
        "within_4m_reference_coverage": errors["within_4m_reference_coverage"],
        "uncapped_position_mae_m": errors["uncapped_position_m"]["mae"],
        "matched_speed_mae_mps": errors["matched_speed_mps"]["mae"],
    }
    if aggregate is not None:
        result["instantaneous_count_mae_vehicles"] = aggregate["instantaneous_vehicle_count"]["mae"]
    return result


def native_integrity(directory, run_end):
    present = set()
    with gzip.open(directory / "simulation.fcd.xml.gz", "rb") as stream:
        for _, element in ET.iterparse(stream, events=("end",)):
            if element.tag == "timestep":
                present.update(vehicle.get("id") for vehicle in element)
                element.clear()
    trips = ET.parse(directory / "tripinfo.xml").findall("tripinfo")
    requests = [
        vehicle
        for vehicle in ET.parse(directory / "routes.xml").findall("vehicle")
        if float(vehicle.get("depart")) < run_end
    ]
    log = (directory / "sumo.log").read_text(encoding="utf-8")
    return {
        "requested_births_before_run_end": len(requests),
        "native_ids_in_fcd": len(present),
        "completed_trips_before_run_end": len(trips),
        "nonzero_depart_delay_trips": sum(float(row.get("departDelay", "0")) > 0 for row in trips),
        "sumo_log_warning_mentions": log.count("Warning"),
        "sumo_log_error_mentions": log.count("Error"),
        "sumo_log_collision_mentions": log.lower().count("collision"),
        "sumo_log_teleport_mentions": log.lower().count("teleport"),
    }


def main():
    if PUBLIC.exists() or (TARGET / "simulation.fcd.xml.gz").exists():
        raise FileExistsError("Preserve completed edge-end speed ablation")
    entries = [
        row
        for row in json.loads(FULL_INPUT.read_text(encoding="utf-8"))["entries"]
        if row["t"] < RUN_END
    ]
    by_id = {row["id"]: row for row in entries}
    original = ET.parse(BASE / "routes.xml")
    route_nodes = [row for row in original.findall("vehicle") if float(row.get("depart")) < RUN_END]
    if len(route_nodes) != len(entries) or {row.get("id") for row in route_nodes} != set(by_id):
        raise ValueError("CV route identities do not exactly match input births")
    changed = []
    for vehicle in route_nodes:
        row = by_id[vehicle.get("id")]
        requested = observed_cv_depart_speed(row["requested_cv_speed_mps"], max_speed_mps=15.65)
        prior = float(vehicle.get("departSpeed"))
        if (
            row["safety_clipped"]
            and requested > prior + 0.01
            and (ALLOWED_EDGES is None or row["edge"] in ALLOWED_EDGES)
        ):
            vehicle.set("departSpeed", f"{requested:.2f}")
            changed.append(
                {
                    "id": vehicle.get("id"),
                    "edge": row["edge"],
                    "prior_speed_mps": prior,
                    "requested_speed_mps": requested,
                }
            )
    if not changed:
        raise ValueError("No births were affected by the edge-end clamp")
    TARGET.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(BASE / "network.net.xml", TARGET / "network.net.xml")
    original.write(TARGET / "routes.xml", encoding="utf-8")
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
            str(RUN_END),
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
    source = development_observations(RUN_END + 1)
    source = source[source.t < RUN_END]
    road, _ = road_model(source)
    all_states, scoring = reference_states(source, road)
    mapping, _ = birth_correspondence(entries, all_states)
    local = geometry_mapper(road)
    direction_lookup = {
        (round(row.t * 10), str(row.vehicle_id)): int(row.direction)
        for row in source.itertuples()
        if round(row.t * 10) % 10 == 0
    }
    directional_scoring = {}
    for name, direction in (("northbound", 2), ("southbound", 4)):
        cohort = defaultdict(list)
        for tick, states in scoring.items():
            cohort[tick] = [
                state for state in states if direction_lookup[(tick, state["id"])] == direction
            ]
        directional_scoring[name] = cohort

    def measure(directory):
        native = native_states(directory)
        errors = physical_errors(mapping, scoring, native, START, END)
        aggregate = evaluate_aggregate(directory, source, local, window=(START, END))
        directional = {
            name: summary(physical_errors(mapping, cohort, native, START, END))
            for name, cohort in directional_scoring.items()
        }
        return summary(errors, aggregate), directional

    before, before_directional = measure(BASE)
    after, after_directional = measure(TARGET)
    if before["reference_states"] != after["reference_states"]:
        raise ValueError("Reference scoring denominators differ")
    if sha(BASE / "network.net.xml") != sha(TARGET / "network.net.xml"):
        raise ValueError("One-factor trial changed the native road/signal network")

    changed_by_edge = {
        edge: sum(row["edge"] == edge for row in changed)
        for edge in sorted({row["edge"] for row in changed})
    }
    report = {
        "schema": "atlas-v8-edge-end-speed-cap-cv-ablation-1",
        "window_s": [START, END],
        "scope": SOURCE_SCOPE,
        "intervention": "Replace the nonphysical end-of-edge braking clamp for affected CV births with their measured initial CV speed, bounded by the unchanged 15.65 m/s type maximum. Native SUMO insertion, traffic lights, car-following, collision checks, routes, seed and network remain unchanged.",
        "reference_states_identical": True,
        "cv_birth_count": len(entries),
        "changed_birth_count": len(changed),
        "changed_birth_count_by_edge": changed_by_edge,
        "changed_northbound_s_in_births": changed_by_edge.get("S_in", 0),
        "intervened_edges": sorted(ALLOWED_EDGES) if ALLOWED_EDGES is not None else "all",
        "signal_state_independently_verified": False,
        "physical_twin_accepted": False,
        "before": before,
        "no_edge_end_speed_cap": after,
        "directional_before": before_directional,
        "directional_no_edge_end_speed_cap": after_directional,
        "baseline_native_integrity": native_integrity(BASE, RUN_END),
        "trial_native_integrity": native_integrity(TARGET, RUN_END),
        "source_sha256": sha(Path(__file__)),
        "birth_speed_policy_sha256": sha(ROOT / "backend/atlas/birth_speed_v8.py"),
        "cv_inputs_sha256": sha(FULL_INPUT),
        "baseline_network_sha256": sha(BASE / "network.net.xml"),
        "trial_network_sha256": sha(TARGET / "network.net.xml"),
        "baseline_routes_sha256": sha(BASE / "routes.xml"),
        "trial_routes_sha256": sha(TARGET / "routes.xml"),
        "baseline_native_fcd_sha256": sha(BASE / "simulation.fcd.xml.gz"),
        "trial_native_fcd_sha256": sha(TARGET / "simulation.fcd.xml.gz"),
    }
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "cv_birth_count",
                    "changed_birth_count",
                    "changed_birth_count_by_edge",
                    "before",
                    "no_edge_end_speed_cap",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
