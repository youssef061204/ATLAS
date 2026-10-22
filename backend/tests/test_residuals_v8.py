import numpy as np
import pytest
from atlas.residuals_v8 import residual_audit, signed_components


def test_signed_components_follow_vehicle_heading():
    assert signed_components((0, 0), (1, 2), (0, 1), 2) == (2.0, 1.0)
    assert signed_components((0, 0), (1, 2), (0, 1), 4) == (-2.0, -1.0)


def test_residual_audit_keeps_missing_reference_in_denominator():
    def road(y):
        return np.column_stack([np.zeros_like(y), y])

    result = residual_audit(
        {"a": {"native_id": "n", "birth_s": 0}},
        {0: [{"id": "a", "point": [0, 1]}, {"id": "b", "point": [0, 2]}]},
        {0: [{"id": "n", "point": [1, 3]}]},
        {(0, "a"): 2, (0, "b"): 2},
        road,
        0,
        1,
    )
    assert result["reference_states"] == 2
    assert result["paired_native_states"] == 1
    assert result["groups"]["all"]["longitudinal"]["mean_m"] == pytest.approx(2)
