"""Bounded Caltrans live VIDEO experiment, rolling diagnostics, temporary visual audit."""

import argparse
import hashlib
import json
import tempfile
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from threading import Timer

import cv2
import httpx
import numpy as np
import psutil
import torch
from atlas import config
from atlas.detector import YOLOTracker
from atlas.hls_v6 import StreamHealth, playlist
from atlas.schemas import CameraConfig

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "https://wzmedia.dot.ca.gov/D12/NB5DisneylandDr.stream/playlist.m3u8"
PAGE = "https://cwwp2.dot.ca.gov/vm/loc/d12/i5112disneylanddr.htm"
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
    parser.add_argument("--recover-low-score", action="store_true")
    parser.add_argument(
        "--runtime", choices=["torch", "openvino-cpu", "openvino-gpu"], default="torch"
    )
    parser.add_argument("--run-label", default="i5-disneyland-384-night")
    parser.add_argument("--model", choices=["yolo11n.pt", "yolo11s.pt"], default="yolo11n.pt")
    parser.add_argument("--resolution", type=int, choices=[320, 384, 640], default=384)
    parser.add_argument("--sample-every", type=int, choices=[1, 3, 6], default=6)
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Two temporary annotated audit images; deleted before exit",
    )
    args = parser.parse_args()
    import re

    if not re.fullmatch(r"[a-z0-9-]{1,64}", args.run_label):
        raise ValueError("Invalid run label")
    destination = ROOT / "artifacts/reality/v7" / f"live-{args.run_label}.json"
    if destination.exists():
        raise FileExistsError("Preserve completed live trial")
    if not 30 <= args.seconds <= 300:
        raise ValueError("Session must be bounded to 30–300 seconds")
    cv2.setNumThreads(1)
    torch.set_num_threads(1)
    # Ultralytics resets torch threads at device selection; explicitly bound this worker.
    import ultralytics.utils.torch_utils as torch_utils

    torch_utils.NUM_THREADS = 1
    config.DEVICE = "cpu"
    config.MODEL = str(ROOT / args.model)
    if not Path(config.MODEL).exists():
        raise ValueError("Expected existing local pretrained COCO weights; no paid model service")
    if args.runtime != "torch" and not args.recover_low_score:
        raise ValueError("OpenVINO live inference requires the explicit low-score-recovery tracker")

    def tracker_class(settings):
        if args.recover_low_score:
            from atlas.live_tracker_v7 import LiveTracker

            tracker = LiveTracker(settings)
        else:
            tracker = YOLOTracker(settings)
        if args.runtime != "torch":
            from atlas.openvino_v7 import OpenVINOModel

            record = json.loads(
                (ROOT / f"data/reality-v7/openvino/{Path(args.model).stem}-export.json").read_text()
            )
            directory = Path(record["model_directory"])
            for name, digest in record["files_sha256"].items():
                if hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
                    raise ValueError("Exported live model changed")
            if (
                hashlib.sha256(Path(config.MODEL).read_bytes()).hexdigest()
                != record["source_sha256"]
            ):
                raise ValueError("Export and source weights differ")
            tracker.model = OpenVINOModel(
                directory, "GPU" if args.runtime.endswith("gpu") else "CPU", threads=1
            )
        return tracker

    def reset_tracker(tracker):
        if args.recover_low_score:
            tracker.reset_tracking()
            return tracker
        return tracker_class(tracker.settings)

    detector = tracker_class(
        CameraConfig(
            detector_profile="coco",
            resolution=args.resolution,
            confidence=0.25,
            tracker="bytetrack.yaml",
        )
    )
    detector.infer(np.zeros((288, 512, 3), dtype=np.uint8))
    detector = reset_tracker(detector)
    health, rows, segments, failures, observations = StreamHealth(), [], [], [], []
    track_samples, inference_ms, receive_latency_ms = defaultdict(list), [], []
    process = psutil.Process()
    cpu_start = process.cpu_times()
    peak_rss = process.memory_info().rss
    audit_written = 0
    raw_boxes = rejected_overlay = 0
    started = time.monotonic()
    identity_epoch, previous_pts = 0, None
    observed_start = datetime.now(UTC).isoformat()
    with (
        httpx.Client(timeout=15, follow_redirects=False) as client,
        tempfile.TemporaryDirectory(prefix="atlas-hls-", dir=ROOT / "data/reality-v7") as temporary,
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
                    detector = reset_tracker(detector)
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
                        raw_before = getattr(detector, "raw_detections", 0)
                        overlay_before = getattr(detector, "overlay_rejections", 0)
                        inference_start = time.monotonic()
                        tracks = detector.infer(frame) if count % args.sample_every == 0 else None
                        raw_boxes += getattr(detector, "raw_detections", 0) - raw_before
                        rejected_overlay += (
                            getattr(detector, "overlay_rejections", 0) - overlay_before
                        )
                        if tracks is not None:
                            inference_ms.append((time.monotonic() - inference_start) * 1000)
                            receive_latency_ms.append((time.monotonic() - received) * 1000)
                            peak_rss = max(peak_rss, process.memory_info().rss)
                            for obj in tracks:
                                x1, y1, x2, y2 = obj["bbox"]
                                track_samples[identity_epoch, obj["id"]].append(
                                    (
                                        len(segments),
                                        count / fps,
                                        (x1 + x2) / 2,
                                        (y1 + y2) / 2,
                                        obj["class"],
                                    )
                                )
                            if (
                                args.audit
                                and tracks
                                and audit_written < 2
                                and (audit_written == 0 or count >= fps * 2)
                            ):
                                image = frame.copy()
                                for obj in tracks:
                                    x1, y1, x2, y2 = map(int, obj["bbox"])
                                    cv2.rectangle(image, (x1, y1), (x2, y2), (80, 255, 160), 1)
                                    cv2.putText(
                                        image,
                                        str(obj["id"]) + " " + obj["class"],
                                        (x1, max(10, y1)),
                                        cv2.FONT_HERSHEY_SIMPLEX,
                                        0.35,
                                        (80, 255, 160),
                                        1,
                                    )
                                image_path = Path(temporary) / f"audit-{audit_written}.jpg"
                                cv2.imwrite(str(image_path), image)
                                expiry = Timer(30, image_path.unlink, kwargs={"missing_ok": True})
                                expiry.daemon = True
                                expiry.start()
                                audit_written += 1
                                print(
                                    json.dumps(
                                        {
                                            "temporary_visual_audit": str(image_path),
                                            "expires_on_exit": True,
                                            "expires_within_seconds": 30,
                                        }
                                    ),
                                    flush=True,
                                )

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
                        "processed_frames": (count + args.sample_every - 1) // args.sample_every,
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
                detector = reset_tracker(detector)
                identity_epoch += 1
                time.sleep(1)

    def percentiles(values):
        return {
            "samples": len(values),
            **{f"p{p}": float(np.percentile(values, p)) if values else None for p in [50, 95, 99]},
        }

    cpu_end = process.cpu_times()
    moving = []
    for (epoch, identity), samples in track_samples.items():
        vehicle = [r for r in samples if r[4] in {"car", "bus", "truck", "motorcycle"}]
        if len(vehicle) >= 5:
            displacement = float(np.linalg.norm(np.array(vehicle[-1][2:4]) - vehicle[0][2:4]))
            if displacement >= 8:
                moving.append(
                    {
                        "identity_epoch": epoch,
                        "track_id": identity,
                        "inference_observations": len(vehicle),
                        "net_displacement_px": displacement,
                    }
                )
    artifact = {
        "processing_performance": {
            "wall_seconds": time.monotonic() - started,
            "cpu_seconds": cpu_end.user + cpu_end.system - cpu_start.user - cpu_start.system,
            "peak_sampled_rss_mb": peak_rss / 1024**2,
            "inference_ms": percentiles(inference_ms),
            "segment_receipt_to_result_ms": percentiles(receive_latency_ms),
            "latency_scope": "Time since completed-segment receipt, not camera-to-display latency; no source wall-clock timestamp",
        },
        "moving_vehicle_track_diagnostics": moving,
        "motion_rule": "At least five inference observations and eight pixels net movement; diagnostic only, not ground-truth precision or vehicle-count accuracy",
        "visual_audit": {"temporary_annotated_images": audit_written, "deleted_on_exit": True},
        "schema": "atlas-caltrans-live-ingestion-7.0",
        "observed_start_utc": observed_start,
        "finished_utc": datetime.now(UTC).isoformat(),
        "source_page": PAGE,
        "hls_url": SOURCE,
        "terms_url": TERMS,
        "integration_url": INTEGRATION,
        "permission_basis": "Official Caltrans-owned public-domain material, explicit free application integration; no contrary source notice found. TLS verification retained; only bounded transient decoding, two optional temporary annotated audit images deleted on exit, no archived/redistributed imagery.",
        "terms_sha256": hashlib.sha256(conditions.encode()).hexdigest(),
        "integration_sha256": hashlib.sha256(integration.encode()).hexdigest(),
        "scope": "Actual bounded native live-stream experiment; archived telemetry is not current live traffic. No field-live worker runs on public Vercel.",
        "physical_calibration": None,
        "inference_runtime": {
            "selected": args.runtime,
            "hardware": "Intel integrated GPU" if args.runtime.endswith("gpu") else "CPU",
            "precision": "FP32",
            "source_sha256": hashlib.sha256(
                (ROOT / "backend/atlas/openvino_v7.py").read_bytes()
            ).hexdigest()
            if args.runtime != "torch"
            else None,
        },
        "low_score_recovery": {
            "enabled": args.recover_low_score,
            "detector_floor": 0.1 if args.recover_low_score else 0.25,
            "new_track_threshold": 0.25,
            "fuse_score": not args.recover_low_score,
            "raw_detector_boxes": raw_boxes if args.recover_low_score else None,
            "provider_overlay_rejections": rejected_overlay if args.recover_low_score else None,
            "source_sha256": hashlib.sha256(
                (ROOT / "backend/atlas/live_tracker_v7.py").read_bytes()
            ).hexdigest()
            if args.recover_low_score
            else None,
            "scope": "Commissioning variant, unchanged frozen NGSIM and CityFlow experiments; provider-overlay filtering is not an accuracy measurement",
        },
        "perception": {
            "model": args.model,
            "resolution": args.resolution,
            "confidence": 0.25,
            "sample_every": args.sample_every,
            "tracker": "ByteTrack",
            "cpu_threads": 1,
            "scope": "Rolling visible tracks only, not physical measurements; blank warmup excluded from source counts",
        },
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
        "buffer_policy": "At most one MPEG-TS segment, <=8 MB; <=60-second transient file, deleted in finally; directory removed on exit. No snapshot inputs. Up to two temporary annotated audit images, each deleted within 30 seconds or sooner on exit; no retained frames.",
        "media_retained": False,
    }
    if not segments or health.frames < 30:
        (ROOT / "data/reality-v7/live-ingestion-failure.json").write_text(
            json.dumps(artifact, indent=2), encoding="utf-8"
        )
        raise ValueError("No successful continuous live session; do not publish as integrated")
    destination.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(
        "Completed native live ingestion, deleted temporary media, frames",
        health.frames,
        flush=True,
    )


if __name__ == "__main__":
    main()
