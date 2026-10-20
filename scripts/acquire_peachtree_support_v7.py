"""Acquire the complete official Peachtree reference CSV, geometry and signal events."""

import hashlib
import json
import zipfile
from pathlib import Path

import httpx
from acquire_video_v6 import RangeReader

ROOT = Path(__file__).resolve().parents[1]
URL = "https://data.transportation.gov/api/views/8ect-6jqj/files/7244a8b5-077f-4851-bc06-3cfc7a75f0b0?download=true"


def main():
    out = ROOT / "data/reality-v7/peachtree/support"
    out.mkdir(parents=True, exist_ok=True)
    records = []
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        with zipfile.ZipFile(RangeReader(client, URL, 50677241)) as archive:
            for info in archive.infolist():
                if "aerial-ortho" in info.filename:
                    continue
                destination = out / Path(info.filename).name
                if not destination.exists():
                    with archive.open(info) as source, destination.open("wb") as target:
                        while block := source.read(1024 * 1024):
                            target.write(block)
                if destination.stat().st_size != info.file_size:
                    raise ValueError("Incomplete source member")
                record = {
                    "file": destination.name,
                    "bytes": destination.stat().st_size,
                    "sha256": hashlib.file_digest(destination.open("rb"), "sha256").hexdigest(),
                    "crc32": f"{info.CRC:08x}",
                }
                if destination.suffix == ".zip":
                    with zipfile.ZipFile(destination) as nested:
                        if nested.testzip() is not None:
                            raise ValueError("Invalid nested archive CRC")
                        record["members"] = nested.namelist()
                        for member in nested.infolist():
                            target = (out / member.filename).resolve()
                            if (
                                not target.is_relative_to(out.resolve())
                                or member.file_size > 50_000_000
                            ):
                                raise ValueError("Unsafe nested asset")
                            if member.is_dir() or target.name.lower() == "thumbs.db":
                                continue
                            target.parent.mkdir(parents=True, exist_ok=True)
                            with nested.open(member) as source, target.open("wb") as handle:
                                while block := source.read(1024 * 1024):
                                    handle.write(block)
                records.append(record)
                print(destination.name, record["bytes"], flush=True)
    manifest = {
        "url": URL,
        "license": "CC BY-SA 3.0, FHWA NGSIM supporting data",
        "records": records,
        "scope": "Full reference acquisition only; reserved spatial/temporal label outcomes remain unscored",
    }
    (out / "source.json").write_bytes(json.dumps(manifest, indent=2).encode())
    (ROOT / "artifacts/reality/v7/peachtree-support-source.json").write_bytes(
        json.dumps(manifest, indent=2).encode()
    )


if __name__ == "__main__":
    main()
