"""Free-running SUMO initialized at observed CV births inside the camera footprint.

This fixes unobservable outer-boundary admission, while changing conditioning:
initial observed interior states are admitted once. They never force later states.
It is not an apples-to-apples outer-boundary prediction accuracy improvement.
"""

import argparse
import gzip
import hashlib
import json
import xml.etree.ElementTree as ET
from collections import defaultdict, deque
from itertools import takewhile
from pathlib import Path

import cv2
import numpy as np
from atlas.city_network import binary
from cv_driven_ngsim_v6 import evaluate_aggregate, geometry_mapper
from diagnose_ngsim_v7 import DATA, ROOT, development_observations
from reconstruct_ngsim_v6 import build, checked, road_model


def lane_project(point, shape):
    vectors = np.diff(shape, axis=0)
    squared = np.sum(vectors * vectors, axis=1)
    fractions = np.clip(
        np.sum((point - shape[:-1]) * vectors, axis=1) / np.maximum(squared, 1e-9), 0, 1
    )
    projections = shape[:-1] + vectors * fractions[:, None]
    distances = np.linalg.norm(projections - point, axis=1)
    index = int(np.argmin(distances))
    lengths = np.sqrt(squared)
    return (
        float(distances[index]),
        float(lengths[:index].sum() + fractions[index] * lengths[index]),
        vectors[index] / max(lengths[index], 1e-9),
    )


def arrivals(frames, network, matrix, local):
    lanes = []
    for edge in network.findall("edge"):
        if edge.get("id", "").startswith(":") or edge.get("id") not in {
            "N_in",
            "S_in",
            "N_out",
            "S_out",
        }:
            continue
        for lane in edge.findall("lane"):
            lanes.append(
                {
                    "edge": edge.get("id"),
                    "id": lane.get("id"),
                    "index": lane.get("index"),
                    "length": float(lane.get("length")),
                    "shape": np.array(
                        [[float(v) for v in pair.split(",")] for pair in lane.get("shape").split()]
                    ),
                }
            )
    histories = defaultdict(deque)
    admitted = set()
    entries = []
    diagnostic = defaultdict(int)
    for frame in frames:
        time = frame["index"] / 10
        for obj in frame["objects"]:
            if obj["class"] not in {"car", "truck", "bus", "motorcycle"} or obj.get("inferred"):
                continue
            identity = obj["id"]
            x1, y1, x2, y2 = obj["bbox"]
            point = cv2.perspectiveTransform(
                np.float64([[[(x1 + x2) / 2, (y1 + y2) / 2]]]), matrix
            )[0, 0]
            road_position = local([point])[0]
            if not 970 < road_position[1] < 1400 or abs(road_position[0]) * 0.3048 > 16:
                continue
            history = histories[identity]
            if history and time - history[-1][0] > 0.3:
                history.clear()
            history.append((time, point))
            while history and history[0][0] < time - 0.75:
                history.popleft()
            if identity in admitted or len(history) < 5:
                continue
            times = np.array([r[0] for r in history])
            points = np.array([r[1] for r in history])
            centered = times - times.mean()
            velocity = centered @ (points - points.mean(axis=0)) / (centered @ centered)
            speed = float(np.linalg.norm(velocity))
            if speed > 25:
                diagnostic["implausible_speed_rejected"] += 1
                continue
            northbound = road_position[0] >= 0
            eligible = {"S_in", "N_out"} if northbound else {"N_in", "S_out"}
            candidates = []
            for lane in lanes:
                if lane["edge"] not in eligible:
                    continue
                distance, position, tangent = lane_project(point, lane["shape"])
                if speed > 1 and np.dot(velocity / speed, tangent) < 0.4:
                    continue
                candidates.append((distance, lane, position, tangent))
            if not candidates:
                diagnostic["no_heading_consistent_lane"] += 1
                continue
            distance, lane, position, tangent = min(candidates, key=lambda row: row[0])
            if distance > 6:
                diagnostic["outside_lane_gate_rejected"] += 1
                continue
            length = (
                10
                if obj["class"] == "bus"
                else 7
                if obj["class"] == "truck"
                else 2
                if obj["class"] == "motorcycle"
                else 4.5
            )
            position = float(np.clip(position + length * 0.5, 0, max(0, lane["length"] - 0.2)))
            remaining = max(0, lane["length"] - position)
            # A requested fixed speed can be physically impossible to insert near
            # a junction. Bound it by reaction + braking distance, keeping all SUMO
            # safety checks enabled. Record clipping instead of hiding it.
            safe_speed = max(0, np.sqrt(4.5**2 + 2 * 4.5 * remaining) - 4.5)
            entries.append(
                {
                    "id": f"cv_{identity}",
                    "t": time,
                    "edge": lane["edge"],
                    "lane": int(lane["index"]),
                    "position_m": position,
                    "speed_mps": float(min(speed, 15.65, safe_speed)),
                    "requested_cv_speed_mps": speed,
                    "safety_clipped": bool(speed > safe_speed),
                    "length_m": length,
                    "class": obj["class"],
                    "observed_world_m": point.tolist(),
                    "projection_residual_m": distance,
                    "conditioning": "One observed CV birth pose/speed, after five actual consecutive detections; no future state forcing",
                }
            )
            admitted.add(identity)
    return entries, dict(diagnostic)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--window", nargs=2, type=int, default=[60, 180])
    parser.add_argument("--variant", default="safe-start-v2")
    args = parser.parse_args()
    start, end = args.window
    if not 0 <= start < end <= 1000:
        raise ValueError("No test outcomes in development reconstruction")
    out = (
        ROOT
        / "data/reality-v7"
        / f"birth-reconstruction-{args.directory.name}-{start}-{end}-{args.variant}"
    )
    out.mkdir(parents=True, exist_ok=True)
    if (out / "validation.json").exists():
        raise FileExistsError("Never overwrite a measured reconstruction")
    development = development_observations(300)
    road, geometry = road_model(development)
    local = geometry_mapper(road)
    build(out, development, road, 1.0, 15.65, 77001, entries_override=[], duration_s=end)
    network = ET.parse(out / "network.net.xml")
    calibration = np.asarray(
        json.loads((DATA / "camera4-calibration.json").read_text())["raw_to_world"]
    )
    with gzip.open(args.directory / "frames.jsonl.gz", "rt", encoding="utf-8") as handle:
        frames = takewhile(
            lambda frame: frame["index"] < end * 10, (json.loads(line) for line in handle)
        )
        entries, diagnostic = arrivals(frames, network.getroot(), calibration, local)
    routes = ET.Element("routes")
    for kind, length in [("car", 4.5), ("truck", 7), ("bus", 10), ("motorcycle", 2)]:
        ET.SubElement(
            routes,
            "vType",
            id=kind,
            length=str(length),
            tau="1",
            accel="2.6",
            decel="4.5",
            sigma=".3",
            maxSpeed="15.65",
            speedFactor="1",
            speedDev="0",
        )
    for row in entries:
        vehicle = ET.SubElement(
            routes,
            "vehicle",
            id=row["id"],
            type=row["class"],
            depart=f"{row['t']:.1f}",
            departLane=str(row["lane"]),
            departPos=f"{row['position_m']:.2f}",
            departSpeed=f"{row['speed_mps']:.2f}",
        )
        edges = {"N_in": "N_in S_out", "S_in": "S_in N_out", "N_out": "N_out", "S_out": "S_out"}[
            row["edge"]
        ]
        ET.SubElement(vehicle, "route", edges=edges)
    ET.ElementTree(routes).write(out / "routes.xml")
    inputs = {
        "geometry": geometry,
        "entries": entries,
        "diagnostics": diagnostic,
        "scope": __doc__,
        "perception_frames_sha256": hashlib.sha256(
            (args.directory / "frames.jsonl.gz").read_bytes()
        ).hexdigest(),
    }
    (out / "inputs.json").write_bytes(json.dumps(inputs, indent=2).encode())
    checked(
        [
            binary("sumo"),
            "-n",
            str(out / "network.net.xml"),
            "-r",
            str(out / "routes.xml"),
            "--begin",
            "0",
            "--end",
            str(end),
            "--step-length",
            ".1",
            "--seed",
            "77001",
            "--fcd-output",
            str(out / "simulation.fcd.xml.gz"),
            "--device.fcd.period",
            "1",
            "--tripinfo-output",
            str(out / "tripinfo.xml"),
            "--no-step-log",
            "true",
            "--duration-log.disable",
            "true",
            "--time-to-teleport",
            "-1",
        ],
        out / "sumo.log",
    )
    # Only after network, demand, routes and simulation outputs are fixed, load scoring labels.
    scoring = development_observations(end + 1)
    report = evaluate_aggregate(out, scoring, local, window=(start, end))
    report.update(
        {
            "split": f"Known development/regression interval [{start},{end}) s",
            "driven_by": "CV birth-initialized free-running SUMO; one observed interior state per admitted track",
            "conditioning": "Changed from v6 outer-boundary-only conditioning. This is an initialization/admission ablation, not a same-input physical-model improvement.",
            "arrivals": len(entries),
            "admission_diagnostics": diagnostic,
            "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "inputs_sha256": hashlib.sha256((out / "inputs.json").read_bytes()).hexdigest(),
        }
    )
    (out / "validation.json").write_bytes(json.dumps(report, indent=2).encode())
    target = (
        ROOT
        / "artifacts/reality/v7"
        / f"birth-reconstruction-{args.directory.name}-{start}-{end}-{args.variant}.json"
    )
    target.write_bytes(json.dumps(report, indent=2).encode())
    print(
        json.dumps(
            {
                key: report[key]
                for key in [
                    "arrivals",
                    "instantaneous_vehicle_count",
                    "sb_queue_count",
                    "crossing_counts",
                    "validated_physical_twin",
                ]
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
