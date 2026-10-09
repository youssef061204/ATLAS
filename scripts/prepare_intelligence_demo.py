"""Execute the complete observation-conditioned pair, then package actual outputs."""

import json
from pathlib import Path

from atlas import config
from atlas.intelligence import execute_pair


def main():
    context = json.loads(
        (config.ARTIFACTS / "cities/toronto-intelligence.json").read_text(encoding="utf-8")
    )
    result = execute_pair(
        "toronto",
        context["observation"],
        {"residence_seconds": 60, "corridor_multiplier": 1, "acknowledge_exploratory": True},
        21001,
    )
    result["camera"] = context["camera"]
    result["alignment"] = context["alignment"]
    result["historical_detector_fusion"] = context["detector_fusion"]
    path = Path(config.DATA / "toronto-golden-path.json")
    path.write_text(json.dumps(result, allow_nan=False), encoding="utf-8")
    print(
        "Actual observation-to-simulation pair saved",
        result["id"],
        result["comparison"],
        flush=True,
    )


if __name__ == "__main__":
    main()
