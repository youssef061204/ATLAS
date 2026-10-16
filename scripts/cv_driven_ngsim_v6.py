"""Run actual SUMO using arrivals estimated only from complete ATLAS CV tracks.

Independent NGSIM labels supply development road geometry/turn frequencies and
post-run scoring, never per-vehicle CV-run arrivals, future paths or states.
"""

import gzip
import hashlib
import json
import xml.etree.ElementTree as ET
from collections import defaultdict, deque
from pathlib import Path

import cv2
import numpy as np
from atlas.city_network import binary
from atlas.reality_v6 import matched_errors
from reconstruct_ngsim_v6 import (
    DATA,
    HIGH,
    LOW,
    METRES,
    ORIGIN,
    build,
    checked,
    load_observations,
    road_model,
)
from scipy.spatial import cKDTree
from scipy.stats import wasserstein_distance


def geometry_mapper(road):
    grid = np.linspace(LOW - 100, HIGH + 100, 2601)
    curve = road(grid)
    tangent = np.gradient(curve, axis=0)
    tangent /= np.linalg.norm(tangent, axis=1)[:, None]
    normal = tangent[:, ::-1] * [1, -1]
    tree = cKDTree(curve)

    def local(points):
        points = np.array(points).reshape(-1, 2)
        _, nearest = tree.query(points)
        lateral = np.sum((points - curve[nearest]) * normal[nearest], axis=1)
        return np.column_stack([lateral / 0.3048, grid[nearest]])

    return local


def inside(point):
    return LOW < point[1] < HIGH and abs(point[0]) < 70


def entry_side(prior):
    return "N" if prior[1] >= HIGH else "S" if prior[1] <= LOW else "E" if prior[0] >= 70 else "W"


def video_entries(result, matrix, local):
    histories = defaultdict(deque)
    previous, admitted = {}, set()
    entries = []
    for frame in result["frames"]:
        time = frame["index"] / 10
        for obj in frame["objects"]:
            if obj["class"] not in {"car", "truck", "bus", "motorcycle"}:
                continue
            x1, y1, x2, y2 = obj["bbox"]
            pixel = np.float64([[[0.5 * (x1 + x2), 0.5 * (y1 + y2)]]])
            world = cv2.perspectiveTransform(pixel, matrix)[0, 0]
            point = local([world])[0]
            identity = obj["id"]
            history = histories[identity]
            if history and time - history[-1][0] > 0.3:
                history.clear()
                previous.pop(identity, None)
            history.append((time, world))
            while history and history[0][0] < time - 0.75:
                history.popleft()
            prior = previous.get(identity)
            if (
                identity not in admitted
                and prior is not None
                and not inside(prior)
                and inside(point)
                and len(history) >= 3
            ):
                side = entry_side(prior)
                times = np.array([r[0] for r in history])
                positions = np.array([r[1] for r in history])
                centered = times - times.mean()
                speed = float(
                    np.linalg.norm(
                        centered @ (positions - positions.mean(axis=0)) / (centered @ centered)
                    )
                )
                # Box corners projected to the road plane provide an explicit noisy length estimate.
                corners = cv2.perspectiveTransform(
                    np.float64([[[x1, y1], [x2, y1], [x2, y2], [x1, y2]]]), matrix
                )[0]
                extent = float(
                    max(
                        np.linalg.norm(corners[0] - corners[2]),
                        np.linalg.norm(corners[1] - corners[3]),
                    )
                )
                length = float(np.clip(extent, 3, 16))
                maximum = 4 if side == "N" else 3 if side == "S" else 2
                lane = (
                    int(np.clip(np.floor((abs(point[0]) * 0.3048 - 1.3) / 3.35) + 1, 1, maximum))
                    if side in "NS"
                    else 1
                )
                entries.append(
                    {
                        "id": f"cv_{identity}",
                        "t": time,
                        "side": side,
                        "lane": lane,
                        "speed": speed,
                        "length": length,
                        "source": "ATLAS calibrated raw-video box-center crossing; no reference vehicle state",
                        "initial_world_m": world.tolist(),
                    }
                )
                admitted.add(identity)
            previous[identity] = point
    return sorted(entries, key=lambda row: (row["t"], row["id"]))


def crossing_times(tracks, window=(600, 1000)):
    start, end = window
    flows = defaultdict(list)
    travel = {"N": [], "S": []}
    for rows in tracks.values():
        rows = sorted(rows, key=lambda row: row[0])
        crossings = defaultdict(list)
        for a, b in zip(rows[:-1], rows[1:], strict=True):
            if b[0] - a[0] > 1.5:
                continue
            for line in [1090, 1360]:
                if (a[2] < line <= b[2]) or (b[2] <= line < a[2]):
                    direction = "N" if b[2] > a[2] else "S"
                    time = a[0] + (b[0] - a[0]) * (line - a[2]) / (b[2] - a[2])
                    if abs(a[1]) < 55 and abs(b[1]) < 55:
                        crossings[(direction, line)].append(time)
        for (direction, line), times in crossings.items():
            flows[(direction, line)].extend(t for t in times if start <= t < end)
        for direction, first, last in [("N", 1090, 1360), ("S", 1360, 1090)]:
            starts, ends = crossings[(direction, first)], crossings[(direction, last)]
            if len(starts) == 1 and len(ends) == 1 and start <= starts[0] < ends[0] < end:
                travel[direction].append(ends[0] - starts[0])
    return flows, travel


def evaluate_aggregate(directory, observations, local, window=(600, 1000)):
    start, end = window
    predicted, reference = defaultdict(list), defaultdict(list)
    native_frames, observed_frames = defaultdict(list), defaultdict(list)
    with gzip.open(directory / "simulation.fcd.xml.gz", "rb") as handle:
        for _, element in ET.iterparse(handle, events=("end",)):
            if element.tag == "timestep":
                time = float(element.get("time"))
                vehicles = list(element)
                positions = local([[float(v.get("x")), float(v.get("y"))] for v in vehicles])
                for vehicle, position in zip(vehicles, positions, strict=True):
                    row = (time, *map(float, position), float(vehicle.get("speed")))
                    predicted[vehicle.get("id")].append(row)
                    native_frames[round(time)].append((vehicle.get("id"), row))
                element.clear()
    actual = observations[observations.global_time % 1000 == 0]
    positions = local((actual[["global_x", "global_y"]].to_numpy() - ORIGIN) * METRES)
    for row, position in zip(actual.to_dict("records"), positions, strict=True):
        state = (float(row["t"]), *map(float, position), float(row["v_vel"]) * 0.3048)
        reference[str(row["vehicle_id"])].append(state)
        observed_frames[round(row["t"])].append((str(row["vehicle_id"]), state))
    observed_flow, observed_travel = crossing_times(reference, window)
    predicted_flow, predicted_travel = crossing_times(predicted, window)
    flow_metrics = {}
    bins = np.arange(start, end + 1, 30)
    if bins[-1] != end:
        bins = np.append(bins, end)
    for direction in "NS":
        for line in [1090, 1360]:
            key = (direction, line)
            a = np.histogram(observed_flow[key], bins=bins)[0].tolist()
            b = np.histogram(predicted_flow[key], bins=bins)[0].tolist()
            flow_metrics[f"{direction}_{line}"] = {
                **matched_errors(a, b),
                "observed_total": sum(a),
                "simulated_total": sum(b),
                "bin_seconds": 30,
                "last_bin_partial": bool((end - start) % 30),
                "bin_edges_s": bins.tolist(),
            }
    series = []
    histories = {"observed": defaultdict(int), "simulated": defaultdict(int)}
    for time in range(start, end):
        values = {"t": time}
        for name, frames in [("observed", observed_frames), ("simulated", native_frames)]:
            visible, queued, active = 0, 0, set()
            for identity, (_, x, y, speed) in frames.get(time, []):
                if 1090 <= y <= 1360 and abs(x) * 0.3048 <= 16:
                    visible += 1
                if 1090 <= y <= 1250 and -55 <= x < 0 and speed < 0.5:
                    active.add(identity)
                    histories[name][identity] += 1
                    queued += histories[name][identity] >= 3
            histories[name] = defaultdict(
                int, {identity: histories[name][identity] for identity in active}
            )
            values[name + "_vehicles"] = visible
            values[name + "_sb_queue"] = queued
        series.append(values)
    travel = {
        direction: {
            "observed_complete_traversals": len(observed_travel[direction]),
            "simulated_complete_traversals": len(predicted_travel[direction]),
            "observed_mean_s": float(np.mean(observed_travel[direction]))
            if observed_travel[direction]
            else None,
            "simulated_mean_s": float(np.mean(predicted_travel[direction]))
            if predicted_travel[direction]
            else None,
            "distribution_wasserstein_s": float(
                wasserstein_distance(observed_travel[direction], predicted_travel[direction])
            )
            if observed_travel[direction] and predicted_travel[direction]
            else None,
            "scope": "Unpaired traversal distributions, not individual-vehicle travel-time prediction error; both endpoints inside the validation window",
        }
        for direction in "NS"
    }
    return {
        "split": "development recording validation, 600–1000 seconds; final holdout not evaluated",
        "driven_by": "Actual complete raw-video ATLAS CV boundary crossings, estimated lanes and box-projected lengths; no ground-truth vehicle arrivals or interior states passed into SUMO",
        "conditioning": "Development-only NGSIM geometry and turn probabilities; independent RSM schedule; SUMO chooses safe insertion speed. This is an approximate baseline, not a validated physical twin.",
        "crossing_counts": flow_metrics,
        "travel_time_distributions": travel,
        "instantaneous_vehicle_count": matched_errors(
            [r["observed_vehicles"] for r in series], [r["simulated_vehicles"] for r in series]
        ),
        "sb_queue_count": {
            **matched_errors(
                [r["observed_sb_queue"] for r in series], [r["simulated_sb_queue"] for r in series]
            ),
            "observed_peak_vehicles": max(r["observed_sb_queue"] for r in series),
            "simulated_peak_vehicles": max(r["simulated_sb_queue"] for r in series),
            "definition": "<0.5 m/s at three consecutive 1 Hz samples (>=2 s), SB upstream band 1090–1250 local ft, lateral -55–0 ft; not physical queue-tail length",
        },
        "series": series,
        "validated_physical_twin": False,
        "limitations": [
            "Incomplete turn bays, bus layby and midblock driveways",
            "Approximate two-stage RSM phasing; signal lamps not independently decoded",
            "CV missed/fragmented tracks and boundary misses propagate into reconstruction",
            "Conditional counts/travel-time distributions do not establish per-vehicle physical accuracy or field intervention effects",
        ],
    }


def main():
    run = json.loads((DATA / "production-pipeline/run.json").read_text())
    result_path = Path(run["result_file"])
    result = json.loads(result_path.read_text())
    observations = load_observations()
    road, geometry = road_model(observations)
    local = geometry_mapper(road)
    calibration = json.loads((DATA / "camera4-calibration.json").read_text())
    entries = video_entries(result, np.array(calibration["raw_to_world"]), local)
    if not entries:
        raise ValueError("No real CV-derived boundary arrivals")
    directory = DATA / "cv-driven-reconstruction"
    directory.mkdir(parents=True, exist_ok=True)
    inputs = build(directory, observations, road, 1.0, 15.65, 66001, entries_override=entries)
    (directory / "inputs.json").write_text(
        json.dumps({"geometry": geometry, **inputs}, indent=2), encoding="utf-8"
    )
    print("CV-derived SUMO inputs", len(entries), flush=True)
    checked(
        [
            binary("sumo"),
            "-n",
            str(directory / "network.net.xml"),
            "-r",
            str(directory / "routes.xml"),
            "--begin",
            "0",
            "--end",
            "1122",
            "--step-length",
            "0.1",
            "--seed",
            "66001",
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
        ],
        directory / "sumo.log",
    )
    artifact = evaluate_aggregate(directory, observations, local)
    artifact["input_result_sha256"] = hashlib.sha256(result_path.read_bytes()).hexdigest()
    artifact["evaluator_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (directory / "validation.json").write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in artifact.items() if k != "series"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
