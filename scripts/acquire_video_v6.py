"""Read public FHWA ZIP64 directory and acquire a complete selected member locally."""

import argparse
import hashlib
import io
import json
import time
import zipfile
from pathlib import Path

import httpx

URL = "https://data.transportation.gov/download/uv3e-y54k/application%2Fx-zip-compressed"
OUT = Path(__file__).resolve().parents[1] / "data/reality-v6"


class RangeReader(io.RawIOBase):
    """Seekable public HTTP resource; reject ignored or incorrect range responses."""

    def __init__(self, client, url, size):
        self.client, self.url, self.size, self.position = client, url, size, 0
        self.transferred = 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        if whence not in (0, 1, 2):
            raise ValueError("Invalid seek origin")
        position = offset + (0 if whence == 0 else self.position if whence == 1 else self.size)
        if position < 0:
            raise ValueError("Negative resource position")
        self.position = position
        return position

    def read(self, size=-1):
        if size < 0:
            size = self.size - self.position
        size = min(size, self.size - self.position)
        if size <= 0:
            return b""
        if size > 8 * 1024 * 1024:
            raise ValueError("Read exceeds bounded acquisition chunk")
        start, end = self.position, self.position + size - 1
        for attempt in range(3):
            try:
                raw = self._range(start, end, size)
                break
            except (httpx.TransportError, httpx.HTTPStatusError) as error:
                if isinstance(error, httpx.HTTPStatusError) and error.response.status_code not in (
                    429,
                    500,
                    502,
                    503,
                    504,
                ):
                    raise
                if attempt == 2:
                    raise
                time.sleep(2**attempt)
        if len(raw) != size:
            raise ValueError("Incomplete range")
        self.position += size
        self.transferred += size
        return raw

    def _range(self, start, end, size):
        with self.client.stream(
            "GET",
            self.url,
            headers={"Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"},
        ) as response:
            response.raise_for_status()
            if (
                response.status_code != 206
                or response.headers.get("content-range") != f"bytes {start}-{end}/{self.size}"
            ):
                raise ValueError(
                    f"Invalid range response: {response.status_code} {response.headers.get('content-range')}"
                )
            chunks, received = [], 0
            for chunk in response.iter_bytes():
                received += len(chunk)
                if received > size:
                    raise ValueError("Range body exceeds declared size")
                chunks.append(chunk)
            raw = b"".join(chunks)
        return raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--member", help="Exact member from published archive directory")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        metadata_path = OUT / "uv3e-y54k-metadata.json"
        if not metadata_path.exists():
            response = client.get("https://data.transportation.gov/api/views/uv3e-y54k.json")
            response.raise_for_status()
            if len(response.content) > 2_000_000:
                raise ValueError("Oversized source catalog")
            metadata_path.write_text(json.dumps(response.json(), indent=2), encoding="utf-8")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if "creativecommons.org/licenses/by-sa/4.0" not in metadata.get("license", {}).get(
            "termsLink", ""
        ):
            raise ValueError("Video catalog license changed; review before acquiring")
        size = int(metadata["blobFileSize"])
        resource = RangeReader(client, URL, size)
        with zipfile.ZipFile(resource) as archive:
            members = [
                {
                    "name": i.filename,
                    "bytes": i.file_size,
                    "compressed_bytes": i.compress_size,
                    "crc32": f"{i.CRC:08x}",
                }
                for i in archive.infolist()
            ]
            (OUT / "video-directory.json").write_text(
                json.dumps(members, indent=2), encoding="utf-8"
            )
            if not args.member:
                print(json.dumps(members, indent=2), flush=True)
                return
            info = archive.getinfo(args.member)
            if (
                info.file_size > 3_000_000_000
                or info.is_dir()
                or not info.filename.lower().endswith(".avi")
            ):
                raise ValueError(
                    "Selected member exceeds the 3 GB local acquisition budget or is a directory"
                )
            destination = OUT / Path(info.filename).name
            record_path = destination.with_suffix(destination.suffix + ".source.json")
            if destination.exists() and record_path.exists():
                previous = json.loads(record_path.read_text(encoding="utf-8"))
                with destination.open("rb") as handle:
                    digest = hashlib.file_digest(handle, "sha256").hexdigest()
                if (
                    previous.get("url") == URL
                    and previous.get("member") == info.filename
                    and previous.get("bytes") == info.file_size == destination.stat().st_size
                    and previous.get("crc32") == f"{info.CRC:08x}"
                    and previous.get("zip_crc_verified") is True
                    and previous.get("sha256") == digest
                ):
                    print("Verified existing complete member", destination.name, digest, flush=True)
                    return
            temporary = destination.with_suffix(destination.suffix + ".part")
            digest, count = hashlib.sha256(), 0
            with archive.open(info) as source, temporary.open("wb") as target:
                while block := source.read(1024 * 1024):
                    target.write(block)
                    digest.update(block)
                    count += len(block)
                    if count % (32 * 1024 * 1024) == 0:
                        print(f"{count}/{info.file_size} bytes", flush=True)
            if count != info.file_size:
                raise ValueError("Incomplete archive member")
            temporary.replace(destination)
            record = {
                "url": URL,
                "member": info.filename,
                "file": destination.name,
                "bytes": count,
                "sha256": digest.hexdigest(),
                "crc32": f"{info.CRC:08x}",
                "zip_crc_verified": True,
                "license": metadata.get("license"),
                "raw_redistribution": False,
            }
            record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
            print(json.dumps(record, indent=2), flush=True)


if __name__ == "__main__":
    main()
