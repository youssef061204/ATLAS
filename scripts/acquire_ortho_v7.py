"""Acquire FHWA's georeferenced orthophoto for honest geographic scene context."""

import hashlib
import json
import zipfile
from pathlib import Path

import httpx
from acquire_support_v6 import URL
from acquire_video_v6 import RangeReader

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT / "data/reality-v7/ortho"
    out.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        with zipfile.ZipFile(RangeReader(client, URL, 144875847)) as archive:
            info = next(i for i in archive.infolist() if "aerial-ortho" in i.filename)
            destination = out / Path(info.filename).name
            if not destination.exists():
                with archive.open(info) as source, destination.open("wb") as target:
                    while block := source.read(1024 * 1024):
                        target.write(block)
            if destination.stat().st_size != info.file_size:
                raise ValueError("Incomplete ortho archive")
            with zipfile.ZipFile(destination) as nested:
                records = []
                for member in nested.infolist():
                    if member.is_dir() or Path(member.filename).suffix.lower() not in {
                        ".tif",
                        ".tfw",
                    }:
                        continue
                    if member.file_size > 1_000_000_000:
                        raise ValueError("Oversized source image")
                    target = out / Path(member.filename).name
                    if not target.exists():
                        with nested.open(member) as source, target.open("wb") as handle:
                            while block := source.read(1024 * 1024):
                                handle.write(block)
                    with nested.open(member) as source:
                        digest = hashlib.file_digest(source, "sha256").hexdigest()
                    with target.open("rb") as handle:
                        if hashlib.file_digest(handle, "sha256").hexdigest() != digest:
                            raise ValueError("Extracted ortho checksum mismatch")
                    records.append(
                        {
                            "file": target.name,
                            "bytes": target.stat().st_size,
                            "sha256": digest,
                            "crc32": f"{member.CRC:08x}",
                        }
                    )
                print(json.dumps(records), flush=True)
            (out / "source.json").write_bytes(
                json.dumps(
                    {"url": URL, "member": info.filename, "files": records}, indent=2
                ).encode()
            )


if __name__ == "__main__":
    main()
