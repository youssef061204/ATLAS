"""Bounded, TLS-verified Caltrans HLS ingestion. No snapshots or retained media."""

import hashlib
import math
from collections import deque
from urllib.parse import urljoin, urlsplit


def permitted_url(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "wzmedia.dot.ca.gov"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise ValueError("Only the reviewed official HTTPS Caltrans media host is permitted")
    return url


def playlist(text, base):
    """Accept actual unencrypted live media playlists; never image slideshow wrappers."""
    permitted_url(base)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or lines[0] != "#EXTM3U" or "#EXT-X-ENDLIST" in lines:
        raise ValueError("Not a continuous live HLS playlist")
    if any(line.startswith("#EXT-X-KEY:") for line in lines):
        raise ValueError("Encrypted source outside reviewed scope")
    if any(line.startswith("#EXT-X-STREAM-INF:") for line in lines):
        for index, line in enumerate(lines[:-1]):
            if line.startswith("#EXT-X-STREAM-INF:"):
                return {"variant": permitted_url(urljoin(base, lines[index + 1]))}
    sequence = next(
        (int(line.split(":", 1)[1]) for line in lines if line.startswith("#EXT-X-MEDIA-SEQUENCE:")),
        None,
    )
    if sequence is None:
        raise ValueError("No progressing media sequence")
    segments, duration, discontinuity = [], None, False
    for line in lines:
        if line == "#EXT-X-DISCONTINUITY":
            discontinuity = True
        elif line.startswith("#EXTINF:"):
            duration = float(line.split(":", 1)[1].split(",")[0])
            if not math.isfinite(duration) or not 0 < duration <= 30:
                raise ValueError("Unbounded segment duration")
        elif not line.startswith("#"):
            if duration is None or not urlsplit(line).path.endswith(".ts"):
                raise ValueError("Expected consecutive MPEG-TS video, not still images")
            segments.append(
                {
                    "sequence": sequence + len(segments),
                    "url": permitted_url(urljoin(base, line)),
                    "duration_s": duration,
                    "discontinuity": discontinuity,
                }
            )
            duration, discontinuity = None, False
    if not segments:
        raise ValueError("No live media segments")
    return {"segments": segments}


class StreamHealth:
    def __init__(self, window_s=30):
        if not 0 < window_s <= 120:
            raise ValueError("Invalid bounded rolling window")
        self.window_s = window_s
        self.rows = deque()
        self.last_sequence = None
        self.last_source_update = None
        self.last_digest = None
        self.identical_frames = 0
        self.frames = 0

    def accept(self, sequence, now):
        if self.last_sequence is not None and sequence <= self.last_sequence:
            return False
        self.last_sequence, self.last_source_update = sequence, now
        return True

    def frame(self, pixels, tracks, now):
        digest = hashlib.sha256(pixels).digest()
        self.identical_frames += int(digest == self.last_digest)
        self.last_digest = digest
        self.frames += 1
        if tracks is not None:
            self.rows.append((now, len(tracks)))
        while self.rows and self.rows[0][0] < now - self.window_s:
            self.rows.popleft()

    def snapshot(self, now):
        active = [row for row in self.rows if row[0] >= now - self.window_s]
        age = now - self.last_source_update if self.last_source_update is not None else None
        return {
            "decoded_frames": self.frames,
            "consecutive_identical_frames": self.identical_frames,
            "last_media_sequence": self.last_sequence,
            "source_update_age_s": age,
            "stale": age is None or age > 30,
            "rolling_visible_track_mean": sum(row[1] for row in active) / len(active)
            if active
            else None,
            "rolling_frames": len(active),
        }
