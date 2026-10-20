"""Bounded-memory readers for reproducible video diagnostics."""

import json
from pathlib import Path


def result_frames(path: Path):
    """Stream the top-level frames array of ATLAS's compact result serialization.

    No trajectory file is loaded into memory in full. Reject malformed/truncated
    frames rather than interpreting an incomplete result as successful processing.
    """
    decoder = json.JSONDecoder()
    marker = '"frames":['
    with path.open(encoding="utf-8") as handle:
        buffer = handle.read(65536)
        start = buffer.find(marker)
        if start < 0:
            raise ValueError("Expected compact ATLAS top-level frames array in header")
        buffer = buffer[start + len(marker) :]
        ended = False
        separator = False
        after_comma = False
        while True:
            buffer = buffer.lstrip()
            if not buffer and not ended:
                extra = handle.read(65536)
                ended = not extra
                buffer += extra
                continue
            if separator:
                if buffer.startswith("]"):
                    return
                if not buffer.startswith(","):
                    raise ValueError("Invalid result frame array separator")
                buffer = buffer[1:]
                separator = False
                after_comma = True
                continue
            if buffer.startswith("]"):
                if after_comma:
                    raise ValueError("Invalid result frame array trailing comma")
                return
            try:
                frame, offset = decoder.raw_decode(buffer)
            except json.JSONDecodeError as error:
                if ended:
                    raise ValueError("Truncated or invalid result frame array") from error
                extra = handle.read(65536)
                ended = not extra
                buffer += extra
                if len(buffer) > 16 * 1024 * 1024:
                    raise ValueError("A single frame exceeds the bounded record size") from error
                continue
            if not isinstance(frame, dict) or "index" not in frame or "objects" not in frame:
                raise ValueError("Invalid ATLAS frame")
            yield frame
            buffer = buffer[offset:]
            separator = True
