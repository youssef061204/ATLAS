"""Fetch only documented Lankershim rows from the official, public Socrata API."""

import gzip
import hashlib
import json
import time
from pathlib import Path

import httpx

FIELDS = "vehicle_id,frame_id,global_time,local_x,local_y,global_x,global_y,v_length,v_width,v_class,v_vel,v_acc,lane_id,o_zone,d_zone,int_id,section_id,direction,movement"


def main():
    root = Path("data/reality-v6/trajectory-pages")
    root.mkdir(parents=True, exist_ok=True)
    records = []
    with httpx.Client(timeout=120) as client:
        for offset in range(0, 1_607_319, 50_000):
            path = root / f"rows-{offset:07d}.csv.gz"
            params = {
                "$select": FIELDS,
                "$where": "location='lankershim'",
                "$order": "global_time,vehicle_id",
                "$limit": 50000,
                "$offset": offset,
            }
            if not path.exists():
                response = client.get(
                    "https://data.transportation.gov/resource/8ect-6jqj.csv", params=params
                )
                response.raise_for_status()
                assert len(response.content) < 30_000_000 and response.content.startswith(
                    b'"vehicle_id"'
                )
                path.write_bytes(gzip.compress(response.content, mtime=0))
                time.sleep(1)
            records.append(
                {
                    "file": path.name,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "offset": offset,
                    "query": params,
                }
            )
            print(path.name, path.stat().st_size, flush=True)
    (root.parent / "trajectory-acquisition.json").write_text(
        json.dumps(
            {
                "source": "https://data.transportation.gov/resource/8ect-6jqj.csv",
                "license": "https://creativecommons.org/licenses/by-sa/3.0/",
                "raw_redistribution": False,
                "pages": records,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
