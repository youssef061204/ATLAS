"""Portable publication audit; raw research media and model caches are unnecessary.

Checks source freezes, native/replay integrity, published metric arithmetic and
scope safeguards. It does not pretend to rerun CV or recover private ground truth.
"""

import argparse
import gzip
import hashlib
import json
import math
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/reality/v7"


def sha(value):
    return hashlib.sha256(value).hexdigest()


def read(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def close(actual, expected):
    assert math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9), (actual, expected)


def presentation():
    media = ROOT / "artifacts/portfolio/v7"
    manifest = json.loads((media / "manifest.json").read_text(encoding="utf-8"))
    record = manifest["recording"]
    assert not record["page_errors"] and not record["failed_site_responses"]
    close(record["decoded_frames"] / record["fps"], record["duration_seconds"])
    assert 30 <= record["duration_seconds"] <= 60
    for name, entry in manifest["files"].items():
        path = media / name
        assert path.stat().st_size == entry["bytes"] and sha(path.read_bytes()) == entry["sha256"]
    with zipfile.ZipFile(media / "presentation-source.zip") as archive:
        for name, expected in manifest["source_files"].items():
            assert sha(archive.read(name)) == expected
    for name, expected in manifest["evidence"].items():
        assert sha((ROOT / name).read_bytes()) == expected
    for report_name, archive_name in [
        ("render-performance-before.json", "render-baseline-source.zip"),
        ("render-performance-materials.json", "render-materials-source.zip"),
        ("render-performance.json", "render-final-source.zip"),
    ]:
        report = read(report_name)
        with zipfile.ZipFile(OUT / archive_name) as archive:
            assert (
                sha(archive.read("frontend/components/reality-scene-v7.tsx"))
                == report["sceneSourceSha256"]
            )
        assert all(
            not row["errors"] and row["actualVideoProgressS"] > 5 for row in report["results"]
        )


def identity(result):
    row = result["identity"]
    tp, fp, fn = (row[key] for key in ["IDTP", "IDFP", "IDFN"])
    denominator = 2 * tp + fp + fn
    close(row["IDF1"], 2 * tp / denominator if denominator else 0)


def points(result):
    identity(result)
    if result["reference_observations"]:
        close(
            result["reference_coverage"], result["matched_pairs"] / result["reference_observations"]
        )
    else:
        assert result["empty_reference_cohort"] is True
        assert result["reference_coverage"] is None
    rows = result["per_frame"]
    close(
        result["instantaneous_count"]["mae"],
        sum(abs(r["observed"] - r["predicted"]) for r in rows) / len(rows),
    )
    assert sum(r["observed"] for r in rows) == result["reference_observations"]
    assert (
        result["actual_detector_observations"] + result["predicted_inferred_observations"]
        == result["predicted_observations"]
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", action="store_true")
    args = parser.parse_args()
    # Original evaluator archives remain immutable even where a documented
    # correction supersedes the active evaluator. Never silently relabel sources.
    active = {
        "perception-v7-frozen.json",
        "openvino-v7-frozen.json",
        "cityflow-v7-frozen.json",
        "peachtree-evaluator-v7-correction.json",
        "lankershim-evaluator-v7-correction.json",
    }
    for path in sorted((ROOT / "docs").glob("*v7*.json")):
        freeze = json.loads(path.read_text(encoding="utf-8"))
        if "archive" not in freeze:
            continue
        archive = ROOT / freeze["archive"]
        assert sha(archive.read_bytes()) == freeze["archive_sha256"], path.name
        with zipfile.ZipFile(archive) as bundle:
            for source, digest in freeze["sources_sha256"].items():
                assert sha(bundle.read(source)) == digest, (path.name, source)
                if path.name in active:
                    assert sha((ROOT / source).read_bytes()) == digest, source
    site = json.loads((ROOT / "docs/peachtree-v7-frozen.json").read_text(encoding="utf-8"))
    assert (
        sha((OUT / "peachtree-calibration-source.zip").read_bytes())
        == site["calibration_source_archive_sha256"]
    )
    for source, digest in site["sources_sha256"].items():
        assert sha((ROOT / source).read_bytes()) == digest
    manifest = read("manifest.json")
    for name, entry in manifest["files"].items():
        path = (OUT / name).resolve()
        assert path.is_relative_to(OUT.resolve())
        raw = path.read_bytes()
        assert len(raw) == entry["bytes"] and sha(raw) == entry["sha256"], name
    assert manifest["frame_count"] == 11220 and manifest["fps"] == 10
    frames, inferred, times = 0, 0, set()
    for chunk in manifest["chunks"]:
        packet = json.loads(gzip.decompress((OUT / (chunk["file"] + ".gz")).read_bytes()))
        assert packet["start_frame"] == frames
        for frame in packet["frames"]:
            for box in frame:
                assert len(box) == 9 and box[3] >= box[1] and box[4] >= box[2]
                inferred += bool(box[7])
        frames += len(packet["frames"])
        times.update(int(t) for t in packet["simulation"])
    assert frames == 11220 and inferred == 11663 and times == set(range(1122))
    tracks = json.loads(gzip.decompress((OUT / "tracks.json.gz").read_bytes()))
    assert len(tracks) == 2524
    assert sum(t["inferred_observations"] for t in tracks.values()) == inferred
    for path in OUT.glob("evaluation-*-window.json"):
        points(json.loads(path.read_text(encoding="utf-8")))
    strict = read("evaluation-full-v7-lankershim-1020-1120-strict.json")
    assert strict["reference_observations"] == 0 and strict["empty_reference_cohort"]
    physical = read("physical-current-acceptance.json")
    errors = physical["physical_errors"]
    close(
        errors["native_presence_coverage"],
        errors["paired_native_observations"] / errors["reference_observations"],
    )
    close(
        errors["within_4m_reference_coverage"],
        errors["within_4m_reference_observations"] / errors["reference_observations"],
    )
    checks = physical["acceptance"]["checks"]
    assert physical["acceptance"]["accepted"] == all(r["passed"] for r in checks.values())
    assert (
        not physical["acceptance"]["accepted"]
        and not checks["signal_state_independently_verified"]["passed"]
    )
    assert errors["uncapped_position_m"]["max"] > 4
    with zipfile.ZipFile(OUT / "native-sumo-evidence.zip") as bundle:
        native = bundle.read("simulation.fcd.xml.gz")
        assert sha(native) == manifest["native_fcd_sha256"] == physical["native_fcd_sha256"]
        root = ET.fromstring(gzip.decompress(native))
        assert [float(v.get("time")) for v in root] == list(range(1122))
        metric = json.loads(bundle.read("validation.json"))
        assert metric["acceptance"] == physical["acceptance"]
        close(
            metric["instantaneous_vehicle_count"]["mae"],
            sum(abs(r["observed_vehicles"] - r["simulated_vehicles"]) for r in metric["series"])
            / len(metric["series"]),
        )
    live = read("live-i5-disneyland-11n-640-openvino-everythird-night.json")
    assert live["media_retained"] is False and live["identity_resets"] == 0
    assert live["final_health"]["decoded_frames"] == 1500
    assert live["processing_performance"]["inference_ms"]["samples"] == 500
    assert len(live["predicted_observations"]) == 499 and not live["failures"]
    segments = live["segments"]
    assert len(segments) == 6 and [s["sequence"] for s in segments] == list(
        range(segments[0]["sequence"], segments[0]["sequence"] + 6)
    )
    close(sum(s["duration_s"] for s in segments), 60)
    assert all(
        s["temporary_retention_s"] <= 60 and s["increasing_pts_pairs"] == s["decoded_frames"] - 1
        for s in segments
    )
    day = read("live-taiwan-21840-daylight.json")
    assert day["decoded_frames"] == day["inference_frames"] == day["unique_jpeg_frames"] == 258
    assert day["frames_with_tracks"] == 142 and day["identity_resets"] == 5
    assert day["tls_verified"] and not day["media_retained"]
    assert read("live-taiwan-visual-audit.json")["daylight_verified"] is True
    forecast = read("video-occupancy-forecast-pilot.json")
    for row in forecast["results"]:
        assert len(row["series"]) == row["test_origins"]
        assert all(
            r["origin_s"] >= 600 and r["origin_s"] + row["horizon_s"] + 30 <= 1000
            for r in row["series"]
        )
        for model, result in row["outcomes"].items():
            close(
                result["mae_vehicles"],
                sum(abs(r[model] - r["target_vehicles"]) for r in row["series"])
                / len(row["series"]),
            )
    assert forecast["unsupported_horizons_s"] == [900, 1800]
    if not args.checkpoint:
        presentation()
        research = read("research.json")
        assert research["checkpoint"] is False and research["live"]["daylight_verified"] is False
        for name, entry in research["source_artifacts"].items():
            assert sha((OUT / name).read_bytes()) == entry["sha256"]
        peach = read("peachtree-frozen-holdout-evaluation-corrected.json")
        assert (
            peach["performance"]["decoded_frames"]
            == peach["performance"]["processed_frames"]
            == 14961
        )
        assert set(peach["reports"]) == {"full_window", "calibration_disjoint", "fresh_tracks"}
        for report in peach["reports"].values():
            points(report)
        multi = read("cityflow-S03-frozen-results.json")
        assert multi["total_decoded_and_processed_frames"] == 13517
        assert len(multi["camera_runs"]) == 6
        assert (
            next(r for r in multi["camera_runs"] if r["camera"] == "c015")["metadata"]["fps"] == 8
        )
        assert len({r["result"]["predicted_boxes"] for r in multi["candidates"]}) == 1
        for row in multi["candidates"]:
            identity(row["result"])
    assert (
        not list(OUT.glob("*.npz")) and not list(OUT.glob("*.onnx")) and not list(OUT.glob("*.pt"))
    )
    print(
        f"Verified ATLAS 7 {'checkpoint' if args.checkpoint else 'release'}: exact source freezes, 11,220 replay frames, native SUMO, uncapped physical errors, live continuity and chronological forecast arithmetic"
    )


if __name__ == "__main__":
    main()
