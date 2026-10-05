"""Regenerate the landing-page preview from the seeded portable simulator."""

import json
from pathlib import Path

from atlas.schemas import SimulationConfig
from atlas.simulation import simulate

preview = simulate(SimulationConfig(duration=90), "baseline")
path = Path(__file__).resolve().parents[1] / "frontend/public/preview.json"
path.write_text(json.dumps(preview["frames"], separators=(",", ":")), encoding="utf-8")
print(f"Prepared {len(preview['frames'])} seeded simulation frames: {path}")
