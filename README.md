# Andreas Weiss – Kommunalwahl Rohrbach

Mini-Website für die Gemeinderatskandidatur mit Themenseiten, Umfragen, Quiz und DSGVO-konformem Tracking.

## Schnellstart

```bash
# 1. Seiten generieren
python3 generate.py

# 2. Umgebungsvariablen setzen
cp .env.example .env    # dann ADMIN_PASS und ANALYTICS_SALT anpassen

# 3. Starten
docker compose up -d --build
```

**Website:** http://localhost/andreasweiss/
**Admin:** http://localhost/andreasweiss/admin/ (Standard: admin / changeme)

## Projektstruktur

```
├── config/
│   └── content.json           ← Source of Truth (Texte, Polls, Quiz)
├── static/                    ← Generierte Seiten + Assets
│   ├── index.html             ← Startseite
│   ├── kinder/jugend/…        ← Themenseiten
│   ├── impressum/datenschutz/ ← Rechtliches
│   ├── admin/                 ← Admin Dashboard
│   └── assets/css + js
├── api/                       ← FastAPI Backend
│   ├── main.py                ← API Endpoints
│   ├── db.py                  ← SQLite
│   ├── geoip.py               ← MaxMind GeoIP
│   └── auth.py                ← Basic Auth
├── nginx/nginx.conf           ← Reverse Proxy
├── docker-compose.yml
├── generate.py                ← Seiten-Generator
└── .env.example
```

## Inhalte ändern

Alle Texte, Polls und Quiz stehen in `config/content.json`. Danach:

```bash
python3 generate.py
docker compose restart nginx
```

## GeoIP (optional)

Für Standortdaten die [MaxMind GeoLite2-City](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data) Datenbank herunterladen (kostenloser Account) und ins Repo legen:

```bash
# .mmdb-Datei nach data/geoip/ kopieren
cp GeoLite2-City.mmdb data/geoip/GeoLite2-City.mmdb
docker compose restart api
```

Der Ordner `data/geoip/` wird direkt in den Container gemountet. Ohne GeoIP-Datei werden Standorte als „unknown" erfasst.

## API Endpoints

| Methode | Pfad | Beschreibung |
|---------|------|-------------|
| POST | `/andreasweiss/api/event/visit` | Seitenaufruf tracken |
| POST | `/andreasweiss/api/poll/vote` | Poll-Stimme abgeben |
| GET | `/andreasweiss/api/poll/results/:id` | Poll-Ergebnisse |
| POST | `/andreasweiss/api/quiz/answer` | Quiz-Antwort senden |
| GET | `/andreasweiss/api/admin/stats` | Admin-Statistiken (Auth) |
| GET | `/andreasweiss/api/admin/export.csv` | CSV-Export (Auth) |
| GET | `/andreasweiss/api/health` | Health Check |

## Umgebungsvariablen

| Variable | Standard | Beschreibung |
|----------|----------|-------------|
| `ADMIN_USER` | admin | Admin-Benutzername |
| `ADMIN_PASS` | changeme | Admin-Passwort |
| `ANALYTICS_SALT` | change-this-salt | Salt für Tages-Hashes |

## Sicherheit & DSGVO

- Keine Cookies, keine externen Dienste
- IP-Adressen werden **nicht** gespeichert
- Tagesbasierter Hash (SHA-256) zur Duplikat-Erkennung
- GeoIP-Lookup rein lokal (kein externer Call)
- CORS: nur Same-Origin (kein CORS-Header nötig)
