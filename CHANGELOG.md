# Changelog

Alle relevanten Änderungen an diesem Projekt werden hier dokumentiert.

## [3.0.0] – 2026-02-14

### Hinzugefügt

- **Konfigurierbare Startseite:** Headline, Slogan, Kampagnen-Banner und Footer-Text können vom Plattform-Admin über den neuen Tab „⚙️ Startseite“ konfiguriert werden
- **Platform-Settings API:** `GET /api/platform/settings` und `PUT /api/platform/settings` für serverseitiges Rendering der Startseite
- **Neue DB-Tabelle `platform_settings`:** Key-Value-Store mit sinnvollen Standardwerten
- **Plattform-Admin mit Tabs:** Statistiken, Kandidaten, Startseite, Daten – übersichtlich organisiert

### Geändert

- **Startseite öffentlich:** `/` ist jetzt für alle Besucher zugänglich (kein Login erforderlich), zeigt Kandidaten mit Portrait und Partei-Logo
- **Registrierung in Admin verschoben:** Neue Kandidaten werden jetzt über den Plattform-Admin („👥 Kandidaten“-Tab) angelegt, nicht mehr auf der Startseite
- Admin-Link im Footer der Startseite für schnellen Zugang

## [2.5.0] – 2026-02-14

### Hinzugefügt

- **Einheitlicher Kandidaten-Header:** Portrait, Name, Partei-Logo und Wahldatum erscheinen jetzt identisch auf jeder Unterseite (Home, Themen, Impressum, Datenschutz)
- Neues Jinja2-Partial `_candidate_header.html` für konsistente Wiederverwendung
- Eigene CSS-Section `.candidate-hero-bar` mit flexiblem Layout
- Kandidaten-Farbvariable `--cand-color` stellt sicher, dass der Header auch auf Theme-Seiten die Kandidatenfarbe nutzt

## [2.4.3] – 2026-02-14

### Geändert

- **Startseite geschützt:** Landing-Page (`/`) und Kandidaten-Registrierung (`POST /api/register`) nur noch für Plattform-Admin zugänglich
- Login-Formular auf der Startseite, Kandidatenliste wird erst nach Anmeldung angezeigt
- Registrierung sendet Authorization-Header mit Platform-Admin-Credentials
- Gleiche Session wie Plattform-Admin (`/admin/`) – einmal anmelden reicht

## [2.4.2] – 2026-02-14

### Hinzugefügt

- **Impressum/Datenschutz vorausgefüllt:** Neue Kandidaten erhalten bei der Registrierung automatisch Standard-Impressum- und Datenschutztexte mit ihrem Namen vorausgefüllt

## [2.4.1] – 2026-02-14

### Geändert

- **GeoIP-Upload:** Von Kandidaten-Admin auf Plattform-Admin verschoben (`POST /api/platform/upload/geoip`)
- GeoIP-Datenbank gilt plattformweit für alle Kandidaten, daher nur noch über den globalen Admin verwaltbar

## [2.4.0] – 2026-02-14

### Hinzugefügt

- **Zugangsdaten ändern:** Kandidaten können Benutzername und Passwort im Admin-Dashboard ändern (Tab „Inhalte")
- **Endpoint:** `PUT /api/{slug}/admin/credentials` mit Validierung (min. 6 Zeichen, Bestätigung)
- **UI:** Formular mit Passwort-Bestätigung, Sicherheitsabfrage und automatischer Neu-Anmeldung

## [2.3.0] – 2026-02-14

### Hinzugefügt

- **Dynamisches Favicon:** Pro Kandidat generiertes SVG-Favicon mit Initialen und Theme-Farbe (`/{slug}/favicon.svg`)
- Gradient aus Theme-Farbe → dunklerer Verlauf, weiße Initialen, abgerundetes Quadrat

### Geändert

- **Templates:** Kandidaten-Seiten nutzen jetzt `/{slug}/favicon.svg` statt dem statischen `/assets/img/favicon.svg`
- Landing-Page und Plattform-Admin behalten das generische Favicon

## [2.2.0] – 2026-02-14

### Hinzugefügt

- **Plattform-Admin:** Eigene Admin-Seite unter `/admin/` mit kumulierten Statistiken über alle Kandidaten
- **Kandidaten-Übersicht:** Tabelle mit Einzelstatistiken (Besuche, Umfragen, Quiz, Feedback, Seiten) pro Kandidat
- **Plattform-Auth:** Separate Authentifizierung via `ADMIN_USER`/`ADMIN_PASS` Umgebungsvariablen
- **DB-Import:** SQLite-Datei-Upload auf Plattform-Admin (mit Validierung und automatischem Backup)
- **Kandidaten-Import:** JSON-Import pro Kandidat – Profil (Update), Seiten (Upsert), Links (ohne Duplikate), Analytik (Append)
- **Import-UI:** Drag & Drop JSON-Import im Kandidaten-Admin Dashboard

### Geändert

- **DB-Export:** Von Kandidaten-Admin auf Plattform-Admin verschoben
- **Admin-UI:** Export-Sektion umbenannt in „Daten exportieren / importieren"

## [2.1.0] – 2026-02-14

### Hinzugefügt

- **Kandidaten-Export:** Vollständiger JSON-Export (Profil, Seiten, Links, Analytics) ohne Credentials
- **Datenbank-Backup:** SQLite-Snapshot-Download via `sqlite3.backup()` für konsistente Sicherung
- **Admin-UI:** Neue Export-Buttons „Kandidat als JSON" und „Gesamte Datenbank" im Dashboard

## [2.0.0] – 2026-02-14

### Hinzugefügt

- **Multi-Tenant-Plattform:** Mehrere Kandidaten unter eigenen Pfaden (`/{slug}/`), jeweils mit eigenem Admin
- **Landing Page:** Übersichtsseite mit allen Kandidaten und Self-Registration
- **Jinja2-Templates:** Dynamisches HTML-Rendering statt statischer Seitengenerierung
- **Per-Kandidat Authentifizierung:** Admin-Zugangsdaten in der Datenbank statt Umgebungsvariablen
- **Content-Management:** Profil, Seiten, Links komplett über Admin-UI editierbar
- **Seiten-CRUD:** Themenseiten anlegen, bearbeiten und löschen im Admin Dashboard
- **Link-Verwaltung:** Externe Partner-Links pro Kandidat hinzufügen/entfernen
- **Datei-Uploads:** Portrait, Logo und GeoIP-Datei per Drag & Drop hochladen
- **Konfigurierbarer Port:** Standard-Port 8026, änderbar über `PORT` in `.env`
- **Migrationsskript:** `migrate.py` für Übernahme bestehender Daten

### Geändert

- **Datenbank:** Neues Multi-Tenant-Schema mit `candidate_slug` auf allen Tabellen
- **API-Pfade:** Von `/andreasweiss/api/...` zu `/api/{slug}/...`
- **Asset-Pfade:** Gemeinsame Assets unter `/assets/`, Per-Kandidat-Uploads unter `/uploads/{slug}/`
- **Standard-Port:** Von 80 auf 8026
- **Domain:** `wahl2026.macherwerkstatt.cc`

### Entfernt

- Statischer Seitengenerator (`generate.py` wird nicht mehr benötigt)
- Feste `ADMIN_USER`/`ADMIN_PASS` Umgebungsvariablen (jetzt per Kandidat in DB)
- `config/content.json` als Runtime-Abhängigkeit (nur noch für Migration)

## [1.0.0] – 2026-02-14

### Hinzugefügt

- **Themenseiten:** 4 interaktive Seiten (Kinder, Jugend, Familie, Innovation) mit Umfrage, Quiz und Rückmelde-Formular
- **Startseite:** Kandidaten-Header mit Portrait + SPD-Logo, CTA-Banner „3 Stimmen", Themen-Karten-Grid, Über-mich-Box
- **DSGVO-konformes Tracking:** Seitenaufrufe, Unique-Besucher (SHA-256 Tages-Hash), kein Cookie, keine IP-Speicherung
- **GeoIP:** Lokaler MaxMind GeoLite2-City Lookup (optional, keine externen Calls)
- **Umfragen:** Pro Themenseite eine Poll mit 4 Optionen, Duplikat-Schutz (Client + Server)
- **Quiz:** Pro Themenseite eine Wissensfrage mit serverseitiger Auswertung und Erklärung
- **Rückmeldungen:** Freitext-Feedback-Formular auf jeder Themenseite (max. 3/Tag/Besucher)
- **Admin Dashboard:** Login mit Basic Auth, Statistik-Karten, Tages-Chart, Seiten-Tabelle, Geo-Tabs (Städte/Regionen/Länder)
- **Admin Umfrage-/Quiz-Ergebnisse:** Farbige Themen-Karten mit gestapelten Balken, Statistik-Zusammenfassung, ✅/❌ Icons
- **Admin Rückmeldungen:** Karten-Layout mit Seiten-Tag, Datum, Ort
- **Admin Export:** Einzelne CSV-Exporte (Besuche, Umfragen, Quiz, Rückmeldungen) + „Alles exportieren"-Button
- **Admin Persistenter Login:** Session wird im localStorage gespeichert, Logout-Button
- **Favicon:** SVG-Favicon (AW-Monogramm mit blau-rotem Verlauf), PNG 192/512px, Apple Touch Icon
- **Web App Manifest:** „Zum Homescreen hinzufügen" Unterstützung (PWA-fähig)
- **Seiten-Generator:** `generate.py` erzeugt alle HTML-Seiten aus `config/content.json`
- **Legal:** Impressum und Datenschutzerklärung
- **Docker:** Nginx + FastAPI, Docker Compose Setup mit SQLite-Volume und GeoIP-Mount
- **README:** Komplette Dokumentation mit Schnellstart, Projektstruktur, API-Referenz
