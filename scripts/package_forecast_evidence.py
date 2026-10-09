"""Preserve full measured forecasting previews; ship a fixed small UI subset."""

import gzip
import json
from pathlib import Path


def main():
    path = Path("artifacts/cities/forecast-v3.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not data.get("preview_archive"):
        full = json.dumps(data["preview"], allow_nan=False).encode()
        packed = gzip.compress(full, mtime=0)
        if gzip.decompress(packed) != full:
            raise ValueError("Preview archive verification failed")
        path.with_name("forecast-v3-preview.json.gz").write_bytes(packed)
        sensors = list(dict.fromkeys(p["sensor"] for p in data["preview"]))[:4]
        data["preview"] = [p for p in data["preview"] if p["sensor"] in sensors]
        data["preview_selection"] = (
            "first four sensors in original source order; first 288 chronological test origins"
        )
        data["preview_archive"] = "forecast-v3-preview.json.gz"
        path.write_text(json.dumps(data, allow_nan=False), encoding="utf-8")
    print("UI forecast evidence:", path.stat().st_size, "bytes; full all-sensor previews archived")


if __name__ == "__main__":
    main()
