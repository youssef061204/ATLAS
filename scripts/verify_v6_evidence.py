"""Check complete-video provenance, real replay coverage and failure-preserving metrics."""

import gzip
import hashlib
import io
import json
import math
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/reality/v6"
BASELINE = OUT / "source-baseline.zip"
BASELINE_SHA256 = "1edbaf868a9cc093316118d546f29f4e75aac91a9f55f1a5892bdc6f27deb90a"


def sha(path):
    # Measured source bytes belong to the frozen v6 experiment, even after v7 edits.
    # Artifacts and media are always checked from the actual published files.
    if path != BASELINE:
        relative = path.relative_to(ROOT).as_posix()
        with zipfile.ZipFile(BASELINE) as archive:
            if relative in archive.namelist():
                return hashlib.sha256(archive.read(relative)).hexdigest()
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def check_series(result):
    rows = result["series"]
    for field, observed, simulated in [
        ("instantaneous_vehicle_count", "observed_vehicles", "simulated_vehicles"),
        ("sb_queue_count", "observed_sb_queue", "simulated_sb_queue"),
    ]:
        residual = [row[simulated] - row[observed] for row in rows]
        metric = result[field]
        assert len(rows) == metric["pairs"]
        assert math.isclose(metric["mae"], sum(abs(x) for x in residual) / len(rows))
        assert math.isclose(metric["bias"], sum(residual) / len(rows))
    assert result["validated_physical_twin"] is False


def main():
    assert sha(BASELINE) == BASELINE_SHA256, "Historical source archive changed"
    manifest = json.loads((OUT / "manifest.json").read_text())
    assert manifest["live"] is False
    assert manifest["frame_count"] == manifest["performance"]["decoded_frames"] == 11220
    assert manifest["performance"]["processed_frames"] == 11220
    assert manifest["protocol_sha256"] == sha(ROOT / "docs/ngsim-v6-protocol.json")
    assert manifest["exporter_sha256"] == sha(ROOT / "scripts/publish_replay_v6.py")
    assert manifest["decoder_guard_runtime_sha256"] == sha(ROOT / "backend/atlas/pipeline.py")
    for name, record in manifest["files"].items():
        path = OUT / name
        assert path.parent == OUT and path.stat().st_size == record["bytes"], name
        assert sha(path) == record["sha256"], name
    capture = cv2.VideoCapture(str(OUT / manifest["video"]))
    assert int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) == 11220
    frames = 0
    while capture.read()[0]:
        frames += 1
    capture.release()
    assert frames == 11220, "Every actual presentation frame must decode"
    with zipfile.ZipFile(OUT / "native-sumo-run.zip") as archive:
        raw = archive.read("simulation.fcd.xml.gz")
        assert hashlib.sha256(raw).hexdigest() == manifest["native_fcd_sha256"]
        assert "Error:" not in archive.read("sumo.log").decode()
        native = {}
        for _, element in ET.iterparse(io.BytesIO(gzip.decompress(raw)), events=("end",)):
            if element.tag == "timestep":
                native[round(float(element.get("time")))] = {
                    vehicle.get("id"): (float(vehicle.get("x")), float(vehicle.get("y")))
                    for vehicle in element
                }
                element.clear()
    offset = 0
    boxes = 0
    for record in manifest["chunks"]:
        chunk = json.loads(gzip.decompress((OUT / (record["file"] + ".gz")).read_bytes()))
        assert chunk["start_frame"] == offset
        assert len(chunk["frames"]) == record["frames"]
        offset += record["frames"]
        boxes += sum(len(objects) for objects in chunk["frames"])
        for t, vehicles in chunk["simulation"].items():
            assert len(vehicles) == len(native[int(t)])
            for identity, x, y, speed, _ in vehicles:
                assert identity.startswith("cv_") and speed >= 0
                actual = native[int(t)][identity]
                assert abs(x - actual[0]) < 0.0011 and abs(y - actual[1]) < 0.0011
    assert offset == 11220 and boxes > 10000
    cv = json.loads((OUT / "cv-validation.json").read_text())
    assert cv["input_result_sha256"] == manifest["input_result_sha256"]
    assert cv["evaluator_sha256"] == sha(ROOT / "scripts/evaluate_ngsim_cv_v6.py")
    identity = cv["identity"]
    assert math.isclose(
        identity["IDF1"],
        2 * identity["IDTP"] / (2 * identity["IDTP"] + identity["IDFP"] + identity["IDFN"]),
    )
    native_result = json.loads((OUT / "cv-driven-validation.json").read_text())
    check_series(native_result)
    assert native_result["input_result_sha256"] == manifest["input_result_sha256"]
    assert native_result["evaluator_sha256"] == sha(ROOT / "scripts/cv_driven_ngsim_v6.py")
    holdout = json.loads((OUT / "holdout-prefix-results.json").read_text())
    check_series(holdout)
    source = holdout["source_availability"]
    assert source["whole_planned_holdout_complete"] is False
    assert source["scored_seconds"] == 471 and source["planned_seconds"] == 720
    assert math.isclose(source["planned_window_coverage"], 471 / 720)
    assert source["decoded_frames"] == 6538 < source["declared_frames"] == 10480
    assert holdout["derived_prefix"]["decoded_frames"] == 6510
    assert (
        holdout["derived_prefix"]["source_pixel_sha256"]
        == holdout["derived_prefix"]["decoded_pixel_sha256"]
    )
    assert holdout["protocol_sha256"] == sha(ROOT / "docs/ngsim-v6-holdout-prefix-protocol.json")
    assert holdout["evaluator_sha256"] == sha(ROOT / "scripts/evaluate_holdout_prefix_v6.py")
    city = json.loads((OUT / "cityflow-results.json").read_text())
    assert city["total_decoded_and_processed_frames"] == 8109
    assert len(city["camera_runs"]) == 4
    assert sum(run["performance"]["processed_frames"] for run in city["camera_runs"]) == 8109
    before, after = city["before_association"], city["after_association_same_detections"]
    assert before["predicted_boxes"] == after["predicted_boxes"]
    assert after["identity"]["IDF1"] < before["identity"]["IDF1"]
    assert math.isclose(
        city["idf1_change_same_detections"], after["identity"]["IDF1"] - before["identity"]["IDF1"]
    )
    assert city["protocol_sha256"] == sha(ROOT / "docs/cityflow-v6-protocol.json")
    assert city["evaluator_sha256"] == sha(ROOT / "scripts/evaluate_cityflow_v6.py")
    assert city["association_source_sha256"] == sha(ROOT / "backend/atlas/multicamera_v6.py")
    # CityFlow was measured before the decoder-only guard. Preserve exact historical source.
    with zipfile.ZipFile(ROOT / "artifacts/cities/v5/cv-runtime-source.zip") as archive:
        historical = hashlib.sha256(archive.read("backend/atlas/pipeline.py")).hexdigest()
    assert manifest["measured_runtime_sha256"] == historical
    assert all(run["inputs"]["pipeline_sha256"] == historical for run in city["camera_runs"])
    live = json.loads((OUT / "live-ingestion-results.json").read_text())
    assert live["worker_sha256"] == sha(ROOT / "scripts/process_caltrans_live_v6.py")
    assert live["health_source_sha256"] == sha(ROOT / "backend/atlas/hls_v6.py")
    assert live["media_retained"] is False and live["physical_calibration"] is None
    assert (
        sum(row["decoded_frames"] for row in live["segments"])
        == live["final_health"]["decoded_frames"]
        == 1740
    )
    assert sum(row["processed_frames"] for row in live["segments"]) == 290
    assert [row["sequence"] for row in live["segments"]] == list(range(6756, 6763))
    assert all(
        row["temporary_retention_s"] < 60
        and row["increasing_pts_pairs"] >= row["decoded_frames"] - 2
        for row in live["segments"]
    )
    assert live["identity_resets"] == 0 and live["predicted_observations"] == []
    media_root = ROOT / "artifacts/portfolio/v6"
    media = json.loads((media_root / "provenance.json").read_text())
    assert media["page_errors"] == []
    for path, digest in media["measured_source_sha256"].items():
        assert sha(ROOT / "frontend" / path) == digest, path
    for capture in media["captures"]:
        assert sha(media_root / capture["file"]) == capture["sha256"]
    assert sha(media_root / media["video"]["file"]) == media["video"]["sha256"]
    assert media["video"]["seconds"] == 41
    assert media["reality_manifest_sha256"] == sha(OUT / "manifest.json")
    assert media["encoder_sha256"] == sha(ROOT / "scripts/encode_media_v6.py")
    print(
        "Verified 11,220 real video frames, native SUMO replay, independent metric arithmetic, qualified 471/720s holdout and regressed 8,109-frame multicamera experiment"
    )


if __name__ == "__main__":
    main()
