"""Publish compact, checksum-linked experiment results without research datasets."""

import argparse
import json

from publish_replay_v7 import OUT, ROOT, sha


def read(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", action="store_true")
    args = parser.parse_args()
    peach_name = "peachtree-frozen-holdout-evaluation-corrected.json"
    multi_name = "cityflow-S03-frozen-results.json"
    if not args.checkpoint and any(not (OUT / name).exists() for name in [peach_name, multi_name]):
        raise ValueError("Complete independent-site and multi-camera tests before publication")
    names = [
        "physical-current-acceptance.json",
        "physical-calibrated-regression.json",
        "video-occupancy-forecast-pilot.json",
        "cityflow-S01-reid-results.json",
        "live-i5-disneyland-11n-640-openvino-everythird-night.json",
        "live-visual-audit.json",
        "evaluation-full-v7-lankershim-1020-1120-window.json",
    ]
    names += ["eager-insertion-development.json", "eager-insertion-regression.json"]
    names += [n for n in [peach_name, multi_name] if (OUT / n).exists()]
    physical = read(names[0])
    live = read(names[4])
    multi = read(multi_name) if (OUT / multi_name).exists() else None
    peach = read(peach_name) if (OUT / peach_name).exists() else None
    dev = read("cityflow-S01-reid-results.json")
    forecast = read("video-occupancy-forecast-pilot.json")
    daytime = read("live-taiwan-21840-daylight.json")
    day_audit = read("live-taiwan-visual-audit.json")
    cpu_live = read("live-taiwan-21840-release-audit.json")
    names += ["live-taiwan-21840-release-audit.json", "live-current-gpu-unavailable.json"]
    names += [
        "live-taiwan-21840-daylight.json",
        "live-taiwan-visual-audit.json",
        "live-taiwan-21840-release-audit.json",
        "live-current-gpu-unavailable.json",
    ]
    result = {
        "schema": "atlas-reality-research-7.0",
        "checkpoint": args.checkpoint,
        "physical": physical,
        "cityflow": {
            "development": {
                "scene": "S01",
                "selected_idf1": dev["selected"]["result"]["identity"]["IDF1"],
            },
            "holdout": {
                k: multi[k]
                for k in [
                    "scene",
                    "split",
                    "total_decoded_and_processed_frames",
                    "candidate_tracklets",
                    "candidates",
                    "selected_config",
                    "selected_padding_px_per_edge",
                    "multicamera_filtered_changed_cohort",
                    "limitations",
                ]
            }
            if multi
            else None,
        },
        "peachtree": {
            "split": peach["split"],
            "reports": {
                key: {k: v for k, v in report.items() if k != "per_frame"}
                for key, report in peach["reports"].items()
            },
            "performance": peach["performance"],
            "limitations": peach["limitations"],
        }
        if peach
        else None,
        "lankershim_reserved_test": {
            k: v for k, v in read(names[6]).items() if k not in ["per_frame", "runtime"]
        },
        "live": {
            "observed_start_utc": live["observed_start_utc"],
            "finished_utc": live["finished_utc"],
            "decoded_frames": live["final_health"]["decoded_frames"],
            "inference_frames": live["processing_performance"]["inference_ms"]["samples"],
            "frames_with_tracks": len(live["predicted_observations"]),
            "source_seconds": sum(s["duration_s"] for s in live["segments"]),
            "segments": len(live["segments"]),
            "identity_resets": live["identity_resets"],
            "inference_p95_ms": live["processing_performance"]["inference_ms"]["p95"],
            "receipt_to_result_p95_ms": live["processing_performance"][
                "segment_receipt_to_result_ms"
            ]["p95"],
            "peak_sampled_rss_mb": live["processing_performance"]["peak_sampled_rss_mb"],
            "source_page": live["source_page"],
            "integration_url": live["integration_url"],
            "media_retained": live["media_retained"],
            "buffer_policy": live["buffer_policy"],
            "hardware": live["inference_runtime"]["hardware"],
            "daylight_verified": False,
            "scope": "Archived native Caltrans HLS experiment, nighttime; not current public live processing. Actual visual car-ID continuity checked, no ground-truth accuracy or unique-vehicle-count claim. No source camera timestamp, so receipt latency is not camera-to-display latency.",
        },
        "daytime": {
            "observed_start_utc": daytime["observed_start_utc"],
            "decoded_frames": daytime["decoded_frames"],
            "frames_with_tracks": daytime["frames_with_tracks"],
            "unique_jpeg_frames": daytime["unique_jpeg_frames"],
            "identity_resets": daytime["identity_resets"],
            "effective_decoded_fps": daytime["effective_decoded_fps"],
            "observed_wall_seconds": daytime["observed_wall_seconds"],
            "inference_p95_ms": daytime["inference_ms"]["p95"],
            "max_receipt_gap_s": daytime["max_receipt_gap_s"],
            "daylight_verified": day_audit["daylight_verified"],
            "tls_verified": daytime["tls_verified"],
            "source_catalog": daytime["source_catalog"],
            "license": daytime["license"],
            "scope": day_audit["scope"],
            "current_cpu_recheck": {
                "decoded_frames": cpu_live["decoded_frames"],
                "frames_with_tracks": cpu_live["frames_with_tracks"],
                "observed_wall_seconds": cpu_live["observed_wall_seconds"],
                "inference_p95_ms": cpu_live["inference_ms"]["p95"],
                "identity_resets": cpu_live["identity_resets"],
                "hardware": cpu_live["runtime"]["device"],
            },
            "optional_gpu_currently_available": False,
            "media_retained": daytime["media_retained"],
        },
        "forecast": {
            "results": [{k: v for k, v in r.items() if k != "series"} for r in forecast["results"]],
            "limitations": forecast["limitations"],
            "target": forecast["protocol"]["target"],
            "unsupported_horizons_s": forecast["unsupported_horizons_s"],
        },
        "source_artifacts": {
            name: {
                "bytes": (OUT / name).stat().st_size,
                "sha256": sha(OUT / name),
                "url": "https://github.com/youssef061204/ATLAS/blob/main/artifacts/reality/v7/"
                + name,
            }
            for name in names
        },
        "publisher_sha256": sha(ROOT / "scripts/publish_research_v7.py"),
    }
    target = OUT / "research.json"
    target.write_bytes(json.dumps(result, indent=2).encode())
    manifest = read("manifest.json")
    manifest["files"]["research.json"] = {"bytes": target.stat().st_size, "sha256": sha(target)}
    manifest["research_v7"] = "research.json"
    (OUT / "manifest.json").write_bytes(json.dumps(manifest, indent=2).encode())
    print(
        json.dumps(
            {
                "checkpoint": args.checkpoint,
                "peachtree_complete": peach is not None,
                "cityflow_complete": multi is not None,
            }
        )
    )


if __name__ == "__main__":
    main()
