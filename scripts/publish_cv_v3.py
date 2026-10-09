"""Publish actual candidate tradeoffs, preserving frozen original CV artifacts."""

import json
from pathlib import Path

from atlas.city_network import sha


def main():
    root = Path("artifacts/cv-v3/benchmarks")
    sources = {}

    def read(path):
        sources[str(path).replace("\\", "/")] = sha(path)
        return json.loads(path.read_text(encoding="utf-8"))

    old = {
        kind: read(Path(f"artifacts/benchmarks/real_{name}.json"))
        for kind, name in [
            ("detection", "detection"),
            ("tracking", "tracking"),
            ("stage_performance", "video_systems"),
        ]
    }
    new = {
        kind: read(root / f"real_{name}_test_yolo26n-v3.json")
        for kind, name in [
            ("detection", "detection"),
            ("tracking", "tracking"),
            ("stage_performance", "video_systems"),
        ]
    }
    result = {
        "experiment_id": "detrac-yolo26n-v3-01",
        "original": {k: v["metrics"] for k, v in old.items()},
        "candidate": {k: v["metrics"] for k, v in new.items()},
        "hardware": new["detection"]["hardware"],
        "sequences": new["detection"]["split"],
        "provenance": "UA-DETRAC original predeclared test cameras; pretrained models; same unchanged evaluation harness",
        "promotion": "Retain YOLO11n by default: candidate has slightly lower mAP@50, recall, IDF1 and HOTA, despite fewer identity switches and higher measured detector/tracker stage FPS",
        "performance_scope": "Separate developer-host runs, not repeated isolated latency trials; detector/tracker stage only, not complete pipeline FPS",
        "source_sha256": sources,
        "limits": [
            "No independently annotated city-camera or pedestrian/cyclist/emergency accuracy",
            "No weather/low-light subgroup evaluation",
            "No visual queue calibration",
            "Accuracy-speed tradeoff, not unconditional candidate superiority",
        ],
    }
    Path("artifacts/cities/vision-v3.json").write_text(
        json.dumps(result, allow_nan=False), encoding="utf-8"
    )
    print("Published CV candidate tradeoffs; original remains default")


if __name__ == "__main__":
    main()
