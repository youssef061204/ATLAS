"""Acquire the pinned MIT-licensed vehicle-specific ReID candidate for local research."""

import hashlib
import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
REVISION = "af810de42bcf460a18610481f639dcdc86249e69"
MANIFEST = f"https://raw.githubusercontent.com/openvinotoolkit/open_model_zoo/{REVISION}/models/public/vehicle-reid-0001/model.yml"
URL = "https://storage.openvinotoolkit.org/repositories/open_model_zoo/public/2022.1/vehicle-reid-0001/osnet_ain_x1_0_vehicle_reid.onnx"
SHA384 = "0515ce72f653c39780d5b87dfed7255d396dd2b1e8b6e91fbaacdfad1da189166343157273c02f3b0fede3050ef7abb7"
LICENSE_URL = "https://raw.githubusercontent.com/sovrasov/deep-person-reid/vehicle_reid/LICENSE"
LICENSE_SHA256 = "3ac8ce2a83d170cb1c7c84152e0c1faca1f187794303514383960d2441716247"


def main():
    out = ROOT / "data/reality-v7/vehicle-reid-0001"
    out.mkdir(parents=True, exist_ok=True)
    model = out / "osnet_ain_x1_0_vehicle_reid.onnx"
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        metadata = client.get(MANIFEST)
        metadata.raise_for_status()
        if SHA384 not in metadata.text or URL not in metadata.text:
            raise ValueError("Pinned official model manifest mismatch")
        license = client.get(LICENSE_URL)
        license.raise_for_status()
        if hashlib.sha256(license.content).hexdigest() != LICENSE_SHA256:
            raise ValueError("Reviewed model license changed")
        if not model.exists():
            temporary = model.with_suffix(".download")
            try:
                with client.stream("GET", URL) as response, temporary.open("wb") as handle:
                    response.raise_for_status()
                    for block in response.iter_bytes(65536):
                        handle.write(block)
                        if handle.tell() > 8836743:
                            raise ValueError("Model exceeds pinned byte budget")
                if (
                    temporary.stat().st_size != 8836743
                    or hashlib.sha384(temporary.read_bytes()).hexdigest() != SHA384
                ):
                    raise ValueError("Pinned model checksum mismatch")
                temporary.replace(model)
            finally:
                temporary.unlink(missing_ok=True)
        if (
            model.stat().st_size != 8836743
            or hashlib.sha384(model.read_bytes()).hexdigest() != SHA384
        ):
            raise ValueError("Cached model checksum mismatch")
        (out / "model.yml").write_bytes(metadata.content)
        (out / "LICENSE.txt").write_bytes(license.content)
    print(
        json.dumps(
            {
                "model": model.name,
                "sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
                "license": "MIT, reviewed exact license hash",
                "scope": "Local vehicle-specific ReID research; no source CityFlow data or descriptors redistributed",
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
