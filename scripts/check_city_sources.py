"""Read official catalogs and bounded image samples; retain aggregate data only."""

import argparse
import json
from pathlib import Path

from atlas.cities import FeedClient, SnapshotPerception, city_configs, inspect_city, now


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--city", choices=[*city_configs(), "all"], default="all")
    p.add_argument("--samples", type=int, choices=range(1, 4), default=2)
    p.add_argument("--perception", action="store_true")
    p.add_argument("--output", type=Path, default=Path("artifacts/cities/source-health.json"))
    args = p.parse_args()
    detector = SnapshotPerception() if args.perception else None
    client = FeedClient()
    try:
        reports = [
            inspect_city(city, client, detector, args.samples)
            for city in (city_configs() if args.city == "all" else [args.city])
        ]
    finally:
        client.close()
    payload = {
        "schema_version": "atlas-city-health-2.0",
        "recorded_at": now(),
        "mode": "recorded_official_source_check",
        "cities": reports,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
    for city in reports:
        print(city["city"], city["status"], len(city["cameras"]), "cameras", city["image_checks"])


if __name__ == "__main__":
    main()
