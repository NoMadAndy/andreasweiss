# Changelog

Alle relevanten Änderungen an diesem Projekt werden hier dokumentiert.

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
