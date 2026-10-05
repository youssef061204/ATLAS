"""Pinned downloads, selective remote ZIP access, and UA-DETRAC conversion."""

import csv
import io
import json
import math
import re
import time
import zipfile
from pathlib import Path

import httpx

from atlas import config
from atlas.evaluation.artifacts import checksum

DATASETS = config.ROOT / "datasets"
DETRAC_REVISION = "72045f434a646e6dc9b04e251a4108705cdfa5bf"
DETRAC_BASE = f"https://huggingface.co/datasets/abhineet123/ua_detrac/resolve/{DETRAC_REVISION}"
DETRAC_ARCHIVES = {
    "test": ("ua_detrac_test_set.zip", 4252838102),
    "validation": ("ua_detrac_training_set.zip", 5630247258),
}
# Fixed before inference; validation cameras belong to official training data.
DETRAC_SEQUENCES = {
    "test": ["MVI_39031", "MVI_39211", "MVI_40701"],
    "validation": ["MVI_20011", "MVI_20012"],
}
METR_REVISION = "800700306275910dcfbb0ac3977c12e72e81f24a"
METR_SHA = "64784b76d6fb8ec9bff4b6decafb354da2bb37840468fdccee5044e511277c05"
RESCO_REVISION = "f1ed9a174f8de41fc9d8689373b836bc882570dc"
RESCO_SHA = {
    "cologne1.net.xml": "599eb9ca03a5fb10a754b935aa0fa3916b92f39ca175e1b6846fd2817542287a",
    "cologne1.rou.xml": "dac6aef4c6cefdfb855f47ad59e3f754b0a887e37cabfe786a520d306c0b86ae",
    "cologne1.sumocfg": "334593043b0250e5e1f1693b7d5b0277f69d99f03c771e766cfbada70fa71117",
    "LICENSE": "306b7b320c107562dd5d8a25494513f55a2f372dcbff7debac568f617785a9b6",
}


class RemoteZip(io.RawIOBase):
    """Range reads fail closed if a server ignores ranges; ZIP CRC verifies members."""

    def __init__(self, url, size):
        self.url, self.size, self.position = url, size, 0
        self.client = httpx.Client(follow_redirects=True, timeout=120)
        self.blocks = []

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        self.position = (
            offset if whence == 0 else self.position + offset if whence == 1 else self.size + offset
        )
        if self.position < 0:
            raise ValueError("Negative archive position")
        return self.position

    def fetch(self, start, end):
        for attempt in range(4):
            try:
                with self.client.stream(
                    "GET",
                    self.url + f"?atlas_range={start}-{end}",
                    headers={"Range": f"bytes={start}-{end}"},
                ) as response:
                    response.raise_for_status()
                    if (
                        response.status_code != 206
                        or response.headers.get("content-range", "")
                        != f"bytes {start}-{end}/{self.size}"
                    ):
                        raise ValueError(
                            "Source lacks valid HTTP range support; use a local archive"
                        )
                    payload = response.read()
                    if len(payload) != end - start + 1:
                        raise ValueError("Truncated archive range")
                    return payload
            except httpx.HTTPError:
                if attempt == 3:
                    raise
                time.sleep(attempt + 1)
        raise RuntimeError("Range fetch exhausted")

    def prefetch(self, start, end):
        self.blocks.append((start, self.fetch(start, end)))

    def read(self, size=-1):
        size = min(size if size >= 0 else self.size - self.position, self.size - self.position)
        if size <= 0:
            return b""
        start = self.position
        for offset, block in self.blocks:
            if offset <= start and start + size <= offset + len(block):
                value = block[start - offset : start - offset + size]
                break
        else:
            value = self.fetch(start, start + size - 1)
        self.position += len(value)
        return value

    def close(self):
        self.client.close()
        super().close()


def download_file(url, destination, expected_sha=None):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and (expected_sha is None or checksum(destination) == expected_sha):
        return
    temporary = destination.with_suffix(".download")
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=120) as response:
            response.raise_for_status()
            with temporary.open("wb") as output:
                for block in response.iter_bytes(1024 * 1024):
                    output.write(block)
        if expected_sha and checksum(temporary) != expected_sha:
            raise ValueError(f"Checksum mismatch: {destination.name}")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def parse_detrac_csv(path, frame_limit=None):
    frames = {}
    with path.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            match = re.fullmatch(r"(?:img|image)(\d+)\.jpg", row["filename"])
            if match is None:
                raise ValueError("Unexpected UA-DETRAC frame filename")
            frame = int(match[1])
            if frame_limit is not None and frame > frame_limit:
                continue
            box = [float(row[name]) for name in ["xmin", "ymin", "xmax", "ymax"]]
            if (
                not all(math.isfinite(value) for value in box)
                or box[2] <= box[0]
                or box[3] <= box[1]
            ):
                raise ValueError("Invalid UA-DETRAC box")
            item = frames.setdefault(
                frame,
                {
                    "frame": frame,
                    "filename": row["filename"],
                    "width": int(row["width"]),
                    "height": int(row["height"]),
                    "objects": [],
                    "ignored": [],
                },
            )
            if row["class"] == "ignored":
                item["ignored"].append(box)
            elif row["class"] == "vehicle":
                identity = int(row["target_id"])
                if identity <= 0:
                    raise ValueError("Vehicle IDs must be positive")
                item["objects"].append({"id": identity, "class": "vehicle", "bbox": box})
            else:
                raise ValueError(f"Unknown DETRAC mirror class: {row['class']}")
    return frames


def prepare_detrac(frame_limit=0, validation_frames=150, local_archives=None):
    root = DATASETS / "ua-detrac"
    manifest = {
        "dataset": "UA-DETRAC",
        "revision": DETRAC_REVISION,
        "fps": 25,
        "protocol": "Three predeclared complete test sequences by default; optional contiguous prefixes. Not the complete challenge test set",
        "class_mapping": "COCO car/motorcycle/bus/truck -> vehicle; mirror collapses vehicle subclasses",
        "source": "https://huggingface.co/datasets/abhineet123/ua_detrac",
        "license_note": "Mirror declares CC-BY-4.0; original author usage terms take precedence. Research evaluation only; no dataset redistribution.",
        "splits": {},
    }
    for split, sequences in DETRAC_SEQUENCES.items():
        archive, size = DETRAC_ARCHIVES[split]
        remote = None
        if local_archives:
            handle = Path(local_archives) / archive
        else:
            remote = RemoteZip(f"{DETRAC_BASE}/{archive}", size)
            handle = remote
        manifest["splits"][split] = []
        try:
            with zipfile.ZipFile(handle) as bundle:
                for sequence in sequences:
                    folder = next(
                        name for name in bundle.namelist() if name.endswith(f"{sequence}/")
                    )
                    target = root / split / sequence
                    target.mkdir(parents=True, exist_ok=True)
                    annotation = target / "annotations.csv"
                    annotation.write_bytes(bundle.read(folder + "annotations.csv"))
                    limit = (
                        (frame_limit or max(parse_detrac_csv(annotation)))
                        if split == "test"
                        else validation_frames
                    )
                    frames = parse_detrac_csv(annotation, limit)
                    names = [folder + frames[i]["filename"] for i in range(1, limit + 1)]
                    infos = [bundle.getinfo(name) for name in names]
                    if remote:
                        remote.blocks.clear()
                        start = min(i.header_offset for i in infos)
                        end = max(
                            i.header_offset
                            + 30
                            + len(i.filename.encode())
                            + len(i.extra)
                            + i.compress_size
                            + 64
                            for i in infos
                        )
                        remote.prefetch(start, min(end, size - 1))
                    for name in names:
                        (target / Path(name).name).write_bytes(bundle.read(name))
                    frames = parse_detrac_csv(annotation, limit)
                    if set(frames) != set(range(1, limit + 1)):
                        raise ValueError(f"Annotation/frame mismatch for {sequence}")
                    (target / "frames.json").write_text(
                        json.dumps(list(frames.values())), encoding="utf-8"
                    )
                    image_hashes = {
                        Path(name).name: checksum(target / Path(name).name) for name in names
                    }
                    manifest["splits"][split].append(
                        {
                            "sequence": sequence,
                            "frames": limit,
                            "annotation_sha256": checksum(annotation),
                            "image_sha256": image_hashes,
                        }
                    )
                    print(
                        f"Prepared {split}/{sequence}: {limit} contiguous real frames", flush=True
                    )
        finally:
            if remote:
                remote.close()
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def validated_detrac_frames(root, split, sequence, manifest):
    folder = root / split / sequence
    source = next(s for s in manifest["splits"][split] if s["sequence"] == sequence)
    if checksum(folder / "annotations.csv") != source["annotation_sha256"]:
        raise ValueError("Annotation checksum mismatch")
    frames = json.loads((folder / "frames.json").read_text())
    if frames != list(parse_detrac_csv(folder / "annotations.csv", len(frames)).values()):
        raise ValueError("Converted annotations differ from verified source")
    if len(frames) != source["frames"]:
        raise ValueError("Prepared frame count differs from manifest")
    for frame in frames:
        if checksum(folder / frame["filename"]) != source["image_sha256"][frame["filename"]]:
            raise ValueError("Evaluation image checksum mismatch")
    return frames


def prepare_metr():
    root = DATASETS / "metr-la"
    download_file(
        f"https://huggingface.co/datasets/MintBruce/SkyTraffic/resolve/{METR_REVISION}/metr-la.h5",
        root / "metr-la.h5",
        METR_SHA,
    )
    return root / "metr-la.h5"


def prepare_resco(scenario="cologne1"):
    checksums = (
        RESCO_SHA
        if scenario == "cologne1"
        else {
            "ingolstadt1.net.xml": "d2bc43e8168380545775bb19bc884517058f7115e228be1c8f8d9b3cfa9705e1",
            "ingolstadt1.rou.xml": "7d4a70e0eae3be87e8836a41836b256a6b0beaeb9227c30e925206fc0d856f8b",
            "ingolstadt1.sumocfg": "f6009d4bbe7a46c23be1bd9153863f1169b647d565fcc079627a26a337d080b7",
            "LICENSE": "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986",
        }
    )
    if scenario not in {"cologne1", "ingolstadt1"}:
        raise ValueError("Unsupported RESCO scenario")
    root = DATASETS / "resco" / scenario
    files = list(checksums)
    for filename in files:
        download_file(
            f"https://raw.githubusercontent.com/Pi-Star-Lab/RESCO/{RESCO_REVISION}/resco_benchmark/environments/{scenario}/{filename}",
            root / filename,
            checksums[filename],
        )
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "revision": RESCO_REVISION,
                "source": "https://github.com/Pi-Star-Lab/RESCO",
                "files": {name: checksum(root / name) for name in files},
            },
            indent=2,
        )
    )
    return root
