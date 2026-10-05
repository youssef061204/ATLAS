import pytest
from atlas import config, db


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA", tmp_path)
    for name in ["uploads", "results"]:
        (tmp_path / name).mkdir()
    db.init()
    return tmp_path
