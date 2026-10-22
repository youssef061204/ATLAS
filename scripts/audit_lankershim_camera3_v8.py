"""Verify complete, genuinely changing FHWA camera-3 video without redistributing it."""

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / "data/reality-v6/lankershim-camera3-0830am-0845am.avi"
SOURCE = VIDEO.with_suffix(VIDEO.suffix + ".source.json")
OUT = ROOT / "artifacts/reality/v8/lankershim-camera3-video-integrity.json"


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main():
    if OUT.exists():
        raise FileExistsError("Preserve completed camera-3 video integrity audit")
    origin = json.loads(SOURCE.read_text(encoding="utf-8"))
    digest = sha(VIDEO)
    if digest != origin["sha256"] or not origin["zip_crc_verified"]:
        raise ValueError("Video differs from CRC-verified source acquisition")
    capture = cv2.VideoCapture(str(VIDEO))
    if not capture.isOpened():
        raise ValueError("Source video cannot be opened")
    reported = {
        "fps": capture.get(cv2.CAP_PROP_FPS),
        "frames": int(capture.get(cv2.CAP_PROP_FRAME_COUNT)),
        "width": int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
    }
    count = changing = exact_duplicates = 0
    differences = []
    previous = None
    sample_hashes = {}
    while True:
        decoded, frame = capture.read()
        if not decoded:
            break
        if frame.shape != (480, 640, 3):
            raise ValueError(f"Unexpected frame shape at {count}: {frame.shape}")
        if count in (0, 1, 2, 600, 3000, 6000, 11219):
            sample_hashes[str(count)] = hashlib.sha256(frame.tobytes()).hexdigest()
        if previous is not None:
            difference = float(
                np.mean(cv2.absdiff(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), previous))
            )
            differences.append(difference)
            if difference > 0.5:
                changing += 1
            if difference == 0:
                exact_duplicates += 1
        previous = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        count += 1
    capture.release()
    if count != 11220 or count != reported["frames"]:
        raise ValueError("Video is incomplete or its header reports a false frame count")
    report = {
        "schema": "atlas-v8-camera3-continuous-video-audit-1",
        "source_member": origin["member"],
        "source_url": origin["url"],
        "source_license": origin["license"]["termsLink"],
        "source_video_sha256": digest,
        "source_zip_crc_verified": origin["zip_crc_verified"],
        "raw_video_redistributed": False,
        "reported": reported,
        "fully_decoded_frames": count,
        "consecutive_frame_pairs": len(differences),
        "consecutive_pairs_with_mean_gray_change_gt_0_5": changing,
        "exact_duplicate_pairs": exact_duplicates,
        "mean_consecutive_gray_change": float(np.mean(differences)),
        "p5_consecutive_gray_change": float(np.percentile(differences, 5)),
        "decoded_frame_sha256_samples": sample_hashes,
        "continuous_video_confirmed": changing / len(differences) > 0.95,
        "main_street_lamp_state_verified": False,
        "signal_note": "Sampled original camera-3 frames show corridor vehicle motion and overlap with camera 4. No readable Main Street signal lamp state was established; this audit must not convert RSM green-split totals into observed lamp colors.",
        "source_sha256": sha(Path(__file__)),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "fully_decoded_frames": count,
                "changing_pairs": changing,
                "exact_duplicate_pairs": exact_duplicates,
                "continuous_video_confirmed": report["continuous_video_confirmed"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
