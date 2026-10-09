import json

from atlas.api import app
from atlas.operations import connection
from fastapi.testclient import TestClient


def test_operator_scene_corrections_are_versioned_and_require_known_observation(
    database, monkeypatch
):
    monkeypatch.setenv("ATLAS_OPERATOR_KEY", "test-only")
    with TestClient(app) as client:
        source = client.get("/api/operations/intelligence/context").json()
        payload = {
            "city": source["city"],
            "camera_id": source["camera"]["id"],
            "observation_id": source["observation"]["id"],
            "road_id": source["alignment"]["candidates"][0]["road_id"],
            "name": "Road region",
            "polygon": [[0, 0], [1, 0], [1, 1], [0, 1]],
        }
        assert client.post("/api/operations/scenes", json=payload).status_code == 401
        headers = {"Authorization": "Bearer test-only"}
        first = client.post("/api/operations/scenes", json=payload, headers=headers)
        assert first.status_code == 200
        second = client.post("/api/operations/scenes", json=payload, headers=headers)
        assert second.json()["revision"] > first.json()["revision"]
        assert first.json()["queue_vehicles"] is None
        assert first.json()["derived_observation"]["counts"] == source["observation"]["counts"]
        assert first.json()["estimated_state"]["source_observation"] == source["observation"]["id"]
        assert first.json()["visible_detections_in_region"] == len(
            source["observation"]["detections"]
        )
        payload["observation_id"] = "unknown"
        assert (
            client.post("/api/operations/scenes", json=payload, headers=headers).status_code == 422
        )
        response = client.get(f"/api/operations/scenes/{source['city']}/{source['camera']['id']}")
        assert len(response.json()["regions"]) == 2
    with connection() as conn:
        stored = json.loads(conn.execute("SELECT payload FROM scene_regions LIMIT 1").fetchone()[0])
        assert "image_data_url" not in stored


def test_remote_camera_cannot_condition_unrelated_corridor(database, monkeypatch):
    from atlas import operations

    monkeypatch.setenv("ATLAS_OPERATOR_KEY", "test-only")
    source = operations.evidence("toronto-intelligence.json")
    camera = {**source["camera"], "lat": 0, "lon": 0}
    monkeypatch.setattr(
        operations, "cities", lambda: {"cities": [{"city": "toronto", "cameras": [camera]}]}
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/operations/intelligence/experiments",
            headers={"Authorization": "Bearer test-only"},
            json={
                "city": "toronto",
                "observation_id": source["observation"]["id"],
                "assumptions": {"acknowledge_exploratory": True},
            },
        )
    assert response.status_code == 422
    assert "1 km geographic screening" in response.json()["detail"]


def test_region_finds_fresh_observation_by_source_digest_not_database_index(database, monkeypatch):
    from atlas import operations

    monkeypatch.setenv("ATLAS_OPERATOR_KEY", "test-only")
    source = operations.evidence("toronto-intelligence.json")
    observation = {**source["observation"], "id": "a" * 64}
    with connection() as conn:
        conn.execute(
            "INSERT INTO observations VALUES (?,?,?)",
            ("distinct-database-index", "toronto", json.dumps(observation)),
        )
    with TestClient(app) as client:
        result = client.post(
            "/api/operations/scenes",
            headers={"Authorization": "Bearer test-only"},
            json={
                "city": "toronto",
                "camera_id": observation["camera_id"],
                "observation_id": observation["id"],
                "road_id": source["alignment"]["candidates"][0]["road_id"],
                "name": "Fresh observation region",
                "polygon": [[0, 0], [1, 0], [1, 1], [0, 1]],
            },
        )
    assert result.status_code == 200
    assert result.json()["derived_observation"]["id"] == observation["id"]
    assert result.json()["derived_observation"]["counts"] == observation["counts"]
