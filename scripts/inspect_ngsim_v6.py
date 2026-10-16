"""Inspect official public dataset structure without downloading the full table."""

import json
from pathlib import Path

import httpx


def main():
    root = Path("data/reality-v6")
    with httpx.Client(timeout=90, follow_redirects=True) as client:
        url = "https://data.transportation.gov/download/uv3e-y54k/application%2Fx-zip-compressed"
        with client.stream("GET", url, headers={"Range": "bytes=-65536"}) as response:
            print(
                "Video blob",
                response.status_code,
                response.headers.get("content-range"),
                response.headers.get("content-length"),
                flush=True,
            )
            if response.status_code == 206:
                raw = response.read()
                assert len(raw) <= 65536
                (root / "video-tail.bin").write_bytes(raw)
                print("Video directory footer", raw[-22:].hex(), flush=True)
        for query in (
            {"$select": "location,count(*)", "$group": "location"},
            {"$limit": 1, "$where": "location='lankershim'"},
        ):
            response = client.get(
                "https://data.transportation.gov/resource/8ect-6jqj.json", params=query
            )
            print(response.status_code, response.text[:2500], flush=True)
            if response.is_success:
                name = "locations.json" if "$group" in query else "sample.json"
                (root / name).write_text(json.dumps(response.json(), indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
