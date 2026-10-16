"""Authorized local noncommercial CityFlowV2 acquisition; never redistribute raw data."""

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

import httpx
from acquire_video_v6 import RangeReader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/reality-v6/cityflow-v2"
URL = "https://drive.usercontent.google.com/download?id=13wNJpS_Oaoe-7y5Dzexg_Ol7bKu1OWuC&export=download&confirm=t"
SIZE = 16912529116


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--member", action="append", default=[])
    parser.add_argument("--scene", choices=["S02"])
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        with zipfile.ZipFile(RangeReader(client, URL, SIZE)) as archive:
            listing = [
                {
                    "name": info.filename,
                    "bytes": info.file_size,
                    "compressed_bytes": info.compress_size,
                    "crc32": f"{info.CRC:08x}",
                }
                for info in archive.infolist()
            ]
            (OUT / "directory.json").write_text(json.dumps(listing, indent=2), encoding="utf-8")
            if args.scene:
                args.member.extend(
                    ["ReadMe.txt", "cam_framenum/S02.txt", "cam_timestamp/S02.txt", "eval/eval.py"]
                )
                for camera in ["c006", "c007", "c008", "c009"]:
                    args.member.extend(
                        f"validation/S02/{camera}/{name}"
                        for name in ["vdo.avi", "roi.jpg", "calibration.txt", "gt/gt.txt"]
                    )
            if not args.member:
                videos = [row for row in listing if row["name"].endswith("vdo.avi")]
                print(json.dumps({"members": len(listing), "videos": videos}, indent=2), flush=True)
            for name in args.member:
                info = archive.getinfo(name)
                target = (OUT / info.filename).resolve()
                if (
                    not target.is_relative_to(OUT.resolve())
                    or info.file_size > 3_000_000_000
                    or info.is_dir()
                ):
                    raise ValueError("Unsafe or oversized member")
                target.parent.mkdir(parents=True, exist_ok=True)
                source_record = target.with_suffix(target.suffix + ".source.json")
                if target.exists() and source_record.exists():
                    previous = json.loads(source_record.read_text())
                    with target.open("rb") as handle:
                        digest = hashlib.file_digest(handle, "sha256").hexdigest()
                    if previous.get("sha256") == digest and target.stat().st_size == info.file_size:
                        print("Verified existing", name, flush=True)
                        continue
                temporary = target.with_suffix(target.suffix + ".part")
                digest = hashlib.sha256()
                count = 0
                with archive.open(info) as source, temporary.open("wb") as output:
                    while block := source.read(4 * 1024 * 1024):
                        count += len(block)
                        digest.update(block)
                        output.write(block)
                if count != info.file_size:
                    raise ValueError("Incomplete source member")
                temporary.replace(target)
                source_record.write_text(
                    json.dumps(
                        {
                            "official_access_page": "https://www.aicitychallenge.org/ai-city-challenge-dataset-access/",
                            "official_download_page": "https://www.aicitychallenge.org/2022-track1-download/",
                            "license": "https://www.aicitychallenge.org/wp-content/uploads/2022/02/Dataset-License-AIC2022.pdf",
                            "scope": "Local noncommercial research only; no production use, model deployment or raw data redistribution",
                            "member": name,
                            "bytes": count,
                            "sha256": digest.hexdigest(),
                            "zip_crc_verified": True,
                            "crc32": f"{info.CRC:08x}",
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                print("Acquired complete member", name, count, flush=True)


if __name__ == "__main__":
    main()
