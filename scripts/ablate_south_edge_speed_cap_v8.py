"""Repeat the CV edge-end speed-cap ablation on northbound S_in births only."""

from pathlib import Path

import ablate_edge_end_speed_cap_v8 as trial

ROOT = Path(__file__).resolve().parents[1]


def main():
    trial.ALLOWED_EDGES = {"S_in"}
    trial.TARGET = ROOT / "data/reality-v8/no-south-edge-speed-cap-cv-development"
    trial.PUBLIC = ROOT / "artifacts/reality/v8/south-edge-speed-cap-ablation-development.json"
    trial.main()


if __name__ == "__main__":
    main()
