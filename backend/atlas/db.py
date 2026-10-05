import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from . import config


def now():
    return datetime.now(UTC).isoformat()


def uid():
    return uuid4().hex


@contextmanager
def connection():
    conn = sqlite3.connect(config.DATA / "atlas.db", timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init(recover=False):
    with connection() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        for migration in sorted((Path(__file__).parent / "migrations").glob("*.sql")):
            version = (
                int(migration.stem.split("_")[0]) if "_" in migration.stem else int(migration.stem)
            )
            has_versions = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            ).fetchone()
            applied = (
                has_versions
                and conn.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=?", (version,)
                ).fetchone()
            )
            if not applied:
                conn.executescript(migration.read_text())
        conn.execute(
            "INSERT OR IGNORE INTO intersections VALUES (?,?,?,?)",
            (
                "demo",
                "Guadalajara · Research intersection",
                "Mixkit time-lapse · image-space motion only",
                now(),
            ),
        )
        conn.execute("INSERT OR IGNORE INTO cameras VALUES (?,?,?)", ("demo", "demo", "{}"))
        if recover:
            conn.execute(
                "UPDATE videos SET status='failed',stage='interrupted',error='Worker restarted. Reprocess this video.' WHERE status IN ('queued','processing')"
            )


def rows(sql, args=()):
    with connection() as conn:
        return [dict(row) for row in conn.execute(sql, args)]


def video(video_id):
    result = rows("SELECT * FROM videos WHERE id=?", (video_id,))
    if not result:
        return None
    value = result[0]
    value.pop("storage_path")
    value["metadata"] = json.loads(value["metadata"])
    return value


def status(video_id, state, stage, progress, error=None, metadata=None):
    with connection() as conn:
        conn.execute(
            "UPDATE videos SET status=?,stage=?,progress=?,error=?,updated_at=? WHERE id=?",
            (state, stage, progress, error, now(), video_id),
        )
        if metadata is not None:
            conn.execute(
                "UPDATE videos SET metadata=? WHERE id=?", (json.dumps(metadata), video_id)
            )


def save_run(kind, payload, intersection_id=None):
    run_id = uid()
    with connection() as conn:
        conn.execute(
            "INSERT INTO runs VALUES (?,?,?,?,?)",
            (run_id, kind, intersection_id, json.dumps(payload, allow_nan=False), now()),
        )
    return run_id
