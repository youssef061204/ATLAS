"""Independent new transfer comparison; never edits historical artifacts."""

import argparse
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from atlas import config
from atlas.city_network import binary, sha
from atlas.evaluation.network_v2 import run_network
from atlas.evaluation.signal import build_period


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--seeds", type=int, default=5)
    p.add_argument("--start", type=int, default=34001)
    p.add_argument("--output", type=Path, default=Path("artifacts/cities/transfer.json"))
    args = p.parse_args()
    runs = []
    for city, begin in (("cologne1", 27000), ("ingolstadt1", 57600)):
        source = config.ROOT / "datasets/resco" / city
        root = config.ROOT / "datasets/cities" / (city + "-reference")
        root.mkdir(parents=True, exist_ok=True)
        net = root / "network.net.xml"
        shutil.copyfile(source / f"{city}.net.xml", net)
        for seed in range(args.start, args.start + args.seeds):
            period, routed = root / "period.xml", root / f"routes-{seed}.xml"
            build_period(source / f"{city}.rou.xml", period, begin, 1800)
            subprocess.run(
                [
                    binary("duarouter"),
                    "--net-file",
                    str(net),
                    "--route-files",
                    str(period),
                    "--output-file",
                    str(routed),
                    "--seed",
                    str(seed),
                    "--no-step-log",
                    "true",
                ],
                check=True,
                capture_output=True,
            )
            tree = ET.parse(routed)
            tree.write(routed, encoding="utf-8", xml_declaration=True)
            manifest = {
                "network_sha256": sha(net),
                "routes_sha256": sha(routed),
                "seed": seed,
                "duration": 1800,
                "period": 1,
                "sumo_version": subprocess.check_output(
                    [binary("sumo"), "--version"], text=True
                ).splitlines()[0],
                "calibration": {
                    "status": "Published RESCO demand",
                    "source": json.loads((source / "manifest.json").read_text(encoding="utf-8")),
                    "begin": begin,
                },
            }
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            for policy in ("fixed", "max_pressure", "original_mpc", "risk_mpc"):
                runs.append(run_network(city, policy, seed, 1800, root=root, routes=routed))
                args.output.write_text(
                    json.dumps(
                        {
                            "scope": "New unchanged zero-shot prototype comparison; native platform numerical drift remains a limitation",
                            "runs": runs,
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )


if __name__ == "__main__":
    main()
