import hashlib
import hmac
import json

import httpx
import numpy as np
import pytest
from atlas import config
from atlas.api import app
from atlas.cities import Camera, CityAdapter, FeedClient, FeedError, city_configs
from atlas.control_v2 import (
    RiskConfig,
    RiskController,
    SafetyGate,
    SafetyProfile,
    authorize_priority,
    cvar,
)
from atlas.operations import PilotInput, pilot_report
from atlas.probabilistic import causal_intervals
from atlas.state import CountFilter, IncidentDetector, calibrate_scale, rolling_intervals
from fastapi.testclient import TestClient


def test_official_catalogs_preserve_real_provenance():
    payload = json.loads(
        (config.ARTIFACTS / "cities/source-health.json").read_text(encoding="utf-8")
    )
    assert {c["city"] for c in payload["cities"]} == set(city_configs())
    for city in payload["cities"]:
        assert city["status"] == "metadata_available"
        assert len(city["cameras"]) > 100
        cameras = [Camera.model_validate(c) for c in city["cameras"]]
        assert len(set(c.id for c in cameras)) == len(cameras)
        for obs in city["observations"]:
            assert obs["captured_at"] is None
            assert obs["speed_mps"] is obs["trajectories"] is obs["flow_veh_hour"] is None
            assert isinstance(obs["counts"], dict)
            assert obs["retention"].startswith("Image processed in memory")


def test_query_preserved_and_retry_does_not_bypass_authentication():
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(403, content=b"restricted")

    c = FeedClient(httpx.MockTransport(handler), min_interval=0)
    with pytest.raises(FeedError):
        c.read("https://web.seattle.gov/api?type=2", ["web.seattle.gov"], {})
    c.close()
    assert requested == ["https://web.seattle.gov/api?type=2"]


def test_feed_enforces_budget_and_redirect_hosts():
    c = FeedClient(
        httpx.MockTransport(lambda _: httpx.Response(200, content=b"12345")), min_interval=0
    )
    with pytest.raises(ValueError, match="byte budget"):
        c.read("https://api.tfl.gov.uk/Place", ["api.tfl.gov.uk"], max_bytes=4)
    c.close()
    c = FeedClient(
        httpx.MockTransport(
            lambda _: httpx.Response(302, headers={"location": "http://127.0.0.1/private"})
        ),
        min_interval=0,
    )
    with pytest.raises(ValueError, match="redirect"):
        c.read("https://api.tfl.gov.uk/Place", ["api.tfl.gov.uk"])
    c.close()


@pytest.mark.parametrize("city", list(city_configs()))
def test_source_adapter_roundtrip(city):
    payload = json.loads(
        (config.ARTIFACTS / "cities/source-health.json").read_text(encoding="utf-8")
    )
    source = next(c for c in payload["cities"] if c["city"] == city)
    assert CityAdapter(city, None).settings["attribution"]
    assert all(Camera.model_validate(c).city == city for c in source["cameras"])


def test_safety_profile_rejects_conflicts_and_unsafe_envelopes():
    with pytest.raises(ValueError):
        SafetyGate(["GG", "rr"], SafetyProfile(conflict_pairs=((0, 1),)))
    with pytest.raises(ValueError):
        SafetyProfile(yellow=1)
    with pytest.raises(ValueError):
        SafetyGate(["Gy", "rG"])


@pytest.mark.parametrize("seed", range(10))
def test_randomized_safety_invariants(seed):
    rng = np.random.default_rng(seed)
    gate = SafetyGate(["Grr", "rGr", "rrG"], SafetyProfile(pedestrian_phases=(1,)))
    previous_phase, green_started, clearance_started = 0, 0, None
    for t in range(3000):
        target = int(rng.integers(-2, 5))
        state, reason = gate.advance(t, target)
        assert state.count("G") <= 1
        if (
            reason in {"switch", "rejected_unsafe_request"}
            and "y" in state
            and clearance_started is None
        ):
            assert t - green_started >= gate.minimum(previous_phase)
            clearance_started = t
        if "G" in state and gate.current != previous_phase:
            assert clearance_started is not None and t - clearance_started >= 5
            green_started, previous_phase, clearance_started = t, gate.current, None
        if "y" in state:
            assert clearance_started is not None and t - clearance_started < 3
        if state == "rrr":
            assert clearance_started is not None and 3 <= t - clearance_started < 5
    assert gate.switches > 30 and gate.rejected > 0


def test_risk_decision_deterministic_and_sensor_fallback():
    lanes = {
        "a": {"queue": 8, "vehicles": 8, "capacity": 20, "arrival_rate": 0.1, "starvation": 12},
        "b": {"queue": 2, "vehicles": 2, "capacity": 20, "arrival_rate": 0.1, "starvation": 12},
    }
    moves = [[("a", "b")], [("b", "a")]]
    actions = []
    for _ in range(2):
        c = RiskController(moves, RiskConfig(small_phase_pressure_fallback=False))
        actions.append(c.decide(15, SafetyGate(["Gr", "rG"]), lanes)[0])
        assert c.last_explanation["expansions"] <= 240
        assert c.last_explanation["alternatives"]
    assert actions[0] == actions[1]
    c = RiskController(moves)
    _, reason = c.decide(15, SafetyGate(["Gr", "rG"]), {})
    assert reason == "invalid_sensor_fallback"


def test_optimizer_respects_single_feasible_action_at_max_green():
    gate = SafetyGate(["Gr", "rG"])
    controller = RiskController([[("a", "b")], [("b", "a")]])
    action, reason = controller.decide(60, gate, {})
    assert action == 1 and action in gate.allowed(60)
    state, _ = gate.advance(60, action)
    assert state == "yr" and gate.rejected == 0


def test_empirical_cvar_fractional_tail():
    assert cvar([1, 2, 10], 0.8) == pytest.approx(10)
    assert cvar([1, 2, 10], 0.5) == pytest.approx(22 / 3)


def test_filter_outage_increases_uncertainty_and_rejects_stale():
    f = CountFilter()
    first = f.update(1, 10)
    missing = f.update(31)
    assert missing["interval95"][1] > first["interval95"][1]
    with pytest.raises(ValueError):
        f.update(30, 10)


def test_calibration_uses_training_only():
    result = calibrate_scale([1, 2, 3], [2, 4, 6], [4, 5], [11, 14])
    assert result["scale"] == 2
    assert result["train_mae"] == 0
    assert result["validation_mae"] == 3.5


def test_rolling_forecast_and_anomaly():
    rows = rolling_intervals(np.full(150, 10.0))
    assert len(rows) == 6
    assert all(r["mae"] == 0 and r["coverage90"] == 1 for r in rows)
    detector = IncidentDetector()
    assert not any(detector.update(5)["anomaly"] for _ in range(20))
    assert detector.update(40)["anomaly"]


def test_priority_requires_signed_fresh_non_replayed_request():
    payload = {"kind": "emergency", "issued": 10, "expires": 30, "nonce": "one"}
    signature = hmac.new(
        b"test-only",
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
        hashlib.sha256,
    ).hexdigest()
    used = set()
    assert authorize_priority(payload, signature, "test-only", 15, used) == payload
    with pytest.raises(ValueError):
        authorize_priority(payload, signature, "test-only", 15, used)
    with pytest.raises(ValueError):
        authorize_priority(payload, "bad", "test-only", 15, set())


def test_operations_api_auth_state_and_exports(database, monkeypatch):
    with TestClient(app) as client:
        response = client.get("/api/operations/cities")
        assert response.status_code == 200 and len(response.json()["cities"]) == 5
        response = client.get("/api/operations/cities/toronto/state")
        assert response.status_code == 200 and response.json()["states"]
        monkeypatch.delenv("ATLAS_OPERATOR_KEY", raising=False)
        assert client.post("/api/operations/cities/toronto/refresh").status_code == 503
        monkeypatch.setenv("ATLAS_OPERATOR_KEY", "test-only")
        assert client.post("/api/operations/cities/toronto/refresh").status_code == 401
        assert (
            client.post(
                "/api/operations/pilot", json={"city": "toronto", "vehicles_per_day": 1000}
            ).status_code
            == 200
        )
        assert client.get("/api/operations/health").json()["hardware_actuation"] is False


def test_pilot_preserves_regression_and_assumptions():
    evidence = {
        "summaries": [
            {"city": "x", "policy": "fixed", "mean_delay_s": 20},
            {"city": "x", "policy": "risk_mpc", "mean_delay_s": 30},
        ],
        "runs": [
            {
                "city": "x",
                "policy": p,
                "seed": 1,
                "network_sha256": "net",
                "routes_sha256": "routes",
                "duration": 300,
                "scenario": "nominal",
            }
            for p in ("fixed", "risk_mpc")
        ],
    }
    report = pilot_report(PilotInput(city="x", vehicles_per_day=1000), evidence)
    assert report["projected_value_per_year"] < 0
    assert report["delay_difference_s"] == -10
    assert report["field_validated"] is False
    assert report["paired_delay_ci95_s"] is None
    evidence["paired"] = [
        {"city": "x", "baseline": "fixed", "pairs": 1, "paired_difference_ci95": [-12, -8]}
    ]
    report = pilot_report(PilotInput(city="x", vehicles_per_day=1000), evidence)
    assert report["projected_value_ci95_from_simulation_seed_variation"][1] < 0
    assert len(report["simulation_inputs"]) == 2
    with pytest.raises(ValueError, match="distinct"):
        pilot_report(PilotInput(city="x", vehicles_per_day=1000, candidate="fixed"), evidence)


def test_interval_forecast_cannot_consume_future_targets():
    rng = np.random.default_rng(41)
    series = rng.uniform(10, 40, (140, 3))
    changed = series.copy()
    changed[90:] += 30
    valid = np.ones(series.shape, dtype=bool)
    for model in ("persistence", "ewma"):
        before, width = causal_intervals(series, valid, np.ones(134, dtype=bool), 6, model)
        after, altered_width = causal_intervals(changed, valid, np.ones(134, dtype=bool), 6, model)
        np.testing.assert_array_equal(before[:90], after[:90])
        np.testing.assert_array_equal(width[:90], altered_width[:90])
