"""Fit native SUMO behavior on 0-300 s only, preserving identical CV admissions.

Every candidate free-runs after one observed birth state. Scoring never feeds
future reference positions to SUMO. The known 600-1000 s interval is regression,
not a new holdout; this script never reads the reserved temporal test.
"""

import argparse
import gzip
import hashlib
import json
import shutil
import socket
import subprocess
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import numpy as np
import traci
from atlas.city_network import binary
from atlas.physical_metrics_v7 import birth_correspondence, physical_errors
from cv_driven_ngsim_v6 import evaluate_aggregate, geometry_mapper
from diagnose_ngsim_v7 import development_observations
from publish_replay_v7 import NATIVE, ROOT
from reconstruct_ngsim_v6 import METRES, ORIGIN, road_model
from scipy.spatial import cKDTree

OUT = ROOT / "data/reality-v7/physical-calibration-v2"


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def reference_states(source, road):
    grid = np.linspace(960, 1410, 1801)
    curve = road(grid)
    tangent = np.gradient(curve, axis=0)
    tangent /= np.linalg.norm(tangent, axis=1)[:, None]
    tree = cKDTree(curve)
    world = (source[["global_x", "global_y"]].to_numpy() - ORIGIN) * METRES
    _, nearest = tree.query(world)
    heading = tangent[nearest] * np.where(source.direction.to_numpy() == 4, -1, 1)[:, None]
    past = source.groupby("vehicle_id")[["global_x", "global_y"]].diff().to_numpy()
    norm = np.linalg.norm(past, axis=1)
    valid = np.isfinite(norm) & (norm > 0.01)
    heading[valid] = past[valid] / norm[valid, None]
    centers = world - source.v_length.to_numpy()[:, None] * 0.3048 * 0.5 * heading
    _, nearest = tree.query(centers)
    normal = tangent[nearest][:, ::-1] * [1, -1]
    lateral = np.sum((centers - curve[nearest]) * normal, axis=1)
    inside = (
        (grid[nearest] >= 1090)
        & (grid[nearest] <= 1360)
        & (abs(lateral) <= 16)
        & source.direction.isin([2, 4]).to_numpy()
        & source.lane_id.between(1, 4).to_numpy()
    )
    all_states, scoring = defaultdict(list), defaultdict(list)
    for i, row in enumerate(source.itertuples()):
        state = {
            "id": str(row.vehicle_id),
            "point": centers[i].tolist(),
            "speed": row.v_vel * 0.3048,
        }
        key = round(row.t * 10)
        all_states[key].append(state)
        if inside[i] and key % 10 == 0:
            scoring[key].append(state)
    return all_states, scoring


def native_states(directory):
    routes = ET.parse(directory / "routes.xml")
    types = {v.get("id"): float(v.get("length")) for v in routes.findall("vType")}
    lengths = {v.get("id"): types[v.get("type")] for v in routes.findall("vehicle")}
    states = defaultdict(list)
    with gzip.open(directory / "simulation.fcd.xml.gz", "rb") as handle:
        for _, element in ET.iterparse(handle, events=("end",)):
            if element.tag != "timestep":
                continue
            t = round(float(element.get("time")))
            for v in element:
                identity = v.get("id")
                angle = np.deg2rad(float(v.get("angle")))
                point = [
                    float(v.get("x")) - np.sin(angle) * lengths[identity] / 2,
                    float(v.get("y")) - np.cos(angle) * lengths[identity] / 2,
                ]
                states[t].append({"id": identity, "point": point, "speed": float(v.get("speed"))})
            element.clear()
    return states


def simulate(tau, speed, end, directory):
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / "simulation.fcd.xml.gz").exists():
        raise FileExistsError("Preserve candidate simulation")
    shutil.copyfile(NATIVE / "network.net.xml", directory / "network.net.xml")
    routes = ET.parse(NATIVE / "routes.xml")
    for kind in routes.findall("vType"):
        kind.set("tau", str(tau))
        kind.set("speedFactor", "1")
    for vehicle in routes.findall("vehicle"):
        if float(vehicle.get("depart")) >= end:
            routes.getroot().remove(vehicle)
    routes.write(directory / "routes.xml")
    command = [
        binary("sumo"),
        "-n",
        str(directory / "network.net.xml"),
        "-r",
        str(directory / "routes.xml"),
        "--begin",
        "0",
        "--end",
        str(end),
        "--step-length",
        ".1",
        "--seed",
        "77001",
        "--fcd-output",
        str(directory / "simulation.fcd.xml.gz"),
        "--device.fcd.period",
        "1",
        "--tripinfo-output",
        str(directory / "tripinfo.xml"),
        "--no-step-log",
        "true",
        "--duration-log.disable",
        "true",
        "--time-to-teleport",
        "-1",
    ]
    # Keep observed departure speed and all native insertion safety constraints.
    # Set a model desired-speed factor once, immediately AFTER native admission;
    # no observed/reference speed is forced at any later time.
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    with (directory / "sumo.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command + ["--remote-port", str(port)],
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        connection = None
        try:
            connection = traci.connect(
                port=port, proc=process, numRetries=20, waitBetweenRetries=0.1
            )
            while connection.simulation.getTime() < end:
                connection.simulationStep()
                for identity in connection.simulation.getDepartedIDList():
                    connection.vehicle.setSpeedFactor(identity, speed / 15.65)
        finally:
            if connection is not None:
                connection.close()
            else:
                process.terminate()
            process.wait(timeout=30)
    if process.returncode or "Error:" in (directory / "sumo.log").read_text(encoding="utf-8"):
        raise RuntimeError(f"Native candidate failed: {directory}")


def score(directory, source, road, entries, start, end):
    all_states, scoring = reference_states(source, road)
    mapping, diagnostic = birth_correspondence(entries, all_states)
    errors = physical_errors(mapping, scoring, native_states(directory), start, end)
    aggregate = evaluate_aggregate(directory, source, geometry_mapper(road), window=(start, end))
    # Missing predictions cannot improve the selection objective by disappearing.
    objective = (errors["uncapped_position_m"]["mae"] or 1e6) + 30 * (
        1 - (errors["native_presence_coverage"] or 0)
    )
    return {
        "physical_errors": errors,
        "aggregate": aggregate,
        "birth_identity_associations": len(mapping),
        "association_diagnostics": diagnostic,
        "selection_objective_m": objective,
        "routes_sha256": sha(directory / "routes.xml"),
        "native_fcd_sha256": sha(directory / "simulation.fcd.xml.gz"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regression", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    inputs = json.loads((NATIVE / "inputs.json").read_text())
    development = development_observations(301)
    # Geometry is fitted only to the original calibration interval, never regression labels.
    road, _ = road_model(development[development.t < 300])
    publication = ROOT / "artifacts/reality/v7/physical-calibration-development.json"
    if not args.regression:
        if publication.exists():
            raise FileExistsError("Preserve parameter selection")
        protocol = {
            "calibration_s": [0, 300],
            "scoring_s": [30, 300],
            "desired_speeds_mps": [8, 11, 15.65],
            "tau_s": [0.7, 1.0, 1.3],
            "selection": "Min uncapped paired position MAE + 30m * missing native reference fraction; tie count MAE then original parameters. No distance censor, no state forcing.",
            "conditioning": "Identical observed birth entries, routes, geometry, signals, seed and insertion safety. Desired-speed factor set once immediately after native admission; no later observed state forcing. Only model desired-speed factor and car-following tau vary. Initial pre-admission factor attempt failed native departure-speed safety checks; archived separately.",
            "source_sha256": sha(Path(__file__)),
            "input_sha256": sha(NATIVE / "inputs.json"),
        }
        with (OUT / "protocol.json").open("x", encoding="utf-8") as handle:
            json.dump(protocol, handle, indent=2)
        candidates = []
        for speed in protocol["desired_speeds_mps"]:
            for tau in protocol["tau_s"]:
                directory = OUT / f"development-speed-{speed}-tau-{tau}"
                simulate(tau, speed, 300, directory)
                result = score(
                    directory,
                    development,
                    road,
                    [e for e in inputs["entries"] if e["t"] < 300],
                    30,
                    300,
                )
                result.update({"speed_mps": speed, "tau_s": tau})
                (directory / "evaluation.json").write_bytes(json.dumps(result, indent=2).encode())
                candidates.append(result)
                print(
                    json.dumps(
                        {
                            "speed": speed,
                            "tau": tau,
                            "objective": result["selection_objective_m"],
                            "position_mae": result["physical_errors"]["uncapped_position_m"]["mae"],
                            "count_mae": result["aggregate"]["instantaneous_vehicle_count"]["mae"],
                        }
                    ),
                    flush=True,
                )
        selected = min(
            candidates,
            key=lambda r: (
                r["selection_objective_m"],
                r["aggregate"]["instantaneous_vehicle_count"]["mae"],
                abs(r["tau_s"] - 1) + abs(r["speed_mps"] - 15.65),
            ),
        )
        report = {
            "protocol": protocol,
            "protocol_sha256": sha(OUT / "protocol.json"),
            "candidates": candidates,
            "selected": {"speed_mps": selected["speed_mps"], "tau_s": selected["tau_s"]},
            "regression_outcomes_read_for_selection": False,
            "validated_physical_twin": False,
            "source_sha256": sha(Path(__file__)),
        }
        publication.write_bytes(json.dumps(report, indent=2).encode())
        print(json.dumps({"selected": report["selected"]}), flush=True)
    else:
        selection = json.loads(publication.read_text())
        if sha(Path(__file__)) != selection["source_sha256"]:
            raise ValueError("Parameter-selection source changed")
        destination = ROOT / "artifacts/reality/v7/physical-calibrated-regression.json"
        if destination.exists():
            raise FileExistsError("Preserve regression results")
        picked = selection["selected"]
        # Include the original model in the same frozen development-region evaluator.
        candidates = []
        for name, speed, tau in [
            ("original", 15.65, 1.0),
            ("development_selected", picked["speed_mps"], picked["tau_s"]),
        ]:
            directory = OUT / f"regression-{name}"
            simulate(tau, speed, 1122, directory)
            result = score(
                directory,
                development_observations(1001),
                road,
                [e for e in inputs["entries"] if e["t"] < 1000],
                600,
                1000,
            )
            result.update({"name": name, "speed_mps": speed, "tau_s": tau})
            candidates.append(result)
            print(
                json.dumps(
                    {
                        "name": name,
                        "position_mae": result["physical_errors"]["uncapped_position_m"]["mae"],
                        "count_mae": result["aggregate"]["instantaneous_vehicle_count"]["mae"],
                    }
                ),
                flush=True,
            )
        report = {
            "split": "Known 600-1000 s regression, not fresh holdout",
            "development_selection_sha256": sha(publication),
            "candidates": candidates,
            "validated_physical_twin": False,
            "limitations": [
                "Independent signal-state confirmation missing; all original acceptance gates remain",
                "Development-fitted geometry remains fixed for both model comparisons",
                "Desired-speed calibration cannot repair missed vehicle admissions, occlusion or unknown turn routes",
            ],
            "source_sha256": sha(Path(__file__)),
        }
        destination.write_bytes(json.dumps(report, indent=2).encode())


if __name__ == "__main__":
    main()
