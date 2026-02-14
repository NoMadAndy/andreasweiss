# Wahl 2026 – Multi-Tenant Kandidaten-Plattform

Multi-Tenant-Plattform für Kommunalwahl-Kandidaten mit eigenen Themenseiten, Umfragen, Quiz und DSGVO-konformem Tracking. Jeder Kandidat verwaltet seine Inhalte selbst über ein Admin-Dashboard.

**Domain:** `https://wahl2026.macherwerkstatt.cc`

## Schnellstart

```bash
# 1. Umgebungsvariablen setzen
cp .env.example .env    # dann ANALYTICS_SALT anpassen

# 2. Starten (Standard-Port: 8026)
docker compose up -d --build
```

**Plattform:** http://localhost:8026/
**Kandidat:** http://localhost:8026/andreasweiss/
**Admin:** http://localhost:8026/andreasweiss/admin/

Den Port kann man über die `PORT`-Variable in `.env` ändern (Standard: `8026`).

## Projektstruktur

```
├── api/                       ← FastAPI Backend (Jinja2)
│   ├── main.py                ← Routen + API Endpoints
│   ├── db.py                  ← SQLite Multi-Tenant
│   ├── auth.py                ← Per-Kandidat Basic Auth
│   ├── geoip.py               ← MaxMind GeoIP
│   ├── migrate.py             ← Migrationsskript
│   └── templates/             ← Jinja2 Templates
│       ├── base.html
│       ├── landing.html       ← Startseite (alle Kandidaten)
│       ├── home.html          ← Kandidaten-Homepage
│       ├── theme.html         ← Themenseite
│       ├── legal.html         ← Impressum/Datenschutz
│       └── admin.html         ← Admin Dashboard
├── static/assets/             ← Gemeinsame CSS/JS/Bilder
├── data/
│   ├── uploads/{slug}/        ← Per-Kandidat Uploads
│   └── geoip/                 ← GeoIP-Datenbank
├── nginx/nginx.conf           ← Reverse Proxy
├── docker-compose.yml
└── .env.example
```

## Funktionsweise

- **Landing Page** (`/`): Zeigt alle Kandidaten, Self-Registration
- **Kandidat** (`/{slug}/`): Eigene Homepage mit Themenkacheln
- **Themenseiten** (`/{slug}/{page}/`): Texte, Umfragen, Quiz, Feedback
- **Admin** (`/{slug}/admin/`): Statistiken, Content-Editing, Seiten-CRUD, Links, Uploads
- **Registrierung**: Neue Kandidaten registrieren sich auf der Startseite

## GeoIP (optional)

Für Standortdaten die [MaxMind GeoLite2-City](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data) Datenbank herunterladen (kostenloser Account):

```bash
cp GeoLite2-City.mmdb data/geoip/GeoLite2-City.mmdb
docker compose restart api
```

Ohne GeoIP-Datei werden Standorte als „unknown" erfasst.

## API Endpoints

| Methode | Pfad | Beschreibung |
|---------|------|-------------|
| GET | `/` | Landing Page (alle Kandidaten) |
| GET | `/{slug}/` | Kandidaten-Homepage |
| GET | `/{slug}/{page}/` | Themenseite |
| GET | `/{slug}/admin/` | Admin Dashboard |
| POST | `/api/register` | Neuen Kandidaten registrieren |
| POST | `/api/{slug}/event/visit` | Seitenaufruf tracken |
| POST | `/api/{slug}/poll/vote` | Poll-Stimme abgeben |
| GET | `/api/{slug}/poll/results/{id}` | Poll-Ergebnisse |
| POST | `/api/{slug}/quiz/answer` | Quiz-Antwort senden |
| POST | `/api/{slug}/feedback` | Feedback senden |
| GET | `/api/{slug}/admin/stats` | Admin-Statistiken (Auth) |
| GET/PUT | `/api/{slug}/admin/content` | Profil lesen/ändern (Auth) |
| POST/PUT/DEL | `/api/{slug}/admin/pages/{slug}` | Seiten-CRUD (Auth) |
| POST/DEL | `/api/{slug}/admin/links/{id}` | Links verwalten (Auth) |
| GET | `/api/{slug}/admin/export.csv` | CSV-Export (Auth) |
| POST | `/api/{slug}/admin/upload/*` | Dateien hochladen (Auth) |
| GET | `/api/health` | Health Check |

## Umgebungsvariablen

| Variable | Standard | Beschreibung |
|----------|----------|-------------|
| `PORT` | 8026 | HTTP-Port des Servers |
| `ANALYTICS_SALT` | change-this-salt | Salt für Tages-Hashes |

Admin-Zugangsdaten werden pro Kandidat in der DB gespeichert (bei Registrierung festgelegt).

## Sicherheit & DSGVO

- Keine Cookies, keine externen Dienste
- IP-Adressen werden **nicht** gespeichert
- Tagesbasierter Hash (SHA-256) zur Duplikat-Erkennung
- GeoIP-Lookup rein lokal (kein externer Call)
- CORS: nur Same-Origin
- Pro-Kandidat isolierte Authentifizierung
