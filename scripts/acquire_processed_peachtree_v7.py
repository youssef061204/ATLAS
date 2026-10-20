"""Acquire labelled reference video for development-only registration, never CV input."""

import hashlib
import json
import zipfile
from pathlib import Path

import httpx
from acquire_video_v6 import RangeReader

ROOT = Path(__file__).resolve().parents[1]
URL = "https://data.transportation.gov/api/views/h35x-vs8r/files/05fe1e5f-89b2-4c66-9d9e-e36aa52b0a15?download=true"


def main():
    out = ROOT / "data/reality-v7/peachtree"
    out.mkdir(parents=True, exist_ok=True)
    target = out / "development-reference-processed.avi"
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        with zipfile.ZipFile(RangeReader(client, URL, 519231231)) as archive:
            info = next(i for i in archive.infolist() if i.filename.endswith(".avi"))
            if not target.exists():
                with archive.open(info) as source, target.open("wb") as handle:
                    count = 0
                    while block := source.read(1024 * 1024):
                        handle.write(block)
                        count += len(block)
                        if count % (64 * 1024 * 1024) == 0:
                            print(f"{count}/{info.file_size} reference bytes", flush=True)
            if target.stat().st_size != info.file_size:
                raise ValueError("Incomplete calibration reference member")
            record = {
                "url": URL,
                "member": info.filename,
                "bytes": target.stat().st_size,
                "crc32": f"{info.CRC:08x}",
                "sha256": hashlib.file_digest(target.open("rb"), "sha256").hexdigest(),
                "scope": "Development reference for video/world/time registration only. Annotated pixels are prohibited as CV detector input.",
            }
            target.with_suffix(".avi.source.json").write_bytes(
                json.dumps(record, indent=2).encode()
            )
            print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
