"""Select only the development-frozen native reconstruction for public replay."""

import json
import shutil

import numpy as np
from atlas.physical_metrics_v7 import acceptance
from calibrate_physics_v7 import sha
from publish_replay_v7 import NATIVE, ROOT


def main():
    development = ROOT / "artifacts/reality/v7/physical-calibration-development.json"
    regression = ROOT / "artifacts/reality/v7/physical-calibrated-regression.json"
    selection = json.loads(development.read_text())
    report = json.loads(regression.read_text())
    if sha(ROOT / "scripts/calibrate_physics_v7.py") != selection["source_sha256"]:
        raise ValueError("Calibrated native runner changed")
    if sha(development) != report["development_selection_sha256"]:
        raise ValueError("Parameter choice changed")
    selected = next(r for r in report["candidates"] if r["name"] == "development_selected")
    if {k: selected[k] for k in ["speed_mps", "tau_s"]} != selection["selected"]:
        raise ValueError("Published model differs from development choice")
    eager = json.loads((ROOT / "artifacts/reality/v7/eager-insertion-regression.json").read_text())
    eager_choice = json.loads(
        (ROOT / "artifacts/reality/v7/eager-insertion-development.json").read_text()
    )
    if (
        not eager_choice["selected_eager_insert"]
        or sha(ROOT / "scripts/evaluate_insertion_v7.py") != eager["source_sha256"]
        or sha(ROOT / "artifacts/reality/v7/eager-insertion-development.json")
        != eager["selection_sha256"]
    ):
        raise ValueError("Eager insertion was not frozen on development")
    selected = eager
    directory = ROOT / "data/reality-v7/eager-insertion/duration-1122"
    if sha(directory / "simulation.fcd.xml.gz") != selected["native_fcd_sha256"]:
        raise ValueError("Native output changed")
    metric = selected["aggregate"]
    errors = selected["physical_errors"]
    flow = metric["crossing_counts"]
    travel = [r["distribution_wasserstein_s"] for r in metric["travel_time_distributions"].values()]
    measured = {
        "count_normalized_mae": metric["instantaneous_vehicle_count"]["mae"]
        / np.mean([r["observed_vehicles"] for r in metric["series"]]),
        "directional_flow_normalized_absolute_error": sum(
            abs(r["observed_total"] - r["simulated_total"]) for r in flow.values()
        )
        / sum(r["observed_total"] for r in flow.values()),
        "queue_count_mae_vehicles": metric["sb_queue_count"]["mae"],
        "uncapped_position_mae_m": errors["uncapped_position_m"]["mae"],
        "within_4m_reference_coverage": errors["within_4m_reference_coverage"],
        "speed_mae_mps": errors["matched_speed_mps"]["mae"],
        "travel_time_distribution_wasserstein_s": max(travel)
        if all(t is not None for t in travel)
        else None,
        "signal_state_independently_verified": False,
    }
    limits = json.loads((ROOT / "docs/reality-v7-protocol.json").read_text())["physical_acceptance"]
    metric.update(
        {
            "split": "Known 600-1000 s regression; never a fresh holdout",
            "driven_by": "Actual CV birth-initialized, free-running native SUMO with development-only car-following calibration",
            "conditioning": "One observed interior CV pose/speed per admitted identity, no later state forcing. Same births/geometry/signals/seed/safety as the original ATLAS 7 model; tau and eager insertion selected on 0-300 s only. Eager insertion tests each pending birth separately with all safety checks intact. Changed conditioning from ATLAS 6 boundary-only admission.",
            "simulation_duration_s": 1122,
            "arrivals": 1272,
            "physical_errors": errors,
            "acceptance": acceptance(measured, limits),
            "calibration_parameters": selection["selected"],
            "development_selection_sha256": sha(development),
            "regression_sha256": sha(regression),
            "native_builder_sha256": eager["source_sha256"],
            "eager_insert": True,
            "eager_selection_sha256": eager["selection_sha256"],
            "admission_builder_sha256": sha(ROOT / "scripts/reconstruct_complete_v7.py"),
        }
    )
    for name in ["inputs.json"]:
        shutil.copyfile(NATIVE / name, directory / name)
    (directory / "validation.json").write_bytes(json.dumps(metric, indent=2).encode())
    baseline = ROOT / "artifacts/reality/v7/native-sumo-baseline-evidence.zip"
    if not baseline.exists():
        shutil.copyfile(ROOT / "artifacts/reality/v7/native-sumo-evidence.zip", baseline)
    (ROOT / "artifacts/reality/v7/physical-current-acceptance.json").write_bytes(
        json.dumps(
            {
                "measured": measured,
                "acceptance": metric["acceptance"],
                "physical_errors": errors,
                "calibration_parameters": selection["selected"],
                "native_fcd_sha256": selected["native_fcd_sha256"],
                "source_sha256": sha(ROOT / "scripts/prepare_calibrated_replay_v7.py"),
            },
            indent=2,
        ).encode()
    )
    print(
        json.dumps(
            {
                "selected": selection["selected"],
                "accepted": metric["acceptance"]["accepted"],
                "position_mae": measured["uncapped_position_mae_m"],
                "reference_coverage_4m": measured["within_4m_reference_coverage"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
