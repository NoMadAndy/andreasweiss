#!/usr/bin/env python3
"""
migrate.py – Migrate Andreas Weiss data from content.json + old DB into new multi-tenant schema.

Usage:
    python3 migrate.py

This runs inside the api container after the new schema is initialized.
"""

import json
import os
import sqlite3
import sys

DB_PATH = os.environ.get("DB_PATH", "/data/wahl2026.db")
OLD_DB_PATH = os.environ.get("OLD_DB_PATH", "/data/andreasweiss.db")
CONFIG_PATH = os.environ.get("CONFIG_PATH", "/app/config/content.json")

SLUG = "andreasweiss"
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "changeme")


def get_db(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def migrate():
    print(f"🔄 Migrating '{SLUG}' into {DB_PATH} ...")

    # Load content.json
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            content = json.load(f)
        print(f"  ✓ Loaded {CONFIG_PATH}")
    else:
        print(f"  ⚠ {CONFIG_PATH} not found, skipping content migration")
        content = None

    db = get_db(DB_PATH)

    # Check if candidate already exists
    existing = db.execute("SELECT slug FROM candidates WHERE slug=?", (SLUG,)).fetchone()
    if existing:
        print(f"  ⚠ Candidate '{SLUG}' already exists, skipping candidate creation")
    elif content:
        site = content["site"]
        home = content["home"]
        about = content["aboutBox"]

        # Insert candidate
        db.execute(
            "INSERT INTO candidates (slug, name, party, tagline, election_date, "
            "headline, intro_text, about_title, about_text, about_name_line, "
            "cta_text, cta_sub, theme_color, admin_user, admin_pass, "
            "impressum_html, datenschutz_html) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                SLUG,
                "Andreas Weiss",
                "SPD",
                "Kommunalwahl Rohrbach",
                site.get("electionDate", "08.03.2026"),
                home.get("headline", ""),
                home.get("text", ""),
                about.get("title", "Über mich"),
                about.get("text", ""),
                about.get("nameLine", ""),
                "Ich würde mich über 3 Stimmen auf Ihrem Stimmzettel freuen!",
                f"Kommunalwahl Rohrbach · {site.get('electionDate', '08.03.2026')}",
                "#1E6FB9",
                ADMIN_USER,
                ADMIN_PASS,
                _impressum_html(),
                _datenschutz_html(),
            ),
        )
        print(f"  ✓ Created candidate '{SLUG}'")

        # Insert pages
        for i, page in enumerate(content.get("pages", [])):
            poll = page.get("poll", {})
            quiz = page.get("quiz", {})
            tile = next(
                (t for t in home.get("tiles", []) if t["slug"] == page["slug"]),
                {"title": page["theme"], "subtitle": ""},
            )
            db.execute(
                "INSERT INTO candidate_pages "
                "(candidate_slug, slug, theme, color, headline, text, "
                "tile_title, tile_subtitle, poll_id, poll_question, poll_options, "
                "quiz_id, quiz_intro, quiz_question, quiz_options, quiz_correct, quiz_explain, sort_order) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    SLUG,
                    page["slug"],
                    page["theme"],
                    page.get("color", "#1E6FB9"),
                    page.get("headline", ""),
                    page.get("text", ""),
                    tile.get("title", page["theme"]),
                    tile.get("subtitle", ""),
                    poll.get("id", ""),
                    poll.get("question", ""),
                    json.dumps(poll.get("options", [])),
                    quiz.get("id", ""),
                    quiz.get("intro", ""),
                    quiz.get("question", ""),
                    json.dumps(quiz.get("options", [])),
                    quiz.get("correct", ""),
                    quiz.get("explainCorrect", ""),
                    i,
                ),
            )
            print(f"  ✓ Page: {page['slug']}")

        # Insert links
        links = [
            ("SPD Rohrbach", "https://www.bewegung-paf.de/rohrbach"),
            ("#Rohrbach2038", "https://christian.keck.bayern/"),
        ]
        for i, (label, url) in enumerate(links):
            db.execute(
                "INSERT INTO candidate_links (candidate_slug, label, url, sort_order) VALUES (?,?,?,?)",
                (SLUG, label, url, i),
            )
        print(f"  ✓ {len(links)} links added")

        db.commit()

    # Migrate old analytics data
    if os.path.exists(OLD_DB_PATH):
        print(f"  🔄 Migrating analytics from {OLD_DB_PATH} ...")
        old_db = get_db(OLD_DB_PATH)

        # Check if visits already have data for this candidate
        existing_visits = db.execute(
            "SELECT COUNT(*) as c FROM visits WHERE candidate_slug=?", (SLUG,)
        ).fetchone()["c"]

        if existing_visits > 0:
            print(f"  ⚠ Already {existing_visits} visits for '{SLUG}', skipping analytics migration")
        else:
            # Visits
            old_visits = old_db.execute("SELECT * FROM visits").fetchall()
            for v in old_visits:
                db.execute(
                    "INSERT INTO visits (ts, candidate_slug, page, city, region, country, uniq_day_hash, user_agent_short, ref) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (v["ts"], SLUG, v["page"], v["city"], v["region"], v["country"],
                     v["uniq_day_hash"], v["user_agent_short"], v["ref"]),
                )
            print(f"  ✓ {len(old_visits)} visits migrated")

            # Poll votes
            old_polls = old_db.execute("SELECT * FROM poll_votes").fetchall()
            for p in old_polls:
                db.execute(
                    "INSERT INTO poll_votes (ts, candidate_slug, page, poll_id, option, city, region, country, uniq_day_hash) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (p["ts"], SLUG, p["page"], p["poll_id"], p["option"],
                     p["city"], p["region"], p["country"], p["uniq_day_hash"]),
                )
            print(f"  ✓ {len(old_polls)} poll votes migrated")

            # Quiz answers
            old_quiz = old_db.execute("SELECT * FROM quiz_answers").fetchall()
            for q in old_quiz:
                db.execute(
                    "INSERT INTO quiz_answers (ts, candidate_slug, page, quiz_id, option, is_correct, city, region, country, uniq_day_hash) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (q["ts"], SLUG, q["page"], q["quiz_id"], q["option"], q["is_correct"],
                     q["city"], q["region"], q["country"], q["uniq_day_hash"]),
                )
            print(f"  ✓ {len(old_quiz)} quiz answers migrated")

            # Feedback
            old_fb = old_db.execute("SELECT * FROM feedback").fetchall()
            for f in old_fb:
                db.execute(
                    "INSERT INTO feedback (ts, candidate_slug, page, message, city, region, country, uniq_day_hash) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (f["ts"], SLUG, f["page"], f["message"],
                     f["city"], f["region"], f["country"], f["uniq_day_hash"]),
                )
            print(f"  ✓ {len(old_fb)} feedback entries migrated")

            db.commit()
        old_db.close()
    else:
        print(f"  ℹ Old DB {OLD_DB_PATH} not found, skipping analytics migration")

    db.close()
    print("✅ Migration complete!")


def _impressum_html():
    return """<h1>Impressum</h1>
<h2>Angaben gemäß § 5 TMG</h2>
<p><strong>Andreas Weiss</strong><br>[Straße und Hausnr.]<br>[PLZ] Rohrbach</p>
<h2>Kontakt</h2>
<p>Telefon: [Telefonnummer]<br>E-Mail: [E-Mail-Adresse]</p>
<h2>Verantwortlich für den Inhalt</h2>
<p>Andreas Weiss (Anschrift wie oben)</p>
<h2>Hinweis</h2>
<p>Diese Website dient der Information über die Kandidatur von Andreas Weiss
für die Kommunalwahl Rohrbach. Es handelt sich um eine private,
nicht-kommerzielle Seite.</p>"""


def _datenschutz_html():
    return """<h1>Datenschutzerklärung</h1>
<h2>1. Verantwortlicher</h2>
<p>Andreas Weiss, [Adresse] – siehe <a href="/andreasweiss/impressum/">Impressum</a>.</p>
<h2>2. Was wir speichern</h2>
<p>Diese Website erhebt <strong>keine personenbezogenen Daten</strong>
im klassischen Sinne. Es werden keine Cookies gesetzt und keine
Drittanbieter-Dienste eingebunden.</p>
<p>Folgende Daten werden serverseitig erfasst:</p>
<ul>
<li><strong>Seitenaufrufe:</strong> Welche Seite besucht wurde, Zeitpunkt,
grober Standort (Stadt/Region/Land), Referrer.</li>
<li><strong>Umfrage-Stimmen:</strong> Gewählte Option, Zeitpunkt, grober Standort.</li>
<li><strong>Quiz-Antworten:</strong> Gewählte Option, ob korrekt, Zeitpunkt, grober Standort.</li>
</ul>
<h2>3. Keine IP-Speicherung</h2>
<p>Ihre IP-Adresse wird <strong>nicht</strong> gespeichert. Zur Erkennung
von Mehrfach-Abstimmungen wird ein tagesbasierter Hash erzeugt
(SHA-256 aus IP + Datum + geheimer Salt). Dieser Hash ist nicht auf
die IP-Adresse rückrechenbar.</p>
<h2>4. Standortbestimmung</h2>
<p>Die grobe Standortbestimmung (Stadt, Region, Land) erfolgt über eine
lokal eingebundene Datenbank (MaxMind GeoLite2). Es werden
<strong>keine externen Dienste</strong> kontaktiert.</p>
<h2>5. Keine Cookies</h2>
<p>Diese Website verwendet <strong>keine Cookies</strong>. Zur lokalen
Speicherung Ihrer Abstimmungs-Teilnahme wird ausschließlich der
localStorage Ihres Browsers genutzt. Diese Daten verlassen
Ihren Browser nicht.</p>
<h2>6. Keine Drittanbieter</h2>
<p>Es werden keine externen Schriftarten, Analyse-Tools,
Social-Media-Plugins oder sonstige Drittanbieter-Dienste eingebunden.</p>
<h2>7. Ihre Rechte</h2>
<p>Da keine personenbezogenen Daten im Sinne der DSGVO gespeichert
werden, entfallen die üblichen Betroffenenrechte. Bei Fragen wenden
Sie sich an die im Impressum genannte Kontaktadresse.</p>"""


if __name__ == "__main__":
    migrate()
