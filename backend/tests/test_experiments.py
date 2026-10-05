import joblib
import numpy as np
from atlas.experiments import calibration_error, forecast_features, generate_conflicts
from sklearn.linear_model import LogisticRegression


def test_synthetic_splits_are_seeded_independent_and_models_serialize(tmp_path):
    x, y = generate_conflicts(1, 500)
    assert np.array_equal(x, generate_conflicts(1, 500)[0])
    assert not np.array_equal(x, generate_conflicts(2, 500)[0])
    model = LogisticRegression(max_iter=1000).fit(x, y)
    path = tmp_path / "model.joblib"
    joblib.dump(model, path)
    assert np.allclose(model.predict_proba(x[:10]), joblib.load(path).predict_proba(x[:10]))


def test_forecast_features_do_not_use_future_targets():
    series = np.arange(100, dtype=float)
    x, y, origins = forecast_features(series, 5)
    assert x[0, 0] == 29
    assert origins[0] == 30
    assert y[0] == 34
    assert calibration_error(np.array([0, 1]), np.array([0.0, 1.0])) == 0
