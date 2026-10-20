import pytest
from atlas.mjpeg_v7 import jpeg_frames


def test_actual_stream_markers_across_partial_network_reads():
    a, b = b"\xff\xd8one\xff\xd9", b"\xff\xd8two\xff\xd9"
    stream = b"--boundary\r\nContent-type: image/jpeg\r\n\r\n" + a + b"\r\n--boundary\r\n" + b
    assert list(jpeg_frames([stream[i : i + 1] for i in range(len(stream))])) == [a, b]


def test_unbounded_or_unterminated_frame_is_rejected():
    with pytest.raises(ValueError, match="exceeds"):
        list(jpeg_frames([b"\xff\xd8" + b"a" * 20], limit=16))
