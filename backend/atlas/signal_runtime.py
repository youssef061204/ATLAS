"""Load the validation-frozen production policy without implicit tuning."""

import json
from pathlib import Path

from atlas import config
from atlas.control import ControlConfig
from atlas.evaluation.artifacts import checksum


def selected_profile(path: Path | None = None) -> ControlConfig:
    profile = json.loads(
        (path or config.ROOT / "docs/signal-controller-frozen.json").read_text(encoding="utf-8")
    )
    if not profile.get("frozen_before_test") or profile["controller_sha256"] != checksum(
        config.ROOT / "backend/atlas/control.py"
    ):
        raise ValueError("Frozen controller profile does not match the runtime source")
    return ControlConfig(**profile["settings"])
