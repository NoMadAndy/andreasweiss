"""FastAPI backend – Multi-tenant Wahlplattform."""

VERSION = "3.8.1"

import csv
import hashlib
import io
import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import shutil
import tempfile

from fastapi import Depends, FastAPI, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

import markdown as md_lib
import bleach
from markupsafe import Markup

from auth import verify_admin, verify_platform_admin
from db import (
    get_db, init_db, get_candidate, get_candidate_pages,
    get_candidate_links, get_all_candidates,
    get_platform_settings, set_platform_settings,
)
from geoip import lookup, reload_reader, GEOIP_PATH

# ── Config ────────────────────────────────────────────────────────
ANALYTICS_SALT = os.environ.get("ANALYTICS_SALT", "default-salt-change-me")
UPLOAD_BASE = os.environ.get("UPLOAD_BASE", "/data/uploads")

# ── App ───────────────────────────────────────────────────────────
app = FastAPI(title="Wahlplattform", docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.globals["VERSION"] = VERSION
templates.env.globals["get_platform_settings"] = get_platform_settings

# ── Markdown filter ───────────────────────────────────────────
_MD = md_lib.Markdown(extensions=["nl2br", "sane_lists", "smarty"])
_BLEACH_TAGS = [
    "p", "br", "a", "img", "strong", "em", "b", "i",
    "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "code", "pre", "hr", "div", "span",
]
_BLEACH_ATTRS = {
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "width", "height"],
}

def _markdown_filter(text: str) -> Markup:
    if not text:
        return Markup("")
    _MD.reset()
    html = _MD.convert(text)
    clean = bleach.clean(html, tags=_BLEACH_TAGS, attributes=_BLEACH_ATTRS)
    # Auto-add target=_blank to links
    clean = clean.replace("<a ", '<a target="_blank" rel="noopener" ')
    return Markup(clean)

templates.env.filters["markdown"] = _markdown_filter


@app.on_event("startup")
def startup():
    init_db()


# ── Helpers ───────────────────────────────────────────────────────
def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real = request.headers.get("X-Real-IP")
    if real:
        return real.strip()
    return request.client.host if request.client else "0.0.0.0"


def _day_hash(ip: str) -> str:
    today = date.today().isoformat()
    return hashlib.sha256(f"{ip}{today}{ANALYTICS_SALT}".encode()).hexdigest()


def _short_ua(request: Request) -> str:
    return (request.headers.get("User-Agent") or "")[:120]


def _require_candidate(slug: str) -> dict:
    """Return candidate dict or raise 404."""
    c = get_candidate(slug)
    if not c:
        raise HTTPException(404, "Kandidat nicht gefunden")
    return c


def _quiz_correct_map(slug: str) -> dict[str, str]:
    """Build quiz_id → correct_answer map for a candidate."""
    pages = get_candidate_pages(slug)
    return {p["quiz_id"]: p["quiz_correct"] for p in pages if p.get("quiz_id")}


def _content_meta(slug: str) -> dict:
    """Build poll/quiz metadata for admin stats."""
    pages = get_candidate_pages(slug)
    meta = {}
    for p in pages:
        if p.get("poll_id"):
            meta[p["poll_id"]] = {
                "type": "poll", "page": p["slug"],
                "theme": p["theme"], "question": p["poll_question"],
            }
        if p.get("quiz_id"):
            meta[p["quiz_id"]] = {
                "type": "quiz", "page": p["slug"],
                "theme": p["theme"], "question": p["quiz_question"],
            }
    return meta


# ── Pydantic Models ───────────────────────────────────────────────
class VisitEvent(BaseModel):
    page: str = Field(..., max_length=50)
    ref: Optional[str] = Field(None, max_length=500)


class PollVote(BaseModel):
    page: str = Field(..., max_length=50)
    poll_id: str = Field(..., max_length=50)
    option: str = Field(..., max_length=200)


class QuizAnswer(BaseModel):
    page: str = Field(..., max_length=50)
    quiz_id: str = Field(..., max_length=50)
    option: str = Field(..., max_length=200)


class FeedbackMessage(BaseModel):
    page: str = Field(..., max_length=50)
    message: str = Field(..., min_length=1, max_length=1000)


class RegisterData(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    slug: str = Field(..., min_length=2, max_length=40, pattern=r"^[a-z0-9\-]+$")
    admin_user: str = Field(..., min_length=2, max_length=50)
    admin_pass: str = Field(..., min_length=6, max_length=100)


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    party: Optional[str] = None
    tagline: Optional[str] = None
    election_date: Optional[str] = None
    theme_color: Optional[str] = None
    headline: Optional[str] = None
    intro_text: Optional[str] = None
    cta_text: Optional[str] = None
    cta_sub: Optional[str] = None
    about_title: Optional[str] = None
    about_text: Optional[str] = None
    about_name_line: Optional[str] = None
    impressum_html: Optional[str] = None
    datenschutz_html: Optional[str] = None


class PageData(BaseModel):
    slug: Optional[str] = None
    theme: str = ""
    color: str = "#1E6FB9"
    headline: str = ""
    text: str = ""
    tile_title: str = ""
    tile_subtitle: str = ""
    poll_id: str = ""
    poll_question: str = ""
    poll_options: list[str] = []
    quiz_id: str = ""
    quiz_intro: str = ""
    quiz_question: str = ""
    quiz_options: list[str] = []
    quiz_correct: str = ""
    quiz_explain: str = ""


class LinkData(BaseModel):
    label: str = Field(..., min_length=1, max_length=200)
    url: str = Field(..., min_length=5, max_length=500)


class CredentialsUpdate(BaseModel):
    new_user: Optional[str] = Field(None, min_length=2, max_length=50)
    new_pass: Optional[str] = Field(None, min_length=6, max_length=100)


# ══════════════════════════════════════════════════════════════════
#  HTML Pages
# ══════════════════════════════════════════════════════════════════

DEFAULT_IMPRESSUM = """<h1>Impressum</h1>
<h2>Angaben gemäß § 5 TMG</h2>
<p><strong>[Name]</strong><br>[Straße und Hausnr.]<br>[PLZ Ort]</p>
<h2>Kontakt</h2>
<p>E-Mail: [E-Mail-Adresse]</p>
<h2>Verantwortlich für den Inhalt</h2>
<p>[Name] (Anschrift wie oben)</p>
<h2>Hinweis</h2>
<p>Diese Website dient der Information über die Kandidatur. Es handelt sich um eine private, nicht-kommerzielle Seite.</p>"""

DEFAULT_DATENSCHUTZ = """<h1>Datenschutzerklärung</h1>
<h2>1. Verantwortlicher</h2>
<p>[Name], [Adresse] – siehe Impressum.</p>
<h2>2. Was wir speichern</h2>
<p>Diese Website erhebt <strong>keine personenbezogenen Daten</strong> im klassischen Sinne.
Es werden keine Cookies gesetzt und keine Drittanbieter-Dienste eingebunden.</p>
<p>Folgende Daten werden serverseitig erfasst:</p>
<ul>
<li><strong>Seitenaufrufe:</strong> Welche Seite besucht wurde, Zeitpunkt, grober Standort (Stadt/Region/Land).</li>
<li><strong>Umfrage-Stimmen:</strong> Gewählte Option, Zeitpunkt, grober Standort.</li>
<li><strong>Quiz-Antworten:</strong> Gewählte Option, ob korrekt, Zeitpunkt, grober Standort.</li>
</ul>
<h2>3. Keine IP-Speicherung</h2>
<p>Ihre IP-Adresse wird <strong>nicht</strong> gespeichert. Zur Erkennung von Mehrfach-Abstimmungen
wird ein tagesbasierter Hash erzeugt (SHA-256 aus IP + Datum + geheimer Salt).
Dieser Hash ist nicht auf die IP-Adresse rückrechenbar.</p>
<h2>4. Standortbestimmung</h2>
<p>Die grobe Standortbestimmung erfolgt über eine lokal eingebundene Datenbank (MaxMind GeoLite2).
Es werden <strong>keine externen Dienste</strong> kontaktiert.</p>
<h2>5. Keine Cookies</h2>
<p>Diese Website verwendet <strong>keine Cookies</strong>. Zur lokalen Speicherung Ihrer
Abstimmungs-Teilnahme wird ausschließlich der localStorage Ihres Browsers genutzt.</p>
<h2>6. Keine Drittanbieter</h2>
<p>Es werden keine externen Schriftarten, Analyse-Tools, Social-Media-Plugins oder
sonstige Drittanbieter-Dienste eingebunden.</p>
<h2>7. Ihre Rechte</h2>
<p>Da keine personenbezogenen Daten gespeichert werden, entfallen die üblichen Betroffenenrechte.
Bei Fragen wenden Sie sich an die im Impressum genannte Kontaktadresse.</p>"""


@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    settings = get_platform_settings()
    # Redirect if configured
    redirect_url = (settings.get("redirect_url") or "").strip()
    if redirect_url:
        from starlette.responses import RedirectResponse
        return RedirectResponse(url=redirect_url, status_code=302)
    candidates = get_all_candidates() if settings.get("show_candidates", "1") == "1" else []
    return templates.TemplateResponse("landing.html", {
        "request": request,
        "settings": settings,
        "candidates": candidates,
    })


# ══════════════════════════════════════════════════════════════════
#  Platform Admin
# ══════════════════════════════════════════════════════════════════

@app.get("/admin/", response_class=HTMLResponse)
async def platform_admin(request: Request):
    return templates.TemplateResponse("platform_admin.html", {"request": request})


@app.get("/api/platform/stats")
async def platform_stats(_admin: str = Depends(verify_platform_admin)):
    """Cumulative stats across ALL candidates."""
    db = get_db()
    try:
        candidates = [dict(r) for r in db.execute(
            "SELECT slug, name, party, theme_color, created_at FROM candidates ORDER BY name"
        ).fetchall()]
        total_visits = db.execute("SELECT COUNT(*) c FROM visits").fetchone()["c"]
        total_polls = db.execute("SELECT COUNT(*) c FROM poll_votes").fetchone()["c"]
        total_quiz = db.execute("SELECT COUNT(*) c FROM quiz_answers").fetchone()["c"]
        total_feedback = db.execute("SELECT COUNT(*) c FROM feedback").fetchone()["c"]
        unique_today = db.execute(
            "SELECT COUNT(DISTINCT uniq_day_hash) c FROM visits WHERE date(ts)=date('now')"
        ).fetchone()["c"]

        # Per-candidate breakdown
        per_candidate = []
        for c in candidates:
            s = c["slug"]
            v = db.execute("SELECT COUNT(*) c FROM visits WHERE candidate_slug=?", (s,)).fetchone()["c"]
            p = db.execute("SELECT COUNT(*) c FROM poll_votes WHERE candidate_slug=?", (s,)).fetchone()["c"]
            q = db.execute("SELECT COUNT(*) c FROM quiz_answers WHERE candidate_slug=?", (s,)).fetchone()["c"]
            f = db.execute("SELECT COUNT(*) c FROM feedback WHERE candidate_slug=?", (s,)).fetchone()["c"]
            pages_count = db.execute("SELECT COUNT(*) c FROM candidate_pages WHERE candidate_slug=?", (s,)).fetchone()["c"]
            per_candidate.append({
                "slug": s, "name": c["name"], "party": c.get("party", ""),
                "theme_color": c.get("theme_color", "#1E6FB9"),
                "created_at": c.get("created_at", ""),
                "visits": v, "polls": p, "quiz": q, "feedback": f,
                "pages": pages_count,
            })

        # Daily visits (last 30 days)
        daily = [dict(r) for r in db.execute(
            "SELECT date(ts) day, COUNT(*) total, COUNT(DISTINCT uniq_day_hash) uniq "
            "FROM visits WHERE ts >= datetime('now', '-30 days') GROUP BY date(ts) ORDER BY day"
        ).fetchall()]
    finally:
        db.close()

    return {
        "total_visits": total_visits,
        "total_polls": total_polls,
        "total_quiz": total_quiz,
        "total_feedback": total_feedback,
        "unique_today": unique_today,
        "candidates": per_candidate,
        "daily": daily,
        "candidate_count": len(candidates),
    }


@app.get("/api/platform/settings")
async def platform_get_settings(_admin: str = Depends(verify_platform_admin)):
    """Return all platform settings."""
    return get_platform_settings()


@app.put("/api/platform/settings")
async def platform_put_settings(request: Request, _admin: str = Depends(verify_platform_admin)):
    """Update platform settings."""
    data = await request.json()
    allowed_keys = {
        "site_title", "site_subtitle", "hero_headline", "hero_text",
        "campaign_title", "campaign_text", "footer_text",
        "show_candidates", "redirect_url",
    }
    filtered = {k: str(v) for k, v in data.items() if k in allowed_keys}
    if filtered:
        set_platform_settings(filtered)
    return {"ok": True, "updated": list(filtered.keys())}


@app.get("/api/platform/export/db")
async def platform_export_db(_admin: str = Depends(verify_platform_admin)):
    """Download a snapshot of the entire SQLite database."""
    from db import DB_PATH as _db_path
    if not os.path.exists(_db_path):
        raise HTTPException(404, "Datenbank nicht gefunden")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    src = get_db()
    try:
        import sqlite3
        dst = sqlite3.connect(tmp.name)
        src.backup(dst)
        dst.close()
    finally:
        src.close()
    return FileResponse(
        tmp.name,
        media_type="application/x-sqlite3",
        filename="platform_backup.db",
        background=None,
    )


@app.post("/api/platform/import/db")
async def platform_import_db(
    file: UploadFile = File(...),
    _admin: str = Depends(verify_platform_admin),
):
    """Import / replace the entire SQLite database from an uploaded .db file."""
    if not file.filename.endswith(".db"):
        raise HTTPException(400, "Nur .db Dateien erlaubt")
    data = await file.read()
    if len(data) > 200 * 1024 * 1024:
        raise HTTPException(400, "Datei zu groß (max 200 MB)")

    # Validate it's a real SQLite DB
    import sqlite3
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.write(data)
    tmp.close()
    try:
        check = sqlite3.connect(tmp.name)
        cur = check.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        check.close()
        required = {"candidates", "candidate_pages", "visits"}
        if not required.issubset(set(tables)):
            os.unlink(tmp.name)
            raise HTTPException(400, f"Ungültige Datenbank – fehlende Tabellen: {required - set(tables)}")
    except sqlite3.DatabaseError:
        os.unlink(tmp.name)
        raise HTTPException(400, "Ungültige SQLite-Datei")

    # Replace the live database
    from db import DB_PATH as _db_path
    # Backup first
    backup_path = _db_path + ".bak"
    if os.path.exists(_db_path):
        shutil.copy2(_db_path, backup_path)
    shutil.move(tmp.name, _db_path)
    # Re-initialize to pick up changes
    init_db()
    return {"ok": True, "tables": tables, "size": len(data)}


# ── Analytics (Statistics) Export / Import / Reset ────────────
ANALYTICS_TABLES = ["visits", "poll_votes", "quiz_answers", "feedback"]


@app.get("/api/platform/analytics/export")
async def platform_analytics_export(_admin: str = Depends(verify_platform_admin)):
    """Export all analytics data (visits, poll_votes, quiz_answers, feedback) as JSON."""
    db = get_db()
    try:
        result: dict = {"export_date": datetime.now().isoformat(), "version": VERSION}
        for table in ANALYTICS_TABLES:
            rows = db.execute(f"SELECT * FROM {table}").fetchall()
            result[table] = [dict(r) for r in rows]
    finally:
        db.close()
    content = json.dumps(result, ensure_ascii=False, indent=2)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="analytics_export.json"'},
    )


@app.post("/api/platform/analytics/import")
async def platform_analytics_import(
    file: UploadFile = File(...),
    _admin: str = Depends(verify_platform_admin),
):
    """Import analytics data from a JSON file. Merges with existing data (appends rows)."""
    if not file.filename.endswith(".json"):
        raise HTTPException(400, "Nur .json Dateien erlaubt")
    raw = await file.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(400, "Ungültige JSON-Datei")

    db = get_db()
    counts: dict = {}
    try:
        for table in ANALYTICS_TABLES:
            rows = data.get(table, [])
            if not rows:
                counts[table] = 0
                continue
            # Get column names from DB (excluding 'id' – auto-increment)
            cols_info = db.execute(f"PRAGMA table_info({table})").fetchall()
            all_cols = [c["name"] for c in cols_info if c["name"] != "id"]
            inserted = 0
            for row in rows:
                vals = {c: row.get(c, "") for c in all_cols}
                placeholders = ", ".join(["?"] * len(vals))
                col_names = ", ".join(vals.keys())
                db.execute(
                    f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",
                    list(vals.values()),
                )
                inserted += 1
            counts[table] = inserted
        db.commit()
    finally:
        db.close()
    return {"ok": True, "imported": counts}


@app.delete("/api/platform/analytics")
async def platform_analytics_reset(_admin: str = Depends(verify_platform_admin)):
    """Delete ALL analytics data (visits, poll_votes, quiz_answers, feedback)."""
    db = get_db()
    counts: dict = {}
    try:
        for table in ANALYTICS_TABLES:
            count = db.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]
            db.execute(f"DELETE FROM {table}")
            counts[table] = count
        db.commit()
    finally:
        db.close()
    return {"ok": True, "deleted": counts}


# ── Per-Candidate Analytics Export / Import / Reset ───────────

@app.get("/api/platform/candidates/{slug}/analytics/export")
async def platform_candidate_analytics_export(
    slug: str, _admin: str = Depends(verify_platform_admin),
):
    """Export analytics for a single candidate."""
    candidate = get_candidate(slug)
    if not candidate:
        raise HTTPException(404, "Kandidat nicht gefunden")
    db = get_db()
    try:
        result: dict = {
            "export_date": datetime.now().isoformat(),
            "version": VERSION,
            "candidate_slug": slug,
            "candidate_name": candidate["name"],
        }
        for table in ANALYTICS_TABLES:
            rows = db.execute(
                f"SELECT * FROM {table} WHERE candidate_slug = ?", (slug,)
            ).fetchall()
            result[table] = [dict(r) for r in rows]
    finally:
        db.close()
    content = json.dumps(result, ensure_ascii=False, indent=2)
    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{slug}_analytics.json"'
        },
    )


@app.post("/api/platform/candidates/{slug}/analytics/import")
async def platform_candidate_analytics_import(
    slug: str,
    file: UploadFile = File(...),
    _admin: str = Depends(verify_platform_admin),
):
    """Import analytics for a single candidate (appends rows, sets candidate_slug)."""
    candidate = get_candidate(slug)
    if not candidate:
        raise HTTPException(404, "Kandidat nicht gefunden")
    if not file.filename.endswith(".json"):
        raise HTTPException(400, "Nur .json Dateien erlaubt")
    raw = await file.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(400, "Ungültige JSON-Datei")

    db = get_db()
    counts: dict = {}
    try:
        for table in ANALYTICS_TABLES:
            rows = data.get(table, [])
            if not rows:
                counts[table] = 0
                continue
            cols_info = db.execute(f"PRAGMA table_info({table})").fetchall()
            all_cols = [c["name"] for c in cols_info if c["name"] != "id"]
            inserted = 0
            for row in rows:
                vals = {c: row.get(c, "") for c in all_cols}
                vals["candidate_slug"] = slug  # force correct slug
                placeholders = ", ".join(["?"] * len(vals))
                col_names = ", ".join(vals.keys())
                db.execute(
                    f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",
                    list(vals.values()),
                )
                inserted += 1
            counts[table] = inserted
        db.commit()
    finally:
        db.close()
    return {"ok": True, "imported": counts}


@app.delete("/api/platform/candidates/{slug}/analytics")
async def platform_candidate_analytics_reset(
    slug: str, _admin: str = Depends(verify_platform_admin),
):
    """Delete analytics data for a single candidate."""
    candidate = get_candidate(slug)
    if not candidate:
        raise HTTPException(404, "Kandidat nicht gefunden")
    db = get_db()
    counts: dict = {}
    try:
        for table in ANALYTICS_TABLES:
            count = db.execute(
                f"SELECT COUNT(*) c FROM {table} WHERE candidate_slug = ?", (slug,)
            ).fetchone()["c"]
            db.execute(f"DELETE FROM {table} WHERE candidate_slug = ?", (slug,))
            counts[table] = count
        db.commit()
    finally:
        db.close()
    return {"ok": True, "deleted": counts}


# ══════════════════════════════════════════════════════════════════
#  Candidate HTML Pages
# ══════════════════════════════════════════════════════════════════

@app.get("/{slug}/", response_class=HTMLResponse)
async def candidate_home(slug: str, request: Request):
    candidate = _require_candidate(slug)
    pages = get_candidate_pages(slug)
    links = get_candidate_links(slug)
    return templates.TemplateResponse("home.html", {
        "request": request,
        "candidate": candidate,
        "pages": pages,
        "links": links,
        "slug": slug,
        "page_id": "home",
        "theme_color": candidate["theme_color"],
    })


@app.get("/{slug}/favicon.svg")
async def candidate_favicon(slug: str):
    """Generate a personalised SVG favicon from candidate initials + theme color."""
    candidate = _require_candidate(slug)
    name = candidate.get("name", slug)
    color = candidate.get("theme_color", "#1E6FB9")
    # Build initials (max 2 chars) from first letters of name parts
    parts = name.split()
    if len(parts) >= 2:
        initials = (parts[0][0] + parts[-1][0]).upper()
    elif parts:
        initials = parts[0][:2].upper()
    else:
        initials = "?"
    # Derive a darker shade for gradient end
    try:
        r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
        r2, g2, b2 = max(0, r - 60), max(0, g - 60), max(0, b - 60)
        color2 = f"#{r2:02x}{g2:02x}{b2:02x}"
    except (ValueError, IndexError):
        color2 = color
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{color}"/>
      <stop offset="100%" stop-color="{color2}"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" rx="96" fill="url(#bg)"/>
  <text x="256" y="280" text-anchor="middle" dominant-baseline="central"
        font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif"
        font-size="240" font-weight="800" fill="#fff" letter-spacing="-8">{initials}</text>
</svg>'''
    return HTMLResponse(content=svg, media_type="image/svg+xml", headers={
        "Cache-Control": "public, max-age=86400",
    })


@app.get("/{slug}/manifest.json")
async def candidate_manifest(slug: str):
    candidate = _require_candidate(slug)
    return JSONResponse({
        "name": candidate["name"],
        "short_name": candidate["name"],
        "start_url": f"/{slug}/",
        "display": "standalone",
        "background_color": "#f5f5f7",
        "theme_color": candidate.get("theme_color", "#1E6FB9"),
        "icons": [
            {"src": "/assets/img/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/assets/img/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    })


@app.get("/{slug}/admin/", response_class=HTMLResponse)
async def candidate_admin(slug: str, request: Request):
    candidate = _require_candidate(slug)
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "candidate": candidate,
    })


@app.get("/{slug}/impressum/", response_class=HTMLResponse)
async def candidate_impressum(slug: str, request: Request):
    candidate = _require_candidate(slug)
    links = get_candidate_links(slug)
    content = candidate.get("impressum_html") or DEFAULT_IMPRESSUM.replace("[Name]", candidate["name"])
    return templates.TemplateResponse("legal.html", {
        "request": request,
        "candidate": candidate,
        "links": links,
        "slug": slug,
        "page_id": "impressum",
        "page_title": "Impressum",
        "content_html": content,
        "theme_color": candidate["theme_color"],
    })


@app.get("/{slug}/datenschutz/", response_class=HTMLResponse)
async def candidate_datenschutz(slug: str, request: Request):
    candidate = _require_candidate(slug)
    links = get_candidate_links(slug)
    content = candidate.get("datenschutz_html") or DEFAULT_DATENSCHUTZ.replace("[Name]", candidate["name"])
    return templates.TemplateResponse("legal.html", {
        "request": request,
        "candidate": candidate,
        "links": links,
        "slug": slug,
        "page_id": "datenschutz",
        "page_title": "Datenschutz",
        "content_html": content,
        "theme_color": candidate["theme_color"],
    })


@app.get("/{slug}/{page_slug}/", response_class=HTMLResponse)
async def candidate_theme_page(slug: str, page_slug: str, request: Request):
    candidate = _require_candidate(slug)
    links = get_candidate_links(slug)
    pages = get_candidate_pages(slug)
    page = next((p for p in pages if p["slug"] == page_slug), None)
    if not page:
        raise HTTPException(404, "Seite nicht gefunden")
    return templates.TemplateResponse("theme.html", {
        "request": request,
        "candidate": candidate,
        "page": page,
        "links": links,
        "slug": slug,
        "page_id": page_slug,
        "theme_color": page["color"],
    })


# ══════════════════════════════════════════════════════════════════
#  Registration
# ══════════════════════════════════════════════════════════════════

RESERVED_SLUGS = {"api", "assets", "uploads", "admin", "static", "health"}


@app.post("/api/register")
async def register(data: RegisterData, _admin: str = Depends(verify_platform_admin)):
    if data.slug in RESERVED_SLUGS:
        raise HTTPException(400, "Dieser Slug ist reserviert")
    db = get_db()
    try:
        existing = db.execute("SELECT slug FROM candidates WHERE slug=?", (data.slug,)).fetchone()
        if existing:
            raise HTTPException(409, "Dieses Kürzel ist bereits vergeben")
        db.execute(
            "INSERT INTO candidates (slug, name, admin_user, admin_pass, impressum_html, datenschutz_html) "
            "VALUES (?,?,?,?,?,?)",
            (data.slug, data.name, data.admin_user, data.admin_pass,
             DEFAULT_IMPRESSUM.replace("[Name]", data.name),
             DEFAULT_DATENSCHUTZ.replace("[Name]", data.name)),
        )
        db.commit()
    finally:
        db.close()
    # Create upload directory
    os.makedirs(os.path.join(UPLOAD_BASE, data.slug), exist_ok=True)
    return {"ok": True, "slug": data.slug}


@app.delete("/api/platform/candidates/{slug}")
async def delete_candidate(slug: str, _admin: str = Depends(verify_platform_admin)):
    """Delete a candidate and all associated data."""
    candidate = get_candidate(slug)
    if not candidate:
        raise HTTPException(404, "Kandidat nicht gefunden")
    db = get_db()
    try:
        db.execute("DELETE FROM feedback WHERE candidate_slug=?", (slug,))
        db.execute("DELETE FROM quiz_answers WHERE candidate_slug=?", (slug,))
        db.execute("DELETE FROM poll_votes WHERE candidate_slug=?", (slug,))
        db.execute("DELETE FROM visits WHERE candidate_slug=?", (slug,))
        db.execute("DELETE FROM candidate_links WHERE candidate_slug=?", (slug,))
        db.execute("DELETE FROM candidate_pages WHERE candidate_slug=?", (slug,))
        db.execute("DELETE FROM candidates WHERE slug=?", (slug,))
        db.commit()
    finally:
        db.close()
    # Remove upload directory
    upload_dir = os.path.join(UPLOAD_BASE, slug)
    if os.path.isdir(upload_dir):
        shutil.rmtree(upload_dir, ignore_errors=True)
    return {"ok": True, "deleted": slug}


@app.get("/api/platform/candidates/{slug}/export")
async def export_single_candidate(slug: str, _admin: str = Depends(verify_platform_admin)):
    """Export a single candidate with pages, links and analytics as JSON."""
    candidate = get_candidate(slug)
    if not candidate:
        raise HTTPException(404, "Kandidat nicht gefunden")
    db = get_db()
    try:
        pages = [dict(r) for r in db.execute(
            "SELECT * FROM candidate_pages WHERE candidate_slug=? ORDER BY sort_order, id", (slug,)
        ).fetchall()]
        links = [dict(r) for r in db.execute(
            "SELECT * FROM candidate_links WHERE candidate_slug=? ORDER BY sort_order, id", (slug,)
        ).fetchall()]
        visits = [dict(r) for r in db.execute(
            "SELECT ts, page, city, region, country, user_agent_short, ref FROM visits WHERE candidate_slug=? ORDER BY ts DESC", (slug,)
        ).fetchall()]
        polls = [dict(r) for r in db.execute(
            "SELECT ts, page, poll_id, option, city, region, country FROM poll_votes WHERE candidate_slug=? ORDER BY ts DESC", (slug,)
        ).fetchall()]
        quizzes = [dict(r) for r in db.execute(
            "SELECT ts, page, quiz_id, option, is_correct, city, region, country FROM quiz_answers WHERE candidate_slug=? ORDER BY ts DESC", (slug,)
        ).fetchall()]
        feedbacks = [dict(r) for r in db.execute(
            "SELECT ts, page, message, city, region, country FROM feedback WHERE candidate_slug=? ORDER BY ts DESC", (slug,)
        ).fetchall()]
    finally:
        db.close()
    safe = {k: v for k, v in candidate.items() if k not in ("admin_user", "admin_pass")}
    payload = {
        "export_date": datetime.now().isoformat(),
        "version": VERSION,
        "candidate": safe,
        "pages": pages,
        "links": links,
        "analytics": {
            "visits": visits,
            "poll_votes": polls,
            "quiz_answers": quizzes,
            "feedback": feedbacks,
        },
    }
    content = json.dumps(payload, ensure_ascii=False, indent=2)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={slug}_export.json"},
    )


@app.post("/api/platform/candidates/{slug}/import")
async def import_single_candidate(
    slug: str,
    file: UploadFile = File(...),
    _admin: str = Depends(verify_platform_admin),
):
    """Import data into an existing candidate from a JSON export file (platform admin)."""
    candidate = get_candidate(slug)
    if not candidate:
        raise HTTPException(404, "Kandidat nicht gefunden")
    if not file.filename.endswith(".json"):
        raise HTTPException(400, "Nur .json Dateien erlaubt")
    raw = await file.read()
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(400, "Datei zu gro\u00df (max 50 MB)")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(400, "Ung\u00fcltiges JSON")

    # Support both single-candidate export format and array format
    if "candidate" in payload:
        c_data = payload["candidate"]
        pages_data = payload.get("pages", [])
        links_data = payload.get("links", [])
    elif isinstance(payload, list) and len(payload) == 1:
        c_data = payload[0]
        pages_data = c_data.get("pages", [])
        links_data = c_data.get("links", [])
    else:
        c_data = payload
        pages_data = payload.get("pages", [])
        links_data = payload.get("links", [])

    imported = {"profile": False, "pages": 0, "links": 0}
    db = get_db()
    try:
        # Update profile fields
        profile_fields = [
            "name", "party", "tagline", "election_date", "theme_color",
            "headline", "intro_text", "cta_text", "cta_sub",
            "about_title", "about_text", "about_name_line",
            "impressum_html", "datenschutz_html",
        ]
        sets, vals = [], []
        for f in profile_fields:
            if f in c_data and c_data[f] is not None:
                sets.append(f"{f}=?")
                vals.append(c_data[f])
        if sets:
            vals.append(slug)
            db.execute(f"UPDATE candidates SET {','.join(sets)} WHERE slug=?", vals)
            imported["profile"] = True

        # Upsert pages
        for p in pages_data:
            page_slug = p.get("slug")
            if not page_slug:
                continue
            poll_opts = json.dumps(p.get("poll_options", []), ensure_ascii=False) if isinstance(p.get("poll_options"), list) else p.get("poll_options", "[]")
            quiz_opts = json.dumps(p.get("quiz_options", []), ensure_ascii=False) if isinstance(p.get("quiz_options"), list) else p.get("quiz_options", "[]")
            existing = db.execute("SELECT id FROM candidate_pages WHERE candidate_slug=? AND slug=?", (slug, page_slug)).fetchone()
            if existing:
                db.execute(
                    "UPDATE candidate_pages SET theme=?, color=?, headline=?, text=?, "
                    "tile_title=?, tile_subtitle=?, poll_id=?, poll_question=?, poll_options=?, "
                    "quiz_id=?, quiz_intro=?, quiz_question=?, quiz_options=?, quiz_correct=?, quiz_explain=?, sort_order=? "
                    "WHERE candidate_slug=? AND slug=?",
                    (p.get("theme",""), p.get("color","#1E6FB9"), p.get("headline",""), p.get("text",""),
                     p.get("tile_title",""), p.get("tile_subtitle",""),
                     p.get("poll_id",""), p.get("poll_question",""), poll_opts,
                     p.get("quiz_id",""), p.get("quiz_intro",""), p.get("quiz_question",""),
                     quiz_opts, p.get("quiz_correct",""), p.get("quiz_explain",""), p.get("sort_order", 0),
                     slug, page_slug),
                )
            else:
                db.execute(
                    "INSERT INTO candidate_pages (candidate_slug, slug, theme, color, headline, text, "
                    "tile_title, tile_subtitle, poll_id, poll_question, poll_options, "
                    "quiz_id, quiz_intro, quiz_question, quiz_options, quiz_correct, quiz_explain, sort_order) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (slug, page_slug, p.get("theme",""), p.get("color","#1E6FB9"),
                     p.get("headline",""), p.get("text",""),
                     p.get("tile_title",""), p.get("tile_subtitle",""),
                     p.get("poll_id",""), p.get("poll_question",""), poll_opts,
                     p.get("quiz_id",""), p.get("quiz_intro",""), p.get("quiz_question",""),
                     quiz_opts, p.get("quiz_correct",""), p.get("quiz_explain",""), p.get("sort_order", 0)),
                )
            imported["pages"] += 1

        # Upsert links
        for l in links_data:
            url = l.get("url", "")
            if not url:
                continue
            exists = db.execute("SELECT id FROM candidate_links WHERE candidate_slug=? AND url=?", (slug, url)).fetchone()
            if not exists:
                db.execute(
                    "INSERT INTO candidate_links (candidate_slug, label, url, sort_order) VALUES (?,?,?,?)",
                    (slug, l.get("label", ""), url, l.get("sort_order", 0)),
                )
                imported["links"] += 1
        db.commit()
    finally:
        db.close()
    return {"ok": True, "imported": imported}


@app.get("/api/platform/candidates/export")
async def export_candidates(_admin: str = Depends(verify_platform_admin)):
    """Export all candidates with their pages and links as JSON."""
    db = get_db()
    try:
        candidates = [dict(r) for r in db.execute("SELECT * FROM candidates ORDER BY name").fetchall()]
        for c in candidates:
            s = c["slug"]
            c["pages"] = [dict(r) for r in db.execute(
                "SELECT * FROM candidate_pages WHERE candidate_slug=? ORDER BY sort_order, id", (s,)
            ).fetchall()]
            c["links"] = [dict(r) for r in db.execute(
                "SELECT * FROM candidate_links WHERE candidate_slug=? ORDER BY sort_order, id", (s,)
            ).fetchall()]
    finally:
        db.close()
    content = json.dumps(candidates, ensure_ascii=False, indent=2)
    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": "attachment; filename=kandidaten_export.json",
        },
    )


@app.post("/api/platform/candidates/import")
async def import_candidates(
    request: Request,
    _admin: str = Depends(verify_platform_admin),
):
    """Import candidates from JSON. Skips existing slugs unless overwrite flag is set."""
    body = await request.json()
    candidates = body.get("candidates", []) if isinstance(body, dict) else body
    if not isinstance(candidates, list):
        raise HTTPException(400, "Erwarte eine Liste von Kandidaten")

    overwrite = body.get("overwrite", False) if isinstance(body, dict) else False
    imported = []
    skipped = []
    db = get_db()
    try:
        for c in candidates:
            slug = c.get("slug", "")
            if not slug:
                continue
            existing = db.execute("SELECT slug FROM candidates WHERE slug=?", (slug,)).fetchone()
            if existing and not overwrite:
                skipped.append(slug)
                continue
            if existing and overwrite:
                # Delete existing data first
                db.execute("DELETE FROM candidate_links WHERE candidate_slug=?", (slug,))
                db.execute("DELETE FROM candidate_pages WHERE candidate_slug=?", (slug,))
                db.execute("DELETE FROM candidates WHERE slug=?", (slug,))

            # Insert candidate
            db.execute(
                "INSERT INTO candidates (slug, name, party, tagline, election_date, headline, "
                "intro_text, about_title, about_text, about_name_line, cta_text, cta_sub, "
                "theme_color, impressum_html, datenschutz_html, admin_user, admin_pass, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (slug, c.get("name", slug), c.get("party", ""), c.get("tagline", ""),
                 c.get("election_date", ""), c.get("headline", ""), c.get("intro_text", ""),
                 c.get("about_title", "Über mich"), c.get("about_text", ""),
                 c.get("about_name_line", ""), c.get("cta_text", ""), c.get("cta_sub", ""),
                 c.get("theme_color", "#1E6FB9"), c.get("impressum_html", ""),
                 c.get("datenschutz_html", ""), c.get("admin_user", "admin"),
                 c.get("admin_pass", "changeme"), c.get("created_at", "")),
            )
            # Insert pages
            for p in c.get("pages", []):
                db.execute(
                    "INSERT INTO candidate_pages (candidate_slug, slug, theme, color, headline, text, "
                    "tile_title, tile_subtitle, poll_id, poll_question, poll_options, "
                    "quiz_id, quiz_intro, quiz_question, quiz_options, quiz_correct, quiz_explain, sort_order) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (slug, p.get("slug", ""), p.get("theme", ""), p.get("color", "#1E6FB9"),
                     p.get("headline", ""), p.get("text", ""), p.get("tile_title", ""),
                     p.get("tile_subtitle", ""), p.get("poll_id"), p.get("poll_question", ""),
                     json.dumps(p.get("poll_options", [])) if isinstance(p.get("poll_options"), list) else p.get("poll_options", "[]"),
                     p.get("quiz_id"), p.get("quiz_intro", ""), p.get("quiz_question", ""),
                     json.dumps(p.get("quiz_options", [])) if isinstance(p.get("quiz_options"), list) else p.get("quiz_options", "[]"),
                     p.get("quiz_correct", ""), p.get("quiz_explain", ""), p.get("sort_order", 0)),
                )
            # Insert links
            for l in c.get("links", []):
                db.execute(
                    "INSERT INTO candidate_links (candidate_slug, label, url, sort_order) VALUES (?,?,?,?)",
                    (slug, l.get("label", ""), l.get("url", ""), l.get("sort_order", 0)),
                )
            # Ensure upload directory
            os.makedirs(os.path.join(UPLOAD_BASE, slug), exist_ok=True)
            imported.append(slug)
        db.commit()
    finally:
        db.close()
    return {"ok": True, "imported": imported, "skipped": skipped}


# ══════════════════════════════════════════════════════════════════
#  Public API (per candidate)
# ══════════════════════════════════════════════════════════════════

@app.post("/api/{slug}/event/visit")
async def track_visit(slug: str, event: VisitEvent, request: Request):
    _require_candidate(slug)
    ip = _client_ip(request)
    geo = lookup(ip)
    db = get_db()
    try:
        db.execute(
            "INSERT INTO visits (candidate_slug, page, city, region, country, uniq_day_hash, user_agent_short, ref) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (slug, event.page, geo["city"], geo["region"], geo["country"],
             _day_hash(ip), _short_ua(request), event.ref),
        )
        db.commit()
    finally:
        db.close()
    return {"ok": True}


@app.post("/api/{slug}/poll/vote")
async def poll_vote(slug: str, vote: PollVote, request: Request):
    _require_candidate(slug)
    ip = _client_ip(request)
    geo = lookup(ip)
    day_hash = _day_hash(ip)

    db = get_db()
    try:
        existing = db.execute(
            "SELECT id FROM poll_votes WHERE uniq_day_hash=? AND poll_id=? AND page=? AND candidate_slug=?",
            (day_hash, vote.poll_id, vote.page, slug),
        ).fetchone()
        already_voted = existing is not None
        if not already_voted:
            db.execute(
                "INSERT INTO poll_votes (candidate_slug, page, poll_id, option, city, region, country, uniq_day_hash) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (slug, vote.page, vote.poll_id, vote.option, geo["city"], geo["region"],
                 geo["country"], day_hash),
            )
            db.commit()
        rows = db.execute(
            "SELECT option, COUNT(*) as cnt FROM poll_votes WHERE poll_id=? AND candidate_slug=? GROUP BY option",
            (vote.poll_id, slug),
        ).fetchall()
    finally:
        db.close()

    total = sum(r["cnt"] for r in rows)
    results = {
        r["option"]: {"count": r["cnt"], "percent": round(r["cnt"] / total * 100) if total else 0}
        for r in rows
    }
    return {"ok": True, "already_voted": already_voted, "results": results, "total": total}


@app.get("/api/{slug}/poll/results/{poll_id}")
async def poll_results(slug: str, poll_id: str):
    db = get_db()
    try:
        rows = db.execute(
            "SELECT option, COUNT(*) as cnt FROM poll_votes WHERE poll_id=? AND candidate_slug=? GROUP BY option",
            (poll_id, slug),
        ).fetchall()
    finally:
        db.close()
    total = sum(r["cnt"] for r in rows)
    results = {
        r["option"]: {"count": r["cnt"], "percent": round(r["cnt"] / total * 100) if total else 0}
        for r in rows
    }
    return {"results": results, "total": total}


@app.post("/api/{slug}/quiz/answer")
async def quiz_answer(slug: str, answer: QuizAnswer, request: Request):
    _require_candidate(slug)
    ip = _client_ip(request)
    geo = lookup(ip)
    day_hash = _day_hash(ip)

    correct_map = _quiz_correct_map(slug)
    correct_answer = correct_map.get(answer.quiz_id)
    is_correct = 1 if answer.option == correct_answer else 0

    db = get_db()
    try:
        db.execute(
            "INSERT INTO quiz_answers (candidate_slug, page, quiz_id, option, is_correct, city, region, country, uniq_day_hash) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (slug, answer.page, answer.quiz_id, answer.option, is_correct,
             geo["city"], geo["region"], geo["country"], day_hash),
        )
        db.commit()
        rows = db.execute(
            "SELECT option, COUNT(*) as cnt FROM quiz_answers WHERE quiz_id=? AND candidate_slug=? GROUP BY option",
            (answer.quiz_id, slug),
        ).fetchall()
    finally:
        db.close()

    total = sum(r["cnt"] for r in rows)
    results = {
        r["option"]: {"count": r["cnt"], "percent": round(r["cnt"] / total * 100) if total else 0}
        for r in rows
    }

    # Get explain text
    explain = ""
    pages = get_candidate_pages(slug)
    for p in pages:
        if p.get("quiz_id") == answer.quiz_id:
            explain = p.get("quiz_explain", "")
            break

    return {
        "ok": True,
        "is_correct": bool(is_correct),
        "correct_answer": correct_answer,
        "explain": explain,
        "explain_html": str(_markdown_filter(explain)) if explain else "",
        "results": results,
        "total": total,
    }


@app.post("/api/{slug}/feedback")
async def submit_feedback(slug: str, fb: FeedbackMessage, request: Request):
    _require_candidate(slug)
    ip = _client_ip(request)
    geo = lookup(ip)
    day_hash = _day_hash(ip)

    db = get_db()
    try:
        count = db.execute(
            "SELECT COUNT(*) as c FROM feedback WHERE uniq_day_hash=? AND page=? AND candidate_slug=?",
            (day_hash, fb.page, slug),
        ).fetchone()["c"]
        if count >= 3:
            return {"ok": False, "error": "Tageslimit erreicht"}
        db.execute(
            "INSERT INTO feedback (candidate_slug, page, message, city, region, country, uniq_day_hash) "
            "VALUES (?,?,?,?,?,?,?)",
            (slug, fb.page, fb.message, geo["city"], geo["region"], geo["country"], day_hash),
        )
        db.commit()
    finally:
        db.close()
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════
#  Admin API
# ══════════════════════════════════════════════════════════════════

@app.get("/api/{slug}/admin/stats")
async def admin_stats(
    slug: str,
    period: int = Query(30, ge=1, le=365),
    _admin: str = Depends(verify_admin),
):
    _require_candidate(slug)
    meta = _content_meta(slug)
    db = get_db()
    try:
        delta = f"-{period} days"
        cond = "candidate_slug=?"

        total_visits = db.execute(f"SELECT COUNT(*) as c FROM visits WHERE {cond}", (slug,)).fetchone()["c"]
        today_iso = date.today().isoformat()
        unique_today = db.execute(
            f"SELECT COUNT(DISTINCT uniq_day_hash) as c FROM visits WHERE {cond} AND date(ts)=?",
            (slug, today_iso),
        ).fetchone()["c"]

        per_page = [dict(r) for r in db.execute(
            f"SELECT page, COUNT(*) as cnt FROM visits WHERE {cond} AND ts >= datetime('now', ?) GROUP BY page ORDER BY cnt DESC",
            (slug, delta),
        ).fetchall()]

        top_cities = [dict(r) for r in db.execute(
            f"SELECT city, COUNT(*) as cnt FROM visits WHERE {cond} AND ts >= datetime('now', ?) GROUP BY city ORDER BY cnt DESC LIMIT 20",
            (slug, delta),
        ).fetchall()]

        top_regions = [dict(r) for r in db.execute(
            f"SELECT region, COUNT(*) as cnt FROM visits WHERE {cond} AND ts >= datetime('now', ?) GROUP BY region ORDER BY cnt DESC LIMIT 20",
            (slug, delta),
        ).fetchall()]

        top_countries = [dict(r) for r in db.execute(
            f"SELECT country, COUNT(*) as cnt FROM visits WHERE {cond} AND ts >= datetime('now', ?) GROUP BY country ORDER BY cnt DESC LIMIT 20",
            (slug, delta),
        ).fetchall()]

        daily = [dict(r) for r in db.execute(
            f"SELECT date(ts) as day, COUNT(*) as total, COUNT(DISTINCT uniq_day_hash) as uniq "
            f"FROM visits WHERE {cond} AND ts >= datetime('now', ?) GROUP BY date(ts) ORDER BY day",
            (slug, delta),
        ).fetchall()]

        # Polls
        poll_rows = db.execute(
            f"SELECT poll_id, option, COUNT(*) as cnt FROM poll_votes WHERE {cond} GROUP BY poll_id, option ORDER BY poll_id, cnt DESC",
            (slug,),
        ).fetchall()
        polls: dict = {}
        for r in poll_rows:
            pid = r["poll_id"]
            if pid not in polls:
                polls[pid] = {"options": {}, "total": 0}
            polls[pid]["options"][r["option"]] = r["cnt"]
            polls[pid]["total"] += r["cnt"]

        # Quizzes
        quiz_rows = db.execute(
            f"SELECT quiz_id, option, is_correct, COUNT(*) as cnt FROM quiz_answers WHERE {cond} GROUP BY quiz_id, option ORDER BY quiz_id, cnt DESC",
            (slug,),
        ).fetchall()
        quizzes: dict = {}
        for r in quiz_rows:
            qid = r["quiz_id"]
            if qid not in quizzes:
                quizzes[qid] = {"options": {}, "total": 0, "correct": 0}
            quizzes[qid]["options"][r["option"]] = {"count": r["cnt"], "is_correct": bool(r["is_correct"])}
            quizzes[qid]["total"] += r["cnt"]
            if r["is_correct"]:
                quizzes[qid]["correct"] += r["cnt"]

        # Feedback
        feedback_rows = [dict(r) for r in db.execute(
            f"SELECT id, ts, page, message, city, region, country FROM feedback WHERE {cond} AND ts >= datetime('now', ?) ORDER BY ts DESC LIMIT 100",
            (slug, delta),
        ).fetchall()]
        feedback_count = db.execute(f"SELECT COUNT(*) as c FROM feedback WHERE {cond}", (slug,)).fetchone()["c"]
    finally:
        db.close()

    return {
        "total_visits": total_visits,
        "unique_today": unique_today,
        "per_page": per_page,
        "top_cities": top_cities,
        "top_regions": top_regions,
        "top_countries": top_countries,
        "daily": daily,
        "polls": polls,
        "quizzes": quizzes,
        "content_meta": meta,
        "feedback": feedback_rows,
        "feedback_count": feedback_count,
    }


@app.get("/api/{slug}/admin/content")
async def admin_content(slug: str, _admin: str = Depends(verify_admin)):
    candidate = _require_candidate(slug)
    pages = get_candidate_pages(slug)
    links = get_candidate_links(slug)
    return {
        **{k: v for k, v in candidate.items() if k not in ("admin_user", "admin_pass")},
        "pages": pages,
        "links": links,
    }


@app.put("/api/{slug}/admin/content")
async def update_content(slug: str, data: ProfileUpdate, _admin: str = Depends(verify_admin)):
    _require_candidate(slug)
    updates = {k: v for k, v in data.dict().items() if v is not None}
    if not updates:
        return {"ok": True}
    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [slug]
    db = get_db()
    try:
        db.execute(f"UPDATE candidates SET {set_clause} WHERE slug=?", values)
        db.commit()
    finally:
        db.close()
    return {"ok": True}


@app.put("/api/{slug}/admin/credentials")
async def update_credentials(slug: str, data: CredentialsUpdate, _admin: str = Depends(verify_admin)):
    """Change admin username and/or password. Requires current valid auth."""
    _require_candidate(slug)
    updates = {}
    if data.new_user is not None:
        updates["admin_user"] = data.new_user
    if data.new_pass is not None:
        updates["admin_pass"] = data.new_pass
    if not updates:
        raise HTTPException(400, "Kein neuer Benutzername oder Passwort angegeben")
    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [slug]
    db = get_db()
    try:
        db.execute(f"UPDATE candidates SET {set_clause} WHERE slug=?", values)
        db.commit()
    finally:
        db.close()
    return {"ok": True, "updated": list(updates.keys())}


@app.post("/api/{slug}/admin/pages")
async def add_page(slug: str, data: PageData, _admin: str = Depends(verify_admin)):
    _require_candidate(slug)
    if not data.slug:
        raise HTTPException(400, "Slug ist erforderlich")
    db = get_db()
    try:
        existing = db.execute(
            "SELECT id FROM candidate_pages WHERE candidate_slug=? AND slug=?",
            (slug, data.slug),
        ).fetchone()
        if existing:
            raise HTTPException(409, "Seite mit diesem Slug existiert bereits")
        max_order = db.execute(
            "SELECT COALESCE(MAX(sort_order), 0) as m FROM candidate_pages WHERE candidate_slug=?",
            (slug,),
        ).fetchone()["m"]
        db.execute(
            "INSERT INTO candidate_pages (candidate_slug, slug, theme, color, headline, text, "
            "tile_title, tile_subtitle, poll_id, poll_question, poll_options, "
            "quiz_id, quiz_intro, quiz_question, quiz_options, quiz_correct, quiz_explain, sort_order) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (slug, data.slug, data.theme, data.color, data.headline, data.text,
             data.tile_title, data.tile_subtitle, data.poll_id, data.poll_question,
             json.dumps(data.poll_options), data.quiz_id, data.quiz_intro,
             data.quiz_question, json.dumps(data.quiz_options),
             data.quiz_correct, data.quiz_explain, max_order + 1),
        )
        db.commit()
    finally:
        db.close()
    return {"ok": True}


@app.put("/api/{slug}/admin/pages/{page_slug}")
async def update_page(slug: str, page_slug: str, data: PageData, _admin: str = Depends(verify_admin)):
    _require_candidate(slug)
    db = get_db()
    try:
        existing = db.execute(
            "SELECT id FROM candidate_pages WHERE candidate_slug=? AND slug=?",
            (slug, page_slug),
        ).fetchone()
        if not existing:
            raise HTTPException(404, "Seite nicht gefunden")
        db.execute(
            "UPDATE candidate_pages SET theme=?, color=?, headline=?, text=?, "
            "tile_title=?, tile_subtitle=?, poll_id=?, poll_question=?, poll_options=?, "
            "quiz_id=?, quiz_intro=?, quiz_question=?, quiz_options=?, quiz_correct=?, quiz_explain=? "
            "WHERE candidate_slug=? AND slug=?",
            (data.theme, data.color, data.headline, data.text,
             data.tile_title, data.tile_subtitle, data.poll_id, data.poll_question,
             json.dumps(data.poll_options), data.quiz_id, data.quiz_intro,
             data.quiz_question, json.dumps(data.quiz_options),
             data.quiz_correct, data.quiz_explain, slug, page_slug),
        )
        db.commit()
    finally:
        db.close()
    return {"ok": True}


@app.delete("/api/{slug}/admin/pages/{page_slug}")
async def delete_page(slug: str, page_slug: str, _admin: str = Depends(verify_admin)):
    _require_candidate(slug)
    db = get_db()
    try:
        db.execute("DELETE FROM candidate_pages WHERE candidate_slug=? AND slug=?", (slug, page_slug))
        db.commit()
    finally:
        db.close()
    return {"ok": True}


@app.post("/api/{slug}/admin/links")
async def add_link(slug: str, data: LinkData, _admin: str = Depends(verify_admin)):
    _require_candidate(slug)
    db = get_db()
    try:
        max_order = db.execute(
            "SELECT COALESCE(MAX(sort_order), 0) as m FROM candidate_links WHERE candidate_slug=?",
            (slug,),
        ).fetchone()["m"]
        db.execute(
            "INSERT INTO candidate_links (candidate_slug, label, url, sort_order) VALUES (?,?,?,?)",
            (slug, data.label, data.url, max_order + 1),
        )
        db.commit()
    finally:
        db.close()
    return {"ok": True}


@app.delete("/api/{slug}/admin/links/{link_id}")
async def delete_link(slug: str, link_id: int, _admin: str = Depends(verify_admin)):
    _require_candidate(slug)
    db = get_db()
    try:
        db.execute("DELETE FROM candidate_links WHERE id=? AND candidate_slug=?", (link_id, slug))
        db.commit()
    finally:
        db.close()
    return {"ok": True}


@app.get("/api/{slug}/admin/export.csv")
async def admin_export(
    slug: str,
    type: str = Query(..., pattern="^(visits|poll|quiz|feedback)$"),
    period: int = Query(30, ge=1, le=365),
    _admin: str = Depends(verify_admin),
):
    _require_candidate(slug)
    db = get_db()
    output = io.StringIO()
    delta = f"-{period} days"
    cond = "candidate_slug=?"

    try:
        if type == "visits":
            rows = db.execute(
                f"SELECT ts, page, city, region, country, user_agent_short, ref FROM visits WHERE {cond} AND ts >= datetime('now', ?) ORDER BY ts DESC",
                (slug, delta),
            ).fetchall()
            writer = csv.writer(output)
            writer.writerow(["ts", "page", "city", "region", "country", "user_agent", "ref"])
            for r in rows:
                writer.writerow([r["ts"], r["page"], r["city"], r["region"], r["country"], r["user_agent_short"], r["ref"]])
        elif type == "poll":
            rows = db.execute(
                f"SELECT ts, page, poll_id, option, city, region, country FROM poll_votes WHERE {cond} AND ts >= datetime('now', ?) ORDER BY ts DESC",
                (slug, delta),
            ).fetchall()
            writer = csv.writer(output)
            writer.writerow(["ts", "page", "poll_id", "option", "city", "region", "country"])
            for r in rows:
                writer.writerow([r["ts"], r["page"], r["poll_id"], r["option"], r["city"], r["region"], r["country"]])
        elif type == "quiz":
            rows = db.execute(
                f"SELECT ts, page, quiz_id, option, is_correct, city, region, country FROM quiz_answers WHERE {cond} AND ts >= datetime('now', ?) ORDER BY ts DESC",
                (slug, delta),
            ).fetchall()
            writer = csv.writer(output)
            writer.writerow(["ts", "page", "quiz_id", "option", "is_correct", "city", "region", "country"])
            for r in rows:
                writer.writerow([r["ts"], r["page"], r["quiz_id"], r["option"], r["is_correct"], r["city"], r["region"], r["country"]])
        elif type == "feedback":
            rows = db.execute(
                f"SELECT ts, page, message, city, region, country FROM feedback WHERE {cond} AND ts >= datetime('now', ?) ORDER BY ts DESC",
                (slug, delta),
            ).fetchall()
            writer = csv.writer(output)
            writer.writerow(["ts", "page", "message", "city", "region", "country"])
            for r in rows:
                writer.writerow([r["ts"], r["page"], r["message"], r["city"], r["region"], r["country"]])
    finally:
        db.close()

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={type}_{slug}_export.csv"},
    )


# ── Full Exports ──────────────────────────────────────────────────

@app.get("/api/{slug}/admin/export/candidate.json")
async def export_candidate_json(
    slug: str,
    _admin: str = Depends(verify_admin),
):
    """Export all candidate data (profile, pages, links, analytics) as JSON."""
    candidate = _require_candidate(slug)
    pages = get_candidate_pages(slug)
    links = get_candidate_links(slug)
    db = get_db()
    try:
        visits = [dict(r) for r in db.execute(
            "SELECT ts, page, city, region, country, user_agent_short, ref FROM visits WHERE candidate_slug=? ORDER BY ts DESC",
            (slug,),
        ).fetchall()]
        polls = [dict(r) for r in db.execute(
            "SELECT ts, page, poll_id, option, city, region, country FROM poll_votes WHERE candidate_slug=? ORDER BY ts DESC",
            (slug,),
        ).fetchall()]
        quizzes = [dict(r) for r in db.execute(
            "SELECT ts, page, quiz_id, option, is_correct, city, region, country FROM quiz_answers WHERE candidate_slug=? ORDER BY ts DESC",
            (slug,),
        ).fetchall()]
        feedbacks = [dict(r) for r in db.execute(
            "SELECT ts, page, message, city, region, country FROM feedback WHERE candidate_slug=? ORDER BY ts DESC",
            (slug,),
        ).fetchall()]
    finally:
        db.close()

    safe = {k: v for k, v in candidate.items() if k not in ("admin_user", "admin_pass")}
    payload = {
        "export_date": datetime.now().isoformat(),
        "version": VERSION,
        "candidate": safe,
        "pages": pages,
        "links": links,
        "analytics": {
            "visits": visits,
            "poll_votes": polls,
            "quiz_answers": quizzes,
            "feedback": feedbacks,
        },
    }
    content = json.dumps(payload, ensure_ascii=False, indent=2)
    return StreamingResponse(
        iter([content]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={slug}_export.json"},
    )


# ── Candidate Import ──────────────────────────────────────────────

@app.post("/api/{slug}/admin/import")
async def import_candidate_json(
    slug: str,
    file: UploadFile = File(...),
    _admin: str = Depends(verify_admin),
):
    """Import candidate data from a previously exported JSON file."""
    _require_candidate(slug)
    if not file.filename.endswith(".json"):
        raise HTTPException(400, "Nur .json Dateien erlaubt")
    raw = await file.read()
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(400, "Datei zu groß (max 50 MB)")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(400, "Ungültiges JSON")

    if "candidate" not in payload:
        raise HTTPException(400, "Kein 'candidate'-Objekt im JSON gefunden")

    imported = {"profile": False, "pages": 0, "links": 0, "visits": 0, "polls": 0, "quiz": 0, "feedback": 0}
    db = get_db()
    try:
        # Update profile fields (skip admin_user, admin_pass, slug)
        c = payload["candidate"]
        profile_fields = [
            "name", "party", "tagline", "election_date", "theme_color",
            "headline", "intro_text", "cta_text", "cta_sub",
            "about_title", "about_text", "about_name_line",
            "impressum_html", "datenschutz_html",
        ]
        sets = []
        vals = []
        for f in profile_fields:
            if f in c and c[f] is not None:
                sets.append(f"{f}=?")
                vals.append(c[f])
        if sets:
            vals.append(slug)
            db.execute(f"UPDATE candidates SET {','.join(sets)} WHERE slug=?", vals)
            imported["profile"] = True

        # Import pages (upsert by slug)
        for p in payload.get("pages", []):
            page_slug = p.get("slug")
            if not page_slug:
                continue
            existing = db.execute(
                "SELECT id FROM candidate_pages WHERE candidate_slug=? AND slug=?",
                (slug, page_slug),
            ).fetchone()
            poll_opts = json.dumps(p.get("poll_options", []), ensure_ascii=False)
            quiz_opts = json.dumps(p.get("quiz_options", []), ensure_ascii=False)
            if existing:
                db.execute(
                    "UPDATE candidate_pages SET theme=?, color=?, headline=?, text=?, "
                    "tile_title=?, tile_subtitle=?, poll_id=?, poll_question=?, poll_options=?, "
                    "quiz_id=?, quiz_intro=?, quiz_question=?, quiz_options=?, quiz_correct=?, quiz_explain=? "
                    "WHERE candidate_slug=? AND slug=?",
                    (p.get("theme",""), p.get("color","#1E6FB9"), p.get("headline",""), p.get("text",""),
                     p.get("tile_title",""), p.get("tile_subtitle",""),
                     p.get("poll_id",""), p.get("poll_question",""), poll_opts,
                     p.get("quiz_id",""), p.get("quiz_intro",""), p.get("quiz_question",""),
                     quiz_opts, p.get("quiz_correct",""), p.get("quiz_explain",""),
                     slug, page_slug),
                )
            else:
                db.execute(
                    "INSERT INTO candidate_pages (candidate_slug, slug, theme, color, headline, text, "
                    "tile_title, tile_subtitle, poll_id, poll_question, poll_options, "
                    "quiz_id, quiz_intro, quiz_question, quiz_options, quiz_correct, quiz_explain) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (slug, page_slug, p.get("theme",""), p.get("color","#1E6FB9"),
                     p.get("headline",""), p.get("text",""),
                     p.get("tile_title",""), p.get("tile_subtitle",""),
                     p.get("poll_id",""), p.get("poll_question",""), poll_opts,
                     p.get("quiz_id",""), p.get("quiz_intro",""), p.get("quiz_question",""),
                     quiz_opts, p.get("quiz_correct",""), p.get("quiz_explain","")),
                )
            imported["pages"] += 1

        # Import links (append, skip duplicates by url)
        for l in payload.get("links", []):
            exists = db.execute(
                "SELECT id FROM candidate_links WHERE candidate_slug=? AND url=?",
                (slug, l["url"]),
            ).fetchone()
            if not exists:
                db.execute(
                    "INSERT INTO candidate_links (candidate_slug, label, url) VALUES (?,?,?)",
                    (slug, l["label"], l["url"]),
                )
                imported["links"] += 1

        # Import analytics data (append)
        analytics = payload.get("analytics", {})
        for v in analytics.get("visits", []):
            db.execute(
                "INSERT INTO visits (candidate_slug, ts, page, city, region, country, user_agent_short, ref) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (slug, v.get("ts"), v.get("page",""), v.get("city",""), v.get("region",""),
                 v.get("country",""), v.get("user_agent_short",""), v.get("ref","")),
            )
            imported["visits"] += 1
        for pv in analytics.get("poll_votes", []):
            db.execute(
                "INSERT INTO poll_votes (candidate_slug, ts, page, poll_id, option, city, region, country) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (slug, pv.get("ts"), pv.get("page",""), pv.get("poll_id",""), pv.get("option",""),
                 pv.get("city",""), pv.get("region",""), pv.get("country","")),
            )
            imported["polls"] += 1
        for qa in analytics.get("quiz_answers", []):
            db.execute(
                "INSERT INTO quiz_answers (candidate_slug, ts, page, quiz_id, option, is_correct, city, region, country) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (slug, qa.get("ts"), qa.get("page",""), qa.get("quiz_id",""), qa.get("option",""),
                 qa.get("is_correct", 0), qa.get("city",""), qa.get("region",""), qa.get("country","")),
            )
            imported["quiz"] += 1
        for fb in analytics.get("feedback", []):
            db.execute(
                "INSERT INTO feedback (candidate_slug, ts, page, message, city, region, country) "
                "VALUES (?,?,?,?,?,?,?)",
                (slug, fb.get("ts"), fb.get("page",""), fb.get("message",""),
                 fb.get("city",""), fb.get("region",""), fb.get("country","")),
            )
            imported["feedback"] += 1

        db.commit()
    finally:
        db.close()

    return {"ok": True, "imported": imported}


# ── File Uploads ──────────────────────────────────────────────────
MAX_IMAGE_SIZE = 5 * 1024 * 1024
MAX_GEOIP_SIZE = 150 * 1024 * 1024


@app.post("/api/{slug}/admin/upload/portrait")
async def upload_portrait(slug: str, file: UploadFile = File(...), _admin: str = Depends(verify_admin)):
    _require_candidate(slug)
    if file.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(400, "Nur JPG, PNG oder WebP erlaubt")
    data = await file.read()
    if len(data) > MAX_IMAGE_SIZE:
        raise HTTPException(400, f"Datei zu groß (max {MAX_IMAGE_SIZE // 1024 // 1024} MB)")
    upload_dir = os.path.join(UPLOAD_BASE, slug)
    os.makedirs(upload_dir, exist_ok=True)
    path = os.path.join(upload_dir, "portrait.jpg")
    with open(path, "wb") as f:
        f.write(data)
    return {"ok": True, "file": "portrait.jpg", "size": len(data)}


@app.post("/api/{slug}/admin/upload/logo")
async def upload_logo(slug: str, file: UploadFile = File(...), _admin: str = Depends(verify_admin)):
    _require_candidate(slug)
    allowed = ("image/svg+xml", "image/png", "image/webp", "image/jpeg")
    if file.content_type not in allowed:
        raise HTTPException(400, "Nur SVG, PNG, JPG oder WebP erlaubt")
    data = await file.read()
    if len(data) > MAX_IMAGE_SIZE:
        raise HTTPException(400, f"Datei zu groß (max {MAX_IMAGE_SIZE // 1024 // 1024} MB)")
    upload_dir = os.path.join(UPLOAD_BASE, slug)
    os.makedirs(upload_dir, exist_ok=True)
    fname = "logo.svg" if file.content_type == "image/svg+xml" else "logo.png"
    path = os.path.join(upload_dir, fname)
    with open(path, "wb") as f:
        f.write(data)
    return {"ok": True, "file": fname, "size": len(data)}


@app.post("/api/platform/upload/geoip")
async def upload_geoip(file: UploadFile = File(...), _admin: str = Depends(verify_platform_admin)):
    if not file.filename.endswith(".mmdb"):
        raise HTTPException(400, "Nur .mmdb Dateien erlaubt")
    data = await file.read()
    if len(data) > MAX_GEOIP_SIZE:
        raise HTTPException(400, f"Datei zu groß (max {MAX_GEOIP_SIZE // 1024 // 1024} MB)")
    geoip_dir = os.path.dirname(GEOIP_PATH)
    os.makedirs(geoip_dir, exist_ok=True)
    with open(GEOIP_PATH, "wb") as f:
        f.write(data)
    loaded = reload_reader()
    return {"ok": True, "file": os.path.basename(GEOIP_PATH), "size": len(data), "loaded": loaded}


# ── Health ────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {"status": "ok", "version": VERSION, "ts": datetime.now().isoformat()}
