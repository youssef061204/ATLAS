import pytest
from atlas.reality_v7 import result_frames


def test_streams_records_across_read_boundaries(tmp_path):
    source = tmp_path / "result.json"
    source.write_text(
        '{"frames":[{"index":0,"objects":[],"note":"'
        + "x" * 70000
        + '"},{"index":1,"objects":[]}],"tracks":[]}'
    )
    assert [f["index"] for f in result_frames(source)] == [0, 1]


def test_truncated_frame_array_is_not_success(tmp_path):
    source = tmp_path / "result.json"
    source.write_text('{"frames":[{"index":0,"objects":[]}, {"index":')
    reader = result_frames(source)
    assert next(reader)["index"] == 0
    with pytest.raises(ValueError, match="Truncated"):
        next(reader)


@pytest.mark.parametrize(
    "records",
    [
        '{"index":0,"objects":[]}{"index":1,"objects":[]}',
        ',{"index":0,"objects":[]}',
        '{"index":0,"objects":[]},',
    ],
)
def test_invalid_array_separators_are_rejected(tmp_path, records):
    source = tmp_path / "result.json"
    source.write_text('{"frames":[' + records + "]}")
    with pytest.raises(ValueError):
        list(result_frames(source))


def test_handoff_contradiction_preserves_two_detections():
    import numpy as np
    from atlas.track_continuity_v7 import stitch

    def obj(identity, x):
        return {"id": identity, "class": "car", "confidence": 0.8, "bbox": [x, 0, x + 2, 2]}

    frames = [
        {"index": 0, "objects": [obj(1, 0)]},
        {"index": 1, "objects": [obj(2, 0.1)]},
        {"index": 2, "objects": [obj(1, 0.2), obj(2, 0.3)]},
    ]
    result, events = stitch(frames, np.eye(3))
    assert result[0]["objects"][0]["id"] == result[1]["objects"][0]["id"]
    assert len({o["id"] for o in result[2]["objects"]}) == 2
    assert any(e["kind"] == "contradiction_split" for e in events)


def test_ambiguous_handoff_is_rejected():
    import numpy as np
    from atlas.track_continuity_v7 import stitch

    def obj(identity, x):
        return {"id": identity, "class": "car", "confidence": 0.8, "bbox": [x, 0, x + 2, 2]}

    frames = [
        {"index": 0, "objects": [obj(1, 0), obj(2, 2)]},
        {"index": 1, "objects": []},
        {"index": 2, "objects": [obj(3, 1)]},
    ]
    result, events = stitch(frames, np.eye(3))
    assert not events
    assert result[2]["objects"][0]["id"] not in {o["id"] for o in result[0]["objects"]}


def test_gap_interpolation_is_explicit_and_bounded():
    from atlas.track_continuity_v7 import interpolate_short_gaps

    def obj(x):
        return {
            "id": 1,
            "class": "car",
            "confidence": 0.8,
            "bbox": [x, 0, x + 2, 2],
            "inferred": False,
        }

    frames = [{"index": i, "objects": []} for i in range(10)]
    frames[0]["objects"] = [obj(0)]
    frames[2]["objects"] = [obj(2)]
    frames[9]["objects"] = [obj(9)]
    result, count = interpolate_short_gaps(frames)
    assert count == 1
    inferred = result[1]["objects"][0]
    assert inferred["inferred"] is True
    assert "not an actual detector" in inferred["uncertainty"]
    assert result[3]["objects"] == []


def test_multiscale_profile_never_silently_ignores_tracker():
    from atlas.schemas import CameraConfig
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="ByteTrack only"):
        CameraConfig(detector_profile="aerial_multiscale", tracker="botsort.yaml")
