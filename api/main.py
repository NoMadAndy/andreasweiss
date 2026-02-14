"""FastAPI backend – Analytics, Polls, Quiz, Admin."""

VERSION = "1.0.0"

import csv
import hashlib
import io
import json
import os
from datetime import date, datetime
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from auth import verify_admin
from db import get_db, init_db
from geoip import lookup

# ── Config ────────────────────────────────────────────────────────
ANALYTICS_SALT = os.environ.get("ANALYTICS_SALT", "default-salt-change-me")
CONFIG_PATH = os.environ.get("CONFIG_PATH", "/app/config/content.json")

with open(CONFIG_PATH, "r", encoding="utf-8") as _f:
    CONTENT = json.load(_f)

# Quiz correct-answer lookup
QUIZ_CORRECT: dict[str, str] = {}
CONTENT_META: dict[str, dict] = {}

for _page in CONTENT.get("pages", []):
    _poll = _page.get("poll")
    _quiz = _page.get("quiz")
    if _poll:
        CONTENT_META[_poll["id"]] = {
            "type": "poll",
            "page": _page["slug"],
            "theme": _page["theme"],
            "question": _poll["question"],
        }
    if _quiz:
        QUIZ_CORRECT[_quiz["id"]] = _quiz["correct"]
        CONTENT_META[_quiz["id"]] = {
            "type": "quiz",
            "page": _page["slug"],
            "theme": _page["theme"],
            "question": _quiz["question"],
        }

# ── App ───────────────────────────────────────────────────────────
app = FastAPI(title="Andreas Weiss API", docs_url=None, redoc_url=None)


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


# ── Models ────────────────────────────────────────────────────────
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


# ── Public endpoints ──────────────────────────────────────────────
@app.post("/api/event/visit")
async def track_visit(event: VisitEvent, request: Request):
    ip = _client_ip(request)
    geo = lookup(ip)
    db = get_db()
    try:
        db.execute(
            "INSERT INTO visits (page, city, region, country, uniq_day_hash, user_agent_short, ref) "
            "VALUES (?,?,?,?,?,?,?)",
            (event.page, geo["city"], geo["region"], geo["country"],
             _day_hash(ip), _short_ua(request), event.ref),
        )
        db.commit()
    finally:
        db.close()
    return {"ok": True}


@app.post("/api/poll/vote")
async def poll_vote(vote: PollVote, request: Request):
    ip = _client_ip(request)
    geo = lookup(ip)
    day_hash = _day_hash(ip)

    db = get_db()
    try:
        # 1-vote-per-day limit
        existing = db.execute(
            "SELECT id FROM poll_votes WHERE uniq_day_hash=? AND poll_id=? AND page=?",
            (day_hash, vote.poll_id, vote.page),
        ).fetchone()

        already_voted = existing is not None
        if not already_voted:
            db.execute(
                "INSERT INTO poll_votes (page, poll_id, option, city, region, country, uniq_day_hash) "
                "VALUES (?,?,?,?,?,?,?)",
                (vote.page, vote.poll_id, vote.option, geo["city"], geo["region"],
                 geo["country"], day_hash),
            )
            db.commit()

        # Current results
        rows = db.execute(
            "SELECT option, COUNT(*) as cnt FROM poll_votes WHERE poll_id=? GROUP BY option",
            (vote.poll_id,),
        ).fetchall()
    finally:
        db.close()

    total = sum(r["cnt"] for r in rows)
    results = {
        r["option"]: {
            "count": r["cnt"],
            "percent": round(r["cnt"] / total * 100) if total else 0,
        }
        for r in rows
    }
    return {"ok": True, "already_voted": already_voted, "results": results, "total": total}


@app.get("/api/poll/results/{poll_id}")
async def poll_results(poll_id: str):
    db = get_db()
    try:
        rows = db.execute(
            "SELECT option, COUNT(*) as cnt FROM poll_votes WHERE poll_id=? GROUP BY option",
            (poll_id,),
        ).fetchall()
    finally:
        db.close()

    total = sum(r["cnt"] for r in rows)
    results = {
        r["option"]: {
            "count": r["cnt"],
            "percent": round(r["cnt"] / total * 100) if total else 0,
        }
        for r in rows
    }
    return {"results": results, "total": total}


@app.post("/api/quiz/answer")
async def quiz_answer(answer: QuizAnswer, request: Request):
    ip = _client_ip(request)
    geo = lookup(ip)
    day_hash = _day_hash(ip)

    correct_answer = QUIZ_CORRECT.get(answer.quiz_id)
    is_correct = 1 if answer.option == correct_answer else 0

    db = get_db()
    try:
        db.execute(
            "INSERT INTO quiz_answers (page, quiz_id, option, is_correct, city, region, country, uniq_day_hash) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (answer.page, answer.quiz_id, answer.option, is_correct,
             geo["city"], geo["region"], geo["country"], day_hash),
        )
        db.commit()

        rows = db.execute(
            "SELECT option, COUNT(*) as cnt FROM quiz_answers WHERE quiz_id=? GROUP BY option",
            (answer.quiz_id,),
        ).fetchall()
    finally:
        db.close()

    total = sum(r["cnt"] for r in rows)
    results = {
        r["option"]: {
            "count": r["cnt"],
            "percent": round(r["cnt"] / total * 100) if total else 0,
        }
        for r in rows
    }

    explain = ""
    for p in CONTENT.get("pages", []):
        q = p.get("quiz")
        if q and q["id"] == answer.quiz_id:
            explain = q.get("explainCorrect", "")
            break

    return {
        "ok": True,
        "is_correct": bool(is_correct),
        "correct_answer": correct_answer,
        "explain": explain,
        "results": results,
        "total": total,
    }


@app.post("/api/feedback")
async def submit_feedback(fb: FeedbackMessage, request: Request):
    ip = _client_ip(request)
    geo = lookup(ip)
    day_hash = _day_hash(ip)

    # Rate limit: max 3 feedbacks per day per user
    db = get_db()
    try:
        count = db.execute(
            "SELECT COUNT(*) as c FROM feedback WHERE uniq_day_hash=? AND page=?",
            (day_hash, fb.page),
        ).fetchone()["c"]
        if count >= 3:
            return {"ok": False, "error": "Tageslimit erreicht"}

        db.execute(
            "INSERT INTO feedback (page, message, city, region, country, uniq_day_hash) "
            "VALUES (?,?,?,?,?,?)",
            (fb.page, fb.message, geo["city"], geo["region"], geo["country"], day_hash),
        )
        db.commit()
    finally:
        db.close()
    return {"ok": True}


# ── Admin endpoints ──────────────────────────────────────────────
@app.get("/api/admin/stats")
async def admin_stats(
    period: int = Query(30, ge=1, le=365),
    _admin: str = Depends(verify_admin),
):
    db = get_db()
    try:
        delta = f"-{period} days"

        total_visits = db.execute("SELECT COUNT(*) as c FROM visits").fetchone()["c"]

        today_iso = date.today().isoformat()
        unique_today = db.execute(
            "SELECT COUNT(DISTINCT uniq_day_hash) as c FROM visits WHERE date(ts)=?",
            (today_iso,),
        ).fetchone()["c"]

        per_page = [
            dict(r) for r in db.execute(
                "SELECT page, COUNT(*) as cnt FROM visits "
                "WHERE ts >= datetime('now', ?) GROUP BY page ORDER BY cnt DESC",
                (delta,),
            ).fetchall()
        ]

        top_cities = [
            dict(r) for r in db.execute(
                "SELECT city, COUNT(*) as cnt FROM visits "
                "WHERE ts >= datetime('now', ?) "
                "GROUP BY city ORDER BY cnt DESC LIMIT 20",
                (delta,),
            ).fetchall()
        ]

        top_regions = [
            dict(r) for r in db.execute(
                "SELECT region, COUNT(*) as cnt FROM visits "
                "WHERE ts >= datetime('now', ?) "
                "GROUP BY region ORDER BY cnt DESC LIMIT 20",
                (delta,),
            ).fetchall()
        ]

        top_countries = [
            dict(r) for r in db.execute(
                "SELECT country, COUNT(*) as cnt FROM visits "
                "WHERE ts >= datetime('now', ?) "
                "GROUP BY country ORDER BY cnt DESC LIMIT 20",
                (delta,),
            ).fetchall()
        ]

        daily = [
            dict(r) for r in db.execute(
                "SELECT date(ts) as day, COUNT(*) as total, "
                "COUNT(DISTINCT uniq_day_hash) as uniq "
                "FROM visits WHERE ts >= datetime('now', ?) "
                "GROUP BY date(ts) ORDER BY day",
                (delta,),
            ).fetchall()
        ]

        # Polls
        poll_rows = db.execute(
            "SELECT poll_id, option, COUNT(*) as cnt "
            "FROM poll_votes GROUP BY poll_id, option ORDER BY poll_id, cnt DESC"
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
            "SELECT quiz_id, option, is_correct, COUNT(*) as cnt "
            "FROM quiz_answers GROUP BY quiz_id, option ORDER BY quiz_id, cnt DESC"
        ).fetchall()
        quizzes: dict = {}
        for r in quiz_rows:
            qid = r["quiz_id"]
            if qid not in quizzes:
                quizzes[qid] = {"options": {}, "total": 0, "correct": 0}
            quizzes[qid]["options"][r["option"]] = {
                "count": r["cnt"],
                "is_correct": bool(r["is_correct"]),
            }
            quizzes[qid]["total"] += r["cnt"]
            if r["is_correct"]:
                quizzes[qid]["correct"] += r["cnt"]

        # Feedback
        feedback_rows = [
            dict(r) for r in db.execute(
                "SELECT id, ts, page, message, city, region, country "
                "FROM feedback WHERE ts >= datetime('now', ?) ORDER BY ts DESC LIMIT 100",
                (delta,),
            ).fetchall()
        ]
        feedback_count = db.execute("SELECT COUNT(*) as c FROM feedback").fetchone()["c"]
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
        "content_meta": CONTENT_META,
        "feedback": feedback_rows,
        "feedback_count": feedback_count,
    }


@app.get("/api/admin/export.csv")
async def admin_export(
    type: str = Query(..., pattern="^(visits|poll|quiz|feedback)$"),
    period: int = Query(30, ge=1, le=365),
    _admin: str = Depends(verify_admin),
):
    db = get_db()
    output = io.StringIO()
    delta = f"-{period} days"

    try:
        if type == "visits":
            rows = db.execute(
                "SELECT ts, page, city, region, country, user_agent_short, ref "
                "FROM visits WHERE ts >= datetime('now', ?) ORDER BY ts DESC",
                (delta,),
            ).fetchall()
            writer = csv.writer(output)
            writer.writerow(["ts", "page", "city", "region", "country", "user_agent", "ref"])
            for r in rows:
                writer.writerow([r["ts"], r["page"], r["city"], r["region"],
                                 r["country"], r["user_agent_short"], r["ref"]])
        elif type == "poll":
            rows = db.execute(
                "SELECT ts, page, poll_id, option, city, region, country "
                "FROM poll_votes WHERE ts >= datetime('now', ?) ORDER BY ts DESC",
                (delta,),
            ).fetchall()
            writer = csv.writer(output)
            writer.writerow(["ts", "page", "poll_id", "option", "city", "region", "country"])
            for r in rows:
                writer.writerow([r["ts"], r["page"], r["poll_id"], r["option"],
                                 r["city"], r["region"], r["country"]])
        elif type == "quiz":
            rows = db.execute(
                "SELECT ts, page, quiz_id, option, is_correct, city, region, country "
                "FROM quiz_answers WHERE ts >= datetime('now', ?) ORDER BY ts DESC",
                (delta,),
            ).fetchall()
            writer = csv.writer(output)
            writer.writerow(["ts", "page", "quiz_id", "option", "is_correct", "city", "region", "country"])
            for r in rows:
                writer.writerow([r["ts"], r["page"], r["quiz_id"], r["option"],
                                 r["is_correct"], r["city"], r["region"], r["country"]])
        elif type == "feedback":
            rows = db.execute(
                "SELECT ts, page, message, city, region, country "
                "FROM feedback WHERE ts >= datetime('now', ?) ORDER BY ts DESC",
                (delta,),
            ).fetchall()
            writer = csv.writer(output)
            writer.writerow(["ts", "page", "message", "city", "region", "country"])
            for r in rows:
                writer.writerow([r["ts"], r["page"], r["message"],
                                 r["city"], r["region"], r["country"]])
    finally:
        db.close()

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={type}_export.csv"},
    )


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": VERSION, "ts": datetime.now().isoformat()}
