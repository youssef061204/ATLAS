"""Bounded daytime MJPEG trial on an official Taiwan Freeway Bureau feed.

Agency attribution: Taiwan Freeway Bureau, 2026, CCTV static information v2.0
and linked public road-camera video; Open Government Data License v1.0,
https://data.gov.tw/license . No recognition of plates or people, no media archive.
"""

import argparse
import hashlib
import json
import re
import tempfile
import time
import zipfile
from collections import defaultdict, deque
from datetime import UTC, datetime
from pathlib import Path
from threading import Timer
from types import SimpleNamespace

import cv2
import httpx
import numpy as np
import psutil
from atlas.detector import TRAFFIC_CLASSES
from atlas.mjpeg_v7 import jpeg_frames
from atlas.openvino_v7 import OpenVINOModel
from ultralytics.engine.results import Boxes
from ultralytics.trackers.byte_tracker import BYTETracker

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "https://cctvn.freeway.gov.tw/abs2mjpg/bmjpg?camera=21840"
CATALOG = "https://data.gov.tw/dataset/37665"
LICENSE = "https://data.gov.tw/license"
NOTICE = "https://www.freeway.gov.tw/Publish.aspx?cnid=1660"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def continuous_frames(client, deadline, events):
    epoch = 0
    while time.monotonic() < deadline:
        try:
            with client.stream("GET", SOURCE) as response:
                response.raise_for_status()
                if (
                    not response.headers.get("content-type", "")
                    .lower()
                    .startswith("multipart/x-mixed-replace")
                ):
                    raise ValueError("Source changed to a still image")
                for jpeg in jpeg_frames(response.iter_bytes(8192)):
                    if time.monotonic() >= deadline:
                        return
                    yield jpeg, epoch
            reason = "Provider closed the continuous video connection"
        except (httpx.RemoteProtocolError, httpx.ReadTimeout, httpx.ConnectError) as error:
            reason = type(error).__name__
        events.append(
            {"monotonic_s": time.monotonic(), "identity_epoch_ended": epoch, "reason": reason}
        )
        epoch += 1
        if epoch > 12:
            raise ValueError("Bounded reconnection budget exhausted")
        time.sleep(min(1, max(0, deadline - time.monotonic())))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--device", choices=["CPU", "GPU"], default="CPU")
    parser.add_argument("--run-label", default="taiwan-21840-daylight")
    args = parser.parse_args()
    if not 30 <= args.seconds <= 120:
        raise ValueError("Bound session to 30-120 seconds")
    cv2.setNumThreads(1)
    if not re.fullmatch(r"[a-z0-9-]{1,64}", args.run_label):
        raise ValueError("Invalid run label")
    output = ROOT / "artifacts/reality/v7" / f"live-{args.run_label}.json"
    if output.exists():
        raise FileExistsError("Preserve first completed Taiwan experiment")
    exported = json.loads((ROOT / "data/reality-v7/openvino/yolo11n-export.json").read_text())
    modeldir = Path(exported["model_directory"])
    for name, digest in exported["files_sha256"].items():
        if sha(modeldir / name) != digest:
            raise ValueError("Model graph changed")
    model = OpenVINOModel(modeldir, args.device, threads=1)
    classes = [i for i, name in model.names.items() if name in TRAFFIC_CLASSES]
    tracker = BYTETracker(
        SimpleNamespace(
            track_high_thresh=0.25,
            track_low_thresh=0.1,
            new_track_thresh=0.25,
            track_buffer=15,
            match_thresh=0.8,
            fuse_score=False,
        )
    )
    # Read one actual frame for shape-specific FP32 compilation, then reconnect
    # rather than process network data accumulated during compilation.
    cold = time.monotonic()
    with httpx.Client(timeout=10, follow_redirects=False, verify=True) as client:
        with client.stream("GET", SOURCE) as response:
            response.raise_for_status()
            if (
                not response.headers.get("content-type", "")
                .lower()
                .startswith("multipart/x-mixed-replace")
            ):
                raise ValueError("Not a continuous multipart video stream")
            first = next(jpeg_frames(response.iter_bytes(8192)))
    frame = cv2.imdecode(np.frombuffer(first, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Source video is undecodable")
    model.predict(frame, conf=0.1, classes=classes, imgsz=640, device="cpu", verbose=False)
    warmup = time.monotonic() - cold
    del first, frame
    process = psutil.Process()
    peak = process.memory_info().rss
    rows, latency, intervals, hashes = [], [], [], set()
    reconnects = []
    current_epoch = 0
    content_type = "multipart/x-mixed-replace;boundary=--myboundary"
    trail = defaultdict(list)
    rolling = deque()
    timers = []
    audits = []
    network_bytes = identical = longest_identical = 0
    previous_hash = None
    previous_time = None
    started = time.monotonic()
    utc = datetime.now(UTC).isoformat()
    directory = ROOT / "data/reality-v7/taiwan-audit"
    directory.mkdir(parents=True, exist_ok=True)
    try:
        with (
            httpx.Client(timeout=10, follow_redirects=False, verify=True) as client,
            tempfile.TemporaryDirectory(prefix="atlas-mjpeg-", dir=ROOT / "data/reality-v7"),
        ):
            print(
                json.dumps(
                    {
                        "continuous_video_connected": True,
                        "warmup_s": warmup,
                        "protocol": "MJPEG with bounded reconnect",
                    }
                ),
                flush=True,
            )
            for jpeg, epoch in continuous_frames(client, started + args.seconds, reconnects):
                if epoch != current_epoch:
                    tracker.reset()
                    current_epoch = epoch
                receipt = time.monotonic()
                elapsed = receipt - started
                if elapsed >= args.seconds:
                    break
                network_bytes += len(jpeg)
                digest = hashlib.sha256(jpeg).hexdigest()
                hashes.add(digest)
                identical = identical + 1 if digest == previous_hash else 0
                longest_identical = max(longest_identical, identical)
                previous_hash = digest
                frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
                if frame is None:
                    raise ValueError("Invalid consecutive MJPEG frame")
                if previous_time is not None:
                    intervals.append(receipt - previous_time)
                previous_time = receipt
                before = time.monotonic()
                result = model.predict(
                    frame, conf=0.1, classes=classes, imgsz=640, device="cpu", verbose=False
                )[0]
                data = (
                    result.boxes.data.cpu().numpy()
                    if result.boxes is not None
                    else np.empty((0, 6), dtype=np.float32)
                )
                tracks = tracker.update(Boxes(data, frame.shape[:2]), frame)
                latency.append((time.monotonic() - before) * 1000)
                objects = []
                for row in tracks:
                    identity = f"e{epoch}:{int(row[4])}"
                    box = row[:4].astype(float).tolist()
                    point = [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2]
                    trail[identity].append(
                        {
                            "frame": len(rows),
                            "elapsed_s": elapsed,
                            "center_px": point,
                            "bbox": box,
                        }
                    )
                    objects.append(
                        {
                            "id": identity,
                            "class": model.names[int(row[6])],
                            "score": float(row[5]),
                            "bbox": box,
                        }
                    )
                rolling.append((elapsed, len(objects)))
                while rolling and rolling[0][0] < elapsed - 10:
                    rolling.popleft()
                rows.append(
                    {
                        "frame": len(rows),
                        "elapsed_s": elapsed,
                        "tracks": objects,
                        "rolling_visible_mean": float(np.mean([r[1] for r in rolling])),
                    }
                )
                peak = max(peak, process.memory_info().rss)
                if (
                    args.audit
                    and len(audits) < 2
                    and objects
                    and elapsed >= (audits[-1]["elapsed_s"] + 1 if audits else 2)
                ):
                    image = frame.copy()
                    for obj in objects:
                        x1, y1, x2, y2 = map(round, obj["bbox"])
                        cv2.rectangle(image, (x1, y1), (x2, y2), (105, 230, 155), 1)
                        cv2.putText(
                            image,
                            f"{obj['class']} #{obj['id']}",
                            (x1, max(12, y1 - 3)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.35,
                            (105, 230, 155),
                            1,
                        )
                    path = directory / f"audit-{len(audits)}.jpg"
                    cv2.imwrite(str(path), image)
                    timer = Timer(30, lambda p=path: p.unlink(missing_ok=True))
                    timer.daemon = True
                    timer.start()
                    timers.append(timer)
                    audits.append(
                        {"frame": len(rows) - 1, "elapsed_s": elapsed, "objects": objects}
                    )
                    print(
                        json.dumps(
                            {"temporary_visual_audit": str(path), "delete_within_seconds": 30}
                        ),
                        flush=True,
                    )
                if len(rows) % 30 == 0:
                    print(
                        json.dumps(
                            {
                                "frames": len(rows),
                                "elapsed_s": elapsed,
                                "visible_tracks": len(objects),
                            }
                        ),
                        flush=True,
                    )
    finally:
        for timer in timers:
            timer.cancel()
        for path in directory.glob("audit-*.jpg"):
            path.unlink(missing_ok=True)
    moving = []
    for identity, points in trail.items():
        distance = float(
            np.linalg.norm(np.asarray(points[-1]["center_px"]) - points[0]["center_px"])
        )
        if len(points) >= 5 and distance >= 8:
            moving.append({"id": identity, "observations": len(points), "net_motion_px": distance})
    record = {
        "schema": "atlas-continuous-mjpeg-7.0",
        "source": SOURCE,
        "source_catalog": CATALOG,
        "license": LICENSE,
        "agency_notice": NOTICE,
        "permission_basis": "Official government dataset links VideoStreamURL under Open Government Data License v1.0; same agency open-material notice. No contrary source notice found. Attribution: Taiwan Freeway Bureau, 2026, CCTV static information v2.0 and linked public road camera video. Inference from reviewed agency notices, not a bespoke written permission.",
        "observed_start_utc": utc,
        "finished_utc": datetime.now(UTC).isoformat(),
        "content_type": content_type,
        "tls_verified": True,
        "runtime": model.runtime(),
        "warmup_reconnected_seconds": warmup,
        "decoded_frames": len(rows),
        "inference_frames": len(rows),
        "unique_jpeg_frames": len(hashes),
        "longest_identical_run": longest_identical,
        "observed_wall_seconds": time.monotonic() - started,
        "effective_decoded_fps": len(rows) / (time.monotonic() - started),
        "frames_with_tracks": sum(bool(r["tracks"]) for r in rows),
        "network_jpeg_bytes": network_bytes,
        "receive_interval_s": {f"p{q}": float(np.percentile(intervals, q)) for q in [50, 95, 99]},
        "max_receipt_gap_s": max(intervals, default=0),
        "inference_ms": {f"p{q}": float(np.percentile(latency, q)) for q in [50, 95, 99]},
        "peak_sampled_rss_mb": peak / 1024**2,
        "moving_track_diagnostics_not_unique_vehicles": moving,
        "observations": rows,
        "temporary_visual_audits": audits,
        "connection_events": [{**r, "elapsed_s": r["monotonic_s"] - started} for r in reconnects],
        "identity_resets": len(reconnects),
        "daylight_verified": False,
        "media_retained": False,
        "buffer_policy": "Only one bounded <=1MiB compressed JPEG and <=2MiB parser buffer in memory plus current decoded frame; no raw stream files. Two optional annotated audit images deleted within 30 seconds or sooner on exit. Temporary directory cleaned on exit.",
        "scope": "Actual continuous multipart MJPEG video, not snapshot polling. No source PTS/camera timestamp: receipt cadence is not independently verified camera FPS. No physical calibration, accuracy ground truth, unique vehicle counts, or accepted SUMO twin. Daylight requires a separate actual-pixel visual audit; not inferred merely from timezone.",
        "model_sha256": exported["source_sha256"],
        "worker_sha256": sha(Path(__file__)),
        "parser_sha256": sha(ROOT / "backend/atlas/mjpeg_v7.py"),
    }
    if len(rows) < 30 or len(hashes) < len(rows) * 0.8:
        raise ValueError("No useful continuous changing video verified")
    output.write_bytes(json.dumps(record, indent=2).encode())
    with zipfile.ZipFile(output.with_suffix(".worker.zip"), "x", zipfile.ZIP_DEFLATED) as z:
        for name in [
            "scripts/process_taiwan_live_v7.py",
            "backend/atlas/mjpeg_v7.py",
            "backend/atlas/openvino_v7.py",
        ]:
            z.write(ROOT / name, name)
    print(
        json.dumps(
            {
                "completed": True,
                "decoded_frames": len(rows),
                "frames_with_tracks": record["frames_with_tracks"],
                "moving_track_diagnostics": len(moving),
                "media_deleted": True,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
