DU BIST: Senior Full-Stack Engineer (sehr pragmatisch, sicher, DSGVO-bewusst).
ZIEL: Baue eine simple Mini-Website im Unterpfad:
https://macherwerkstatt.cc/andreasweiss
BASE-PATH: /andreasweiss (muss überall funktionieren).

WICHTIGER ANSATZ:
- Die Inhalte kommen aus EINER Datei: content.json (liegt im Projekt unter /config/content.json).
- Der Generator/Renderer soll daraus die Startseite und 4 Themenseiten automatisch bauen.

ROUTES:
- GET  /andreasweiss/                      Startseite (aus content.json->home)
- GET  /andreasweiss/:slug                 (slug in {kinder,jugend,familie,innovation})
- GET  /andreasweiss/impressum
- GET  /andreasweiss/datenschutz
- GET  /andreasweiss/admin                 Admin UI (Auth)
- API: /andreasweiss/api/*

FRONTEND (sehr leicht):
- Statisches HTML/CSS/JS (no heavy framework).
- Jede Themenseite rendert:
  headline + text + Poll (4 Buttons) + Quiz (4 Buttons) + Ergebnisbereich.
- Nach Vote/Quiz: sofort Feedback + Live-Prozente (vom Server).
- Base-path-sichere Links/Assets.
- Farben pro Seite: aus content.json->pages[].color.

BACKEND:
- FastAPI + SQLite (persistentes Volume).
- Nginx als Reverse Proxy für static und /api.
- Docker Compose: nginx + api.

TRACKING/ANALYTICS (DSGVO pragmatisch):
- Kein Drittanbieter, keine Cookies nötig.
- Ortsabhängige Besucherzählung serverseitig via Geo-IP (city/region/country).
- Speichere KEINE IP im Klartext.
- Unique per Tag: uniq_day_hash = SHA256(ip + YYYY-MM-DD + SALT_ENV).
- SALT kommt aus ENV (z.B. ANALYTICS_SALT). Rotation daily über Datum.

DB SCHEMA (SQLite):
- visits(id, ts, page, city, region, country, uniq_day_hash, user_agent_short, ref)
- poll_votes(id, ts, page, poll_id, option, city, region, country, uniq_day_hash)
- quiz_answers(id, ts, page, quiz_id, option, is_correct, city, region, country, uniq_day_hash)

EVENTS:
1) Bei Seitenaufruf:
   - Frontend pingt POST /api/event/visit { page, ref }
2) Bei Poll:
   - POST /api/poll/vote { page, poll_id, option }
   - Server kann optional 1 Vote pro uniq_day_hash+poll_id+page limitieren (empfohlen).
3) Bei Quiz:
   - POST /api/quiz/answer { page, quiz_id, option }
   - Server bewertet is_correct anhand content.json correct field.

ADMIN:
- Auth: Basic Auth via ENV ADMIN_USER, ADMIN_PASS.
- /admin zeigt:
  a) Visits: total + unique/day + per page
  b) Orte: Top cities/regions/countries pro Zeitraum
  c) Poll results: counts & %
  d) Quiz results: correct rate + häufigste falsche Option
  e) Zeitreihe daily für visits (7/30/90 days)
- Optionale CSV Exporte: /api/admin/export.csv?type=visits|poll|quiz&period=30

GEOIP:
- Verwende eine lokal eingebundene GeoIP Datenbank (MaxMind GeoLite2 City).
- Lade/lege DB in /data/geoip/GeoLite2-City.mmdb ab (Volume).
- Wenn nicht vorhanden: fallback city="unknown", region="unknown", country="unknown".
- KEINE externen Calls beim Request.

CONTENT:
- Nutze ausschließlich /config/content.json als Source of Truth:
  - Polls/Quiz Fragen/Optionen/Correct Answers exakt übernehmen.
  - Texte exakt übernehmen (maximal typografisch glätten, KEINE inhaltlichen Änderungen).

PRIVACY PAGES:
- /datenschutz erklärt kurz:
  - Speicherung: page events, poll votes, quiz answers
  - Unique Hash per Tag (nicht rückrechenbar ohne Salt)
  - Grobe Location (Stadt/Region/Land) aus IP, IP nicht gespeichert
  - Keine Drittanbieter, keine Cookies notwendig
- /impressum: Platzhalterfelder.

DELIVERABLES:
- Vollständiges Repo:
  /static (index.html + page.html template + css + js)
  /api (main.py + db.py + geoip.py + auth.py)
  /config/content.json
  docker-compose.yml
  nginx.conf
  README.md (lokal starten + deploy; 3 commands)
- Stelle sicher: Alles läuft unter /andreasweiss base-path korrekt.
- Sorge für sichere Defaults (CORS nur same-origin; rate-limit minimal optional).

BEGINNE JETZT:
1) Lege die Projektstruktur an.
2) Erstelle content.json aus meinem gegebenen JSON.
3) Implementiere Frontend Renderer + API + Admin Dashboard.
