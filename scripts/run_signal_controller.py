"""Run the selected ATLAS feedback controller in actual local SUMO; never tune."""

import argparse

from atlas.evaluation.signal_lab import run
from atlas.signal_runtime import selected_profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=5001)
    parser.add_argument("--scenario", choices=["cologne1", "ingolstadt1"], default="cologne1")
    parser.add_argument("--fresh", action="store_true")
    args = parser.parse_args()
    result = run(
        "atlas_improved",
        args.seed,
        begin=27000 if args.scenario == "cologne1" else 57600,
        scenario=args.scenario,
        settings=selected_profile(),
        reuse=not args.fresh,
    )
    print(result["metrics"])


if __name__ == "__main__":
    main()
