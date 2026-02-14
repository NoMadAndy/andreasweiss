"""SQLite database – multi-tenant schema for Wahlplattform."""

import json
import os
import sqlite3

DB_PATH = os.environ.get("DB_PATH", "/data/wahl2026.db")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = get_db()
    conn.executescript("""
        -- ── Candidates ──────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS candidates (
            slug            TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            party           TEXT DEFAULT '',
            tagline         TEXT DEFAULT '',
            election_date   TEXT DEFAULT '',
            headline        TEXT DEFAULT '',
            intro_text      TEXT DEFAULT '',
            about_title     TEXT DEFAULT 'Über mich',
            about_text      TEXT DEFAULT '',
            about_name_line TEXT DEFAULT '',
            cta_text        TEXT DEFAULT '',
            cta_sub         TEXT DEFAULT '',
            theme_color     TEXT DEFAULT '#1E6FB9',
            impressum_html  TEXT DEFAULT '',
            datenschutz_html TEXT DEFAULT '',
            admin_user      TEXT NOT NULL,
            admin_pass      TEXT NOT NULL,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- ── Candidate Pages (themes with polls/quizzes) ─────────
        CREATE TABLE IF NOT EXISTS candidate_pages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_slug  TEXT NOT NULL,
            slug            TEXT NOT NULL,
            theme           TEXT NOT NULL,
            color           TEXT DEFAULT '#1E6FB9',
            headline        TEXT DEFAULT '',
            text            TEXT DEFAULT '',
            tile_title      TEXT DEFAULT '',
            tile_subtitle   TEXT DEFAULT '',
            poll_id         TEXT,
            poll_question   TEXT DEFAULT '',
            poll_options    TEXT DEFAULT '[]',
            quiz_id         TEXT,
            quiz_intro      TEXT DEFAULT '',
            quiz_question   TEXT DEFAULT '',
            quiz_options    TEXT DEFAULT '[]',
            quiz_correct    TEXT DEFAULT '',
            quiz_explain    TEXT DEFAULT '',
            sort_order      INTEGER DEFAULT 0,
            UNIQUE(candidate_slug, slug),
            FOREIGN KEY (candidate_slug) REFERENCES candidates(slug) ON DELETE CASCADE
        );

        -- ── External Links ──────────────────────────────────────
        CREATE TABLE IF NOT EXISTS candidate_links (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_slug  TEXT NOT NULL,
            label           TEXT NOT NULL,
            url             TEXT NOT NULL,
            sort_order      INTEGER DEFAULT 0,
            FOREIGN KEY (candidate_slug) REFERENCES candidates(slug) ON DELETE CASCADE
        );

        -- ── Analytics: Visits ───────────────────────────────────
        CREATE TABLE IF NOT EXISTS visits (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT NOT NULL DEFAULT (datetime('now')),
            candidate_slug  TEXT NOT NULL DEFAULT '',
            page            TEXT NOT NULL,
            city            TEXT DEFAULT 'unknown',
            region          TEXT DEFAULT 'unknown',
            country         TEXT DEFAULT 'unknown',
            uniq_day_hash   TEXT,
            user_agent_short TEXT,
            ref             TEXT
        );

        -- ── Analytics: Polls ────────────────────────────────────
        CREATE TABLE IF NOT EXISTS poll_votes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT NOT NULL DEFAULT (datetime('now')),
            candidate_slug  TEXT NOT NULL DEFAULT '',
            page            TEXT NOT NULL,
            poll_id         TEXT NOT NULL,
            option          TEXT NOT NULL,
            city            TEXT DEFAULT 'unknown',
            region          TEXT DEFAULT 'unknown',
            country         TEXT DEFAULT 'unknown',
            uniq_day_hash   TEXT
        );

        -- ── Analytics: Quiz ─────────────────────────────────────
        CREATE TABLE IF NOT EXISTS quiz_answers (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT NOT NULL DEFAULT (datetime('now')),
            candidate_slug  TEXT NOT NULL DEFAULT '',
            page            TEXT NOT NULL,
            quiz_id         TEXT NOT NULL,
            option          TEXT NOT NULL,
            is_correct      INTEGER NOT NULL DEFAULT 0,
            city            TEXT DEFAULT 'unknown',
            region          TEXT DEFAULT 'unknown',
            country         TEXT DEFAULT 'unknown',
            uniq_day_hash   TEXT
        );

        -- ── Analytics: Feedback ─────────────────────────────────
        CREATE TABLE IF NOT EXISTS feedback (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT NOT NULL DEFAULT (datetime('now')),
            candidate_slug  TEXT NOT NULL DEFAULT '',
            page            TEXT NOT NULL,
            message         TEXT NOT NULL,
            city            TEXT DEFAULT 'unknown',
            region          TEXT DEFAULT 'unknown',
            country         TEXT DEFAULT 'unknown',
            uniq_day_hash   TEXT
        );

        -- ── Indexes ─────────────────────────────────────────────
        CREATE INDEX IF NOT EXISTS idx_visits_cand   ON visits(candidate_slug);
        CREATE INDEX IF NOT EXISTS idx_visits_page   ON visits(page);
        CREATE INDEX IF NOT EXISTS idx_visits_ts     ON visits(ts);
        CREATE INDEX IF NOT EXISTS idx_visits_hash   ON visits(uniq_day_hash);
        CREATE INDEX IF NOT EXISTS idx_poll_cand     ON poll_votes(candidate_slug);
        CREATE INDEX IF NOT EXISTS idx_poll_poll     ON poll_votes(poll_id);
        CREATE INDEX IF NOT EXISTS idx_poll_hash     ON poll_votes(uniq_day_hash);
        CREATE INDEX IF NOT EXISTS idx_quiz_cand     ON quiz_answers(candidate_slug);
        CREATE INDEX IF NOT EXISTS idx_quiz_quiz     ON quiz_answers(quiz_id);
        CREATE INDEX IF NOT EXISTS idx_fb_cand       ON feedback(candidate_slug);
        CREATE INDEX IF NOT EXISTS idx_fb_page       ON feedback(page);
        CREATE INDEX IF NOT EXISTS idx_fb_ts         ON feedback(ts);

        -- ── Platform Settings ───────────────────────────────────
        CREATE TABLE IF NOT EXISTS platform_settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        );
    """)
    # Seed default platform settings if empty
    defaults = {
        "site_title": "Wahlplattform",
        "site_subtitle": "Gemeinsam für unsere Gemeinde",
        "hero_headline": "Willkommen",
        "hero_text": "Lernen Sie unsere Kandidaten kennen – mit Umfragen, Quiz und Bürgerbeteiligung.",
        "campaign_title": "",
        "campaign_text": "",
        "footer_text": "Wahlplattform",
        "show_candidates": "1",
        "redirect_url": "",
    }
    existing = conn.execute("SELECT COUNT(*) c FROM platform_settings").fetchone()[0]
    if existing == 0:
        conn.executemany(
            "INSERT INTO platform_settings (key, value) VALUES (?, ?)",
            defaults.items(),
        )
        conn.commit()
    else:
        # Ensure new keys are added to existing installations
        for k, v in defaults.items():
            conn.execute(
                "INSERT OR IGNORE INTO platform_settings (key, value) VALUES (?, ?)",
                (k, v),
            )
        conn.commit()
    conn.close()


# ── Helpers ────────────────────────────────────────────────────────
def get_platform_settings() -> dict:
    """Return all platform settings as a dict."""
    db = get_db()
    try:
        rows = db.execute("SELECT key, value FROM platform_settings").fetchall()
        return {r["key"]: r["value"] for r in rows}
    finally:
        db.close()


def set_platform_settings(settings: dict):
    """Upsert platform settings from a dict."""
    db = get_db()
    try:
        for k, v in settings.items():
            db.execute(
                "INSERT INTO platform_settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (k, v),
            )
        db.commit()
    finally:
        db.close()


def get_candidate(slug: str) -> dict | None:
    """Return candidate row as dict, or None."""
    db = get_db()
    try:
        row = db.execute("SELECT * FROM candidates WHERE slug=?", (slug,)).fetchone()
        return dict(row) if row else None
    finally:
        db.close()


def get_candidate_pages(slug: str) -> list[dict]:
    """Return all pages for a candidate, ordered by sort_order."""
    db = get_db()
    try:
        rows = db.execute(
            "SELECT * FROM candidate_pages WHERE candidate_slug=? ORDER BY sort_order, id",
            (slug,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["poll_options"] = json.loads(d["poll_options"]) if d["poll_options"] else []
            d["quiz_options"] = json.loads(d["quiz_options"]) if d["quiz_options"] else []
            result.append(d)
        return result
    finally:
        db.close()


def get_candidate_links(slug: str) -> list[dict]:
    """Return all external links for a candidate."""
    db = get_db()
    try:
        rows = db.execute(
            "SELECT * FROM candidate_links WHERE candidate_slug=? ORDER BY sort_order, id",
            (slug,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


def get_all_candidates() -> list[dict]:
    """Return all candidates (slug, name, party, tagline)."""
    db = get_db()
    try:
        rows = db.execute(
            "SELECT slug, name, party, tagline, election_date, theme_color, created_at "
            "FROM candidates ORDER BY created_at",
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()
