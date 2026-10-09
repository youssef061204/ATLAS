import argparse
import json
from pathlib import Path

from atlas.cities import city_configs, now
from atlas.city_network import generate


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--city", choices=[*city_configs(), "all"], default="all")
    p.add_argument("--seed", type=int, default=12001)
    p.add_argument("--duration", type=int, default=600)
    p.add_argument("--period", type=float, default=4)
    p.add_argument("--download", action="store_true")
    args = p.parse_args()
    reports = []
    for city in city_configs() if args.city == "all" else [args.city]:
        try:
            report = generate(city, args.seed, args.duration, args.period, args.download)
            print(
                city,
                len(report["roads"]),
                "roads",
                len(report["signals"]),
                "signals",
                report["scheduled"],
                "routed vehicles",
                flush=True,
            )
            reports.append(report)
        except Exception as exc:
            reports.append({"city": city, "mode": "blocked", "reason": str(exc)})
            print(city, "blocked:", exc, flush=True)
    path = Path("artifacts/cities/networks.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    if args.city != "all" and path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))["networks"]
        reports = [item for item in previous if item["city"] != args.city] + reports
    path.write_text(
        json.dumps({"recorded_at": now(), "networks": reports}, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
