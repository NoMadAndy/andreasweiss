"""SQLite database – multi-tenant schema for Wahlplattform."""

import json
import os
import sqlite3

DB_PATH = os.environ.get("DB_PATH", "/data/wahl2026.db")

# ── Default Wahlinfo Content ──────────────────────────────────────
_DEFAULT_WAHLINFO = """## 🗳️ Kommunalwahl am 9. März 2026

Am **9. März 2026** finden in ganz Bayern die Kommunalwahlen statt. In **Rohrbach an der Ilm** werden der **Gemeinderat** und der/die **Bürgermeister/in** gewählt. Gleichzeitig finden die **Kreistagswahl** und die **Landratswahl** im Landkreis Pfaffenhofen a.d. Ilm statt.

---

## 📋 Was wird gewählt?

### Gemeinderatswahl
- Der Gemeinderat von Rohrbach besteht aus **16 Mitgliedern** (plus Bürgermeister/in)
- Sie haben **16 Stimmen**, die Sie auf die Kandidaten verteilen können
- **Kumulieren**: Sie können einem Kandidaten bis zu **3 Stimmen** geben
- **Panaschieren**: Sie können Ihre Stimmen auf Kandidaten **verschiedener Listen** verteilen

### Bürgermeisterwahl
- Hier haben Sie **1 Stimme** für Ihren Wunschkandidaten
- Erreicht kein Kandidat mehr als 50% der Stimmen, findet eine **Stichwahl** am 23. März 2026 statt

---

## ✏️ Der Stimmzettel – So funktioniert's

### Variante 1: Nur ein Kreuz bei einer Liste
Sie machen **ein Kreuz oben bei einer Partei/Liste**. Dann erhält jeder Kandidat auf dieser Liste automatisch eine Stimme – bis alle 16 Stimmen verteilt sind.

### Variante 2: Einzelne Kandidaten ankreuzen
Sie verteilen Ihre **16 Stimmen einzeln** an beliebige Kandidaten – auch über Parteigrenzen hinweg. Pro Kandidat sind **maximal 3 Stimmen** möglich.

### Variante 3: Listenstimme + Einzelstimmen kombinieren
Sie kreuzen **eine Liste an** und verändern diese, indem Sie einzelne Kandidaten zusätzlich ankreuzen oder streichen. Achtung: Die Gesamtzahl darf **16 Stimmen nicht überschreiten**.

> **Tipp:** Nehmen Sie sich Zeit für Ihren Stimmzettel! Informieren Sie sich vorab über die Kandidaten und deren Positionen.

---

## 🏛️ Kreistagswahl & Landratswahl

Gleichzeitig mit der Gemeinderatswahl wählen Sie auch den **Kreistag** des Landkreises Pfaffenhofen a.d. Ilm und den/die **Landrätin/Landrat**.

### Kreistag
- Der Kreistag hat **50 Sitze**
- Das Wahlverfahren ist identisch: **Kumulieren und Panaschieren**
- Sie haben **50 Stimmen** zu vergeben

### Warum lokale Kandidaten wichtig sind
Achten Sie bei der Kreistagswahl besonders auf **Kandidaten aus dem Gemeindebereich Rohrbach**! Je mehr Vertreter aus unserer Gemeinde im Kreistag sitzen, desto besser werden die Interessen von Rohrbach auf Landkreisebene vertreten – **unabhängig von der Partei**.

> **Überparteilicher Appell:** Wählen Sie Kandidaten aus Rohrbach – egal welcher Partei sie angehören. Lokale Vertretung ist wichtiger als Parteizugehörigkeit!

---

## 🎪 Antretende Parteien & Listen

### Gemeinderatswahl Rohrbach

- **SPD** – *Sozialdemokratische Partei Deutschlands* – Für soziale Gerechtigkeit, bezahlbares Wohnen und starke Gemeindepolitik
- **CSU** – *Christlich-Soziale Union*
- **Freie Wähler** – *Freie Wählergemeinschaft*
- **GRÜNE** – *Bündnis 90/Die Grünen*

### Kreistagswahl Landkreis Pfaffenhofen

Auch hier treten mehrere Listen an. Unterstützen Sie **Rohrbacher Kandidaten** auf allen Listen!

---

## 📌 Wichtige Infos

- **Wahltag:** Sonntag, 9. März 2026
- **Wahlzeit:** 8:00 – 18:00 Uhr
- **Wahlbenachrichtigung:** Kommt per Post – bitte mitbringen!
- **Briefwahl:** Kann im Rathaus oder online beantragt werden
- **Stichwahl** (falls nötig): 23. März 2026

### Was Sie brauchen
- Ihre **Wahlbenachrichtigung** (oder einen gültigen Ausweis)
- Etwas **Zeit** – der Stimmzettel ist groß!
- Einen **Kugelschreiber** (liegt auch im Wahllokal bereit)

---

## 🔴 Warum SPD wählen?

Die **SPD Rohrbach** setzt sich ein für:

- **Bezahlbaren Wohnraum** – Familien sollen sich das Leben in Rohrbach leisten können
- **Starke Infrastruktur** – Schnelles Internet, gute Straßen, ÖPNV-Anbindung
- **Kinder & Jugend** – Moderne Betreuungsangebote und Freizeitmöglichkeiten
- **Transparenz** – Offene Gemeindepolitik, bei der alle Bürger mitreden können
- **Nachhaltigkeit** – Klima- und umweltbewusste Entscheidungen für unsere Zukunft

[Mehr über unsere Kandidaten erfahren →](/)

---

*Haben Sie Fragen zur Wahl? Sprechen Sie uns an – wir helfen gerne!*
"""


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
            notify_email    TEXT DEFAULT '',
            notify_on_feedback INTEGER DEFAULT 0,
            notify_digest   INTEGER DEFAULT 0,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- ── Password Reset Tokens ───────────────────────────────
        CREATE TABLE IF NOT EXISTS password_resets (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_slug  TEXT NOT NULL,
            token           TEXT NOT NULL UNIQUE,
            expires_at      TEXT NOT NULL,
            used            INTEGER DEFAULT 0,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (candidate_slug) REFERENCES candidates(slug) ON DELETE CASCADE
        );

        -- ── Digest Tracking ─────────────────────────────────────
        CREATE TABLE IF NOT EXISTS digest_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_slug  TEXT NOT NULL,
            sent_at         TEXT NOT NULL DEFAULT (datetime('now')),
            feedback_count  INTEGER DEFAULT 0,
            visits_count    INTEGER DEFAULT 0
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
            device_type     TEXT DEFAULT 'unknown',
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
        CREATE INDEX IF NOT EXISTS idx_reset_token    ON password_resets(token);
        CREATE INDEX IF NOT EXISTS idx_reset_slug     ON password_resets(candidate_slug);
        CREATE INDEX IF NOT EXISTS idx_digest_slug    ON digest_log(candidate_slug);

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
        "wahlinfo_enabled": "0",
        "wahlinfo_title": "Wahlinfo",
        "wahlinfo_content": _DEFAULT_WAHLINFO,
        "smtp_host": "",
        "smtp_port": "587",
        "smtp_user": "",
        "smtp_pass": "",
        "smtp_from": "",
        "smtp_tls": "1",
        "digest_hour": "7",
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
    # ── Migrations: add new columns to existing tables ────────
    _migrate_columns(conn, "candidates", {
        "notify_email": "TEXT DEFAULT ''",
        "notify_on_feedback": "INTEGER DEFAULT 0",
        "notify_digest": "INTEGER DEFAULT 0",
    })
    _migrate_columns(conn, "visits", {
        "device_type": "TEXT DEFAULT 'unknown'",
    })
    conn.close()


# ── Helpers ────────────────────────────────────────────────────────

def _migrate_columns(conn: sqlite3.Connection, table: str, columns: dict):
    """Add missing columns to an existing table (safe ALTER TABLE)."""
    existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for col, typedef in columns.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")
    conn.commit()


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
