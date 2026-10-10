"""Acquire OFL-licensed, versioned Google font assets for offline frontend builds."""

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import httpx


def main():
    output = Path("frontend/public/fonts")
    output.mkdir(parents=True, exist_ok=True)
    manifest = output / "sources.json"
    if manifest.exists():
        value = json.loads(manifest.read_bytes())
        for asset in value["assets"]:
            assert (
                hashlib.sha256((output / asset["file"]).read_bytes()).hexdigest() == asset["sha256"]
            )
        print("Verified pinned local font assets")
        return
    assets = []
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    with httpx.Client(timeout=20, headers={"User-Agent": user_agent}) as client:
        for family, slug, weight in (
            ("DM Sans", "dmsans", "400..700"),
            ("Space Grotesk", "spacegrotesk", "400..700"),
            ("IBM Plex Mono", "ibmplexmono", "400;500"),
        ):
            url = (
                "https://fonts.googleapis.com/css2?family="
                + family.replace(" ", "+")
                + ":wght@"
                + weight
                + "&display=swap"
            )
            response = client.get(url)
            response.raise_for_status()
            found = []
            for block in response.text.split("/* latin */")[1:]:
                match = re.search(r"url\((https://[^)]+\.woff2)\)", block)
                assert match is not None
                resource = match.group(1)
                assert urlparse(resource).hostname == "fonts.gstatic.com"
                if resource not in found:
                    found.append(resource)
            assert len(found) == (2 if slug == "ibmplexmono" else 1), found
            for i, resource in enumerate(found):
                filename = slug + (f"-{400 + 100 * i}" if slug == "ibmplexmono" else "") + ".woff2"
                raw = client.get(resource)
                raw.raise_for_status()
                assert raw.content[:4] == b"wOF2" and len(raw.content) < 200_000
                (output / filename).write_bytes(raw.content)
                assets.append(
                    {
                        "file": filename,
                        "source": resource,
                        "sha256": hashlib.sha256(raw.content).hexdigest(),
                        "license": "SIL Open Font License 1.1",
                    }
                )
            license_url = f"https://raw.githubusercontent.com/google/fonts/main/ofl/{slug}/OFL.txt"
            license_response = client.get(license_url)
            license_response.raise_for_status()
            assert "SIL OPEN FONT LICENSE" in license_response.text
            filename = slug + "-OFL.txt"
            (output / filename).write_bytes(license_response.content)
            assets.append(
                {
                    "file": filename,
                    "source": license_url,
                    "sha256": hashlib.sha256(license_response.content).hexdigest(),
                    "license": "SIL Open Font License 1.1",
                }
            )
    manifest.write_text(
        json.dumps(
            {
                "assets": assets,
                "scope": "Versioned original Latin font files, unmodified, retained OFL licenses. Local Next.js font loading removes external runtime font requests.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("Acquired four small WOFF2 files and three OFL licenses")


if __name__ == "__main__":
    main()
