import argparse
import gzip
import hashlib
import json
import shutil
import urllib.request
from pathlib import Path

from . import config, db
from .experiments import (
    benchmark_cv,
    benchmark_forecast,
    benchmark_risk,
    benchmark_simulation,
    evaluate_mot,
    save,
)
from .pipeline import persist, process_video

DEMO_URL = "https://assets.mixkit.co/videos/1755/1755-720.mp4"


def download_demo():
    path = config.DATA / "demo.mp4"
    if not path.exists() or path.stat().st_size < 10000:
        request = urllib.request.Request(
            DEMO_URL, headers={"User-Agent": "ATLAS/1.0 traffic-research demo"}
        )
        temporary = path.with_suffix(".download")
        try:
            with (
                urllib.request.urlopen(request, timeout=90) as response,
                temporary.open("wb") as target,
            ):
                shutil.copyfileobj(response, target)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    attribution = {
        "title": "City busy traffic intersection, time-lapse",
        "author": "Mixkit stock contributor (see source page)",
        "license": "Mixkit Stock Video Free License; do not redistribute as a standalone stock asset",
        "source_page": "https://mixkit.co/free-stock-video/city-busy-traffic-intersection-time-lapse-1755/",
        "time_lapse": True,
        "download": DEMO_URL,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    (config.DATA / "demo-attribution.json").write_text(
        json.dumps(attribution, indent=2), encoding="utf-8"
    )
    return path


def main():
    parser = argparse.ArgumentParser(description="ATLAS reproducible commands")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo")
    demo.add_argument("--download-only", action="store_true")
    demo.add_argument(
        "--cached", action="store_true", help="Restore a checksum-verified cached real CV run"
    )
    process = sub.add_parser("process")
    process.add_argument("path", type=Path)
    process.add_argument("--camera-config", type=Path)
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument(
        "--only", choices=["risk", "forecast", "simulation", "cv", "tracking", "all"], default="all"
    )
    evaluate.add_argument("--dataset", default="coco8.yaml")
    evaluate.add_argument("--gt", type=Path)
    evaluate.add_argument("--pred", type=Path)
    benchmark = sub.add_parser("benchmark")
    benchmark.add_argument("path", type=Path)
    args = parser.parse_args()
    db.init()
    if args.command in {"demo", "process", "benchmark"}:
        from .api import register_video
        from .schemas import CameraConfig

        path = download_demo() if args.command == "demo" else args.path.resolve()
        if args.command == "demo" and args.download_only:
            print(path)
            return
        cached_result = None
        if args.command == "demo" and args.cached:
            try:
                cached_result, cache_sha = load_demo_cache(path)
            except (ValueError, OSError) as exc:
                parser.error(str(exc))
            previous = db.rows(
                "SELECT id,metadata FROM videos WHERE filename='demo.mp4' AND storage_path=? AND status='complete' ORDER BY created_at DESC",
                (str(path),),
            )
            for video in previous:
                metadata = json.loads(video["metadata"])
                if (
                    metadata.get("cache_sha256") == cache_sha
                    and (config.DATA / "results" / f"{video['id']}.json").exists()
                ):
                    print(
                        json.dumps(
                            {"video_id": video["id"], "cached": True, "already_loaded": True}
                        )
                    )
                    return
        video_id = register_video(path, path.name, "demo")
        camera_file = (
            config.ROOT / "docs" / "demo-camera.json"
            if args.command == "demo"
            else getattr(args, "camera_config", None)
        )
        if camera_file:
            settings = CameraConfig.model_validate_json(camera_file.read_text())
            with db.connection() as conn:
                conn.execute(
                    "UPDATE cameras SET config=? WHERE id=(SELECT camera_id FROM videos WHERE id=?)",
                    (settings.model_dump_json(), video_id),
                )
        if args.command == "demo" and args.cached:
            result = cached_result
            result["video_id"] = video_id
            result["provenance"]["cached"] = True
            persist(video_id, result)
            db.status(
                video_id,
                "complete",
                "complete",
                1,
                metadata={
                    **result["metadata"],
                    "summary": result["summary"],
                    "performance": result["performance"],
                    "cached": True,
                    "cache_sha256": cache_sha,
                },
            )
        else:
            result = process_video(video_id)
        save(
            "pipeline",
            {
                "scope": "Measured CPU/GPU run on attributed source video; detection accuracy not inferred from speed",
                "video_id": video_id,
                "performance": result["performance"],
                "summary": result["summary"],
                "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            },
        )
        print(
            json.dumps(
                {
                    "video_id": video_id,
                    "summary": result["summary"],
                    "performance": result["performance"],
                },
                indent=2,
            )
        )
    elif args.command == "evaluate":
        results = {}
        if args.only in {"all", "risk"}:
            results["risk"] = benchmark_risk()
        if args.only in {"all", "forecast"}:
            results["forecast"] = benchmark_forecast()
        if args.only in {"all", "simulation"}:
            results["simulation"] = benchmark_simulation()
        if args.only == "cv":
            results["cv"] = benchmark_cv(args.dataset)
        if args.only == "tracking":
            if not args.gt or not args.pred:
                parser.error("Tracking evaluation needs --gt and --pred")
            results["tracking"] = evaluate_mot(args.gt, args.pred)
        print(json.dumps({k: v.get("scope") for k, v in results.items()}, indent=2))


def load_demo_cache(path):
    cache = config.ARTIFACTS / "demo" / "result.json.gz"
    manifest = json.loads((cache.parent / "manifest.json").read_text(encoding="utf-8"))
    cache_sha = hashlib.sha256(cache.read_bytes()).hexdigest()
    if cache_sha != manifest["artifact_sha256"]:
        raise ValueError("Cached CV output checksum mismatch; run atlas demo without --cached")
    source_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if source_sha != manifest["source_sha256"]:
        raise ValueError("Downloaded sample differs from the cached source; run without --cached")
    with gzip.open(cache, "rt", encoding="utf-8") as source:
        result = json.load(source)
    if source_sha != result["provenance"]["source_sha256"]:
        raise ValueError("Cached result provenance differs from the source manifest")
    return result, cache_sha


if __name__ == "__main__":
    main()
