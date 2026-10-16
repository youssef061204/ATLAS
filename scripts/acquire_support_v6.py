"""Retrieve intact FHWA geometry/timing packages from a public DOT catalog copy."""

import hashlib
import json
import zipfile
from pathlib import Path

import httpx
from acquire_video_v6 import RangeReader

URL = "https://data.transportation.gov/api/views/h35x-vs8r/files/0bfd5672-08e8-4a89-929f-10ecf25bad22?download=true"
OUT = Path(__file__).resolve().parents[1] / "data/reality-v6/support"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        with zipfile.ZipFile(RangeReader(client, URL, 144875847)) as archive:
            for info in archive.infolist():
                if "aerial-ortho" in info.filename:
                    continue
                destination = OUT / Path(info.filename).name
                if not destination.exists() or destination.stat().st_size != info.file_size:
                    temporary = destination.with_suffix(".part")
                    with archive.open(info) as source, temporary.open("wb") as target:
                        while block := source.read(1024 * 1024):
                            target.write(block)
                    if temporary.stat().st_size != info.file_size:
                        raise ValueError("Incomplete support archive")
                    temporary.replace(destination)
                with zipfile.ZipFile(destination) as nested:
                    bad = nested.testzip()
                    if bad is not None:
                        raise ValueError(f"Invalid source CRC: {bad}")
                    for member in nested.infolist():
                        target = (OUT / member.filename).resolve()
                        if (
                            not target.is_relative_to(OUT.resolve())
                            or member.file_size > 100_000_000
                        ):
                            raise ValueError("Unsafe nested source member")
                        if not member.is_dir() and target.name.lower() != "thumbs.db":
                            target.parent.mkdir(parents=True, exist_ok=True)
                            with nested.open(member) as source, target.open("wb") as output:
                                while block := source.read(1024 * 1024):
                                    output.write(block)
                    names = nested.namelist()
                with destination.open("rb") as handle:
                    digest = hashlib.file_digest(handle, "sha256").hexdigest()
                records.append(
                    {
                        "file": destination.name,
                        "sha256": digest,
                        "bytes": destination.stat().st_size,
                        "members": names,
                        "zip_crc_verified": True,
                    }
                )
                print(destination.name, len(names), "members", flush=True)
    (OUT / "acquisition.json").write_text(
        json.dumps(
            {
                "url": URL,
                "attribution": "FHWA NGSIM, June 16 2005 Lankershim Boulevard",
                "raw_redistribution": False,
                "assets": records,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
