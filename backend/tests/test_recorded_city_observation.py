"""Published counts are allowed only by their actual source city/id, never caller payload."""

import json

from atlas import config
from atlas.operations import recorded_city_observation


def test_recorded_observations_preserve_provenance_and_reject_cross_city_or_unknown_ids():
    source = json.loads((config.ARTIFACTS / "cities/v4/intelligence-smoke.json").read_text())
    for record in source["records"]:
        actual = next(
            attempt["context"]["observation"]
            for attempt in record["attempts"]
            if attempt.get("context")
        )
        assert recorded_city_observation(record["city"], actual["id"]) == actual
        other = "london" if record["city"] != "london" else "toronto"
        assert recorded_city_observation(other, actual["id"]) is None
    assert recorded_city_observation("toronto", "untrusted-observation") is None
