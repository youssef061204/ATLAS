import json
from pathlib import Path

from atlas.cities import FeedClient
from atlas.traffic_context import inspect_context

if __name__ == "__main__":
    client = FeedClient(min_interval=1)
    try:
        report = inspect_context(client)
        Path("artifacts/cities/traffic-context.json").write_text(
            json.dumps(report, allow_nan=False), encoding="utf-8"
        )
        print([(c["city"], c["status"], len(c["events"])) for c in report["cities"]])
        print(
            "Regional weather observations:",
            sum(w["status"] == "available" for w in report["weather"]),
        )
    finally:
        client.close()
