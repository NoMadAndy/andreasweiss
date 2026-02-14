"""FastAPI backend – Multi-tenant Wahl2026 platform."""

VERSION = "2.0.0"

import csv
import hashlib
import io
import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from auth import verify_admin
from db import (
    get_db, init_db, get_candidate, get_candidate_pages,
    get_candidate_links, get_all_candidates,
)
from geoip import lookup, reload_reader, GEOIP_PATH

# ── Config ────────────────────────────────────────────────────────
ANALYTICS_SALT = os.environ.get("ANALYTICS_SALT", "default-salt-change-me")
UPLOAD_BASE = os.environ.get("UPLOAD_BASE", "/data/uploads")

# ── App ───────────────────────────────────────────────────────────
app = FastAPI(title="Wahl2026 Platform", docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


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
    candidates = get_all_candidates()
    return templates.TemplateResponse("landing.html", {
        "request": request,
        "candidates": candidates,
    })


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
async def register(data: RegisterData):
    if data.slug in RESERVED_SLUGS:
        raise HTTPException(400, "Dieser Slug ist reserviert")
    db = get_db()
    try:
        existing = db.execute("SELECT slug FROM candidates WHERE slug=?", (data.slug,)).fetchone()
        if existing:
            raise HTTPException(409, "Dieses Kürzel ist bereits vergeben")
        db.execute(
            "INSERT INTO candidates (slug, name, admin_user, admin_pass) VALUES (?,?,?,?)",
            (data.slug, data.name, data.admin_user, data.admin_pass),
        )
        db.commit()
    finally:
        db.close()
    # Create upload directory
    os.makedirs(os.path.join(UPLOAD_BASE, data.slug), exist_ok=True)
    return {"ok": True, "slug": data.slug}


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


@app.post("/api/{slug}/admin/upload/geoip")
async def upload_geoip(slug: str, file: UploadFile = File(...), _admin: str = Depends(verify_admin)):
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
