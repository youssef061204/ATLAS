"""Restore checksum-pinned redistributable small OSM scenarios without a download."""

import gzip
import json
import shutil
from pathlib import Path

from atlas.cities import city_configs
from atlas.city_network import sha


def main():
    for city in city_configs():
        source = Path("artifacts/cities/scenarios") / city
        root = Path("datasets/cities") / city
        root.mkdir(parents=True, exist_ok=True)
        manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
        for name in ("source.osm.xml", "network.net.xml"):
            root.joinpath(name).write_bytes(
                gzip.decompress(source.joinpath(name + ".gz").read_bytes())
            )
        shutil.copyfile(
            source / "routes.xml",
            root / f"routes-{manifest['seed']}-{manifest['duration']}-{manifest['period']}.xml",
        )
        for name in ("manifest.json", "source.json"):
            shutil.copyfile(source / name, root / name)
        if (
            sha(root / "network.net.xml") != manifest["network_sha256"]
            or sha(source / "routes.xml") != manifest["routes_sha256"]
            or sha(root / "source.osm.xml") != manifest["source"]["sha256"]
        ):
            raise ValueError("Pinned city scenario checksum mismatch")
        print(city, "restored and verified", flush=True)


if __name__ == "__main__":
    main()
