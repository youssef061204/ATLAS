from atlas.crossing_v8 import observed_crossing


def row(t, y, direction=2, movement=1):
    return {
        "t": t,
        "local_x": 0,
        "local_y": y,
        "direction": direction,
        "movement": movement,
        "lane_id": 2,
    }


def test_north_and_south_through_crossings_interpolate():
    assert observed_crossing(row(0, 1040), row(0.1, 1050)) == 0.05
    assert observed_crossing(row(0, 1050, 4), row(0.1, 1040, 4)) == 0.05


def test_turn_and_missing_frame_do_not_count_as_through_crossing():
    assert observed_crossing(row(0, 1040, movement=2), row(0.1, 1050)) is None
    assert observed_crossing(row(0, 1040), row(1.0, 1050)) is None
