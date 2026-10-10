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
    qualify_vehicle_metrics(result)
    result["telemetry"] = {
        "adapter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "unavailable_fields": unavailable,
        "scope": "Unavailable replay coordinates are omitted from maps. Non-finite measured outcomes fail; controller and simulator physics remain unchanged.",
    }
    return result


def qualify_vehicle_metrics(result):
    """SUMO invalid vehicle subscriptions can corrupt integrated mass/stop totals."""
    metrics = result["metrics"]
    invalid = {
        key: metrics[key]
        for key in ("co2_model_kg", "fuel_model_kg")
        if metrics.get(key, 0) is not None and metrics.get(key, 0) < 0
    }
    if invalid:
        result["measurement_quality"] = {
            "invalid_recorded_values": invalid,
            "unavailable_fields": ["co2_model_kg", "fuel_model_kg", "stops_per_vehicle"],
            "scope": "Invalid vehicle subscription sentinels contaminate integrated emissions and potentially stops. Traffic delay/completion come from SUMO trip outputs; lane queues and signal safety are separate. No corrected mass or stop estimate is invented.",
        }
        for key in result["measurement_quality"]["unavailable_fields"]:
            metrics[key] = None
