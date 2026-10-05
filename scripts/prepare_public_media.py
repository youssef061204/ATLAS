"""Create an annotated, attributed presentation clip from the genuine cached CV run."""

import gzip
import json
import subprocess

import cv2
import httpx
from atlas import config
from atlas.evaluation.artifacts import checksum


def main():
    import imageio_ffmpeg

    folder = config.ARTIFACTS / "demo"
    manifest = json.loads((folder / "manifest.json").read_text())
    saved = folder / "result.json.gz"
    source = config.DATA / "demo.mp4"
    if (
        checksum(saved) != manifest["artifact_sha256"]
        or checksum(source) != manifest["source_sha256"]
    ):
        raise ValueError("Demo source or actual CV cache does not match its verified manifest")
    result = json.loads(gzip.decompress(saved.read_bytes()))
    metadata = result["metadata"]
    destination = folder / "annotated-preview.webm"
    command = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pixel_format",
        "bgr24",
        "-video_size",
        f"{metadata['width']}x{metadata['height']}",
        "-framerate",
        str(metadata["fps"]),
        "-i",
        "pipe:0",
        "-an",
        "-c:v",
        "libvpx",
        "-b:v",
        "1800k",
        "-crf",
        "14",
        "-deadline",
        "good",
        "-cpu-used",
        "4",
        str(destination),
    ]
    capture = cv2.VideoCapture(str(source))
    encoded = subprocess.Popen(command, stdin=subprocess.PIPE)
    try:
        for frame in result["frames"]:
            ok, image = capture.read()
            if not ok:
                raise ValueError("Source ended before recorded observations")
            for obj in frame["objects"]:
                x1, y1, x2, y2 = map(int, obj["bbox"])
                color = (184, 213, 148) if obj["class"] != "person" else (139, 196, 232)
                cv2.rectangle(image, (x1, y1), (x2, y2), color, 1)
            cv2.rectangle(image, (0, 0), (metadata["width"], 34), (17, 29, 34), -1)
            caption = f"ATLAS | actual YOLO / ByteTrack output | Mixkit #1755 | playback {frame['t']:.2f}s"
            cv2.putText(
                image,
                caption,
                (14, 23),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (205, 227, 221),
                1,
                cv2.LINE_AA,
            )
            encoded.stdin.write(image.tobytes())
    finally:
        capture.release()
        encoded.stdin.close()
        encoded.wait(timeout=120)
    if encoded.returncode:
        raise RuntimeError("Presentation encoding failed")
    with httpx.Client(timeout=120) as client:
        response = client.post(
            "http://127.0.0.1:8000/api/simulations",
            json={"seed": 42, "duration": 300, "demand": [0.38, 0.12, 0.32, 0.1]},
        )
        response.raise_for_status()
        payload = response.json()
    (folder / "simulation.json.gz").write_bytes(
        gzip.compress(json.dumps(payload).encode(), mtime=0)
    )
    (folder / "presentation-manifest.json").write_text(
        json.dumps(
            {
                "annotated_video_sha256": checksum(destination),
                "original_source_sha256": manifest["source_sha256"],
                "actual_cv_cache_sha256": manifest["artifact_sha256"],
                "simulation_sha256": checksum(folder / "simulation.json.gz"),
                "scope": "Annotated/composited presentation, not an unmodified redistributable stock asset. Mixkit Stock Video Free License. Synthetic simulation recorded from actual ATLAS API.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Prepared attributed presentation: {destination.stat().st_size / 1024**2:.2f} MiB")


if __name__ == "__main__":
    main()
