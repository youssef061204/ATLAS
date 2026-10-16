"""Encode actual stable application recordings; never edit displayed measurements."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import cv2
import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/portfolio/v6"
CLIPS = ROOT / "data/media-capture/v6"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    provenance = json.loads((OUT / "provenance.json").read_text())
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    pieces = []
    for index, record in enumerate(provenance["captures"]):
        destination = CLIPS / f"part-{index}.mp4"
        duration = str(record["stable_tail_seconds"])
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-sseof",
                "-" + duration,
                "-i",
                str(CLIPS / record["source_clip"]),
                "-t",
                duration,
                "-an",
                "-vf",
                "scale=1280:-2",
                "-r",
                "25",
                "-c:v",
                "libx264",
                "-crf",
                "28",
                "-preset",
                "medium",
                "-threads",
                "4",
                str(destination),
            ],
            check=True,
            timeout=120,
        )
        pieces.append(destination)
        record["sha256"] = sha(OUT / record["file"])
    listing = CLIPS / "concat.txt"
    listing.write_text("\n".join(f"file '{path.as_posix()}'" for path in pieces), encoding="utf-8")
    video = OUT / "walkthrough.mp4"
    subprocess.run(
        [
            ffmpeg,
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
        timeout=60,
    )
    capture = cv2.VideoCapture(str(video))
    fps = capture.get(cv2.CAP_PROP_FPS)
    count = 0
    while capture.read()[0]:
        count += 1
    capture.release()
    expected = sum(row["stable_tail_seconds"] for row in provenance["captures"])
    if abs(count / fps - expected) > 0.2:
        raise ValueError("Walkthrough duration does not match actual recorded stable segments")
    shutil.copyfile(ROOT / "artifacts/reality/v6/source-license.txt", OUT / "source-license.txt")
    with (OUT / "source-license.txt").open("a", encoding="utf-8") as handle:
        handle.write(
            "\nPresentation screenshots/walkthrough containing this FHWA footage are adaptations under CC BY-SA 4.0. ATLAS UI software retains its repository license. Other scenes show separately labelled historical ATLAS simulator/benchmark results, not field benefits. No CityFlow source footage or Caltrans live imagery is included.\n"
        )
    provenance["video"] = {
        "file": video.name,
        "seconds": count / fps,
        "decoded_frames": count,
        "fps": fps,
        "sha256": sha(video),
        "bytes": video.stat().st_size,
    }
    provenance["reality_manifest_sha256"] = sha(ROOT / "artifacts/reality/v6/manifest.json")
    provenance["encoder_sha256"] = sha(Path(__file__))
    (OUT / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    print(json.dumps(provenance["video"], indent=2), flush=True)


if __name__ == "__main__":
    main()
