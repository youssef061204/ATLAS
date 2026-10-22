"""Web-encode the unedited ATLAS 8 browser recording and record media provenance."""

import hashlib
import json
import subprocess
from pathlib import Path

import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/portfolio/v8"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    capture = json.loads((ROOT / "data/reality-v8/media/capture.json").read_text("utf-8"))
    assert not capture["errors"] and not capture["failures"]
    source_script = ROOT / "frontend/scripts/capture-reality-v8.mjs"
    assert digest(source_script) == capture["sourceSha256"], (
        "Capture script changed after recording"
    )

    movie = OUT / "walkthrough-v8.mp4"
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
    duration = decoded_frames / metadata["fps"]
    assert 30 <= duration <= 60, f"Walkthrough outside 30–60 s: {duration:.1f}"

    sources = [
        "frontend/scripts/capture-reality-v8.mjs",
        "frontend/app/ground-truth/page.tsx",
        "frontend/public/ground-truth/summary.json",
        "docs/reality-v8-diagnostics.md",
        "artifacts/reality/v8/geometry-video-overlay.png",
    ]
    media = [OUT / "ground-truth-v8.jpg", movie]
    manifest = {
        "schema": "atlas-real-presentation-v8",
        "source": capture["source"],
        "recording": {
            "trim_start_seconds": capture["trimStartSeconds"],
            "capture_flow_seconds": capture["flowSeconds"],
            "decoded_frames": decoded_frames,
            "fps": metadata["fps"],
            "duration_seconds": duration,
            "size": metadata["size"],
            "page_errors": capture["errors"],
            "failed_site_responses": capture["failures"],
        },
        "source_files": {name: digest(ROOT / name) for name in sources},
        "files": {
            file.name: {"bytes": file.stat().st_size, "sha256": digest(file)} for file in media
        },
        "limitations": [
            "Historical source footage and precomputed CV/native SUMO, not a live public worker.",
            "The Ground Truth result is a reference-assisted, exposed-development diagnostic and is not deployable prediction.",
            "Physical acceptance remains failed; no observed field control benefit is claimed.",
            "Source footage and its adaptations retain FHWA CC BY-SA 4.0; supporting trajectory/survey material retains the catalog CC BY-SA 3.0 terms.",
        ],
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest["recording"]))


if __name__ == "__main__":
    main()
