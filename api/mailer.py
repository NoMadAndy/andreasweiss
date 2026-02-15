"""E-Mail module – SMTP sending for notifications, digest, password reset."""

import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from db import get_platform_settings

log = logging.getLogger("mailer")


def _get_smtp_config() -> dict | None:
    """Read SMTP settings from platform_settings. Returns None if not configured."""
    s = get_platform_settings()
    host = s.get("smtp_host", "").strip()
    if not host:
        return None
    return {
        "host": host,
        "port": int(s.get("smtp_port", "587")),
        "user": s.get("smtp_user", ""),
        "pass": s.get("smtp_pass", ""),
        "from": s.get("smtp_from", "") or s.get("smtp_user", ""),
        "tls": s.get("smtp_tls", "1") == "1",
    }


def send_email(to: str, subject: str, body_html: str) -> bool:
    """Send an HTML email. Returns True on success."""
    cfg = _get_smtp_config()
    if not cfg:
        log.warning("SMTP nicht konfiguriert – E-Mail wird nicht gesendet")
        return False
    if not to:
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = cfg["from"]
        msg["To"] = to
        msg["Subject"] = subject
        # Plain-text fallback
        import re
        plain = re.sub(r"<[^>]+>", "", body_html)
        plain = re.sub(r"\n{3,}", "\n\n", plain).strip()
        msg.attach(MIMEText(plain, "plain", "utf-8"))
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        if cfg["tls"]:
            ctx = ssl.create_default_context()
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as srv:
                srv.ehlo()
                srv.starttls(context=ctx)
                srv.ehlo()
                if cfg["user"]:
                    srv.login(cfg["user"], cfg["pass"])
                srv.sendmail(cfg["from"], [to], msg.as_string())
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as srv:
                if cfg["user"]:
                    srv.login(cfg["user"], cfg["pass"])
                srv.sendmail(cfg["from"], [to], msg.as_string())
        log.info("E-Mail gesendet an %s: %s", to, subject)
        return True
    except Exception as e:
        log.error("E-Mail-Versand fehlgeschlagen: %s", e)
        return False


# ── Notification Templates ────────────────────────────────────────

def send_feedback_notification(candidate_name: str, slug: str, email: str,
                                page: str, message: str, city: str,
                                base_url: str = ""):
    """Send instant notification when new feedback arrives."""
    subject = f"💬 Neue Rückmeldung – {candidate_name}"
    body = f"""
    <div style="font-family:-apple-system,sans-serif;max-width:600px;margin:0 auto">
        <h2 style="color:#1e6fb9">💬 Neue Rückmeldung</h2>
        <p>Für <strong>{candidate_name}</strong> ist eine neue Nachricht eingegangen:</p>
        <div style="background:#f5f5f7;border-left:4px solid #D97706;padding:1rem 1.25rem;border-radius:0 8px 8px 0;margin:1rem 0">
            <p style="color:#6e6e73;font-size:.85rem;margin:0 0 .5rem">Seite: {page}{(' · ' + city) if city and city != 'unknown' else ''}</p>
            <p style="margin:0;font-size:1rem;line-height:1.6">{message}</p>
        </div>
        <p style="margin-top:1.5rem">
            <a href="{base_url}/{slug}/admin/" style="background:#1e6fb9;color:#fff;padding:.6rem 1.2rem;border-radius:8px;text-decoration:none;font-weight:600">
                Zum Admin-Dashboard →
            </a>
        </p>
        <p style="color:#aaa;font-size:.78rem;margin-top:2rem">
            Du erhältst diese E-Mail, weil Benachrichtigungen für {candidate_name} aktiviert sind.
            Deaktiviere sie im <a href="{base_url}/{slug}/admin/">Admin-Bereich</a> unter Einstellungen.
        </p>
    </div>
    """
    return send_email(email, subject, body)


def send_daily_digest(candidate_name: str, slug: str, email: str,
                      visits: int, feedback_count: int, poll_votes: int,
                      quiz_answers: int, new_feedback: list,
                      base_url: str = ""):
    """Send daily summary digest."""
    subject = f"📊 Tagesbericht – {candidate_name}"

    fb_html = ""
    if new_feedback:
        fb_items = ""
        for fb in new_feedback[:10]:
            ts = fb.get("ts", "")[:16].replace("T", " ")
            fb_items += f"""
            <div style="background:#f5f5f7;border-left:3px solid #D97706;padding:.75rem 1rem;border-radius:0 6px 6px 0;margin:.5rem 0">
                <span style="color:#8e8e93;font-size:.75rem">{ts} · {fb.get('page', '')}</span>
                <p style="margin:.25rem 0 0;font-size:.9rem">{fb.get('message', '')}</p>
            </div>"""
        fb_html = f"""
        <h3 style="margin-top:1.5rem;color:#1d1d1f">💬 Neue Rückmeldungen ({feedback_count})</h3>
        {fb_items}
        """

    body = f"""
    <div style="font-family:-apple-system,sans-serif;max-width:600px;margin:0 auto">
        <h2 style="color:#1e6fb9">📊 Tagesbericht</h2>
        <p>Zusammenfassung der letzten 24 Stunden für <strong>{candidate_name}</strong>:</p>

        <table style="width:100%;border-collapse:collapse;margin:1rem 0">
            <tr>
                <td style="padding:.75rem;background:#f0f8ff;border-radius:8px 0 0 0;text-align:center;border:1px solid #e0e0e0">
                    <strong style="font-size:1.5rem;color:#1e6fb9">{visits}</strong><br>
                    <span style="font-size:.78rem;color:#6e6e73">Besuche</span>
                </td>
                <td style="padding:.75rem;background:#f0fff4;text-align:center;border:1px solid #e0e0e0">
                    <strong style="font-size:1.5rem;color:#16a34a">{feedback_count}</strong><br>
                    <span style="font-size:.78rem;color:#6e6e73">Rückmeldungen</span>
                </td>
                <td style="padding:.75rem;background:#fff8f0;text-align:center;border:1px solid #e0e0e0">
                    <strong style="font-size:1.5rem;color:#D97706">{poll_votes}</strong><br>
                    <span style="font-size:.78rem;color:#6e6e73">Umfragen</span>
                </td>
                <td style="padding:.75rem;background:#f5f0ff;border-radius:0 8px 0 0;text-align:center;border:1px solid #e0e0e0">
                    <strong style="font-size:1.5rem;color:#6A3FB5">{quiz_answers}</strong><br>
                    <span style="font-size:.78rem;color:#6e6e73">Quiz</span>
                </td>
            </tr>
        </table>

        {fb_html}

        <p style="margin-top:1.5rem">
            <a href="{base_url}/{slug}/admin/" style="background:#1e6fb9;color:#fff;padding:.6rem 1.2rem;border-radius:8px;text-decoration:none;font-weight:600">
                Zum Dashboard →
            </a>
        </p>
        <p style="color:#aaa;font-size:.78rem;margin-top:2rem">
            Tägliche Zusammenfassung für {candidate_name}.
            Deaktiviere sie im <a href="{base_url}/{slug}/admin/">Admin-Bereich</a> unter Einstellungen.
        </p>
    </div>
    """
    return send_email(email, subject, body)


def send_password_reset_email(candidate_name: str, email: str,
                               reset_url: str):
    """Send password reset link."""
    subject = f"🔑 Passwort zurücksetzen – {candidate_name}"
    body = f"""
    <div style="font-family:-apple-system,sans-serif;max-width:600px;margin:0 auto">
        <h2 style="color:#1e6fb9">🔑 Passwort zurücksetzen</h2>
        <p>Für den Admin-Bereich von <strong>{candidate_name}</strong> wurde ein Passwort-Reset angefordert.</p>
        <p>Klicke auf den folgenden Button, um ein neues Passwort zu setzen:</p>
        <p style="margin:1.5rem 0">
            <a href="{reset_url}" style="background:linear-gradient(135deg,#D97706,#b45309);color:#fff;padding:.75rem 1.5rem;border-radius:10px;text-decoration:none;font-weight:700;font-size:1rem">
                Neues Passwort setzen →
            </a>
        </p>
        <p style="color:#6e6e73;font-size:.85rem">
            Der Link ist <strong>1 Stunde</strong> gültig. Falls du keinen Reset angefordert hast, ignoriere diese E-Mail.
        </p>
        <p style="color:#aaa;font-size:.75rem;margin-top:2rem;border-top:1px solid #eee;padding-top:1rem">
            Link funktioniert nicht? Kopiere diese URL in deinen Browser:<br>
            <span style="word-break:break-all">{reset_url}</span>
        </p>
    </div>
    """
    return send_email(email, subject, body)
