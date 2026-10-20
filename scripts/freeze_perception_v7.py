"""Freeze measured development selection before any new held-out label scoring."""

import hashlib
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    destination = ROOT / "docs/perception-v7-frozen.json"
    if destination.exists():
        raise FileExistsError("Never silently replace a frozen experiment")
    sources = [
        "backend/atlas/" + name + ".py"
        for name in [
            "config",
            "db",
            "detector",
            "schemas",
            "multiscale_v7",
            "pipeline",
            "analytics",
            "forecast",
            "geometry",
            "safety",
            "track_continuity_v7",
        ]
    ]
    sources += ["scripts/process_video_v7.py"]
    digests = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in sources}
    archive_path = ROOT / "artifacts/reality/v7/perception-source.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sources:
            info = zipfile.ZipInfo(path, (2026, 10, 16, 7, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, (ROOT / path).read_bytes())
    frozen = {
        "frozen_utc": datetime.now(UTC).isoformat(),
        "selection_data": "Lankershim camera 4 first recording, consecutive frames 600..1799 (60..180 seconds), independent FHWA point annotations; no reserved test scores computed",
        "candidate": "Full 960-pixel aerial frame + two overlapping 640-pixel crops, class-agnostic NMS at .45, one ByteTrack instance",
        "camera_config": {
            "detector_profile": "aerial_multiscale",
            "tracker": "bytetrack.yaml",
            "resolution": 960,
            "confidence": 0.1,
            "sample_every": 1,
        },
        "model_sha256": "060866322c84caa59d7cbd7874efbe1af5e957a862169f2ac6778a8e7e3c4851",
        "primary_output": "Raw detector/tracker observations; no interpolation included in the raw result",
        "secondary_offline_output": {
            "handoff_max_gap_s": 1.0,
            "ambiguity_margin_m": 0.65,
            "interpolation_max_missing_s": 0.5,
            "rule": "Report inferred observations separately. No inference across an unbounded disappearance. The 1.5-second candidate regressed IDF1 and speed error and is rejected.",
        },
        "development_results": {
            "baseline_point_idf1": 0.6476761619190404,
            "selected_raw_point_idf1": 0.6744525547445256,
            "selected_with_explicit_offline_gaps_point_idf1": 0.7138810198300283,
            "baseline_reference_coverage": 0.5283018867924528,
            "selected_raw_reference_coverage": 0.5683962264150944,
            "selected_with_gaps_reference_coverage": 0.6155660377358491,
        },
        "point_metric": "Fixed v6 ROI, 1 Hz, 4 metre gate. Not bounding-box IDF1 or mAP. Do not exclude occluded reference misses from primary scores.",
        "temporal_test_s": [1020, 1120],
        "temporal_scope": "Same camera/date; never call this an independent-location test. Strict whole-reference-track cohort excludes identities seen before the reserved interval; also show fixed-window regression cohort separately.",
        "additional_location": "Peachtree camera 5 noon: source integrity verified, temporal alignment and reference calibration still under investigation. Freeze any location-specific calibration and scoring protocol before inspecting its holdout outcomes.",
        "calibration_sha256": hashlib.sha256(
            (ROOT / "data/reality-v6/camera4-calibration.json").read_bytes()
        ).hexdigest(),
        "sources_sha256": digests,
        "archive": "artifacts/reality/v7/perception-source.zip",
        "archive_sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        "physical_scope": "No accepted physical twin or controller promotion follows from perception gains. Physical model freeze and independent acceptance gates are separate.",
    }
    destination.write_bytes(json.dumps(frozen, indent=2).encode())
    print(
        json.dumps(
            {
                "frozen": True,
                "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                "sources": len(sources),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
