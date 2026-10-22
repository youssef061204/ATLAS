"""Publish a small, checked ATLAS 8 diagnosis for the web demo."""

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts/reality/v8"
WEB = ROOT / "frontend/public/ground-truth"
IMAGE = ARTIFACTS / "geometry-video-overlay.png"


def read(name):
    return json.loads((ARTIFACTS / name).read_text(encoding="utf-8"))


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main():
    lifecycle = read("lifecycle-known-regression.json")
    demand = read("demand-attribution-development.json")
    post = read("post-main-admission-ablation-development.json")
    length = read("south-approach-length-ablation-development.json")
    turn = read("turn-location-development-audit.json")
    signal = read("signal-rsm89-audit.json")
    camera3 = read("lankershim-camera3-video-integrity.json")
    stages = lifecycle["stage_accounting"]["stage_counts"]
    if sum(stages.values()) != 2670 or lifecycle["stage_accounting"]["reference_states"] != 2670:
        raise ValueError("Known-regression reference denominator changed")
    paired = post["common_post_birth_cohorts"]
    if paired["all"]["original_oracle_birth"]["reference_states"] != 1441:
        raise ValueError("Development reference denominator changed")
    if paired["all"]["downstream_oracle_birth"]["reference_states"] != 1441:
        raise ValueError("Downstream trial changed the scored states")
    if (
        paired["southbound"]["original_oracle_birth"]
        != paired["southbound"]["downstream_oracle_birth"]
    ):
        raise ValueError("Unchanged southbound control differs")
    if post["baseline_network_sha256"] != post["trial_network_sha256"]:
        raise ValueError("The controlled run changed road/signal network")
    if turn["within_50m_official_signal_counts"]["89"] != 10:
        raise ValueError("Main Street route cohort changed")
    if signal["physical_signal_verified"] or post["physical_twin_accepted"]:
        raise ValueError("The physical acceptance gate was not met")
    if length["maximum_initial_pose_shift_m"] > 0.25:
        raise ValueError("Approach-length trial changed initial world positions")
    if not camera3["continuous_video_confirmed"] or camera3["main_street_lamp_state_verified"]:
        raise ValueError("Camera-3 evidence scope changed")
    before = demand["reference_initialized"]["physical_errors"]
    if (
        before["native_presence_coverage"]
        != paired["all"]["original_oracle_birth"]["native_presence"]
    ):
        raise ValueError("Independent diagnostic reports disagree")
    manifest = {
        "schema": "atlas-v8-public-ground-truth-diagnosis-1",
        "status": "physical_twin_not_accepted",
        "development_window_s": [30, 300],
        "known_regression_window_s": [600, 1000],
        "new_independent_holdout": False,
        "camera3_continuous_frames": camera3["fully_decoded_frames"],
        "camera3_lamp_verified": False,
        "known_reference_states": 2670,
        "known_stage_counts": stages,
        "development_reference_states": 1441,
        "main_street_oracle_turns": 10,
        "other_intersection_turns_rejected": 53,
        "rsm_cycle_pairs_matching_current_report_length": signal["cycle_timestamp_evidence"][
            "gaps_equal_current_row_cycle"
        ],
        "oracle_before_after_main": paired,
        "approach_length_only": {
            "before_m": length["edge_lengths_m"]["S_in"]["before_m"],
            "after_m": length["edge_lengths_m"]["S_in"]["after_m"],
            "position_mae_before_m": length["before"]["uncapped_position_mae_m"],
            "position_mae_after_m": length["extended_approach"]["uncapped_position_mae_m"],
            "maximum_initial_pose_shift_m": length["maximum_initial_pose_shift_m"],
        },
        "message": "Starting northbound oracle vehicles after Main Street localizes a major approach/junction error; it is not deployable prediction, accepted physical fidelity or an observed controller benefit.",
        "source_artifact_sha256": {
            name: sha(ARTIFACTS / name)
            for name in (
                "lifecycle-known-regression.json",
                "demand-attribution-development.json",
                "post-main-admission-ablation-development.json",
                "south-approach-length-ablation-development.json",
                "turn-location-development-audit.json",
                "signal-rsm89-audit.json",
                "lankershim-camera3-video-integrity.json",
            )
        },
        "source_image_sha256": sha(IMAGE),
        "image_license_note": "Actual FHWA video CC BY-SA 4.0 and FHWA/NGSIM derived trajectory/survey overlay CC BY-SA 3.0; see technical diagnosis and source artifacts.",
    }
    WEB.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(IMAGE, WEB / IMAGE.name)
    (WEB / "summary.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "image_sha256": manifest["source_image_sha256"],
                "known_states": 2670,
                "development_states": 1441,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
