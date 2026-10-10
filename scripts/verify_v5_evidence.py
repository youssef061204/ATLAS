"""Verify published ATLAS 5 evidence without privileged datasets or native SUMO."""

import gzip
import hashlib
import json
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "artifacts/cities/v5"
CITIES = {"toronto", "london", "seattle", "austin", "calgary"}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(name):
    return json.loads((EVIDENCE / name).read_bytes())


def verify_sources(values):
    for path, expected in values.items():
        assert sha((ROOT / path).read_bytes()) == expected, f"Changed measured source: {path}"


def main():
    calibration = load("calibration-readiness.json")
    verify_sources(
        {
            "docs/calibration-v5-protocol.json": calibration["protocol_sha256"],
            "backend/atlas/calibration_v5.py": calibration["estimator_sha256"],
            "scripts/evaluate_calibration_v5.py": calibration["evaluator_sha256"],
        }
    )
    assert calibration["independently_validated_twins"] == 0
    assert {c["city"] for c in calibration["cities"]} == CITIES
    for city in calibration["cities"]:
        assert city["evidence_level"] == 1 and city["twin_status"] == "exploratory"
        assert (
            sha((ROOT / f"artifacts/cities/v4/data-{city['city']}.json.gz").read_bytes())
            == city["source_sha256"]
        )
        dates = city["split_dates"]
        assert (
            max(dates["calibration"])
            < min(dates["validation"])
            <= max(dates["validation"])
            < min(dates["final"])
        )
        for metric in (
            "speed_error",
            "travel_time_error",
            "physical_queue_error",
            "occupancy_error",
        ):
            assert city["count_demand_regression"]["final"][metric] is None
    series = json.loads(gzip.decompress((EVIDENCE / "count-demand-series.json.gz").read_bytes()))
    assert all(r["simulated_count"] is None for rows in series["cities"].values() for r in rows)
    forecast = load("forecast-results.json")
    whitehall = load("whitehall-results.json")
    verify_sources(
        {
            "docs/whitehall-v5-protocol.json": whitehall["protocol_sha256"],
            "scripts/evaluate_whitehall_v5.py": whitehall["evaluator_sha256"],
            "backend/atlas/calibration_v5.py": whitehall["estimator_sha256"],
            "artifacts/cities/v5/data-whitehall.json.gz": whitehall["data_sha256"],
        }
    )
    assert whitehall["record_count"] == 240 and whitehall["evidence_level"] == 1
    assert not whitehall["independent_simulation_state_validation"]
    assert whitehall["final"]["geh_below_5_fraction"] == 0
    verify_sources(
        {
            "docs/city-forecast-v5-protocol.json": forecast["protocol_sha256"],
            "backend/atlas/city_forecast_v5.py": forecast["source_sha256"],
            "scripts/evaluate_city_forecast_v5.py": forecast["evaluator_sha256"],
        }
    )
    assert len(forecast["local"]) == len(forecast["zero_shot"]) == 5
    for row in forecast["zero_shot"]:
        assert row["target_label_rows_used"] == 0
        assert not row["target_normalization_statistics_used"]
        assert row["held_out_city"] not in row["source_cities"]
    frozen = load("control-frozen.json")
    verify_sources(frozen["source_sha256"])
    verify_sources({"scripts/benchmark_control_v5.py": frozen["evaluator_sha256"]})
    assert frozen["frozen_before_final"] and not frozen["production_promoted"]
    index = load("control-evidence-index.json")
    assert len(index["bundles"]) == 75
    cohorts = {
        stage: load(f"control-{stage}.json") for stage in ("development", "validation", "final")
    }
    summaries = {
        (stage, r["city"], r["case"], r["seed"], r["candidate"]): r
        for stage, doc in cohorts.items()
        for r in doc["runs"]
    }
    seen = set()
    counts = Counter()
    pairs = defaultdict(dict)
    for bundle in index["bundles"]:
        compressed = (EVIDENCE / bundle["file"]).read_bytes()
        assert sha(compressed) == bundle["gzip_sha256"]
        raw = gzip.decompress(compressed)
        assert sha(raw) == bundle["raw_sha256"] and len(raw) == bundle["raw_bytes"]
        lines = raw.splitlines()
        assert len(lines) == len(bundle["members"])
        for line, member in zip(lines, bundle["members"], strict=True):
            assert sha(line) == member["raw_sha256"]
            run = json.loads(line)
            key = (run["stage"], run["city"], run["case"], run["seed"], run["candidate"])
            assert key not in seen and key in summaries
            seen.add(key)
            assert run["metrics"] == summaries[key]["metrics"]
            assert run["metrics"]["modeled_safety_violations"] == 0
            assert run["calibration"]["status"] == "uncalibrated"
            assert len(run["trace"]) > 0 and run["duration"] == 300
            counts[run["stage"]] += 1
            if run["stage"] == "final":
                assert 55301 <= run["seed"] <= 55310
                pairs[(run["city"], run["case"], run["seed"])][run["candidate"]] = {
                    key: run[key]
                    for key in (
                        "metrics",
                        "network_sha256",
                        "routes_sha256",
                        "initial_states",
                        "duration",
                        "scenario",
                    )
                }
    assert seen == set(summaries)
    assert counts == {"development": 150, "validation": 300, "final": 2100}
    assert len(pairs) == 300
    for runs in pairs.values():
        assert len(runs) == 7
        reference = next(iter(runs.values()))
        for run in runs.values():
            for key in (
                "network_sha256",
                "routes_sha256",
                "initial_states",
                "duration",
                "scenario",
            ):
                assert run[key] == reference[key]
        for metric in ("mean_delay_s", "completed_trips", "mean_queue", "phase_switches"):
            assert (
                runs["cached_original"]["metrics"][metric]
                == runs["original_mpc"]["metrics"][metric]
            )
    assessment = load("control-assessment.json")
    assert assessment["final_episodes"] == 2100 and not assessment["production_promoted"]
    assert not assessment["promotion_checks"]["worst_episode"]
    assert (
        next(r for r in assessment["overall"] if r["baseline"] == "cached_original")[
            "mean_paired_delay_reduction_pct"
        ]
        < 0
    )
    cv = load("cv-runtime.json")
    verify_sources(cv["source_sha256"])
    verify_sources(
        {
            "docs/cv-v5-protocol.json": cv["protocol_sha256"],
            "scripts/benchmark_cv_v5.py": cv["evaluator_sha256"],
        }
    )
    assert Counter(r["tracker"] for r in cv["runs"]) == {"bytetrack.yaml": 3, "botsort.yaml": 3}
    assert all(r["frames"] == 1130 and r["complete_pipeline_wall_s"] > 0 for r in cv["runs"])
    worker = load("worker-verification.json")
    verify_sources(worker["execution_sources_sha256"])
    verify_sources({"scripts/verify_execution_v5.py": worker["verifier_sha256"]})
    assert worker["new_native_processing"] and not worker["public_execution_verified"]
    for city in CITIES:
        for case in ("low", "nominal", "high", "incident", "outage", "shift"):
            study = load(f"studio-{city}-{case}.json")
            assert study["seed_count"] == 10 and len(study["runs"]) == 7
            assert all(r["seed"] == 55301 and r["city"] == city for r in study["runs"])
            assert not study["production_promoted"]
    for name, archive_name in (
        ("ux-before.json", "ux-before-source.zip"),
        ("ux-performance.json", "ux-measured-source.zip"),
    ):
        ux = load(name)
        assert len(ux["scans"]) == 30
        with zipfile.ZipFile(EVIDENCE / archive_name) as archive:
            for path, digest in ux["measured_source_sha256"].items():
                assert sha(archive.read(path)) == digest, path
        assert all(
            not r["violations"]
            and not r["page_errors"]
            and not r["failed_responses"]
            and r["horizontal_overflow_px"] <= 2
            for r in ux["scans"]
        )
    fonts = json.loads((ROOT / "frontend/public/fonts/sources.json").read_bytes())
    for asset in fonts["assets"]:
        assert sha((ROOT / "frontend/public/fonts" / asset["file"]).read_bytes()) == asset["sha256"]
        assert asset["license"] == "SIL Open Font License 1.1"
    media_root = ROOT / "artifacts/portfolio/v5"
    media = json.loads((media_root / "provenance.json").read_bytes())
    assert len(media["captures"]) == 5 and not media["page_errors"]
    with zipfile.ZipFile(EVIDENCE / "ux-measured-source.zip") as archive:
        for path, digest in media["measured_source_sha256"].items():
            assert sha(archive.read(f"frontend/{path}")) == digest
    for capture in media["captures"]:
        assert sha((media_root / capture["file"]).read_bytes()) == capture["sha256"]
    video = media["walkthrough"]
    assert 30 <= video["duration_s"] <= 60
    assert sha((media_root / video["file"]).read_bytes()) == video["sha256"]
    print(
        "Verified 2,550 lossless SUMO episodes, frozen policy, 300 matched cache pairs, five-city calibration/forecast provenance, six CV repeats and private native worker"
    )


if __name__ == "__main__":
    main()
