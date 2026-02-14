#!/usr/bin/env python3
"""
generate.py – Build static HTML pages from config/content.json.

Usage:
    python3 generate.py

Reads config/content.json and writes ready-to-serve HTML into static/.
"""

import json
from html import escape
from pathlib import Path

STATIC_DIR = Path("static")
CONFIG_PATH = Path("config/content.json")
VERSION = "1.0.0"

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    C = json.load(f)

BASE = C["basePath"]
SITE = C["site"]


# ── Layout helpers ──────────────────────────────────────────────────
def _head(title: str, theme_color: str | None = None) -> str:
    tc = (
        f"\n    <style>:root{{--theme-color:{theme_color}}}</style>"
        if theme_color
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape(title)}</title>
    <meta name="description" content="{escape(SITE['tagline'])}">
    <link rel="icon" type="image/svg+xml" href="{BASE}/assets/img/favicon.svg">
    <link rel="icon" type="image/png" sizes="192x192" href="{BASE}/assets/img/icon-192.png">
    <link rel="apple-touch-icon" href="{BASE}/assets/img/apple-touch-icon.png">
    <link rel="manifest" href="{BASE}/manifest.json">
    <meta name="theme-color" content="#1E6FB9">
    <link rel="stylesheet" href="{BASE}/assets/css/style.css">{tc}
</head>"""


def _header_home() -> str:
    return f"""    <header class="site-header">
        <div class="container">
            <a href="{BASE}/" class="site-logo">Andreas Weiss</a>
            <span class="site-tagline">Kommunalwahl Rohrbach</span>
        </div>
    </header>"""


def _header_theme(theme_name: str, color: str) -> str:
    return f"""    <div class="theme-bar"></div>
    <header class="site-header">
        <div class="container">
            <a href="{BASE}/" class="back-link">&#8592; Zurück</a>
            <span class="page-theme" style="color:{color}">{escape(theme_name)}</span>
        </div>
    </header>"""


def _header_legal() -> str:
    return f"""    <header class="site-header">
        <div class="container">
            <a href="{BASE}/" class="back-link">&#8592; Zurück</a>
            <span class="site-tagline">Kommunalwahl Rohrbach</span>
        </div>
    </header>"""


def _footer() -> str:
    return f"""    <footer class="site-footer">
        <div class="container footer-main">
            <div class="footer-links">
                <a href="{BASE}/impressum/">Impressum</a>
                <a href="{BASE}/datenschutz/">Datenschutz</a>
            </div>
            <div class="footer-external">
                <a href="https://www.bewegung-paf.de/rohrbach" target="_blank" rel="noopener">SPD Rohrbach ↗</a>
                <a href="https://christian.keck.bayern/" target="_blank" rel="noopener">#Rohrbach2038 ↗</a>
            </div>
            <span style="color:#aaa;font-size:.7rem">v{VERSION}</span>
        </div>
    </footer>
    <script src="{BASE}/assets/js/main.js"></script>
</body>
</html>"""


# ── Page generators ─────────────────────────────────────────────────
def generate_home() -> str:
    home = C["home"]
    about = C["aboutBox"]

    tiles = ""
    for tile in home["tiles"]:
        page = next((p for p in C["pages"] if p["slug"] == tile["slug"]), None)
        color = page["color"] if page else "#1E6FB9"
        tiles += f"""            <a href="{BASE}/{tile['slug']}/" class="card-link" style="border-left-color:{color}">
                <h3>{escape(tile['title'])}</h3>
                <p>{escape(tile['subtitle'])}</p>
            </a>
"""

    return f"""{_head(SITE['title'])}
<body data-page="home">
{_header_home()}
    <main class="container">
        <section class="hero">
            <div class="candidate-header">
                <img src="{BASE}/assets/img/portrait.jpg" alt="Andreas Weiss" class="portrait"
                     onerror="this.style.display='none'">
                <div class="candidate-info">
                    <p class="name">Andreas Weiss</p>
                    <p class="party">
                        <img src="{BASE}/assets/img/spd-logo.svg" alt="SPD" class="party-logo"
                             onerror="this.style.display='none'">
                        Kommunalwahl Rohrbach
                    </p>
                </div>
            </div>
            <span class="election-badge">Wahl am {escape(SITE['electionDate'])}</span>
            <h1>{escape(home['headline'])}</h1>
            <p>{escape(home['text'])}</p>
        </section>

        <div class="cta-banner">
            <p>Ich würde mich über 3 Stimmen auf Ihrem Stimmzettel freuen!</p>
            <p class="cta-sub">Kommunalwahl Rohrbach &middot; {escape(SITE['electionDate'])}</p>
        </div>

        <div class="cards-grid">
{tiles}        </div>

        <section class="about-box">
            <h2>{escape(about['title'])}</h2>
            <p>{escape(about['text'])}</p>
            <p class="name-line">{escape(about['nameLine'])}</p>
        </section>

        <section class="partner-section">
            <h2>Netzwerk &amp; Partner</h2>
            <div class="partner-cards">
                <a href="https://www.bewegung-paf.de/rohrbach" target="_blank" rel="noopener" class="partner-card">
                    <span class="partner-label">SPD Rohrbach</span>
                    <span class="partner-url">bewegung-paf.de/rohrbach ↗</span>
                </a>
                <a href="https://christian.keck.bayern/" target="_blank" rel="noopener" class="partner-card">
                    <span class="partner-label">#Rohrbach2038</span>
                    <span class="partner-url">christian.keck.bayern ↗</span>
                </a>
            </div>
        </section>
    </main>
{_footer()}"""


def generate_theme(page: dict) -> str:
    poll = page["poll"]
    quiz = page["quiz"]

    poll_opts = "\n".join(
        f'                    <button class="option-btn" data-option="{escape(o)}">{escape(o)}</button>'
        for o in poll["options"]
    )

    quiz_opts = "\n".join(
        f'                    <button class="option-btn" data-option="{escape(o)}">{escape(o)}</button>'
        for o in quiz["options"]
    )

    return f"""{_head(f"{page['theme']} – {SITE['title']}", page['color'])}
<body data-page="{page['slug']}">
{_header_theme(page['theme'], page['color'])}
    <main class="container">
        <section class="hero">
            <h1>{escape(page['headline'])}</h1>
            <p>{escape(page['text'])}</p>
        </section>

        <section class="section-card poll-section" data-poll-id="{escape(poll['id'])}" data-page="{escape(page['slug'])}">
            <h2>&#x1F5F3;&#xFE0F; {escape(poll['question'])}</h2>
            <div class="options">
{poll_opts}
            </div>
            <div class="results hidden"></div>
        </section>

        <section class="section-card quiz-section" data-quiz-id="{escape(quiz['id'])}" data-page="{escape(page['slug'])}">
            <p class="intro">{escape(quiz['intro'])}</p>
            <h2>&#x2753; {escape(quiz['question'])}</h2>
            <div class="options">
{quiz_opts}
            </div>
            <div class="quiz-feedback hidden"></div>
        </section>

        <section class="section-card feedback-form" data-page="{escape(page['slug'])}">
            <h2>&#x1F4AC; Deine Meinung zu {escape(page['theme'])}</h2>
            <textarea placeholder="Was denkst du zu diesem Thema? Was fehlt? Was w&#252;rdest du dir w&#252;nschen?" maxlength="1000"></textarea>
            <span class="char-count" style="font-size:.75rem;color:#6e6e73">0 / 1000</span>
            <div style="margin-top:.5rem">
                <button class="submit-btn">Absenden</button>
            </div>
            <p class="feedback-success hidden"></p>
        </section>
    </main>
{_footer()}"""


def generate_impressum() -> str:
    return f"""{_head(f"Impressum – {SITE['title']}")}
<body data-page="impressum">
{_header_legal()}
    <main class="container">
        <section class="legal-content">
            <h1>Impressum</h1>

            <h2>Angaben gemäß § 5 TMG</h2>
            <p>
                <strong>Andreas Weiss</strong><br>
                [Straße und Hausnr.]<br>
                [PLZ] Rohrbach
            </p>

            <h2>Kontakt</h2>
            <p>
                Telefon: [Telefonnummer]<br>
                E-Mail: [E-Mail-Adresse]
            </p>

            <h2>Verantwortlich für den Inhalt</h2>
            <p>Andreas Weiss (Anschrift wie oben)</p>

            <h2>Hinweis</h2>
            <p>Diese Website dient der Information über die Kandidatur von Andreas Weiss
               für die Kommunalwahl Rohrbach. Es handelt sich um eine private,
               nicht-kommerzielle Seite.</p>
        </section>
    </main>
{_footer()}"""


def generate_datenschutz() -> str:
    return f"""{_head(f"Datenschutz – {SITE['title']}")}
<body data-page="datenschutz">
{_header_legal()}
    <main class="container">
        <section class="legal-content">
            <h1>Datenschutzerklärung</h1>

            <h2>1. Verantwortlicher</h2>
            <p>Andreas Weiss, [Adresse] – siehe
               <a href="{BASE}/impressum/">Impressum</a>.</p>

            <h2>2. Was wir speichern</h2>
            <p>Diese Website erhebt <strong>keine personenbezogenen Daten</strong>
               im klassischen Sinne. Es werden keine Cookies gesetzt und keine
               Drittanbieter-Dienste eingebunden.</p>
            <p>Folgende Daten werden serverseitig erfasst:</p>
            <ul>
                <li><strong>Seitenaufrufe:</strong> Welche Seite besucht wurde,
                    Zeitpunkt, grober Standort (Stadt/Region/Land), Referrer.</li>
                <li><strong>Umfrage-Stimmen:</strong> Gewählte Option, Zeitpunkt,
                    grober Standort.</li>
                <li><strong>Quiz-Antworten:</strong> Gewählte Option, ob korrekt,
                    Zeitpunkt, grober Standort.</li>
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
               Social-Media-Plugins oder sonstige Drittanbieter-Dienste
               eingebunden.</p>

            <h2>7. Ihre Rechte</h2>
            <p>Da keine personenbezogenen Daten im Sinne der DSGVO gespeichert
               werden, entfallen die üblichen Betroffenenrechte. Bei Fragen wenden
               Sie sich an die im Impressum genannte Kontaktadresse.</p>
        </section>
    </main>
{_footer()}"""


# ── Write helper ────────────────────────────────────────────────────
def _write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  ✓ {path}")


# ── Main ────────────────────────────────────────────────────────────
def main():
    print("Generating pages from config/content.json …")

    _write(STATIC_DIR / "index.html", generate_home())

    for page in C["pages"]:
        _write(STATIC_DIR / page["slug"] / "index.html", generate_theme(page))

    _write(STATIC_DIR / "impressum" / "index.html", generate_impressum())
    _write(STATIC_DIR / "datenschutz" / "index.html", generate_datenschutz())

    print(f"Done – {2 + len(C['pages'])} pages generated.")


if __name__ == "__main__":
    main()
