import io
import sys
import zipfile
from pathlib import Path

import httpx
import pytest
from atlas.reality_v6 import matched_errors, normalize_ngsim, partition_tracks

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from acquire_video_v6 import RangeReader  # noqa: E402


def observation(**changes):
    return {
        "vehicle_id": "7",
        "frame_id": "3",
        "global_time": "1118935680200",
        "local_x": "-10",
        "local_y": "100",
        "v_vel": "20",
        "v_length": "15",
        "lane_id": "1",
        "direction": "4",
        "section_id": "4",
        "int_id": "0",
        **changes,
    }


def test_observation_units_and_sequence_identity_are_preserved():
    first = normalize_ngsim(observation())
    second = normalize_ngsim(observation(global_time="1118936700200"))
    assert first["x_m"] == -3.048
    assert first["speed_mps"] == 6.096
    assert first["sequence_epoch_ms"] == 1118935680000
    assert first["vehicle_id"] != second["vehicle_id"]


@pytest.mark.parametrize(
    "changes",
    [
        {"v_length": ""},
        {"v_length": "-1"},
        {"v_vel": "nan"},
        {"frame_id": "0"},
        {"lane_id": "1.5"},
        {"direction": "0"},
    ],
)
def test_bad_observations_do_not_become_default_physical_measurements(changes):
    with pytest.raises(ValueError):
        normalize_ngsim(observation(**changes))


def test_whole_tracks_crossing_split_boundary_are_excluded():
    points = [{"vehicle_id": "crossing", "timestamp_ms": t} for t in [5, 10]] + [
        {"vehicle_id": "heldout", "timestamp_ms": 12}
    ]
    result, excluded = partition_tracks(points, {"calibration": [0, 10], "final": [10, 20]})
    assert result["calibration"] == []
    assert result["final"] == [{"vehicle_id": "heldout", "timestamp_ms": 12}]
    assert excluded == ["crossing"]
    with pytest.raises(ValueError):
        partition_tracks(points, {"calibration": [0, 11], "final": [10, 20]})
    with pytest.raises(ValueError):
        partition_tracks(points + [points[0]], {"all": [0, 20]})


def test_missing_predictions_report_coverage_instead_of_zero_speed():
    result = matched_errors([10, 20, 30], [12, None, 28])
    assert result == {
        "pairs": 2,
        "eligible_observations": 3,
        "coverage": 2 / 3,
        "mae": 2,
        "rmse": 2,
        "bias": 0,
    }
    assert matched_errors([10], [None])["mae"] is None
    with pytest.raises(ValueError):
        matched_errors([10], [])


def test_seekable_http_archive_enforces_ranges_and_validates_member_crc():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("complete.avi", b"consecutive video data" * 1000)
    raw = buffer.getvalue()

    def handler(request):
        start, end = map(int, request.headers["range"].removeprefix("bytes=").split("-"))
        return httpx.Response(
            206,
            headers={"content-range": f"bytes {start}-{end}/{len(raw)}"},
            content=raw[start : end + 1],
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        resource = RangeReader(client, "https://example.test/archive.zip", len(raw))
        with zipfile.ZipFile(resource) as archive:
            assert archive.read("complete.avi") == b"consecutive video data" * 1000


@pytest.mark.parametrize(
    "status,headers,body",
    [
        (200, {}, b"ignored range"),
        (206, {"content-range": "bytes 1-3/4"}, b"abc"),
        (206, {"content-range": "bytes 0-2/4"}, b"ab"),
        (206, {"content-range": "bytes 0-2/4"}, b"abcd"),
    ],
)
def test_invalid_or_incomplete_http_ranges_fail_closed(status, headers, body):
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(status, headers=headers, content=body)
        )
    ) as client:
        with pytest.raises(ValueError):
            RangeReader(client, "https://example.test/archive.zip", 4).read(3)
