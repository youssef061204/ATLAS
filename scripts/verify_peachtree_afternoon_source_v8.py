"""Verify sealed FHWA Peachtree afternoon source metadata, never labels."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIDEO_MEMBER = "NGSIM Peachtree Videos/peachtree-camera5-0400pm-0415pm.avi"
VIDEO_URL = "https://data.transportation.gov/download/mupt-aksf/application%2Fx-zip-compressed"
REFERENCE_NAME = "NGSIM_Peachtree_Vehicle_Trajectories.csv"
REFERENCE_SHA256 = "1ec10349176788ca199132677154b9b7d207b7ec9605bfa16b600660085a76d9"
VIDEO_CRC32 = "9f2f36f4"
VIDEO_BYTES = 468_006_912
DECLARED_FRAMES = 14_981


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def verify(require_video: bool = False) -> dict:
    """Read only frozen manifests, and optionally hash the raw video bytes."""
    archive = _read_json(ROOT / "artifacts/reality/v7/source-header-audit-mupt-aksf.json")
    support = _read_json(ROOT / "artifacts/reality/v7/peachtree-support-source.json")
    members = [item for item in archive["videos"] if item["member"] == VIDEO_MEMBER]
    if len(members) != 1:
        raise ValueError("Expected exactly one official afternoon camera-5 member")
    member = members[0]
    if (
        archive["url"] != VIDEO_URL
        or "by-sa/4.0" not in archive["license"]["termsLink"]
        or member["bytes"] != VIDEO_BYTES
        or member["crc32"] != VIDEO_CRC32
        or member["declared_frames"] != DECLARED_FRAMES
        or not member["header_consistent"]
    ):
        raise ValueError("Official video archive declaration differs from the sealed protocol")
    references = [item for item in support["records"] if item["file"] == REFERENCE_NAME]
    if (
        len(references) != 1
        or references[0]["sha256"] != REFERENCE_SHA256
        or support["url"]
        != "https://data.transportation.gov/api/views/8ect-6jqj/files/7244a8b5-077f-4851-bc06-3cfc7a75f0b0?download=true"
        or "by-sa 3.0" not in support["license"].lower()
    ):
        raise ValueError("Official reference archive declaration differs from the sealed protocol")

    result = {
        "status": "source_metadata_verified",
        "video_member": VIDEO_MEMBER,
        "video_crc32": VIDEO_CRC32,
        "video_bytes": VIDEO_BYTES,
        "video_declared_frames": DECLARED_FRAMES,
        "reference_file": REFERENCE_NAME,
        "reference_source_sha256": REFERENCE_SHA256,
        "afternoon_reference_rows_read": False,
        "accuracy_metrics_computed": False,
    }
    path = ROOT / "data/reality-v7/official-videos/peachtree-camera5-0400pm-0415pm.avi"
    manifest_path = path.with_suffix(".avi.source.json")
    if require_video or manifest_path.exists():
        if not path.exists() or not manifest_path.exists():
            raise ValueError("Raw video and its source manifest must both exist")
        manifest = _read_json(manifest_path)
        with path.open("rb") as handle:
            actual_sha = hashlib.file_digest(handle, "sha256").hexdigest()
        if (
            manifest["member"] != VIDEO_MEMBER
            or manifest["url"] != VIDEO_URL
            or manifest["bytes"] != VIDEO_BYTES == path.stat().st_size
            or manifest["crc32"] != VIDEO_CRC32
            or manifest["sha256"] != actual_sha
            or manifest["decoded_frames"] != DECLARED_FRAMES
            or manifest["declared_frames"] != DECLARED_FRAMES
            or manifest["consecutive_identical_pixel_pairs"] >= DECLARED_FRAMES * 0.01
            or not manifest["zip_crc_verified_during_full_extraction"]
            or manifest["status"] != "complete_source_decode_verified"
        ):
            raise ValueError("Local raw video failed CRC, SHA or complete-decode verification")
        result.update(
            status="complete_video_source_verified",
            video_sha256=actual_sha,
            video_decoded_frames=manifest["decoded_frames"],
            video_fps=manifest["fps"],
            exact_duplicate_consecutive_pairs=manifest["consecutive_identical_pixel_pairs"],
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-video", action="store_true")
    args = parser.parse_args()
    print(json.dumps(verify(require_video=args.require_video), indent=2))


if __name__ == "__main__":
    main()
