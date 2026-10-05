import argparse

from atlas.evaluation.data import prepare_detrac, prepare_metr, prepare_resco

parser = argparse.ArgumentParser(
    description="Prepare pinned research datasets without redistributing them"
)
parser.add_argument("--only", choices=["all", "detrac", "metr", "resco"], default="all")
parser.add_argument(
    "--frames", type=int, default=0, help="Test prefix length; 0 uses complete selected sequences"
)
parser.add_argument("--validation-frames", type=int, default=150)
parser.add_argument("--resco-scenario", choices=["cologne1", "ingolstadt1"], default="cologne1")
parser.add_argument(
    "--local-archives", help="Directory with locally acquired UA-DETRAC mirror ZIP files"
)
args = parser.parse_args()
if args.frames < 0 or args.validation_frames < 1:
    parser.error("Test frame count must be nonnegative and validation count positive")
if args.only in {"all", "detrac"}:
    prepare_detrac(args.frames, args.validation_frames, args.local_archives)
if args.only in {"all", "metr"}:
    print("Prepared", prepare_metr(), flush=True)
if args.only in {"all", "resco"}:
    print("Prepared", prepare_resco(args.resco_scenario), flush=True)
