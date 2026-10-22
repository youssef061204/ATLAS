"""Check ATLAS 8 diagnostic artifacts without needing raw proprietary-sized inputs."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts/reality/v8"
WEB = ROOT / "frontend/public/ground-truth"


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def read(name):
    return json.loads((ARTIFACTS / name).read_text(encoding="utf-8"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    lifecycle = read("lifecycle-known-regression.json")["stage_accounting"]
    stages = lifecycle["stage_counts"]
    require(sum(stages.values()) == lifecycle["reference_states"] == 2670, "State partition")
    require(
        (stages["native_beyond_4m"] + stages["native_within_4m"]) / 2670
        == lifecycle["native_presence_coverage"],
        "Presence arithmetic",
    )
    require(
        stages["native_within_4m"] / 2670 == lifecycle["within_4m_reference_coverage"],
        "Four-metre arithmetic",
    )
    demand = read("demand-attribution-development.json")
    cv = demand["cv"]["physical_errors"]
    oracle = demand["reference_initialized"]["physical_errors"]
    require(
        cv["reference_observations"] == oracle["reference_observations"] == 1441, "Demand cohort"
    )
    require(oracle["native_presence_coverage"] > cv["native_presence_coverage"], "Demand effect")
    require(
        oracle["within_4m_reference_coverage"] < 0.2,
        "Oracle result no longer matches failed physical gate",
    )
    post = read("post-main-admission-ablation-development.json")
    cohorts = post["common_post_birth_cohorts"]
    for group in ("all", "northbound", "southbound"):
        before = cohorts[group]["original_oracle_birth"]
        after = cohorts[group]["downstream_oracle_birth"]
        require(before["reference_states"] == after["reference_states"], f"{group} denominator")
    require(
        cohorts["all"]["original_oracle_birth"]["reference_states"] == 1441,
        "Post-Main cohort size",
    )
    require(
        cohorts["southbound"]["original_oracle_birth"]
        == cohorts["southbound"]["downstream_oracle_birth"],
        "Unchanged southbound control",
    )
    require(post["baseline_network_sha256"] == post["trial_network_sha256"], "Network changed")
    require(not post["physical_twin_accepted"], "Oracle bypass misreported as accepted")
    extension = read("south-approach-length-ablation-development.json")
    require(extension["maximum_initial_pose_shift_m"] <= 0.25, "Initial world pose changed")
    require(extension["same_controlled_connections"], "Junction connections changed")
    require(
        extension["before"]["reference_states"]
        == extension["extended_approach"]["reference_states"]
        == 1441,
        "Length ablation cohort",
    )
    require(
        extension["extended_approach"]["uncapped_position_mae_m"]
        > extension["before"]["uncapped_position_mae_m"],
        "Length-only regression lost",
    )
    turn = read("turn-location-development-audit.json")
    require(turn["routes_in_rejected_single_junction_oracle_trial"] == 63, "Rejected route cohort")
    require(turn["within_50m_official_signal_counts"]["89"] == 10, "Main route cohort")
    main_turn = read("main-turn-route-ablation-development.json")
    require(main_turn["changed_main_street_routes"] == 10, "Incorrect Main route count")
    require(main_turn["excluded_other_intersection_turns"] == 53, "Other turns omitted")
    require(not main_turn["physical_twin_accepted"], "Route oracle misreported as accepted")
    signal = read("signal-rsm89-audit.json")
    timing = signal["cycle_timestamp_evidence"]
    require(
        timing["gaps_equal_current_row_cycle"] == timing["consecutive_timestamp_gaps"] == 875,
        "RSM cycle timing",
    )
    require(not signal["physical_signal_verified"], "Unverified lamps reported as observed")
    read("signal-cycle-ablation-development.json")
    read("physical-residual-development.json")
    crossing = read("main-through-crossing-development.json")
    require(
        crossing["native_first_outgoing_edge_sample_minus_observed_s"]["northbound"]["paired"] > 50,
        "Northbound crossing pairs",
    )
    cityflow = read("cityflow-annotation-audit.json")
    require(
        cityflow["scenes"]["S03"]["totals"]["annotated_vehicles_with_verified_cross_camera_links"]
        == 4,
        "Cross-camera audit",
    )
    camera = read("lankershim-camera3-video-integrity.json")
    require(camera["fully_decoded_frames"] == 11220, "Camera-3 full decode")
    require(camera["continuous_video_confirmed"], "Camera-3 is not confirmed continuous")
    require(not camera["main_street_lamp_state_verified"], "Unverified camera lamps")
    afternoon = read("peachtree-afternoon-source-integrity.json")
    require(afternoon["video_decoded_frames"] == 14981, "Afternoon full decode")
    require(afternoon["continuous_video_confirmed"], "Afternoon is not continuous video")
    require(not afternoon["afternoon_reference_rows_read"], "Sealed afternoon outcomes opened")
    require(not afternoon["accuracy_metrics_computed"], "Unfrozen afternoon score")
    noon = read("peachtree-noon-camera5-registration-readiness.json")
    require(
        noon["audit_script_sha256"] == sha(ROOT / "scripts/audit_peachtree_noon_camera5_v8.py"),
        "Noon readiness source changed",
    )
    require(noon["worldfile_ft_per_pixel"] == [0.25, -0.25], "Noon ortho scale")
    require(not noon["camera5_metric_registration_verified"], "Unverified calibration")
    require(not noon["physical_candidate_frozen"], "Unfrozen candidate misreported")
    require(not noon["afternoon_labels_opened"], "Sealed labels opened")
    speed_development = read("edge-end-speed-cap-ablation-development.json")
    speed_south = read("south-edge-speed-cap-ablation-development.json")
    speed_known = read("edge-end-speed-cap-known-regression.json")
    for label, report, expected in (
        ("all-edge development", speed_development, 1441),
        ("south-edge development", speed_south, 1441),
        ("known regression", speed_known, 2670),
    ):
        require(report["before"]["reference_states"] == expected, f"{label} denominator")
        require(
            report["no_edge_end_speed_cap"]["reference_states"] == expected,
            f"{label} trial denominator",
        )
        require(
            sum(report["changed_birth_count_by_edge"].values()) == report["changed_birth_count"],
            f"{label} changed birth accounting",
        )
        require(
            report["baseline_network_sha256"] == report["trial_network_sha256"],
            f"{label} network changed",
        )
        require(not report["physical_twin_accepted"], f"{label} misreported as accepted")
        require("no fresh holdout" in report["scope"], f"{label} split provenance")
        for side in ("baseline_native_integrity", "trial_native_integrity"):
            integrity = report[side]
            require(
                integrity["requested_births_before_run_end"] == report["cv_birth_count"],
                f"{label} birth request count",
            )
            require(
                not any(
                    integrity[field]
                    for field in (
                        "sumo_log_warning_mentions",
                        "sumo_log_error_mentions",
                        "sumo_log_collision_mentions",
                        "sumo_log_teleport_mentions",
                    )
                ),
                f"{label} native warning/error",
            )
        require(
            report["birth_speed_policy_sha256"] == sha(ROOT / "backend/atlas/birth_speed_v8.py"),
            f"{label} source drift",
        )
    require(speed_south["intervened_edges"] == ["S_in"], "Northbound edge isolation")
    require(speed_known["cv_birth_count"] == 1272, "Full-video birth count")
    require(
        speed_development["source_sha256"]
        == speed_south["source_sha256"]
        == speed_known["source_sha256"],
        "Speed-trial source mismatch",
    )
    summary_path = WEB / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    require(summary["status"] == "physical_twin_not_accepted", "Web gate")
    require(summary["known_stage_counts"] == stages, "Web lifecycle arithmetic")
    require(summary["oracle_before_after_main"] == cohorts, "Web oracle values")
    for name, digest in summary["source_artifact_sha256"].items():
        require(sha(ARTIFACTS / name) == digest, f"Stale web source: {name}")
    require(
        sha(WEB / "geometry-video-overlay.png") == sha(ARTIFACTS / "geometry-video-overlay.png"),
        "Published image differs",
    )
    require(
        sha(WEB / "geometry-video-overlay.png") == summary["source_image_sha256"],
        "Image manifest differs",
    )
    checks = len(list(ARTIFACTS.glob("*.json")))
    print(
        json.dumps(
            {
                "diagnostic_json_artifacts": checks,
                "reference_states": [1441, 2670],
                "camera3_frames": 11220,
                "physical_twin_accepted": False,
                "web_artifacts_match": True,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
