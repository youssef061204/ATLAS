"""Run the opt-in CV birth policy on complete footage and score known regression."""

from pathlib import Path

import ablate_edge_end_speed_cap_v8 as trial

ROOT = Path(__file__).resolve().parents[1]


def main():
    trial.BASE = ROOT / "data/reality-v7/eager-insertion/duration-1122"
    trial.TARGET = ROOT / "data/reality-v8/no-edge-end-speed-cap-cv-full-1122"
    trial.PUBLIC = ROOT / "artifacts/reality/v8/edge-end-speed-cap-known-regression.json"
    trial.START = 600
    trial.END = 1000
    trial.RUN_END = 1122
    trial.SOURCE_SCOPE = (
        "Already exposed 600–1000 s known regression only; no fresh holdout. "
        "CV births only and independent annotations used solely for post-run scoring."
    )
    trial.main()


if __name__ == "__main__":
    main()
