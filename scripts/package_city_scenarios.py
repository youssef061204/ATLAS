"""Package small ODbL research corridors, never source camera imagery."""

import gzip
import json
import shutil
from pathlib import Path

from atlas.cities import city_configs
from atlas.city_network import sha


def main():
    target = Path("artifacts/cities/scenarios")
    for city in city_configs():
        root = Path("datasets/cities") / city
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        out = target / city
        out.mkdir(parents=True, exist_ok=True)
        for name in ("source.osm.xml", "network.net.xml"):
            with (out / (name + ".gz")).open("wb") as f:
                f.write(gzip.compress((root / name).read_bytes(), mtime=0))
        source_routes = next(
            p for p in root.glob("routes-*.xml") if sha(p) == manifest["routes_sha256"]
        )
        shutil.copyfile(source_routes, out / "routes.xml")
        shutil.copyfile(root / "manifest.json", out / "manifest.json")
        shutil.copyfile(root / "source.json", out / "source.json")
        (out / "ATTRIBUTION.txt").write_text(
            "© OpenStreetMap contributors. ODbL 1.0: https://www.openstreetmap.org/copyright\nSUMO-converted exploratory map; synthetic assumed demand. Not an agency signal plan or calibrated city model.\n",
            encoding="utf-8",
        )
        print(city, "pinned network", manifest["network_sha256"][:12], flush=True)


if __name__ == "__main__":
    main()
