"""Trace ATLAS 7 Lankershim reference states through CV admission and native SUMO.

The 600-1000 s cohort was previously scored in ATLAS 6/7. This post-outcome
diagnostic cannot become a fresh held-out ATLAS 8 acceptance test. It uses the
same reference centering, ROI, birth association, and native body centering as
the retained ATLAS 7 physical metric; its stage counts must recompose that
metric exactly. No reference data enters an online admission or SUMO run.
"""

import argparse
import gzip
import hashlib
import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
from atlas.lifecycle_v8 import audit_lifecycle
from atlas.physical_metrics_v7 import birth_correspondence
from diagnose_ngsim_v7 import development_observations
from reconstruct_ngsim_v6 import DATA, METRES, ORIGIN, road_model
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
CV = ROOT / "data/reality-v7/full-v7-lankershim/frames.jsonl.gz"
NATIVE = ROOT / "data/reality-v7/eager-insertion/duration-1122"
WINDOWS = {"development": (0, 300), "known-regression": (600, 1000)}


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def reference_states(entries, start, end):
    source = development_observations(end=1001)
    road, _ = road_model(source)
    grid = np.linspace(960, 1410, 1801)
    curve = road(grid)
    tangents = np.gradient(curve, axis=0)
    tangents /= np.linalg.norm(tangents, axis=1)[:, None]
    tree = cKDTree(curve)

    def roi(points):
        array = np.asarray(points, dtype=float).reshape(-1, 2)
        if len(array) == 0:
            return np.array([], dtype=bool)
        _, nearest = tree.query(array)
        normal = tangents[nearest][:, ::-1] * [1, -1]
        lateral = np.sum((array - curve[nearest]) * normal, axis=1)
        return (grid[nearest] >= 1090) & (grid[nearest] <= 1360) & (abs(lateral) <= 16)

    world = (source[["global_x", "global_y"]].to_numpy() - ORIGIN) * METRES
    _, nearest = tree.query(world)
    heading = tangents[nearest] * np.where(source.direction.to_numpy() == 4, -1, 1)[:, None]
    previous = source.groupby("vehicle_id")[["global_x", "global_y"]].diff().to_numpy()
    magnitude = np.linalg.norm(previous, axis=1)
    valid = np.isfinite(magnitude) & (magnitude > 0.01)
    heading[valid] = previous[valid] / magnitude[valid, None]
    centers = world - source.v_length.to_numpy()[:, None] * 0.3048 * 0.5 * heading
    inside = (
        roi(centers)
        & source.direction.isin([2, 4]).to_numpy()
        & source.lane_id.between(1, 4).to_numpy()
    )
    requested_keys = {round(float(entry["t"]) * 10) for entry in entries}
    birth_reference, scoring_reference = defaultdict(list), defaultdict(list)
    for i, row in enumerate(source.itertuples()):
        key = round(row.t * 10)
        if key not in requested_keys and not (start * 10 <= key < end * 10 and key % 10 == 0):
            continue
        state = {"id": str(row.vehicle_id), "point": [row.global_x, row.global_y]}
        state["point"] = centers[i].tolist()
        if key in requested_keys:
            birth_reference[key].append(state)
        if start * 10 <= key < end * 10 and key % 10 == 0 and inside[i]:
            scoring_reference[key].append(state)
    return birth_reference, scoring_reference, roi


def cv_states(start, end, roi):
    matrix = np.asarray(
        json.loads((DATA / "camera4-calibration.json").read_text(encoding="utf-8"))["raw_to_world"]
    )
    frames = {}
    with gzip.open(CV, "rt", encoding="utf-8") as handle:
        for line in handle:
            frame = json.loads(line)
            index = frame["index"]
            if index >= end * 10:
                break
            if index < start * 10 or index % 10:
                continue
            objects = [
                obj
                for obj in frame["objects"]
                if obj["class"] in {"car", "bus", "truck", "motorcycle"}
                and not obj.get("inferred", False)
            ]
            if not objects:
                frames[index // 10] = []
                continue
            pixels = np.asarray(
                [
                    [(obj["bbox"][0] + obj["bbox"][2]) / 2, (obj["bbox"][1] + obj["bbox"][3]) / 2]
                    for obj in objects
                ],
                dtype=np.float64,
            )
            world = cv2.perspectiveTransform(pixels.reshape(1, -1, 2), matrix)[0]
            frames[index // 10] = [
                {"id": str(obj["id"]), "point": point.tolist()}
                for obj, point, keep in zip(objects, world, roi(world), strict=True)
                if keep
            ]
    missing = [t for t in range(start, end) if t not in frames]
    if missing:
        raise ValueError(f"Missing actual CV frames at 1 Hz: {missing[:5]}")
    return frames


def native_states():
    routes = ET.parse(NATIVE / "routes.xml")
    types = {row.get("id"): float(row.get("length")) for row in routes.findall("vType")}
    lengths = {row.get("id"): types[row.get("type")] for row in routes.findall("vehicle")}
    frames = defaultdict(list)
    with gzip.open(NATIVE / "simulation.fcd.xml.gz", "rb") as handle:
        for _, element in ET.iterparse(handle, events=("end",)):
            if element.tag != "timestep":
                continue
            t = round(float(element.get("time")))
            for vehicle in element:
                identity = vehicle.get("id")
                angle = np.deg2rad(float(vehicle.get("angle")))
                frames[t].append(
                    {
                        "id": identity,
                        "point": [
                            float(vehicle.get("x")) - np.sin(angle) * lengths[identity] / 2,
                            float(vehicle.get("y")) - np.cos(angle) * lengths[identity] / 2,
                        ],
                        "edge_lane": vehicle.get("lane"),
                    }
                )
            element.clear()
    return frames


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window", choices=WINDOWS, default="known-regression")
    args = parser.parse_args()
    start, end = WINDOWS[args.window]
    out = ROOT / "artifacts/reality/v8" / f"lifecycle-{args.window}.json"
    local = ROOT / "data/reality-v8" / f"lifecycle-{args.window}-vehicles.json"
    if out.exists() or local.exists():
        raise FileExistsError("Preserve measured audit outputs; use a new version for a new method")

    inputs = json.loads((NATIVE / "inputs.json").read_text(encoding="utf-8"))
    entries = [row for row in inputs["entries"] if row["t"] < end]
    birth_reference, scoring_reference, roi = reference_states(entries, start, end)
    mapping, association_diagnostics = birth_correspondence(entries, birth_reference)
    result = audit_lifecycle(
        scoring_reference,
        cv_states(start, end, roi),
        entries,
        mapping,
        native_states(),
        start,
        end,
    )
    if args.window == "known-regression":
        retained = json.loads(
            (ROOT / "artifacts/reality/v7/physical-current-acceptance.json").read_text(
                encoding="utf-8"
            )
        )["physical_errors"]
        if result["reference_states"] != retained["reference_observations"]:
            raise AssertionError("Reference denominator differs from preserved physical result")
        for key in ("native_presence_coverage", "within_4m_reference_coverage"):
            if abs(result[key] - retained[key]) > 1e-12:
                raise AssertionError(f"{key} differs from preserved physical result")
        if (
            abs(
                result["conditional_native_position_mae_m"] - retained["uncapped_position_m"]["mae"]
            )
            > 1e-9
        ):
            raise AssertionError("Uncapped native error differs from preserved physical result")

    vehicles = result.pop("per_vehicle")
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(json.dumps(vehicles, indent=2), encoding="utf-8")
    report = {
        "version": "ATLAS 8 post-outcome lifecycle diagnosis, method 1",
        "window_s": [start, end],
        "cohort": "Previously exposed development"
        if start == 0
        else "Previously exposed known regression",
        "not_independent_holdout": True,
        "gate_m": 4,
        "stage_accounting": result,
        "birth_association_diagnostics": association_diagnostics,
        "local_per_vehicle_audit_sha256": sha(local),
        "local_per_vehicle_audit_path": "data/reality-v8/" + local.name,
        "source_sha256": {
            "cv_frames": sha(CV),
            "native_inputs": sha(NATIVE / "inputs.json"),
            "native_fcd": sha(NATIVE / "simulation.fcd.xml.gz"),
            "camera_calibration": sha(DATA / "camera4-calibration.json"),
            "script": sha(Path(__file__)),
            "module": sha(ROOT / "backend/atlas/lifecycle_v8.py"),
        },
        "limits": [
            "Birth association is one spatial link at requested CV admission and can be wrong or absent; stages diagnose that association, not oracle identity.",
            "Same-second 4 m CV matches are one-to-one spatial matches, not verified identity labels or detection recall.",
            "First and last native timestamps are 1 Hz output samples, not exact insertion and exit times.",
            "The detailed per-vehicle audit is local and ignored by Git; only aggregate derived evidence is published.",
            "No new physical acceptance or controller promotion follows from this post-outcome audit.",
        ],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(out), **result}, indent=2))


if __name__ == "__main__":
    main()
