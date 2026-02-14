"""SQLite database module – visits, poll votes, quiz answers."""

import os
import sqlite3

DB_PATH = os.environ.get("DB_PATH", "/data/andreasweiss.db")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS visits (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT    NOT NULL DEFAULT (datetime('now')),
            page            TEXT    NOT NULL,
            city            TEXT    DEFAULT 'unknown',
            region          TEXT    DEFAULT 'unknown',
            country         TEXT    DEFAULT 'unknown',
            uniq_day_hash   TEXT,
            user_agent_short TEXT,
            ref             TEXT
        );

        CREATE TABLE IF NOT EXISTS poll_votes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT    NOT NULL DEFAULT (datetime('now')),
            page            TEXT    NOT NULL,
            poll_id         TEXT    NOT NULL,
            option          TEXT    NOT NULL,
            city            TEXT    DEFAULT 'unknown',
            region          TEXT    DEFAULT 'unknown',
            country         TEXT    DEFAULT 'unknown',
            uniq_day_hash   TEXT
        );

        CREATE TABLE IF NOT EXISTS quiz_answers (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT    NOT NULL DEFAULT (datetime('now')),
            page            TEXT    NOT NULL,
            quiz_id         TEXT    NOT NULL,
            option          TEXT    NOT NULL,
            is_correct      INTEGER NOT NULL DEFAULT 0,
            city            TEXT    DEFAULT 'unknown',
            region          TEXT    DEFAULT 'unknown',
            country         TEXT    DEFAULT 'unknown',
            uniq_day_hash   TEXT
        );

        CREATE TABLE IF NOT EXISTS feedback (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT    NOT NULL DEFAULT (datetime('now')),
            page            TEXT    NOT NULL,
            message         TEXT    NOT NULL,
            city            TEXT    DEFAULT 'unknown',
            region          TEXT    DEFAULT 'unknown',
            country         TEXT    DEFAULT 'unknown',
            uniq_day_hash   TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_visits_page   ON visits(page);
        CREATE INDEX IF NOT EXISTS idx_visits_ts     ON visits(ts);
        CREATE INDEX IF NOT EXISTS idx_visits_hash   ON visits(uniq_day_hash);
        CREATE INDEX IF NOT EXISTS idx_poll_poll     ON poll_votes(poll_id);
        CREATE INDEX IF NOT EXISTS idx_poll_hash     ON poll_votes(uniq_day_hash);
        CREATE INDEX IF NOT EXISTS idx_quiz_quiz     ON quiz_answers(quiz_id);
        CREATE INDEX IF NOT EXISTS idx_feedback_page ON feedback(page);
        CREATE INDEX IF NOT EXISTS idx_feedback_ts   ON feedback(ts);
    """)
    conn.close()
