"""Account for every independently observed state in a native replay.

The categories are mutually exclusive. Reference identities are used only to
score completed runs; no reference state is fed back to a CV-driven simulator.
"""

from collections import Counter
from math import dist


def state_attribution(mapping, reference, native, start_s, end_s, gate_m=4.0):
    """Explain reference-state attrition without changing the v7 scoring cohort."""
    counts = Counter()
    vehicles = {
        key: set()
        for key in (
            "no_cv_birth_association",
            "before_cv_birth",
            "native_vehicle_absent",
            "native_present_outside_gate",
            "native_present_within_gate",
        )
    }
    for second in range(start_s, end_s):
        predicted = {str(row["id"]): row for row in native.get(second, [])}
        for observed in reference.get(second * 10, []):
            identity = str(observed["id"])
            match = mapping.get(identity)
            if match is None:
                category = "no_cv_birth_association"
            elif second < match["birth_s"]:
                category = "before_cv_birth"
            elif match["native_id"] not in predicted:
                category = "native_vehicle_absent"
            elif dist(observed["point"], predicted[match["native_id"]]["point"]) > gate_m:
                category = "native_present_outside_gate"
            else:
                category = "native_present_within_gate"
            counts[category] += 1
            vehicles[category].add(identity)
    total = sum(counts.values())
    if total == 0:
        raise ValueError("No reference states in requested interval")
    return {
        "window_s": [start_s, end_s],
        "reference_states": total,
        "exclusive_state_categories": {
            category: {
                "states": counts[category],
                "fraction": counts[category] / total,
                "distinct_reference_ids": len(vehicles[category]),
            }
            for category in vehicles
        },
        "scope": (
            "Categories partition the same reference 1 Hz states as the frozen v7 "
            "physical evaluator. Distinct ID counts overlap across categories as "
            "a vehicle changes status. Birth matching is scoring correspondence, "
            "not a deployable reference-assisted tracker."
        ),
    }


def admission_lifecycle(entries, mapping, native, end_s):
    """Trace requests to first sampled native appearance, keeping unknowns explicit."""
    first = {}
    last = {}
    for second in range(end_s):
        for row in native.get(second, []):
            identity = str(row["id"])
            first.setdefault(identity, second)
            last[identity] = second
    reference_by_native = {row["native_id"]: key for key, row in mapping.items()}
    records = []
    for entry in entries:
        identity = str(entry["id"])
        appeared = first.get(identity)
        records.append(
            {
                "id": identity,
                "requested_s": entry["t"],
                "first_sampled_native_s": appeared,
                "last_sampled_native_s": last.get(identity),
                "first_sample_offset_s": appeared - entry["t"] if appeared is not None else None,
                "reference_id": reference_by_native.get(identity),
                "edge": entry.get("edge"),
                "lane": entry.get("lane"),
                "projection_residual_m": entry.get("projection_residual_m"),
            }
        )
    return {
        "requested_births": len(records),
        "sampled_native_births": sum(row["first_sampled_native_s"] is not None for row in records),
        "unsampled_native_births": sum(row["first_sampled_native_s"] is None for row in records),
        "reference_associated_births": sum(row["reference_id"] is not None for row in records),
        "records": records,
        "scope": (
            "Native timing is from 1 Hz FCD, so first-sample offset includes up to "
            "one second of sampling lag. An unsampled vehicle may have entered and "
            "left between samples; tripinfo/SUMO logs must be checked separately."
        ),
    }
