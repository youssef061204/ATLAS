"""Check the opt-in birth policy contract at a continuing junction edge."""

import pytest
from atlas.birth_speed_v8 import observed_cv_depart_speed


def test_observed_speed_is_not_braked_solely_for_edge_end():
    # A track measured at 12 m/s near a green continuing edge should request
    # 12 m/s; SUMO, rather than this adapter, decides safe admission.
    assert observed_cv_depart_speed(12.0, max_speed_mps=15.65) == 12.0


def test_vehicle_type_maximum_remains_enforced():
    assert observed_cv_depart_speed(20.0, max_speed_mps=15.65) == 15.65
    assert observed_cv_depart_speed(0.0, max_speed_mps=15.65) == 0.0


@pytest.mark.parametrize("speed", [-1, 26, float("nan"), float("inf")])
def test_invalid_cv_speed_rejected(speed):
    with pytest.raises(ValueError, match="CV speed"):
        observed_cv_depart_speed(speed, max_speed_mps=15.65)


def test_invalid_vehicle_maximum_rejected():
    with pytest.raises(ValueError, match="maximum speed"):
        observed_cv_depart_speed(10, max_speed_mps=0)
