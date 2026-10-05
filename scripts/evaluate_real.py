"""Run every available prepared dataset; downloads are a separate action."""

import argparse
import importlib

from atlas.evaluation.data import DATASETS

EVALUATIONS = {
    "vision": ("vision", "evaluate_vision", DATASETS / "ua-detrac" / "manifest.json"),
    "forecast": ("forecasting", "evaluate_forecasting", DATASETS / "metr-la" / "metr-la.h5"),
    "signal": (
        "signal",
        "evaluate_signal_control",
        DATASETS / "resco" / "cologne1" / "manifest.json",
    ),
    "systems": ("systems", "evaluate_real_video", DATASETS / "ua-detrac" / "manifest.json"),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=["all", *EVALUATIONS], default="all")
    parser.add_argument(
        "--reuse", action="store_true", help="Reuse checksum/config-matched vision predictions"
    )
    args = parser.parse_args()
    for name, (module, function, required) in EVALUATIONS.items():
        if args.only not in {"all", name}:
            continue
        if not required.exists():
            if args.only != "all":
                raise FileNotFoundError(f"Prepare {name} data first: {required}")
            print(f"SKIPPED {name}: dataset not prepared ({required})", flush=True)
            continue
        run = getattr(importlib.import_module(f"atlas.evaluation.{module}"), function)
        result = run(reuse=args.reuse) if name == "vision" else run()
        print(f"Completed {name}" + (f": {result}" if name == "vision" else ""), flush=True)


if __name__ == "__main__":
    main()
