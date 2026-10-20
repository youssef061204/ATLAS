"""Test native insertion scheduling without disabling vehicle safety checks.

SUMO's default edge-level insertion queue can block independent interior birth
positions behind one failed insertion. Eager insertion tests each pending birth
separately. Selection uses only 0-300 s; regression is never a fresh holdout.
"""

import argparse
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from atlas.city_network import binary
from calibrate_physics_v7 import OUT as PRIOR
from calibrate_physics_v7 import score, sha
from diagnose_ngsim_v7 import development_observations
from publish_replay_v7 import NATIVE, ROOT
from reconstruct_ngsim_v6 import checked, road_model

OUT = ROOT / "data/reality-v7/eager-insertion"
PUBLIC = ROOT / "artifacts/reality/v7"


def run(end, source):
    out = OUT / f"duration-{end}"
    out.mkdir(parents=True, exist_ok=True)
    if (out / "simulation.fcd.xml.gz").exists():
        raise FileExistsError("Preserve insertion experiment")
    shutil.copyfile(source / "network.net.xml", out / "network.net.xml")
    shutil.copyfile(source / "routes.xml", out / "routes.xml")
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
            "--eager-insert",
            "true",
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
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regression", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    selection_path = PUBLIC / "eager-insertion-development.json"
    entries = json.loads((NATIVE / "inputs.json").read_text())["entries"]
    development = development_observations(301)
    road, _ = road_model(development)
    prior_selection = json.loads((PUBLIC / "physical-calibration-development.json").read_text())
    if prior_selection["selected"] != {"speed_mps": 15.65, "tau_s": 0.7}:
        raise ValueError("This experiment retains the preceding development-selected model")
    if not args.regression:
        if selection_path.exists():
            raise FileExistsError("Preserve insertion model selection")
        protocol = {
            "source_sha256": sha(Path(__file__)),
            "metric_source_sha256": sha(ROOT / "scripts/calibrate_physics_v7.py"),
            "comparison": "Same CV birth poses, initial speeds, lanes, routes, tau .7, desired speed 15.65, seed and safety. Only --eager-insert changes pending-birth scheduling. No clipping of scoring errors or dropping delayed vehicles.",
            "selection": "Use eager insertion only if development uncapped position MAE + 30m * missing native fraction improves, without reducing within-4m coverage; report full failed candidates too.",
            "source_documentation": "https://sumo.dlr.de/docs/Simulation/VehicleInsertion.html",
            "calibration_window_s": [0, 300],
            "score_window_s": [30, 300],
        }
        with (OUT / "protocol.json").open("x", encoding="utf-8") as f:
            json.dump(protocol, f, indent=2)
        directory = run(300, PRIOR / "development-speed-15.65-tau-0.7")
        result = score(directory, development, road, [e for e in entries if e["t"] < 300], 30, 300)
        original = next(
            c
            for c in prior_selection["candidates"]
            if c["speed_mps"] == 15.65 and c["tau_s"] == 0.7
        )
        chosen = (
            result["selection_objective_m"] < original["selection_objective_m"]
            and result["physical_errors"]["within_4m_reference_coverage"]
            >= original["physical_errors"]["within_4m_reference_coverage"]
        )
        record = {
            "protocol": protocol,
            "original": original,
            "eager": result,
            "selected_eager_insert": bool(chosen),
            "source_sha256": sha(Path(__file__)),
            "regression_labels_read_for_selection": False,
        }
        selection_path.write_bytes(json.dumps(record, indent=2).encode())
        print(
            json.dumps(
                {
                    "selected_eager": chosen,
                    "original_objective": original["selection_objective_m"],
                    "eager_objective": result["selection_objective_m"],
                    "eager_position_mae": result["physical_errors"]["uncapped_position_m"]["mae"],
                    "eager_4m_coverage": result["physical_errors"]["within_4m_reference_coverage"],
                }
            ),
            flush=True,
        )
    else:
        selection = json.loads(selection_path.read_text())
        if (
            selection["source_sha256"] != sha(Path(__file__))
            or not selection["selected_eager_insert"]
        ):
            raise ValueError("No unchanged development-selected eager insertion model")
        target = PUBLIC / "eager-insertion-regression.json"
        if target.exists():
            raise FileExistsError("Preserve regression evidence")
        directory = run(1122, PRIOR / "regression-development_selected")
        result = score(
            directory,
            development_observations(1001),
            road,
            [e for e in entries if e["t"] < 1000],
            600,
            1000,
        )
        # Exact native admission delays are available for completed and unfinished trips.
        # Full sampled admission timing is also inspectable from FCD; never substitute
        # a requested departure timestamp for an actual simulated state.
        result.update(
            {
                "split": "Known 600-1000 s regression; not fresh holdout",
                "selection_sha256": sha(selection_path),
                "source_sha256": sha(Path(__file__)),
                "validated_physical_twin": False,
            }
        )
        target.write_bytes(json.dumps(result, indent=2).encode())
        shutil.copyfile(NATIVE / "inputs.json", directory / "inputs.json")
        assert ET.parse(directory / "routes.xml").find("vType").get("tau") == "0.7"
        print(
            json.dumps(
                {
                    "position_mae": result["physical_errors"]["uncapped_position_m"]["mae"],
                    "coverage_4m": result["physical_errors"]["within_4m_reference_coverage"],
                    "count_mae": result["aggregate"]["instantaneous_vehicle_count"]["mae"],
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
