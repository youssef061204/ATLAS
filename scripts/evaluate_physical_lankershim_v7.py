"""Measure uncapped future physical errors for the completed native reconstruction."""

import gzip
import hashlib
import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import numpy as np
from atlas.physical_metrics_v7 import acceptance, birth_correspondence, physical_errors
from diagnose_ngsim_v7 import development_observations
from publish_replay_v7 import NATIVE, OUT, ROOT
from reconstruct_ngsim_v6 import METRES, ORIGIN, road_model
from scipy.spatial import cKDTree


def main():
    target = OUT / "physical-lankershim-regression.json"
    if target.exists():
        raise FileExistsError("Preserve measured physical evaluation")
    source = development_observations(end=1001)
    road, _ = road_model(source)
    grid = np.linspace(960, 1410, 1801)
    curve = road(grid)
    tangents = np.gradient(curve, axis=0)
    tangents /= np.linalg.norm(tangents, axis=1)[:, None]
    tree = cKDTree(curve)
    world = (source[["global_x", "global_y"]].to_numpy() - ORIGIN) * METRES
    _, nearest = tree.query(world)
    heading = tangents[nearest] * np.where(source.direction.to_numpy() == 4, -1, 1)[:, None]
    past = source.groupby("vehicle_id")[["global_x", "global_y"]].diff().to_numpy()
    magnitude = np.linalg.norm(past, axis=1)
    valid = np.isfinite(magnitude) & (magnitude > 0.01)
    heading[valid] = past[valid] / magnitude[valid, None]
    centers = world - source.v_length.to_numpy()[:, None] * 0.3048 * 0.5 * heading
    source["cx"], source["cy"] = centers.T
    all_reference, scoring_reference = defaultdict(list), defaultdict(list)
    _, nearest = tree.query(centers)
    normal = tangents[nearest][:, ::-1] * [1, -1]
    lateral = np.sum((centers - curve[nearest]) * normal, axis=1)
    inside = (
        (grid[nearest] >= 1090)
        & (grid[nearest] <= 1360)
        & (abs(lateral) <= 16)
        & source.direction.isin([2, 4]).to_numpy()
        & source.lane_id.between(1, 4).to_numpy()
    )
    for i, row in enumerate(source.itertuples()):
        state = {"id": str(row.vehicle_id), "point": [row.cx, row.cy], "speed": row.v_vel * 0.3048}
        key = round(row.t * 10)
        all_reference[key].append(state)
        if inside[i] and key % 10 == 0:
            scoring_reference[key].append(state)
    inputs = json.loads((NATIVE / "inputs.json").read_text())
    entries = [e for e in inputs["entries"] if e["t"] < 1000]
    mapping, diagnostic = birth_correspondence(entries, all_reference)
    routes = ET.parse(NATIVE / "routes.xml")
    types = {v.get("id"): float(v.get("length")) for v in routes.findall("vType")}
    lengths = {v.get("id"): types[v.get("type")] for v in routes.findall("vehicle")}
    native = defaultdict(list)
    present = set()
    with gzip.open(NATIVE / "simulation.fcd.xml.gz", "rb") as handle:
        for _, element in ET.iterparse(handle, events=("end",)):
            if element.tag == "timestep":
                t = round(float(element.get("time")))
                for v in element:
                    identity = v.get("id")
                    present.add(identity)
                    angle = np.deg2rad(float(v.get("angle")))
                    point = [
                        float(v.get("x")) - np.sin(angle) * lengths[identity] / 2,
                        float(v.get("y")) - np.cos(angle) * lengths[identity] / 2,
                    ]
                    native[t].append(
                        {"id": identity, "point": point, "speed": float(v.get("speed"))}
                    )
                element.clear()
    result = physical_errors(mapping, scoring_reference, native, 600, 1000)
    aggregate = json.loads((NATIVE / "validation.json").read_text())
    count_mean = float(np.mean([r["observed_vehicles"] for r in aggregate["series"]]))
    flow = aggregate["crossing_counts"]
    flow_nae = sum(abs(v["simulated_total"] - v["observed_total"]) for v in flow.values()) / sum(
        v["observed_total"] for v in flow.values()
    )
    travel = [
        v["distribution_wasserstein_s"] for v in aggregate["travel_time_distributions"].values()
    ]
    measured = {
        "count_normalized_mae": aggregate["instantaneous_vehicle_count"]["mae"] / count_mean,
        "directional_flow_normalized_absolute_error": flow_nae,
        "queue_count_mae_vehicles": aggregate["sb_queue_count"]["mae"],
        "uncapped_position_mae_m": result["uncapped_position_m"]["mae"],
        "within_4m_reference_coverage": result["within_4m_reference_coverage"],
        "speed_mae_mps": result["matched_speed_mps"]["mae"],
        "travel_time_distribution_wasserstein_s": max(travel)
        if all(t is not None for t in travel)
        else None,
        "signal_state_independently_verified": False,
    }
    limits = json.loads((ROOT / "docs/reality-v7-protocol.json").read_text())["physical_acceptance"]
    report = {
        "split": "Known 600-1000 s regression, not a fresh physical holdout",
        "physical_errors": result,
        "birth_identity_associations": len(mapping),
        "birth_association_diagnostics": diagnostic,
        "native_admitted_ids": len(present),
        "requested_cv_admissions": len(inputs["entries"]),
        "admission_presence_fraction": len(present) / len(inputs["entries"]),
        "conditioning": aggregate["conditioning"],
        "acceptance": acceptance(measured, limits),
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "metrics_source_sha256": hashlib.sha256(
            (ROOT / "backend/atlas/physical_metrics_v7.py").read_bytes()
        ).hexdigest(),
        "native_input_sha256": hashlib.sha256((NATIVE / "inputs.json").read_bytes()).hexdigest(),
        "limitations": [
            "Reference identities are associated only for post-run error measurement, never for demand or state forcing",
            "Birth matching is conditional and can be wrong; ambiguity and repeated-admission rejections remain counted",
            "Native front-to-body conversion uses class-based approximate native lengths",
            "Counts/flows retain the earlier front-coordinate convention; trajectory errors use body centres and report their scope separately",
            "Approximate source RSM signal stages are not independently verified lamp observations",
            "No physical acceptance or new controller promotion",
        ],
    }
    target.write_bytes(json.dumps(report, indent=2).encode())
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
