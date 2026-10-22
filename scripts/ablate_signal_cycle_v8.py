"""Paired native SUMO development ablation of corrected RSM cycle selection."""

from __future__ import annotations

import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from atlas.city_network import binary
from atlas.physical_metrics_v7 import birth_correspondence, physical_errors
from atlas.rsm_v8 import read_rsm
from atlas.signal_ablation_v8 import write_approximate_signal_program
from calibrate_physics_v7 import native_states, reference_states
from cv_driven_ngsim_v6 import evaluate_aggregate, geometry_mapper
from diagnose_ngsim_v7 import development_observations
from reconstruct_ngsim_v6 import checked, road_model

ROOT = Path(__file__).resolve().parents[1]
BASE_CV = ROOT / "data/reality-v7/eager-insertion/duration-300"
BASE_REF = ROOT / "data/reality-v8/reference-demand-development"
RSM = (
    ROOT
    / "data/reality-v6/support/signal-timing/real-time-split-monitor-reports"
    / "Original Text files/RSM089-061605.txt"
)
FULL_INPUT = ROOT / "data/reality-v7/eager-insertion/duration-1122/inputs.json"
DEST = ROOT / "data/reality-v8"
PUBLIC = ROOT / "artifacts/reality/v8/signal-cycle-ablation-development.json"
START, END = 30, 300


def sha(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def run_variant(source: Path, target: Path, rows) -> dict:
    target.mkdir(parents=True, exist_ok=True)
    if (target / "simulation.fcd.xml.gz").exists():
        raise FileExistsError(f"Preserve completed native trial: {target}")
    shutil.copyfile(source / "routes.xml", target / "routes.xml")
    network = ET.parse(source / "network.net.xml")
    program = write_approximate_signal_program(network, rows, END + 100)
    network.write(target / "network.net.xml", encoding="utf-8")
    checked(
        [
            binary("sumo"),
            "-n",
            str(target / "network.net.xml"),
            "-r",
            str(target / "routes.xml"),
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
            str(target / "simulation.fcd.xml.gz"),
            "--device.fcd.period",
            "1",
            "--tripinfo-output",
            str(target / "tripinfo.xml"),
            "--no-step-log",
            "true",
            "--duration-log.disable",
            "true",
            "--time-to-teleport",
            "-1",
        ],
        target / "sumo.log",
    )
    return {
        "source_routes_sha256": sha(source / "routes.xml"),
        "copied_routes_sha256": sha(target / "routes.xml"),
        "source_network_sha256": sha(source / "network.net.xml"),
        "corrected_network_sha256": sha(target / "network.net.xml"),
        "native_fcd_sha256": sha(target / "simulation.fcd.xml.gz"),
        "program": program,
    }


def summary(errors: dict, aggregate: dict) -> dict:
    return {
        "reference_states": errors["reference_observations"],
        "native_presence": errors["native_presence_coverage"],
        "within_4m_reference_coverage": errors["within_4m_reference_coverage"],
        "uncapped_position_mae_m": errors["uncapped_position_m"]["mae"],
        "count_mae_vehicles": aggregate["instantaneous_vehicle_count"]["mae"],
        "queue_mae_vehicles": aggregate["sb_queue_count"]["mae"],
    }


def main() -> None:
    if PUBLIC.exists():
        raise FileExistsError("Preserve completed v8 signal ablation")
    rows = read_rsm(RSM)
    source = development_observations(301)
    source = source[source.t < END]
    road, _ = road_model(source)
    reference, scoring = reference_states(source, road)
    local = geometry_mapper(road)
    cv_entries = [
        item
        for item in json.loads(FULL_INPUT.read_text(encoding="utf-8"))["entries"]
        if item["t"] < END
    ]
    cv_mapping, _ = birth_correspondence(cv_entries, reference)
    oracle_routes = ET.parse(BASE_REF / "routes.xml").getroot()
    oracle_mapping = {
        vehicle.get("id").removeprefix("ref_"): {
            "native_id": vehicle.get("id"),
            "birth_s": float(vehicle.get("depart")),
        }
        for vehicle in oracle_routes.findall("vehicle")
    }
    results = {}
    for name, base, mapping in (
        ("cv", BASE_CV, cv_mapping),
        ("reference_initialized", BASE_REF, oracle_mapping),
    ):
        target = DEST / f"signal-cycle-end-{name}-development"
        trial = run_variant(base, target, rows)
        before_states = native_states(base)
        after_states = native_states(target)
        before_errors = physical_errors(mapping, scoring, before_states, START, END)
        after_errors = physical_errors(mapping, scoring, after_states, START, END)
        before_agg = evaluate_aggregate(base, source, local, window=(START, END))
        after_agg = evaluate_aggregate(target, source, local, window=(START, END))
        results[name] = {
            "run": trial,
            "before": summary(before_errors, before_agg),
            "corrected_record": summary(after_errors, after_agg),
        }
    report = {
        "schema": "atlas-v8-signal-cycle-end-ablation-1",
        "window_s": [START, END],
        "source_scope": "Already exposed Lankershim 0-300 s development; not independent validation",
        "experiment": "Only the assignment of each RSM split row to its completed cycle changes. Existing estimated stage order, clearance, road, route and vehicle behavior are held fixed.",
        "oracle_scope": "Reference initialized with first independently annotated state; cannot be called deployable prediction",
        "signal_state_independently_verified": False,
        "rsm_sha256": sha(RSM),
        "source_sha256": sha(Path(__file__)),
        "results": results,
    }
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                name: {"before": item["before"], "corrected_record": item["corrected_record"]}
                for name, item in results.items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
