import pytest
from atlas.hls_v6 import StreamHealth, permitted_url, playlist

BASE = "https://wzmedia.dot.ca.gov/D12/NBPCHBLUEBIRD.stream/playlist.m3u8"


@pytest.mark.parametrize(
    "source",
    [
        "https://example.com/a.m3u8",
        "http://wzmedia.dot.ca.gov/a",
        "https://x@wzmedia.dot.ca.gov/a",
        "https://wzmedia.dot.ca.gov:8000/a",
    ],
)
def test_unreviewed_stream_is_rejected(source):
    with pytest.raises(ValueError):
        permitted_url(source)


@pytest.mark.parametrize(
    "source",
    [
        "jpeg",
        "#EXTM3U\n#EXT-X-MEDIA-SEQUENCE:4\n#EXTINF:10,\npicture.jpg",
        "#EXTM3U\n#EXT-X-ENDLIST",
        "#EXTM3U\n#EXT-X-MEDIA-SEQUENCE:4\n#EXTINF:inf,\na.ts",
    ],
)
def test_snapshots_vod_and_unbounded_segments_are_not_live_video(source):
    with pytest.raises(ValueError):
        playlist(source, BASE)


def test_segments_preserve_sequence_and_discontinuity():
    result = playlist(
        "#EXTM3U\n#EXT-X-MEDIA-SEQUENCE:42\n#EXTINF:9.6,\na.ts\n#EXT-X-DISCONTINUITY\n#EXTINF:12,\nb.ts",
        BASE,
    )
    assert [row["sequence"] for row in result["segments"]] == [42, 43]
    assert result["segments"][1]["discontinuity"]


def test_health_rejects_duplicate_sequence_and_expires_rolling_metrics():
    health = StreamHealth(10)
    assert health.accept(7, 0)
    assert not health.accept(7, 1)
    health.frame(b"one", [1, 2], 0)
    health.frame(b"one", [1], 1)
    assert health.snapshot(2)["rolling_visible_track_mean"] == 1.5
    assert health.snapshot(2)["consecutive_identical_frames"] == 1
    assert health.snapshot(40)["stale"]
    assert health.snapshot(40)["rolling_visible_track_mean"] is None
