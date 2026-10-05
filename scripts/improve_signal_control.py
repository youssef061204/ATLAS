"""Reproduce the predeclared controller study, without implicit dataset downloads."""

import argparse

from atlas.evaluation import signal_study as study


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        choices=[
            "audit",
            "train",
            "validate",
            "final",
            "ablations",
            "generalize",
            "publish",
            "all",
        ],
        default="all",
    )
    args = parser.parse_args()
    tasks = {
        "audit": study.audit,
        "train": study.train,
        "validate": study.validate,
        "final": study.final,
        "ablations": study.ablate,
        "generalize": study.generalize,
        "publish": study.publish_search,
    }
    for name, task in tasks.items():
        if args.stage in {name, "all"}:
            task()


if __name__ == "__main__":
    main()
