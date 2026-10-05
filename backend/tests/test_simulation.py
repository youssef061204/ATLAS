import pytest
from atlas.schemas import SimulationConfig
from atlas.simulation import arrivals, simulate


def test_seed_reproduces_complete_trajectories_and_demand():
    settings = SimulationConfig(duration=60, seed=123)
    first, second = simulate(settings, "baseline"), simulate(settings, "baseline")
    assert first == second
    adaptive = simulate(settings, "adaptive")
    assert (
        first["metrics"]["arrived"] == adaptive["metrics"]["arrived"] == len(arrivals(settings)[0])
    )


def test_vehicle_conservation_and_nonnegative_metrics():
    run = simulate(SimulationConfig(duration=90), "adaptive")
    metrics = run["metrics"]
    assert metrics["throughput"] + metrics["unfinished"] == metrics["arrived"]
    assert metrics["delay"] >= 0
    for frame in run["frames"]:
        for v in frame["vehicles"]:
            assert 0 <= v["velocity"] <= 12
        for approach in range(4):
            positions = sorted(
                v["position"] for v in frame["vehicles"] if v["approach"] == approach
            )
            assert all(b - a >= 6.99 for a, b in zip(positions, positions[1:], strict=False))


def test_signal_clearance_never_allows_conflicting_greens():
    run = simulate(SimulationConfig(duration=90), "baseline")
    frames = run["frames"]
    assert frames[30]["signal"] == "yellow"
    assert frames[33]["signal"] == "all_red"
    assert frames[35]["signal"] == "green"
    assert frames[35]["phase"] == 1


def test_empty_demand_and_invalid_configuration():
    run = simulate(
        SimulationConfig(duration=60, demand=[0, 0, 0, 0], pedestrian_rate=0), "atlas", [12, 12]
    )
    assert run["metrics"]["delay"] == 0
    assert run["metrics"]["arrived"] == 0
    with pytest.raises(ValueError):
        SimulationConfig(demand=[1, -1, 0, 0])


def test_delay_retains_insertion_wait_after_burst_vehicles_enter(monkeypatch):
    monkeypatch.setattr("atlas.simulation.arrivals", lambda _: ([(0, 0)] * 12, []))
    run = simulate(SimulationConfig(duration=120), "atlas", [60, 12])
    first_visible = {}
    for frame in run["frames"]:
        for vehicle in frame["vehicles"]:
            first_visible.setdefault(vehicle["id"], frame["t"])
    assert len(first_visible) == 12
    assert run["metrics"]["unfinished"] == 0
    # Every entrant waited at least this long before reaching the visible road.
    # One-second frame sampling overestimates entry time by at most one second.
    minimum_delay = sum(max(0, t - 1) for t in first_visible.values()) / 12
    assert run["metrics"]["delay"] >= minimum_delay
