"""Observed-boundary SUMO baseline; independent interior observations are scored only afterward.

This deliberately separate experiment diagnoses physical-model error before CV-driven
boundary error is added. See cv_driven_ngsim_v6.py for the end-to-end experiment.
"""

import argparse
import gzip
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from atlas.city_network import binary
from atlas.reality_v6 import matched_errors

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/reality-v6"
EPOCH = 1118935680000
METRES = 1200 / 3937
ORIGIN = np.array([6452300.0, 1873700.0])
LOW, HIGH, JUNCTION = 960.0, 1410.0, 1045.0


def load_observations(epoch=EPOCH):
    frames = []
    for path in sorted((DATA / "trajectory-pages").glob("*.gz")):
        frame = pd.read_csv(path)
        frame = frame[frame.global_time - (frame.frame_id - 1) * 100 == epoch]
        if len(frame):
            frames.append(frame)
    result = pd.concat(frames, ignore_index=True).sort_values(["vehicle_id", "global_time"])
    if result.duplicated(["vehicle_id", "global_time"]).any():
        raise ValueError("Duplicate independent source observations")
    result["t"] = (result.global_time - epoch) / 1000
    return result


def features(x, y):
    x, y = np.asarray(x) * 0.3048, np.asarray(y) * 0.3048 / 100
    return np.column_stack([np.ones_like(y), y, y**2, y**3, x / 10, x * y / 10])


def road_model(observations):
    development = observations[
        (observations.t < 300)
        & observations.direction.isin([2, 4])
        & observations.section_id.isin([3, 4])
        & observations.lane_id.between(1, 4)
    ]
    design = features(development.local_x, development.local_y)
    target = (development[["global_x", "global_y"]].to_numpy() - ORIGIN) * METRES
    coefficients = np.linalg.lstsq(design, target, rcond=None)[0]

    def point(y):
        return features(np.zeros(np.size(y)), np.atleast_1d(y)) @ coefficients

    return point, {
        "development_rows": len(development),
        "global_origin_survey_ft": ORIGIN.tolist(),
        "coefficients": coefficients.tolist(),
        "fit_coordinate_rmse_m": np.sqrt(
            np.mean((design @ coefficients - target) ** 2, axis=0)
        ).tolist(),
        "scope": "Estimated median from first-five-minute coordinate pairs, checked against FHWA GIS/road schematic; not an engineering-grade lane survey",
    }


def source_entries(observations):
    entries, complete = [], []
    for identity, track in observations.groupby("vehicle_id", sort=True):
        rows = track.to_dict("records")
        inside = [LOW < r["local_y"] < HIGH and abs(r["local_x"]) < 70 for r in rows]
        for index in range(1, len(rows)):
            if inside[index] and not inside[index - 1]:
                prior, current = rows[index - 1], rows[index]
                side = (
                    "N"
                    if prior["local_y"] >= HIGH
                    else "S"
                    if prior["local_y"] <= LOW
                    else "E"
                    if prior["local_x"] >= 70
                    else "W"
                )
                entry = {
                    "id": str(int(identity)),
                    "t": current["t"],
                    "side": side,
                    "lane": int(current["lane_id"]),
                    "speed": float(current["v_vel"]) * 0.3048,
                    "length": float(current["v_length"]) * 0.3048,
                }
                entries.append(entry)
                for following in rows[index + 1 :]:
                    if not (LOW < following["local_y"] < HIGH and abs(following["local_x"]) < 70):
                        destination = (
                            "N"
                            if following["local_y"] >= HIGH
                            else "S"
                            if following["local_y"] <= LOW
                            else "E"
                            if following["local_x"] >= 70
                            else "W"
                        )
                        if following["t"] < 300 and destination != side:
                            complete.append((side, destination))
                        break
                break
    probabilities = {}
    for side in "NSEW":
        counts = Counter(destination for origin, destination in complete if origin == side)
        probabilities[side] = (
            dict(counts) if counts else {dict(N="S", S="N", E="W", W="E")[side]: 1}
        )
    return sorted(entries, key=lambda row: (row["t"], row["id"])), probabilities


def checked(command, log):
    response = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=300,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    log.write_text(response.stdout + response.stderr, encoding="utf-8")
    if response.returncode or "Error:" in response.stdout or "Error:" in response.stderr:
        raise RuntimeError(f"Native process failed; inspect {log}")


def rsm_rows():
    path = (
        DATA
        / "support/signal-timing/real-time-split-monitor-reports/Original Text files/RSM089-061605.txt"
    )
    rows = []
    for line in path.read_text().splitlines():
        fields = line.split()
        if fields and len(fields[0]) == 8 and fields[0][2] == ":":
            h, m, s = map(int, fields[0].split(":"))
            rows.append(
                {"time": h * 3600 + m * 60 + s, "cycle": int(fields[2]), "green": int(fields[5])}
            )
    return rows


def signal_stage(t, rows, clock_origin_s=8 * 3600 + 27 * 60 + 34):
    # FHWA: source 08:28:00 corresponds to RSM 08:27:34.
    clock = clock_origin_s + t
    row = max((row for row in rows if row["time"] <= clock), key=lambda row: row["time"])
    age = (clock - row["time"]) % row["cycle"]
    if row["green"] >= row["cycle"]:
        return "main"
    green = min(row["green"], row["cycle"] - 8.5)
    if age < green:
        return "main"
    if age < green + 3.5:
        return "main_yellow"
    if age < green + 4.5 or age >= row["cycle"] - 1:
        return "red"
    if age >= row["cycle"] - 4:
        return "cross_yellow"
    return "cross"


def build(
    directory,
    observations,
    point,
    tau,
    desired_speed,
    seed,
    entries_override=None,
    duration_s=1122,
    clock_origin_s=8 * 3600 + 27 * 60 + 34,
):
    nodes = ET.Element("nodes")
    center = point(JUNCTION)[0]
    tangent = point(JUNCTION + 1)[0] - point(JUNCTION - 1)[0]
    tangent /= np.linalg.norm(tangent)
    normal = np.array([tangent[1], -tangent[0]])
    coordinates = {
        "J": center,
        "N": point(HIGH)[0],
        "S": point(LOW)[0],
        "E": center + normal * 70 * 0.3048,
        "W": center - normal * 70 * 0.3048,
    }
    for identity, xy in coordinates.items():
        ET.SubElement(
            nodes,
            "node",
            id=identity,
            x=str(xy[0]),
            y=str(xy[1]),
            type="traffic_light" if identity == "J" else "priority",
        )
    ET.ElementTree(nodes).write(directory / "nodes.xml")
    edges = ET.Element("edges")
    lanes = {"N": (4, 4), "S": (3, 3), "E": (2, 1), "W": (2, 1)}
    for side in "NSEW":
        ys = np.linspace(HIGH if side == "N" else LOW, JUNCTION, 25)
        shape = point(ys) if side in "NS" else np.array([coordinates[side], center])
        for inbound, count in [(True, lanes[side][0]), (False, lanes[side][1])]:
            points = shape if inbound else shape[::-1]
            ET.SubElement(
                edges,
                "edge",
                {
                    "id": f"{side}_{'in' if inbound else 'out'}",
                    "from": side if inbound else "J",
                    "to": "J" if inbound else side,
                    "numLanes": str(count),
                    "speed": str(desired_speed),
                    "width": "3.35",
                    "spreadType": "right",
                    "shape": " ".join(f"{x},{y}" for x, y in points),
                },
            )
    ET.ElementTree(edges).write(directory / "edges.xml")
    checked(
        [
            binary("netconvert"),
            "--node-files",
            str(directory / "nodes.xml"),
            "--edge-files",
            str(directory / "edges.xml"),
            "--output-file",
            str(directory / "network.net.xml"),
            "--offset.disable-normalization",
            "true",
            "--no-turnarounds",
            "true",
        ],
        directory / "netconvert.log",
    )
    network = ET.parse(directory / "network.net.xml")
    logic = network.find("tlLogic")
    connections = [c for c in network.findall("connection") if c.get("tl") == "J"]
    size = max(int(c.get("linkIndex")) for c in connections) + 1

    def state(stage):
        value = ["r"] * size
        for connection in connections:
            main = connection.get("from")[0] in "NS"
            selected = (stage.startswith("main") and main) or (
                stage.startswith("cross") and not main
            )
            if selected:
                value[int(connection.get("linkIndex"))] = (
                    "y"
                    if stage.endswith("yellow")
                    else "G"
                    if connection.get("dir") == "s"
                    else "g"
                )
        return "".join(value)

    for child in list(logic):
        logic.remove(child)
    phases = []
    timing = rsm_rows()
    for tick in range(int((duration_s + 100) * 10)):
        value = state(signal_stage(tick / 10, timing, clock_origin_s))
        if phases and phases[-1][0] == value:
            phases[-1][1] += 0.1
        else:
            phases.append([value, 0.1])
    for value, duration in phases:
        ET.SubElement(logic, "phase", duration=f"{duration:.1f}", state=value)
    network.write(directory / "network.net.xml")
    entries, probabilities = source_entries(
        observations if entries_override is None else observations[observations.t < 300]
    )
    if entries_override is not None:
        entries = entries_override
    routes = ET.Element("routes")
    generator = np.random.default_rng(seed)
    inputs = []
    for entry in entries:
        destinations = list(probabilities[entry["side"]])
        weights = np.array(list(probabilities[entry["side"]].values()), dtype=float)
        destination = generator.choice(destinations, p=weights / weights.sum())
        identity = "observed_" + entry["id"]
        ET.SubElement(
            routes,
            "vType",
            id=identity,
            length=str(entry["length"]),
            tau=str(tau),
            accel="2.6",
            decel="4.5",
            sigma="0.3",
            speedFactor="1",
            speedDev="0",
            maxSpeed=str(desired_speed),
        )
        count = lanes[entry["side"]][0]
        lane = (
            count - entry["lane"]
            if 1 <= entry["lane"] <= count
            else count - 1
            if entry["lane"] >= 11 and entry["lane"] < 31
            else 0
        )
        vehicle = ET.SubElement(
            routes,
            "vehicle",
            id=entry["id"],
            type=identity,
            depart=f"{entry['t']:.1f}",
            departLane=str(lane),
            departSpeed="max",
            departPos="0",
        )
        ET.SubElement(vehicle, "route", edges=f"{entry['side']}_in {destination}_out")
        inputs.append({**entry, "sampled_destination": str(destination)})
    ET.ElementTree(routes).write(directory / "routes.xml")
    return {
        "entries": len(entries),
        "route_frequency_development": probabilities,
        "inputs": inputs,
        "boundary_speed_scope": "Source entry speed is retained for auditing but not imposed. SUMO max insertion chooses the safe speed up to the configured desired speed, avoiding impossible fixed-speed insertion on short approaches. No safety checks disabled.",
        "signal_scope": "Approximate two-stage reduction of independent RSM89 mainline split, assuming row timestamps begin cycles; 26 s source clock correction. Minor phase sequence, turn bays and midblock driveways are not reconstructed; exact lamp states are not independently validated.",
    }


def evaluate(directory, observations, point):
    # Freeze model inputs first; only now read independent interior states for scoring.
    predictions = []
    with gzip.open(directory / "simulation.fcd.xml.gz", "rb") as handle:
        for _, element in ET.iterparse(handle, events=("end",)):
            if element.tag == "timestep":
                t = float(element.get("time"))
                if 600 <= t < 1000:
                    for vehicle in element:
                        predictions.append(
                            {
                                "id": int(vehicle.get("id")),
                                "t": t,
                                "x": float(vehicle.get("x")),
                                "y": float(vehicle.get("y")),
                                "speed": float(vehicle.get("speed")),
                            }
                        )
                element.clear()
    actual = observations[
        (observations.t >= 600)
        & (observations.t < 1000)
        & (observations.global_time % 1000 == 0)
        & observations.local_y.between(1090, 1360)
        & observations.direction.isin([2, 4])
        & observations.lane_id.between(1, 4)
    ].copy()
    actual["x"] = (actual.global_x - ORIGIN[0]) * METRES
    actual["y"] = (actual.global_y - ORIGIN[1]) * METRES
    lookup = {(r["id"], round(r["t"])): r for r in predictions}
    speeds, speed_predictions, positions = [], [], []
    coverage = Counter()
    for row in actual.to_dict("records"):
        prediction = lookup.get((int(row["vehicle_id"]), round(row["t"])))
        speeds.append(float(row["v_vel"]) * 0.3048)
        speed_predictions.append(prediction["speed"] if prediction else None)
        coverage["eligible"] += 1
        if prediction:
            coverage["matched"] += 1
            positions.append(
                float(
                    np.linalg.norm(
                        np.array([row["x"], row["y"]]) - [prediction["x"], prediction["y"]]
                    )
                )
            )
    return {
        "split": "First recording validation 08:38:00–08:44:40 PDT; separate from development/calibration and reserved second-recording final holdout",
        "window_seconds": [600, 1000],
        "reference": "Independent FHWA source interior positions/speeds; never passed into SUMO",
        "conditioning": "Independent observed boundary arrival time/lane/length and fixed independent signal-monitor reports. Insertion speed is chosen safely by SUMO, not imposed from the reference. This diagnostic does not include CV errors.",
        "speed_mps": matched_errors(speeds, speed_predictions),
        "front_position_error_m": {
            "mean": float(np.mean(positions)) if positions else None,
            "p95": float(np.percentile(positions, 95)) if positions else None,
            "matched_observations": len(positions),
        },
        "eligible_vehicles": int(actual.vehicle_id.nunique()),
        "validated_physical_twin": False,
        "scope": "Observation-conditioned boundary diagnostic only, not the end-to-end CV-driven experiment. Incomplete lane/turn-bay/driveway geometry and approximate signal phasing. Separate artifacts report CV-driven aggregate errors; no accepted physical fidelity.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tau", type=float, default=1.0)
    parser.add_argument("--desired-speed", type=float, default=15.65)
    parser.add_argument("--seed", type=int, default=66001)
    args = parser.parse_args()
    if args.tau < 0.1 or not 5 <= args.desired_speed <= 30:
        raise ValueError("Invalid bounded physical model settings")
    directory = DATA / f"reconstruction-{args.tau}-{args.desired_speed}-{args.seed}"
    directory.mkdir(parents=True, exist_ok=True)
    observations = load_observations()
    point, geometry = road_model(observations)
    inputs = build(directory, observations, point, args.tau, args.desired_speed, args.seed)
    (directory / "inputs.json").write_text(
        json.dumps({"geometry": geometry, **inputs}, indent=2), encoding="utf-8"
    )
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
            str(args.seed),
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
    results = evaluate(directory, observations, point)
    results["model"] = vars(args)
    results["source_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (directory / "validation.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2), flush=True)


if __name__ == "__main__":
    main()
