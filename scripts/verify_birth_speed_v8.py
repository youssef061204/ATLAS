"""Verify the opt-in CV speed experiments changed only departure speed requests."""

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "backend/atlas/birth_speed_v8.py"
EXPERIMENT = ROOT / "scripts/ablate_edge_end_speed_cap_v8.py"
INPUTS = ROOT / "data/reality-v7/eager-insertion/duration-1122/inputs.json"
RUNS = (
    (
        "development_all_edges",
        ROOT / "artifacts/reality/v8/edge-end-speed-cap-ablation-development.json",
        ROOT / "data/reality-v7/eager-insertion/duration-300",
        ROOT / "data/reality-v8/no-edge-end-speed-cap-cv-development",
        1441,
    ),
    (
        "development_south_edge",
        ROOT / "artifacts/reality/v8/south-edge-speed-cap-ablation-development.json",
        ROOT / "data/reality-v7/eager-insertion/duration-300",
        ROOT / "data/reality-v8/no-south-edge-speed-cap-cv-development",
        1441,
    ),
    (
        "known_regression_full_video",
        ROOT / "artifacts/reality/v8/edge-end-speed-cap-known-regression.json",
        ROOT / "data/reality-v7/eager-insertion/duration-1122",
        ROOT / "data/reality-v8/no-edge-end-speed-cap-cv-full-1122",
        2670,
    ),
)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def route_diff(before, after, input_edges):
    old_root, new_root = ET.parse(before).getroot(), ET.parse(after).getroot()
    old_types = {row.get("id"): dict(row.attrib) for row in old_root.findall("vType")}
    new_types = {row.get("id"): dict(row.attrib) for row in new_root.findall("vType")}
    if old_types != new_types:
        raise ValueError("Vehicle type definitions changed")
    old = {row.get("id"): row for row in old_root.findall("vehicle")}
    new = {row.get("id"): row for row in new_root.findall("vehicle")}
    if old.keys() != new.keys():
        raise ValueError("Vehicle identities changed")
    changes = []
    for identity in old:
        original, trial = old[identity], new[identity]
        old_attributes, new_attributes = dict(original.attrib), dict(trial.attrib)
        old_speed = float(old_attributes.pop("departSpeed"))
        new_speed = float(new_attributes.pop("departSpeed"))
        if old_attributes != new_attributes or ET.tostring(original.find("route")) != ET.tostring(
            trial.find("route")
        ):
            raise ValueError(f"Non-speed route field changed for {identity}")
        if abs(old_speed - new_speed) > 0.005:
            changes.append(input_edges[identity])
    return changes


def main():
    input_edges = {
        row["id"]: row["edge"] for row in json.loads(INPUTS.read_text(encoding="utf-8"))["entries"]
    }
    output = {}
    for name, artifact, baseline, trial, denominator in RUNS:
        report = json.loads(artifact.read_text(encoding="utf-8"))
        for label, path in (
            ("source_sha256", EXPERIMENT),
            ("birth_speed_policy_sha256", POLICY),
            ("cv_inputs_sha256", INPUTS),
            ("baseline_network_sha256", baseline / "network.net.xml"),
            ("trial_network_sha256", trial / "network.net.xml"),
            ("baseline_routes_sha256", baseline / "routes.xml"),
            ("trial_routes_sha256", trial / "routes.xml"),
            ("baseline_native_fcd_sha256", baseline / "simulation.fcd.xml.gz"),
            ("trial_native_fcd_sha256", trial / "simulation.fcd.xml.gz"),
        ):
            if report[label] != sha(path):
                raise ValueError(f"{name}: {label} mismatch")
        if report["baseline_network_sha256"] != report["trial_network_sha256"]:
            raise ValueError(f"{name}: native network changed")
        if (
            report["before"]["reference_states"] != denominator
            or report["no_edge_end_speed_cap"]["reference_states"] != denominator
        ):
            raise ValueError(f"{name}: scoring denominator changed")
        changes = route_diff(baseline / "routes.xml", trial / "routes.xml", input_edges)
        by_edge = {edge: changes.count(edge) for edge in sorted(set(changes))}
        if (
            len(changes) != report["changed_birth_count"]
            or by_edge != report["changed_birth_count_by_edge"]
        ):
            raise ValueError(f"{name}: route speed changes differ from artifact")
        for side in ("baseline_native_integrity", "trial_native_integrity"):
            for field in (
                "sumo_log_error_mentions",
                "sumo_log_collision_mentions",
                "sumo_log_teleport_mentions",
            ):
                if report[side][field]:
                    raise ValueError(f"{name}: SUMO reported {field}")
        output[name] = {
            "reference_states": denominator,
            "speed_only_route_changes": len(changes),
            "full_window_native_fcd_sha256": {
                "baseline": report["baseline_native_fcd_sha256"],
                "v8_opt_in": report["trial_native_fcd_sha256"],
            },
            "native_integrity": {
                "baseline": report["baseline_native_integrity"],
                "v8_opt_in": report["trial_native_integrity"],
            },
        }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
