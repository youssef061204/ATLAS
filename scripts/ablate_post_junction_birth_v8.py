"""Isolate Main Street crossing error by starting an oracle run downstream.

Northbound reference vehicles enter the unchanged SUMO model only after their
first annotated state north of Main Street. Southbound admissions stay fixed.
Both native runs are compared on the same post-birth reference states. This is
an oracle structural diagnostic, not an operational CV predictor or acceptance.
"""

import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from atlas.city_network import binary
from atlas.physical_metrics_v7 import physical_errors
from attribute_demand_v8 import build_reference_routes, reference_first_states
from calibrate_physics_v7 import native_states, reference_states
from diagnose_ngsim_v7 import development_observations
from reconstruct_ngsim_v6 import checked, road_model

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/reality-v8/reference-demand-development"
TARGET = ROOT / "data/reality-v8/reference-post-main-development"
PUBLIC = ROOT / "artifacts/reality/v8/post-main-admission-ablation-development.json"
START, END = 30, 300


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def mapping_from(entries):
    return {
        item["reference_id"]: {"native_id": item["id"], "birth_s": item["t"]} for item in entries
    }


def summarized(errors):
    return {
        "reference_states": errors["reference_observations"],
        "native_presence": errors["native_presence_coverage"],
        "within_4m_reference_coverage": errors["within_4m_reference_coverage"],
        "uncapped_position_mae_m": errors["uncapped_position_m"]["mae"],
        "matched_speed_mae_mps": errors["matched_speed_mps"]["mae"],
    }


def main():
    if PUBLIC.exists() or (TARGET / "simulation.fcd.xml.gz").exists():
        raise FileExistsError("Preserve completed post-Main admission ablation")
    source = development_observations(301)
    source = source[source.t < END]
    road, _ = road_model(source)
    all_states, scoring = reference_states(source, road)
    baseline_network = ET.parse(BASE / "network.net.xml").getroot()
    original_entries, _ = reference_first_states(source, all_states, baseline_network)
    downstream_source = source[(source.direction != 2) | (source.local_y >= 1100)]
    later_entries, rejects = reference_first_states(downstream_source, all_states, baseline_network)
    before = mapping_from(original_entries)
    after = mapping_from(later_entries)
    if len(after) < 240 or len(after.keys() & before.keys()) < 240:
        raise ValueError("Unexpected loss of reference-initialized vehicles")
    shared = after.keys() & before.keys()
    directions = {
        (round(row.t * 10), str(row.vehicle_id)): int(row.direction)
        for row in source.itertuples()
        if round(row.t * 10) % 10 == 0
    }
    common = {"all": {}, "northbound": {}, "southbound": {}}
    for tick, states in scoring.items():
        second = tick // 10
        eligible = [
            state
            for state in states
            if state["id"] in shared and second >= after[state["id"]]["birth_s"]
        ]
        for name, desired in (("all", None), ("northbound", 2), ("southbound", 4)):
            selected = [
                state
                for state in eligible
                if desired is None or directions[(tick, state["id"])] == desired
            ]
            if selected:
                common[name][tick] = selected
    TARGET.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(BASE / "network.net.xml", TARGET / "network.net.xml")
    build_reference_routes(later_entries, BASE / "routes.xml", TARGET / "routes.xml")
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
    original_native = native_states(BASE)
    later_native = native_states(TARGET)
    comparisons = {
        group: {
            "original_oracle_birth": summarized(
                physical_errors(before, rows, original_native, START, END)
            ),
            "downstream_oracle_birth": summarized(
                physical_errors(after, rows, later_native, START, END)
            ),
        }
        for group, rows in common.items()
    }
    full_reference_denominator = {
        "original_oracle_birth": summarized(
            physical_errors(before, scoring, original_native, START, END)
        ),
        "downstream_oracle_birth": summarized(
            physical_errors(after, scoring, later_native, START, END)
        ),
    }
    report = {
        "schema": "atlas-v8-post-main-oracle-admission-ablation-1",
        "window_s": [START, END],
        "source_scope": "Already exposed 0-300 s development; future reference first states are oracle inputs, not CV estimates or independent holdout",
        "intervention": "Northbound first annotated admission at local_y >= 1100 ft, after the approximate Main Street J at 1045 ft; southbound initial states unchanged. Exact same native network, signal, driver model, seed and safety checks.",
        "evaluation": "Primary paired comparison uses identical reference identities and timestamps after the later birth. Full original denominator is also reported so changing the start time cannot silently improve coverage.",
        "original_reference_births": len(before),
        "downstream_reference_births": len(after),
        "shared_reference_births": len(shared),
        "new_projection_rejections": rejects,
        "signal_state_independently_verified": False,
        "physical_twin_accepted": False,
        "common_post_birth_cohorts": comparisons,
        "full_original_reference_cohort": full_reference_denominator,
        "source_sha256": sha(Path(__file__)),
        "baseline_network_sha256": sha(BASE / "network.net.xml"),
        "trial_network_sha256": sha(TARGET / "network.net.xml"),
        "baseline_native_fcd_sha256": sha(BASE / "simulation.fcd.xml.gz"),
        "trial_native_fcd_sha256": sha(TARGET / "simulation.fcd.xml.gz"),
        "trial_routes_sha256": sha(TARGET / "routes.xml"),
    }
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(comparisons, indent=2))


if __name__ == "__main__":
    main()
