"""Acquire one complete public FHWA video member, verify CRC and decode every frame."""

import argparse
import hashlib
import json
import struct
import zipfile
from pathlib import Path

import cv2
import httpx
from acquire_video_v6 import RangeReader

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", choices=["mupt-aksf", "uv3e-y54k"], required=True)
    parser.add_argument("--member", required=True)
    args = parser.parse_args()
    out = ROOT / "data/reality-v7/official-videos"
    out.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        response = client.get(f"https://data.transportation.gov/api/views/{args.catalog}.json")
        response.raise_for_status()
        metadata = response.json()
        if "creativecommons.org/licenses/by-sa/4.0" not in metadata.get("license", {}).get(
            "termsLink", ""
        ):
            raise ValueError("Review changed official video license before acquiring")
        url = f"https://data.transportation.gov/download/{args.catalog}/application%2Fx-zip-compressed"
        resource = RangeReader(client, url, int(metadata["blobFileSize"]))
        with zipfile.ZipFile(resource) as archive:
            info = archive.getinfo(args.member)
            if info.file_size > 3_000_000_000 or not info.filename.lower().endswith(".avi"):
                raise ValueError("Invalid video member or size")
            destination = out / Path(info.filename).name
            partial = destination.with_suffix(".avi.part")
            if not destination.exists():
                with archive.open(info) as source, partial.open("wb") as target:
                    while block := source.read(1024 * 1024):
                        target.write(block)
                if partial.stat().st_size != info.file_size:
                    raise ValueError("Incomplete acquisition")
                partial.replace(destination)
            with destination.open("rb") as handle:
                header = handle.read(12)
                if (
                    header[:4] != b"RIFF"
                    or struct.unpack("<I", header[4:8])[0] + 8 > info.file_size
                ):
                    raise ValueError("AVI header declares missing source bytes")
                handle.seek(0)
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
            cv2.setNumThreads(1)
            capture = cv2.VideoCapture(str(destination))
            declared = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = capture.get(cv2.CAP_PROP_FPS)
            decoded = 0
            identical = 0
            previous = None
            while True:
                ok, image = capture.read()
                if not ok:
                    break
                current = hashlib.sha256(image.tobytes()).digest()
                identical += previous == current
                previous = current
                decoded += 1
            capture.release()
            if decoded != declared:
                raise ValueError(f"Incomplete video: decoded {decoded}/{declared}")
            record = {
                "catalog": args.catalog,
                "url": url,
                "member": info.filename,
                "bytes": destination.stat().st_size,
                "sha256": digest,
                "crc32": f"{info.CRC:08x}",
                "zip_crc_verified_during_full_extraction": True,
                "declared_frames": declared,
                "decoded_frames": decoded,
                "fps": fps,
                "consecutive_identical_pixel_pairs": identical,
                "license": metadata["license"],
                "status": "complete_source_decode_verified",
                "scope": "Acquisition and decoding only; no held-out annotations or accuracy outcomes inspected",
            }
            destination.with_suffix(".avi.source.json").write_bytes(
                json.dumps(record, indent=2).encode()
            )
            publication = (
                ROOT / "artifacts/reality/v7" / f"source-integrity-{destination.stem}.json"
            )
            publication.write_bytes(json.dumps(record, indent=2).encode())
            print(json.dumps(record, indent=2), flush=True)


if __name__ == "__main__":
    main()
