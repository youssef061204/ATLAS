"""Derive compact public evidence without altering any measured benchmark values."""

import json
from pathlib import Path

from atlas.evidence_v4 import (
    CITIES,
    benchmark_summary,
    city_summary,
    control_assessment,
    control_replay,
)


def main():
    out = Path("artifacts/cities/v4")
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(
        json.dumps(benchmark_summary(), indent=2, allow_nan=False), encoding="utf-8"
    )
    for city in CITIES:
        (out / f"evidence-{city}.json").write_text(
            json.dumps(city_summary(city), indent=2, allow_nan=False), encoding="utf-8"
        )
    replay = control_replay()
    if replay:
        (out / "controller-replay.json").write_text(
            json.dumps(replay, separators=(",", ":"), allow_nan=False), encoding="utf-8"
        )
    assessment = control_assessment()
    if assessment:
        (out / "controller-assessment.json").write_text(
            json.dumps(assessment, separators=(",", ":"), allow_nan=False), encoding="utf-8"
        )
    print("Derived compact benchmark summary and five provenance-aware city responses")


if __name__ == "__main__":
    main()
