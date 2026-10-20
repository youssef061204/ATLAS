"""Package an actual browser recording and unaltered screenshots for publication."""

import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/portfolio/v7"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    capture = json.loads((ROOT / "data/reality-v7/media/capture.json").read_text("utf-8"))
    assert not capture["errors"] and not capture["failures"]
    script = ROOT / "frontend/scripts/capture-reality-v7.mjs"
    assert digest(script) == capture["sourceSha256"], "Capture script changed after recording"
    movie = OUT / "walkthrough-v7.mp4"
    subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-ss",
            str(capture["trimStartSeconds"]),
            "-i",
            capture["recording"],
            "-t",
            str(capture["flowSeconds"]),
            "-an",
            "-vf",
            "fps=25",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "28",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(movie),
        ],
        check=True,
    )
    frames = imageio_ffmpeg.read_frames(str(movie), pix_fmt="rgb24")
    metadata = next(frames)
    decoded_frames = sum(1 for _ in frames)
    assert 30 <= decoded_frames / metadata["fps"] <= 60
    source_paths = [
        "frontend/scripts/capture-reality-v7.mjs",
        "frontend/scripts/benchmark-reality-v7.mjs",
        "frontend/components/reality-scene-v7.tsx",
        "frontend/components/reality-scene-v7.module.css",
        "frontend/components/reality-replay.tsx",
        "frontend/components/reality-evidence-v7.tsx",
    ]
    archive = OUT / "presentation-source.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as package:
        for name in source_paths:
            package.writestr(name, (ROOT / name).read_bytes())
    files = [*sorted(OUT.glob("*.jpg")), movie, archive]
    manifest = {
        "schema": "atlas-real-presentation-v7",
        "source": capture["source"],
        "recording": {
            "trim_start_seconds": capture["trimStartSeconds"],
            "capture_flow_seconds": capture["flowSeconds"],
            "decoded_frames": decoded_frames,
            "fps": metadata["fps"],
            "duration_seconds": decoded_frames / metadata["fps"],
            "size": metadata["size"],
            "page_errors": capture["errors"],
            "failed_site_responses": capture["failures"],
        },
        "source_files": {name: digest(ROOT / name) for name in source_paths},
        "evidence": {
            name: digest(ROOT / name)
            for name in [
                "artifacts/reality/v7/manifest.json",
                "artifacts/reality/v7/research.json",
                "artifacts/reality/v7/render-performance.json",
            ]
        },
        "files": {
            path.name: {"bytes": path.stat().st_size, "sha256": digest(path)} for path in files
        },
        "limitations": [
            "Historical footage and precomputed real CV/native SUMO output, not a live public worker.",
            "Physical acceptance fails; screen displays actual failures and held-out results.",
            "Buildings, trees and heights are illustrative; georeferenced imagery is historical.",
            "Signal comparison is the separately scoped retained RESCO simulation, not a field gain.",
            "No CityFlow source imagery, model weights, live imagery or private ground truth included.",
        ],
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest["recording"]))


if __name__ == "__main__":
    main()
