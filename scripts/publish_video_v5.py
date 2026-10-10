"""Encode genuine stable screen-recording tails; never edit application values."""

import hashlib
import json
import subprocess
from pathlib import Path

import imageio_ffmpeg


def main():
    output = Path("artifacts/portfolio/v5")
    metadata = json.loads((output / "provenance.json").read_bytes())
    work = Path("data/media-capture/v5")
    executable = imageio_ffmpeg.get_ffmpeg_exe()
    parts = []
    for capture in metadata["captures"]:
        destination = (work / capture["source_clip"]).with_suffix(".mp4").resolve()
        subprocess.run(
            [
                executable,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-sseof",
                str(-capture["stable_tail_seconds"]),
                "-i",
                str(work / capture["source_clip"]),
                "-t",
                str(capture["stable_tail_seconds"]),
                "-an",
                "-vf",
                "fps=24,scale=1280:800",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "26",
                "-pix_fmt",
                "yuv420p",
                str(destination),
            ],
            check=True,
        )
        parts.append(destination)
    listing = work / "concat.txt"
    listing.write_text("\n".join(f"file '{p.as_posix()}'" for p in parts), encoding="utf-8")
    video = output / "walkthrough.mp4"
    subprocess.run(
        [
            executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(video),
        ],
        check=True,
    )
    reader = imageio_ffmpeg.read_frames(str(video))
    video_metadata = next(reader)
    reader.close()
    assert 30 <= video_metadata["duration"] <= 60
    metadata["walkthrough"] = {
        "file": video.name,
        "duration_s": video_metadata["duration"],
        "bytes": video.stat().st_size,
        "sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
        "resolution": video_metadata["size"],
        "processing": "Stable tails of actual source clips; chronological screen flow, no loading footage. H.264 encoding/resizing only; no benchmark value or application pixel alterations.",
        "publisher_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    for capture in metadata["captures"]:
        capture["sha256"] = hashlib.sha256((output / capture["file"]).read_bytes()).hexdigest()
    (output / "provenance.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata["walkthrough"], indent=2))


if __name__ == "__main__":
    main()
