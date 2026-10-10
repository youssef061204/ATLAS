"""Native worker adapter: preserve frozen simulation, qualify unavailable telemetry."""

import hashlib
import json
import math
import types
from pathlib import Path

from atlas.evaluation import network_v4


def sanitize(value, unavailable, path=""):
    if isinstance(value, float) and not math.isfinite(value):
        if not path.startswith("trace"):
            raise ValueError(f"Non-finite measured outcome: {path}")
        unavailable[path] = repr(value)
        return None
    if isinstance(value, dict):
        return {
            key: sanitize(item, unavailable, f"{path}.{key}" if path else key)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize(item, unavailable, f"{path}[{index}]") for index, item in enumerate(value)]
    return value


def run_network(*args, **kwargs):
    """Called only inside an isolated native simulation worker process."""
    unavailable = {}
    original_json = network_v4.json

    def dump(value, **options):
        return json.dumps(sanitize(value, unavailable), **options)

    network_v4.json = types.SimpleNamespace(loads=json.loads, dumps=dump)
    try:
        result = network_v4.run_network(*args, **kwargs)
    finally:
        network_v4.json = original_json
    result = sanitize(result, unavailable)
    result["telemetry"] = {
        "adapter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "unavailable_fields": unavailable,
        "scope": "Unavailable replay coordinates are omitted from maps. Non-finite measured outcomes fail; controller and simulator physics remain unchanged.",
    }
    return result
