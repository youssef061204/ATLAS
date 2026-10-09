"""Losslessly compress bulky research traces, keeping compact web metadata separate."""

import gzip
import hashlib
import json
from pathlib import Path


def main():
    root = Path("artifacts/cities")
    scratch = Path("data/research-evidence-uncompressed")
    scratch.mkdir(parents=True, exist_ok=True)
    entries = []
    for name in (
        "five-city-nominal.json",
        "transfer.json",
        "experiments-initial-smoke.json",
        "transfer-initial-prototype.json",
        "transfer-interrupted-diagnostic.json",
        "resilience.json",
    ):
        path = root / name
        compressed = Path(str(path) + ".gz")
        raw = path.read_bytes() if path.exists() else gzip.decompress(compressed.read_bytes())
        packed = gzip.compress(raw, compresslevel=9, mtime=0)
        if gzip.decompress(packed) != raw:
            raise ValueError("Lossless archive verification failed")
        compressed.write_bytes(packed)
        entries.append(
            {
                "source": name,
                "published": compressed.name,
                "uncompressed_bytes": len(raw),
                "compressed_bytes": len(packed),
                "uncompressed_sha256": hashlib.sha256(raw).hexdigest(),
                "archive_sha256": hashlib.sha256(packed).hexdigest(),
            }
        )
        if path.exists():
            # Move within known workspace directories; retain scratch for local analysis.
            path.replace(scratch / name)
    root.joinpath("evidence-archives.json").write_text(
        json.dumps(
            {"format": "gzip, JSON; exact original traces retained", "archives": entries}, indent=2
        ),
        encoding="utf-8",
    )
    print(
        "Verified",
        len(entries),
        "lossless archives;",
        sum(e["uncompressed_bytes"] for e in entries),
        "bytes reduced to",
        sum(e["compressed_bytes"] for e in entries),
    )


if __name__ == "__main__":
    main()
