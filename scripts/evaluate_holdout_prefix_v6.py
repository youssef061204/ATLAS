"""Qualified second-recording temporal holdout; never call its truncated file complete."""

import hashlib
import json
import struct
from pathlib import Path

import cv2
import numpy as np
from atlas import config, db
from atlas.city_network import binary
from cv_driven_ngsim_v6 import evaluate_aggregate, geometry_mapper, video_entries
from reconstruct_ngsim_v6 import DATA, build, checked, load_observations, road_model

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def image(path, index):
    capture = cv2.VideoCapture(str(path))
    capture.set(cv2.CAP_PROP_POS_FRAMES, index)
    ok, frame = capture.read()
    capture.release()
    if not ok:
        raise ValueError("Missing static registration frame")
    return frame


def main():
    protocol_path = ROOT / "docs/ngsim-v6-holdout-prefix-protocol.json"
    protocol = json.loads(protocol_path.read_text())
    source = DATA / "lankershim-camera4-0845am-0900am.avi"
    source_record = json.loads(source.with_suffix(".avi.source.json").read_text())
    if sha(source) != source_record["sha256"]:
        raise ValueError("Secondary source checksum changed")
    with source.open("rb") as handle:
        header = handle.read(12)
    declared_bytes = struct.unpack("<I", header[4:8])[0] + 8
    config.DATA = DATA / "production-pipeline"
    db.init()
    prefix_source = DATA / "lankershim-camera4-holdout-prefix.avi"
    prefix_audit = json.loads(prefix_source.with_suffix(".avi.source.json").read_text())
    if sha(prefix_source) != prefix_audit["sha256"] or prefix_audit["parent_sha256"] != sha(source):
        raise ValueError("Derived prefix source chain changed")
    run = json.loads((config.DATA / "run-holdout-prefix.json").read_text())
    result_path = Path(run["result_file"])
    result = json.loads(result_path.read_text())
    assert result["performance"]["decoded_frames"] == result["metadata"]["frame_count"] == 6510
    assert declared_bytes == 419190690 > source.stat().st_size == 261284939
    for field, value in {
        "resolution": 960,
        "confidence": 0.15,
        "sample_every": 1,
        "detector_profile": "aerial",
        "tracker": "bytetrack.yaml",
    }.items():
        if result["config"][field] != value:
            raise ValueError("Qualified holdout cannot change the frozen perception settings")
    failure = {
        "source": source.name,
        "source_sha256": sha(source),
        "zip_crc_verified": True,
        "source_bytes": source.stat().st_size,
        "declared_riff_bytes": declared_bytes,
        "declared_frames": 10480,
        "decoded_frames": 6538,
        "complete_video": False,
        "scope": "Archive CRC establishes faithful download, not completeness of the originally published AVI. Incomplete source is rejected; only its explicit quality-guarded prefix is analyzed.",
    }
    (config.DATA / "failure-holdout.json").write_text(
        json.dumps(failure, indent=2), encoding="utf-8"
    )
    # Freeze extrinsic alignment using static image features, without heldout GT.
    development = image(DATA / "lankershim-camera4-0830am-0845am.avi", 600)
    secondary = image(source, 0)
    detector = cv2.SIFT_create(nfeatures=6000)
    ka, da = detector.detectAndCompute(secondary, None)
    kb, db_features = detector.detectAndCompute(development, None)
    pairs = cv2.BFMatcher().knnMatch(da, db_features, k=2)
    pairs = [a for a, b in pairs if a.distance < 0.75 * b.distance]
    a, b = (
        np.float32([ka[m.queryIdx].pt for m in pairs]),
        np.float32([kb[m.trainIdx].pt for m in pairs]),
    )
    registration, mask = cv2.findHomography(a, b, cv2.RANSAC, 2)
    if registration is None or int(mask.sum()) < 40:
        raise ValueError(
            "Heldout camera registration fails the frozen static-feature quality guard"
        )
    residual = cv2.perspectiveTransform(a.reshape(-1, 1, 2), registration).reshape(-1, 2) - b
    calibration = json.loads((DATA / "camera4-calibration.json").read_text())
    matrix = np.array(calibration["raw_to_world"]) @ registration
    primary = load_observations()
    road, geometry = road_model(primary)
    local = geometry_mapper(road)
    start, end = protocol["available_analysis_window_s"]
    assert end <= int(6538 / 10 - 2)
    result["frames"] = result["frames"][: end * 10]
    entries = video_entries(result, matrix, local)
    directory = DATA / "holdout-prefix-reconstruction"
    directory.mkdir(parents=True, exist_ok=True)
    inputs = build(
        directory,
        primary,
        road,
        1.0,
        15.65,
        66001,
        entries_override=entries,
        duration_s=end,
        clock_origin_s=8 * 3600 + 44 * 60 + 34,
    )
    registration_audit = {
        "method": "Static SIFT second raw frame0 to first raw frame600, no second-recording trajectory calibration",
        "inliers": int(mask.sum()),
        "matches": len(pairs),
        "inlier_rmse_px": float(
            np.sqrt(np.mean(np.sum(residual[mask.ravel().astype(bool)] ** 2, axis=1)))
        ),
        "raw_to_world": matrix.tolist(),
    }
    (directory / "inputs-before-reference.json").write_text(
        json.dumps(
            {
                "geometry": geometry,
                "registration": registration_audit,
                **inputs,
                "protocol_sha256": sha(protocol_path),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    checked(
        [
            binary("sumo"),
            "-n",
            str(directory / "network.net.xml"),
            "-r",
            str(directory / "routes.xml"),
            "--begin",
            "0",
            "--end",
            str(end),
            "--step-length",
            "0.1",
            "--seed",
            "66001",
            "--fcd-output",
            str(directory / "simulation.fcd.xml.gz"),
            "--device.fcd.period",
            "1",
            "--tripinfo-output",
            str(directory / "tripinfo.xml"),
            "--no-step-log",
            "true",
            "--duration-log.disable",
            "true",
            "--time-to-teleport",
            "-1",
        ],
        directory / "sumo.log",
    )
    # Only after inputs and native output are frozen: evaluate independent source states.
    reference = load_observations(epoch=1118936700000)
    artifact = evaluate_aggregate(
        directory, reference[reference.t < end], local, window=(start, end)
    )
    artifact.update(
        {
            "schema": "atlas-qualified-ngsim-holdout-prefix-6.0",
            "split": "Second-recording temporal holdout-prefix diagnostic; no tuning on these outcomes",
            "source_availability": {
                **failure,
                "original_planned_window_s": [180, 900],
                "scored_window_s": [start, end],
                "planned_seconds": 720,
                "scored_seconds": end - start,
                "planned_window_coverage": (end - start) / 720,
                "whole_planned_holdout_complete": False,
            },
            "driven_by": "Actual available-prefix raw-video ATLAS CV boundary crossings; original video incomplete and never claimed complete",
            "registration": registration_audit,
            "cv_derived_arrivals": len(entries),
            "protocol_sha256": sha(protocol_path),
            "evaluator_sha256": sha(Path(__file__)),
            "cv_boundary_source_sha256": sha(ROOT / "scripts/cv_driven_ngsim_v6.py"),
            "native_builder_sha256": sha(ROOT / "scripts/reconstruct_ngsim_v6.py"),
            "input_partial_result_sha256": sha(result_path),
            "derived_prefix": prefix_audit,
            "limitations": artifact["limitations"]
            + [
                "Original 720-second final holdout is incomplete; only 471 quality-guarded seconds can be scored",
                "This is aggregate temporal validation, not a vehicle-disjoint identity benchmark or full planned-window validation",
            ],
        }
    )
    destination = ROOT / "artifacts/reality/v6/holdout-prefix-results.json"
    destination.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(
        json.dumps({key: value for key, value in artifact.items() if key != "series"}, indent=2),
        flush=True,
    )


if __name__ == "__main__":
    main()
