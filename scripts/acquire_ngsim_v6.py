"""Bounded, resumable acquisition of public FHWA Lankershim research assets."""

import hashlib
import json
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/reality-v6"
BASE = "https://data.transportation.gov"
VIEW = "8ect-6jqj"
WANTED = {
    "Lankershim-Boulevard-LosAngeles-CA.zip": "support.zip",
    "Lankershim_Blvd_Metadata_Documentation.pdf": "metadata.pdf",
    "lankershim-boulevard-ProcessedVideo-0830am-0845am-Cam45.zip": "video-cam45.zip",
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        response = client.get(f"{BASE}/api/views/{VIEW}.json")
        response.raise_for_status()
        metadata = response.json()
        assert "creativecommons.org/licenses/by-sa/3.0" in metadata["license"]["termsLink"]
        (OUT / "trajectory-catalog.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )
        for attachment in sorted(metadata["metadata"]["attachments"], key=lambda a: a["filename"]):
            if attachment["filename"] not in WANTED:
                continue
            destination = OUT / WANTED[attachment["filename"]]
            url = f"{BASE}/api/views/{VIEW}/files/{attachment['assetId']}?download=true"
            head = client.head(url)
            head.raise_for_status()
            size = int(head.headers["content-length"])
            if size > 150_000_000:
                raise ValueError("Asset exceeds the fixed free/local acquisition budget")
            if not destination.exists() or destination.stat().st_size != size:
                temporary = destination.with_suffix(".part")
                count = 0
                with client.stream("GET", url) as stream, temporary.open("wb") as file:
                    stream.raise_for_status()
                    for block in stream.iter_bytes(1024 * 1024):
                        count += len(block)
                        if count > size:
                            raise ValueError("Unexpected download size")
                        file.write(block)
                assert count == size
                temporary.replace(destination)
            with destination.open("rb") as handle:
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
            record = {
                "file": destination.name,
                "original_filename": attachment["filename"],
                "url": url,
                "bytes": size,
                "sha256": digest,
                "license": metadata["license"],
                "attribution": metadata["attribution"],
            }
            if destination.suffix == ".zip":
                try:
                    with zipfile.ZipFile(destination) as archive:
                        record["members"] = [
                            {"file": i.filename, "bytes": i.file_size} for i in archive.infolist()
                        ]
                    record["archive_usable"] = True
                except zipfile.BadZipFile:
                    record["archive_usable"] = False
                    record["error"] = (
                        "Published archive has no usable ZIP central directory; do not treat as a complete valid archive"
                    )
            records.append(record)
            print(
                destination.name,
                size,
                "bytes",
                len(record.get("members", [])),
                "members",
                flush=True,
            )
            time.sleep(0.2)
    (OUT / "acquisition.json").write_text(
        json.dumps(
            {
                "acquired_at": datetime.now(UTC).isoformat(),
                "assets": records,
                "scope": "Public FHWA catalog attachments under their catalog CC BY-SA 3.0 license; separately cataloged videos have CC BY-SA 4.0. Preserve attribution and license per asset. Raw archives remain outside source control.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
