"""Bounded multipart MJPEG extraction, without retaining a video archive."""


def jpeg_frames(chunks, limit=1024 * 1024):
    buffer = bytearray()
    for chunk in chunks:
        buffer.extend(chunk)
        if len(buffer) > limit * 2:
            raise ValueError("MJPEG transient buffer exceeds limit")
        while True:
            start = buffer.find(b"\xff\xd8")
            if start < 0:
                # Preserve one marker-prefix byte across network chunk boundaries.
                buffer[:] = buffer[-1:]
                break
            if start:
                del buffer[:start]
            end = buffer.find(b"\xff\xd9", 2)
            if end < 0:
                if len(buffer) > limit:
                    raise ValueError("MJPEG frame exceeds limit")
                break
            if end + 2 > limit:
                raise ValueError("MJPEG frame exceeds limit")
            frame = bytes(buffer[: end + 2])
            del buffer[: end + 2]
            yield frame
