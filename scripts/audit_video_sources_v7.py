"""Audit official AVI headers through bounded HTTP ranges before full acquisition."""

import argparse
import json
import struct
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import httpx
from acquire_video_v6 import RangeReader

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", choices=["uv3e-y54k", "mupt-aksf"], default="uv3e-y54k")
    args = parser.parse_args()
    url = f"https://data.transportation.gov/download/{args.catalog}/application%2Fx-zip-compressed"
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        response = client.get(f"https://data.transportation.gov/api/views/{args.catalog}.json")
        response.raise_for_status()
        metadata = response.json()
        resource = RangeReader(client, url, int(metadata["blobFileSize"]))
        records = []
        with zipfile.ZipFile(resource) as archive:
            for info in archive.infolist():
                if (
                    not info.filename.lower().endswith(".avi")
                    or "processed" in info.filename.lower()
                ):
                    continue
                with archive.open(info) as member:
                    header = member.read(4096)
                riff = header[:4] == b"RIFF" and header[8:12] == b"AVI "
                declared = struct.unpack("<I", header[4:8])[0] + 8 if riff else None
                index = header.find(b"avih")
                frame_count = (
                    struct.unpack("<I", header[index + 24 : index + 28])[0] if index >= 0 else None
                )
                record = {
                    "member": info.filename,
                    "bytes": info.file_size,
                    "crc32": f"{info.CRC:08x}",
                    "riff_declared_bytes": declared,
                    "declared_frames": frame_count,
                    "header_consistent": riff and declared <= info.file_size,
                    "full_decode_verified": False,
                }
                records.append(record)
                print(json.dumps(record), flush=True)
        report = {
            "observed_utc": datetime.now(UTC).isoformat(),
            "catalog": args.catalog,
            "url": url,
            "license": metadata.get("license"),
            "archive_bytes": resource.size,
            "transferred_bytes": resource.transferred,
            "videos": records,
            "scope": "Header consistency alone never establishes complete decoding or alignment to labels. Full CRC and complete decode are mandatory before evaluation.",
        }
        out = ROOT / "artifacts/reality/v7"
        out.mkdir(parents=True, exist_ok=True)
        (out / f"source-header-audit-{args.catalog}.json").write_bytes(
            json.dumps(report, indent=2).encode()
        )


if __name__ == "__main__":
    main()
