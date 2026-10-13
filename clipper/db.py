"""SQLite state: source videos, clip candidates, and every post we create."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    video_id      TEXT PRIMARY KEY,
    campaign_id   TEXT NOT NULL,
    url           TEXT NOT NULL,
    title         TEXT,
    duration      REAL,
    transcript    TEXT,               -- path to cached transcript JSON
    select_rounds INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'new',   -- new | transcribed | exhausted | failed
    error         TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clips (
    clip_id       TEXT PRIMARY KEY,
    campaign_id   TEXT NOT NULL,
    video_id      TEXT NOT NULL,
    start         REAL NOT NULL,
    end           REAL NOT NULL,
    score         REAL NOT NULL,
    hook_text     TEXT,
    title         TEXT,
    caption       TEXT,
    hashtags      TEXT,               -- space separated
    reasoning     TEXT,
    status        TEXT NOT NULL DEFAULT 'candidate',  -- candidate | rejected | rendered | queued | failed
    reason        TEXT,
    media_url     TEXT,               -- Post for Me public media URL after upload
    slot_at       TEXT,               -- UTC ISO time the clip is scheduled for
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS clips_video ON clips(video_id);
CREATE TABLE IF NOT EXISTS posts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id       TEXT NOT NULL,
    campaign_id   TEXT NOT NULL,
    platform      TEXT NOT NULL,
    account_id    TEXT NOT NULL,
    attempt       INTEGER NOT NULL,
    external_id   TEXT NOT NULL UNIQUE,
    pfm_post_id   TEXT,
    scheduled_at  TEXT NOT NULL,
    status        TEXT NOT NULL,      -- creating | scheduled | published | failed | superseded
    url           TEXT,
    error         TEXT,
    reported      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS seen_campaigns (
    url           TEXT PRIMARY KEY,
    name          TEXT,
    first_seen    TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def upsert_video(conn: sqlite3.Connection, video_id: str, campaign_id: str, url: str,
                 title: str | None, duration: float | None) -> sqlite3.Row:
    ts = now_iso()
    conn.execute(
        """INSERT INTO videos (video_id, campaign_id, url, title, duration, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(video_id) DO UPDATE SET
             title = COALESCE(excluded.title, videos.title),
             duration = COALESCE(excluded.duration, videos.duration),
             updated_at = excluded.updated_at""",
        (video_id, campaign_id, url, title, duration, ts, ts),
    )
    conn.commit()
    return conn.execute("SELECT * FROM videos WHERE video_id = ?", (video_id,)).fetchone()


def update_video(conn: sqlite3.Connection, video_id: str, **fields) -> None:
    fields["updated_at"] = now_iso()
    cols = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE videos SET {cols} WHERE video_id = ?", (*fields.values(), video_id))
    conn.commit()


def update_clip(conn: sqlite3.Connection, clip_id: str, **fields) -> None:
    fields["updated_at"] = now_iso()
    cols = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE clips SET {cols} WHERE clip_id = ?", (*fields.values(), clip_id))
    conn.commit()


def used_ranges(conn: sqlite3.Connection, video_id: str) -> list[tuple[float, float]]:
    """Segments already queued/posted or in progress for a video (candidates excluded)."""
    rows = conn.execute(
        "SELECT start, end FROM clips WHERE video_id = ? AND status IN ('rendered', 'queued')",
        (video_id,),
    ).fetchall()
    return [(r["start"], r["end"]) for r in rows]


def update_post(conn: sqlite3.Connection, post_row_id: int, **fields) -> None:
    fields["updated_at"] = now_iso()
    cols = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE posts SET {cols} WHERE id = ?", (*fields.values(), post_row_id))
    conn.commit()
