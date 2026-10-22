"""Test whether the short southern SUMO edge causes the Main Street failure.

Extend only the road south of its prior boundary. The near-junction geometry,
initial world positions, reference births, signals, driving model and SUMO seed
stay fixed. The added linework is an explicitly estimated diagnostic extension.
"""

import copy
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from atlas.city_network import binary
from atlas.physical_metrics_v7 import physical_errors
from calibrate_physics_v7 import native_states, reference_states
from diagnose_ngsim_v7 import development_observations
from reconstruct_ngsim_v6 import checked, road_model

ROOT = Path(__file__).resolve().parents[1]
PLAIN = ROOT / "data/reality-v6/reconstruction-1.0-15.65-66001"
BASE = ROOT / "data/reality-v8/reference-demand-development"
TARGET = ROOT / "data/reality-v8/extended-south-approach-development"
PUBLIC = ROOT / "artifacts/reality/v8/south-approach-length-ablation-development.json"
START, END = 30, 300
EXTENSION_START_LOCAL_Y_FT = 700


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def shape_points(text):
    return np.array([[float(value) for value in pair.split(",")] for pair in text.split()])


def shape_text(points):
    return " ".join(f"{x:.9f},{y:.9f}" for x, y in points)


def controlled_connections(root):
    return sorted(
        tuple(row.get(key) for key in ("from", "to", "fromLane", "toLane", "dir", "linkIndex"))
        for row in root.findall("connection")
        if row.get("tl") == "J"
    )


def point_at(lane, position):
    points = shape_points(lane.get("shape"))
    segment = np.linalg.norm(np.diff(points, axis=0), axis=1)
    arclength = np.concatenate(([0], np.cumsum(segment)))
    return np.array([np.interp(position, arclength, points[:, axis]) for axis in (0, 1)])


def main():
    if PUBLIC.exists() or (TARGET / "simulation.fcd.xml.gz").exists():
        raise FileExistsError("Preserve completed approach-length ablation")
    source = development_observations(301)
    source = source[source.t < END]
    road, _ = road_model(source)
    _, scoring = reference_states(source, road)
    nodes = ET.parse(PLAIN / "nodes.xml")
    edges = ET.parse(PLAIN / "edges.xml")
    incoming = edges.find("edge[@id='S_in']")
    outgoing = edges.find("edge[@id='S_out']")
    south_node = nodes.find("node[@id='S']")
    if incoming is None or outgoing is None or south_node is None:
        raise ValueError("Missing original southern approach")
    original_shape = shape_points(incoming.get("shape"))
    extension = road(np.linspace(EXTENSION_START_LOCAL_Y_FT, 960, 41))[:-1]
    if np.linalg.norm(extension[-1] - original_shape[0]) > 2:
        raise ValueError("Estimated extension does not connect to original road")
    new_shape = np.vstack([extension, original_shape])
    south_node.set("x", str(new_shape[0, 0]))
    south_node.set("y", str(new_shape[0, 1]))
    incoming.set("shape", shape_text(new_shape))
    outgoing.set("shape", shape_text(new_shape[::-1]))
    TARGET.mkdir(parents=True, exist_ok=True)
    nodes.write(TARGET / "nodes.xml")
    edges.write(TARGET / "edges.xml")
    checked(
        [
            binary("netconvert"),
            "--node-files",
            str(TARGET / "nodes.xml"),
            "--edge-files",
            str(TARGET / "edges.xml"),
            "--output-file",
            str(TARGET / "network.net.xml"),
            "--offset.disable-normalization",
            "true",
            "--no-turnarounds",
            "true",
        ],
        TARGET / "netconvert.log",
    )
    base_network = ET.parse(BASE / "network.net.xml")
    trial_network = ET.parse(TARGET / "network.net.xml")
    before = base_network.getroot()
    after = trial_network.getroot()
    if controlled_connections(before) != controlled_connections(after):
        raise ValueError("Approach extension changed signal-controlled lane connections")
    old_logic = before.find("tlLogic[@id='J']")
    new_logic = after.find("tlLogic[@id='J']")
    if old_logic is None or new_logic is None:
        raise ValueError("Signal logic missing")
    index = list(after).index(new_logic)
    after.remove(new_logic)
    after.insert(index, copy.deepcopy(old_logic))
    trial_network.write(TARGET / "network.net.xml", encoding="utf-8")
    old_lanes = {
        lane.get("id"): lane for edge in before.findall("edge") for lane in edge.findall("lane")
    }
    new_lanes = {
        lane.get("id"): lane for edge in after.findall("edge") for lane in edge.findall("lane")
    }
    routes = ET.parse(BASE / "routes.xml")
    mapping = {}
    shifts = []
    adjusted = 0
    lengths = {}
    for edge_name in ("S_in", "S_out"):
        lengths[edge_name] = {
            "before_m": float(old_lanes[f"{edge_name}_0"].get("length")),
            "after_m": float(new_lanes[f"{edge_name}_0"].get("length")),
        }
    for vehicle in routes.findall("vehicle"):
        identity = vehicle.get("id")
        mapping[identity.removeprefix("ref_")] = {
            "native_id": identity,
            "birth_s": float(vehicle.get("depart")),
        }
        edge = vehicle.find("route").get("edges").split()[0]
        if edge not in lengths:
            continue
        lane_id = f"{edge}_{vehicle.get('departLane')}"
        old_lane = old_lanes[lane_id]
        new_lane = new_lanes[lane_id]
        old_position = float(vehicle.get("departPos"))
        delta = float(new_lane.get("length")) - float(old_lane.get("length"))
        new_position = old_position + delta if edge == "S_in" else old_position
        if edge == "S_out":
            # J->S is extended only after the existing near-junction section.
            new_position = old_position
        shifts.append(
            float(
                np.linalg.norm(point_at(old_lane, old_position) - point_at(new_lane, new_position))
            )
        )
        if shifts[-1] > 0.25:
            raise ValueError("Reference initial world position changed")
        vehicle.set("departPos", f"{new_position:.2f}")
        adjusted += 1
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

    def summary(directory):
        result = physical_errors(mapping, scoring, native_states(directory), START, END)
        return {
            "reference_states": result["reference_observations"],
            "native_presence": result["native_presence_coverage"],
            "within_4m_reference_coverage": result["within_4m_reference_coverage"],
            "uncapped_position_mae_m": result["uncapped_position_m"]["mae"],
            "matched_speed_mae_mps": result["matched_speed_mps"]["mae"],
        }

    report = {
        "schema": "atlas-v8-south-approach-length-oracle-ablation-1",
        "window_s": [START, END],
        "source_scope": "Already exposed development; reference first-state oracle. The added southward geometry is estimated and no new independent test is scored.",
        "experiment": "Longer S_in/S_out edges outside the previous boundary; identical near-J lane connections and exact same original signal program, initial world positions within 0.25 m, vehicle types, depart times/speeds, seed and safety checks.",
        "extended_start_local_y_ft": EXTENSION_START_LOCAL_Y_FT,
        "edge_lengths_m": lengths,
        "adjusted_route_births": adjusted,
        "maximum_initial_pose_shift_m": max(shifts),
        "same_controlled_connections": True,
        "physical_twin_accepted": False,
        "before": summary(BASE),
        "extended_approach": summary(TARGET),
        "source_sha256": sha(Path(__file__)),
        "plain_nodes_sha256": sha(PLAIN / "nodes.xml"),
        "plain_edges_sha256": sha(PLAIN / "edges.xml"),
        "baseline_network_sha256": sha(BASE / "network.net.xml"),
        "trial_network_sha256": sha(TARGET / "network.net.xml"),
        "trial_native_fcd_sha256": sha(TARGET / "simulation.fcd.xml.gz"),
    }
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "edge_lengths_m",
                    "maximum_initial_pose_shift_m",
                    "before",
                    "extended_approach",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
