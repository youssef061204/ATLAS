"""Extract a lossless, explicitly partial clip; never repair or invent source frames."""

import hashlib
import json
from pathlib import Path

import cv2


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main():
    data = Path(__file__).resolve().parents[1] / "data/reality-v6"
    source = data / "lankershim-camera4-0845am-0900am.avi"
    record = json.loads(source.with_suffix(".avi.source.json").read_text())
    if sha(source) != record["sha256"]:
        raise ValueError("Parent checksum mismatch")
    destination = data / "lankershim-camera4-holdout-prefix.avi"
    capture = cv2.VideoCapture(str(source))
    width, height = (int(capture.get(key)) for key in (3, 4))
    writer = cv2.VideoWriter(str(destination), cv2.VideoWriter_fourcc(*"FFV1"), 10, (width, height))
    if not writer.isOpened():
        raise ValueError("Lossless writer unavailable")
    pixels = hashlib.sha256()
    try:
        for _ in range(6510):
            ok, frame = capture.read()
            if not ok:
                raise ValueError("Source ended before the frozen quality guard")
            pixels.update(frame.tobytes())
            writer.write(frame)
    finally:
        writer.release()
        capture.release()
    decoded = hashlib.sha256()
    capture = cv2.VideoCapture(str(destination))
    count = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        decoded.update(frame.tobytes())
        count += 1
    capture.release()
    if count != 6510 or pixels.hexdigest() != decoded.hexdigest():
        raise ValueError("Derived clip is not pixel-identical to its source prefix")
    audit = {
        "sha256": sha(destination),
        "derived_clip": True,
        "parent_file": source.name,
        "parent_sha256": record["sha256"],
        "parent_complete": False,
        "parent_declared_frames": 10480,
        "parent_decodable_frames": 6538,
        "frame_interval": [0, 6510],
        "fps": 10,
        "decoded_frames": count,
        "decoded_pixel_sha256": decoded.hexdigest(),
        "source_pixel_sha256": pixels.hexdigest(),
        "description": "Exact consecutive source pixels, lossless FFV1; last 28 decoded parent frames excluded by the predeclared quality guard. No repair, interpolation or invented frames. This is not the complete original recording.",
    }
    destination.with_suffix(".avi.source.json").write_text(
        json.dumps(audit, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, indent=2), flush=True)


if __name__ == "__main__":
    main()
