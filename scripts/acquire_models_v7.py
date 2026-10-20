"""Acquire explicitly pinned AGPL aerial research weights; keep binaries ignored."""

import hashlib
import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "dronefreak/visdrone-yolo11s"
REVISION = "c1c9c8f559a7ebdc5271f8d5695b026dd22420cc"


def main():
    destination = ROOT / "data/visdrone-yolo11s.pt"
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        metadata = client.get(
            f"https://huggingface.co/api/models/{REPOSITORY}/revision/{REVISION}?blobs=true"
        )
        metadata.raise_for_status()
        data = metadata.json()
        if data["sha"] != REVISION or data["cardData"]["license"] != "agpl-3.0":
            raise ValueError("Pinned model identity/license mismatch")
        file = next(row for row in data["siblings"] if row["rfilename"] == "best.pt")
        expected = file["lfs"]["sha256"]
        if not destination.exists():
            temporary = destination.with_suffix(".download")
            received = 0
            try:
                with client.stream(
                    "GET", f"https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/best.pt"
                ) as response:
                    response.raise_for_status()
                    with temporary.open("wb") as handle:
                        for chunk in response.iter_bytes():
                            received += len(chunk)
                            if received > file["size"] or received > 100_000_000:
                                raise ValueError("Model exceeds expected download budget")
                            handle.write(chunk)
                if hashlib.sha256(temporary.read_bytes()).hexdigest() != expected:
                    raise ValueError("Model checksum mismatch")
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
        if hashlib.sha256(destination.read_bytes()).hexdigest() != expected:
            raise ValueError("Existing cached model checksum mismatch")
        record = {
            "repository": REPOSITORY,
            "revision": REVISION,
            "license": "agpl-3.0",
            "bytes": destination.stat().st_size,
            "sha256": expected,
        }
        out = ROOT / "artifacts/reality/v7"
        out.mkdir(parents=True, exist_ok=True)
        (out / "aerial-model-source.json").write_bytes(json.dumps(record, indent=2).encode())
        print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
