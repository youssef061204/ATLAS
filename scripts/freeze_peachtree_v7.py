"""Freeze site calibration and clock registration before independent holdout scoring."""

import hashlib
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/reality-v7/peachtree"


def main():
    destination = ROOT / "docs/peachtree-v7-frozen.json"
    if destination.exists():
        raise FileExistsError("Never silently replace a frozen calibration")
    calibration = json.loads((DATA / "calibration-development.json").read_text())
    alignment = json.loads((DATA / "development-time-alignment.json").read_text())
    if {r["offset_frames"] for r in alignment["development_frames"]} != {4}:
        raise ValueError("Inconsistent source clock")
    sources = [
        "scripts/calibrate_peachtree_v7.py",
        "scripts/align_peachtree_video_v7.py",
        "docs/peachtree-v7-protocol.json",
    ]
    archive_path = ROOT / "artifacts/reality/v7/peachtree-calibration-source.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sources:
            archive.write(ROOT / path, path)
    public = ROOT / "artifacts/reality/v7"
    (public / "peachtree-calibration.json").write_bytes(
        (DATA / "calibration-development.json").read_bytes()
    )
    (public / "peachtree-time-alignment.json").write_bytes(
        (DATA / "development-time-alignment.json").read_bytes()
    )
    frozen = {
        "frozen_utc": datetime.now(UTC).isoformat(),
        "holdout_labels_scored": False,
        "calibration_window_s": [0, 300],
        "holdout_window_s": [600, 900],
        "raw_frame_offset": 4,
        "calibration_sha256": hashlib.sha256(
            (DATA / "calibration-development.json").read_bytes()
        ).hexdigest(),
        "alignment_sha256": hashlib.sha256(
            (DATA / "development-time-alignment.json").read_bytes()
        ).hexdigest(),
        "protocol_sha256": hashlib.sha256(
            (ROOT / "docs/peachtree-v7-protocol.json").read_bytes()
        ).hexdigest(),
        "calibration_source_archive_sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        "sources_sha256": {
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in sources
        },
        "scope": "Camera 1 development-only image/world/time registration, independent from Lankershim model selection. This does not freeze or accept the physical traffic model; physical parameters need a separate freeze before physical test evaluation.",
    }
    destination.write_bytes(json.dumps(frozen, indent=2).encode())
    print(
        json.dumps(
            {
                "frozen": True,
                "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                "spatial_check_rmse_m": calibration["spatial_check_rmse_m"],
                "temporal_check_rmse_m": calibration["temporal_check_rmse_m"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
