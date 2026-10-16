"""Run a bounded real Caltrans HLS session; publish telemetry only, delete every segment."""

import argparse
import hashlib
import json
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import cv2
import httpx
import numpy as np
import torch
from atlas import config
from atlas.detector import YOLOTracker
from atlas.hls_v6 import StreamHealth, playlist
from atlas.schemas import CameraConfig

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "https://wzmedia.dot.ca.gov/D12/NBPCHBLUEBIRD.stream/playlist.m3u8"
PAGE = "https://cwwp2.dot.ca.gov/vm/loc/d12/sr1580nbpchatbluebird.htm"
TERMS = "https://dot.ca.gov/conditions-of-use"
INTEGRATION = "https://cwwp2.dot.ca.gov/documentation/cctv/cctv.htm"


def fetch(client, url, limit):
    with client.stream("GET", url) as response:
        response.raise_for_status()
        content = bytearray()
        for block in response.iter_bytes(65536):
            content.extend(block)
            if len(content) > limit:
                raise ValueError("Source exceeds bounded download budget")
        return bytes(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=60)
    args = parser.parse_args()
    if not 30 <= args.seconds <= 300:
        raise ValueError("Session must be bounded to 30–300 seconds")
    cv2.setNumThreads(1)
    torch.set_num_threads(1)
    # Ultralytics resets torch threads at device selection; explicitly bound this worker.
    import ultralytics.utils.torch_utils as torch_utils

    torch_utils.NUM_THREADS = 1
    config.DEVICE = "cpu"
    config.MODEL = str(ROOT / "yolo11n.pt")
    if not Path(config.MODEL).exists():
        raise ValueError("Expected existing local pretrained COCO weights; no paid model service")
    detector = YOLOTracker(
        CameraConfig(
            detector_profile="coco", resolution=320, confidence=0.25, tracker="bytetrack.yaml"
        )
    )
    detector.infer(np.zeros((288, 512, 3), dtype=np.uint8))
    detector = YOLOTracker(detector.settings)
    health, rows, segments, failures, observations = StreamHealth(), [], [], [], []
    started = time.monotonic()
    identity_epoch, previous_pts = 0, None
    observed_start = datetime.now(UTC).isoformat()
    with (
        httpx.Client(timeout=15, follow_redirects=False) as client,
        tempfile.TemporaryDirectory(prefix="atlas-hls-", dir=ROOT / "data/reality-v6") as temporary,
    ):
        conditions = fetch(client, TERMS, 500000).decode()
        integration = fetch(client, INTEGRATION, 500000).decode()
        if "public domain" not in conditions or "There is no charge" not in integration:
            raise ValueError("Reviewed public-domain/free application-integration terms changed")
        while time.monotonic() - started < args.seconds:
            try:
                parsed = playlist(fetch(client, SOURCE, 65536).decode(), SOURCE)
                media = parsed.get("variant", SOURCE)
                if "variant" in parsed:
                    parsed = playlist(fetch(client, media, 65536).decode(), media)
                available = [
                    segment
                    for segment in parsed["segments"]
                    if health.last_sequence is None or segment["sequence"] > health.last_sequence
                ]
                # Start at the newest completed segment; do not accumulate an archive/backlog.
                if not available:
                    if health.snapshot(time.monotonic())["stale"]:
                        failures.append({"stage": "playlist", "error": "stale media sequence"})
                    time.sleep(1)
                    continue
                segment = available[-1]
                if health.last_sequence is not None and (
                    segment["discontinuity"] or segment["sequence"] != health.last_sequence + 1
                ):
                    detector = YOLOTracker(detector.settings)
                    identity_epoch += 1
                health.accept(segment["sequence"], time.monotonic())
                received = time.monotonic()
                content = fetch(client, segment["url"], 8000000)
                path = Path(temporary) / "current.ts"
                path.write_bytes(content)
                capture = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 1])
                fps, count, progressing = capture.get(cv2.CAP_PROP_FPS), 0, 0
                if not capture.isOpened() or not 1 <= fps <= 60:
                    capture.release()
                    path.unlink(missing_ok=True)
                    raise ValueError("Segment is not decodable continuous video")
                try:
                    while time.monotonic() - received < 60:
                        ok, frame = capture.read()
                        if not ok:
                            break
                        pts = capture.get(cv2.CAP_PROP_POS_MSEC)
                        progressing += int(previous_pts is not None and pts > previous_pts)
                        previous_pts = pts
                        tracks = detector.infer(frame) if count % 6 == 0 else None
                        if tracks:
                            observations.append(
                                {
                                    "sequence": segment["sequence"],
                                    "frame_index": count,
                                    "pts_ms": pts,
                                    "identity_epoch": identity_epoch,
                                    "tracks": tracks,
                                }
                            )
                        health.frame(frame.tobytes(), tracks, time.monotonic())
                        count += 1
                        if count % 30 == 0:
                            print(
                                json.dumps(
                                    {
                                        "mode": "LIVE PROCESSING / CALTRANS HLS",
                                        **health.snapshot(time.monotonic()),
                                    }
                                ),
                                flush=True,
                            )
                    else:
                        raise ValueError(
                            "Temporary buffer expired; drop backlog and reset tracking"
                        )
                finally:
                    capture.release()
                    path.unlink(missing_ok=True)
                if count < 2 or progressing < count - 2:
                    raise ValueError("No consecutive timestamp progression")
                segments.append(
                    {
                        "sequence": segment["sequence"],
                        "duration_s": segment["duration_s"],
                        "decoded_frames": count,
                        "processed_frames": (count + 5) // 6,
                        "decoded_fps": fps,
                        "increasing_pts_pairs": progressing,
                        "sha256": hashlib.sha256(content).hexdigest(),
                        "temporary_retention_s": time.monotonic() - received,
                    }
                )
                row = {
                    "elapsed_s": time.monotonic() - started,
                    "identity_epoch": identity_epoch,
                    **health.snapshot(time.monotonic()),
                }
                rows.append(row)
                print(json.dumps({"mode": "LIVE PROCESSING / CALTRANS HLS", **row}), flush=True)
            except (httpx.HTTPError, ValueError) as exc:
                failures.append(
                    {"stage": "stream", "error": type(exc).__name__ + ": " + str(exc)[:120]}
                )
                print(json.dumps(failures[-1]), flush=True)
                detector = YOLOTracker(detector.settings)
                identity_epoch += 1
                time.sleep(1)
    artifact = {
        "schema": "atlas-caltrans-live-ingestion-6.0",
        "observed_start_utc": observed_start,
        "finished_utc": datetime.now(UTC).isoformat(),
        "source_page": PAGE,
        "hls_url": SOURCE,
        "terms_url": TERMS,
        "integration_url": INTEGRATION,
        "permission_basis": "Official Caltrans-owned public-domain material, explicit free application integration; no contrary source notice found. TLS verification retained; only bounded transient decoding, no archived/redistributed imagery.",
        "terms_sha256": hashlib.sha256(conditions.encode()).hexdigest(),
        "integration_sha256": hashlib.sha256(integration.encode()).hexdigest(),
        "scope": "Actual bounded native live-stream experiment; archived telemetry is not current live traffic. No field-live worker runs on public Vercel.",
        "physical_calibration": None,
        "perception": "Pretrained COCO YOLO11n / ByteTrack, 320px, confidence .25, inference every sixth consecutive decoded frame, CPU one thread. Rolling visible-track metrics use inference frames only; no calibrated physical quantities. Blank model warmup excluded from source frame counts.",
        "physical_speed_queue_accuracy": "Unavailable; no physical speed, queue, flow accuracy or SUMO fidelity claim",
        "model_sha256": hashlib.sha256(Path(config.MODEL).read_bytes()).hexdigest(),
        "worker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "health_source_sha256": hashlib.sha256(
            (ROOT / "backend/atlas/hls_v6.py").read_bytes()
        ).hexdigest(),
        "segments": segments,
        "predicted_observations": observations,
        "telemetry": rows,
        "failures": failures,
        "final_health": health.snapshot(time.monotonic()),
        "identity_resets": identity_epoch,
        "buffer_policy": "At most one MPEG-TS segment, <=8 MB; <=60-second transient file, deleted in finally; directory removed on exit. No snapshots used, no retained frames.",
        "media_retained": False,
    }
    if not segments or health.frames < 30:
        (ROOT / "data/reality-v6/live-ingestion-failure.json").write_text(
            json.dumps(artifact, indent=2), encoding="utf-8"
        )
        raise ValueError("No successful continuous live session; do not publish as integrated")
    destination = ROOT / "artifacts/reality/v6/live-ingestion-results.json"
    destination.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(
        "Completed native live ingestion, deleted temporary media, frames",
        health.frames,
        flush=True,
    )


if __name__ == "__main__":
    main()
