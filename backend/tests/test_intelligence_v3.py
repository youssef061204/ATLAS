import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest
from atlas import config
from atlas.forecast_v3 import features, graph_weights
from atlas.intelligence import (
    DemandAssumptions,
    assimilate,
    camera_alignment,
    count_forecast,
    prepare_scenario,
)


def observation(count=4):
    return {
        "id": "source-digest",
        "camera_id": "camera",
        "retrieved_at": "2026-10-08T20:00:00+00:00",
        "counts": {"car": count, "person": 12, "bicycle": 3},
    }


def test_snapshot_assimilation_does_not_invent_flow_or_queue():
    state = assimilate(observation())
    assert 0 < state["mean"] < 4
    assert state["flow_veh_hour"] is None and state["queue_vehicles"] is None
    assert not state["capture_timestamp_verified"]
    rows = count_forecast(state)
    assert rows[-1]["interval95"][1] > rows[0]["interval95"][1]
    assert not rows[-1]["calibrated"]
    with pytest.raises(ValueError):
        assimilate({"counts": {"car": -1}, "id": "x", "retrieved_at": "2026-10-08T20:00:00+00:00"})


def test_camera_alignment_measures_segment_not_just_endpoints():
    result = camera_alignment(
        {"lat": 0, "lon": 0.0005},
        {
            "roads": [
                {"id": "a", "coordinates": [[0, 0], [0.001, 0]]},
                {"id": "b", "coordinates": [[0, 0.001], [0.001, 0.001]]},
            ]
        },
    )
    assert result["candidates"][0]["road_id"] == "a"
    assert result["candidates"][0]["distance_m"] == pytest.approx(0, abs=1e-6)
    assert result["status"] == "geographic_candidate_not_validated"


def test_graph_context_has_directional_neighbors_and_no_self_edges():
    matrix = np.array([[1, 2, 0], [0, 1, 3], [0, 0, 1]], dtype=float)
    weights = graph_weights(matrix)
    assert weights[0, 1] == 1 and weights[1, 2] == 1 and weights[2].sum() == 0
    history = np.broadcast_to(np.array([10, 20, 30])[None, :, None], (2, 3, 6))
    times = np.array(["2026-10-08T20:00", "2026-10-08T20:05"], dtype="datetime64[m]")
    result = features(history, times, np.array([8, 18, 28]), matrix)
    assert result.shape == (2, 3, 18)
    assert result[0, 0, -4] == 20 and result[0, 1, -4] == 30
    changed = history.copy()
    changed[1] = 99
    np.testing.assert_array_equal(
        result[0], features(changed, times, np.array([8, 18, 28]), matrix)[0]
    )
    with pytest.raises(ValueError):
        graph_weights(np.array([[1, -1], [0, 1]]))


@pytest.fixture
def scenario_source(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(config, "DATA", tmp_path / "data")
    source = tmp_path / "datasets/cities/toronto"
    source.mkdir(parents=True)
    net = source / "network.net.xml"
    net.write_text("<net/>")
    routes = source / "routes-template.xml"
    routes.write_text(
        '<routes><vType id="passenger" vClass="passenger"/><vehicle id="template" type="passenger" depart="0"><route edges="a b"/></vehicle></routes>'
    )
    manifest = {
        "network_sha256": hashlib.sha256(net.read_bytes()).hexdigest(),
        "routes_sha256": hashlib.sha256(routes.read_bytes()).hexdigest(),
        "seed": 1,
        "duration": 300,
        "period": 3,
    }
    (source / "manifest.json").write_text(json.dumps(manifest))
    return source


def test_observation_conditioned_routes_are_reproducible_and_keep_types(scenario_source):
    assumptions = DemandAssumptions(acknowledge_exploratory=True)
    first, route_a, lineage = prepare_scenario("toronto", observation(), assumptions)
    _, route_b, other = prepare_scenario("toronto", observation(), assumptions)
    assert route_a.read_bytes() == route_b.read_bytes()
    assert ET.parse(route_a).getroot().find("vType").attrib["id"] == "passenger"
    assert lineage["routes_sha256"] == other["routes_sha256"]
    assert lineage["calibration"]["independent_validation"] is None
    _, _, changed = prepare_scenario(
        "toronto",
        observation(),
        DemandAssumptions(acknowledge_exploratory=True, residence_seconds=20),
    )
    assert (
        changed["demand"]["arrival_rate_assumed_veh_s"]
        > lineage["demand"]["arrival_rate_assumed_veh_s"]
    )
    assert first != route_b.parent


def test_exploration_requires_acknowledgement_and_observable_demand(scenario_source):
    with pytest.raises(ValueError, match="acknowledgement"):
        prepare_scenario("toronto", observation(), DemandAssumptions())
    with pytest.raises(ValueError, match="Zero observed"):
        prepare_scenario("toronto", observation(0), DemandAssumptions(acknowledge_exploratory=True))
    with pytest.raises(ValueError, match="budget"):
        prepare_scenario(
            "toronto",
            observation(1000),
            DemandAssumptions(
                acknowledge_exploratory=True, residence_seconds=10, corridor_multiplier=10
            ),
        )


def test_nominal_study_sources_remain_frozen():
    protocol = json.loads(Path("docs/atlas-2-protocol.json").read_text(encoding="utf-8"))
    for name, digest in protocol["frozen_source_sha256"].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest


def test_official_historical_turning_counts_match_published_total():
    counts = json.loads(Path("artifacts/cities/toronto-counts.json").read_text(encoding="utf-8"))
    fields = [
        f"{direction}_appr_{vehicle}_{turn}"
        for direction in "nesw"
        for vehicle in ("cars", "truck", "bus")
        for turn in "rtl"
    ]
    assert (
        sum(sum(row[field] for field in fields) for row in counts["records"])
        == counts["study"]["total_vehicle"]
    )
    assert len(counts["records"]) == 56
    assert counts["independent_of_camera_date"]
