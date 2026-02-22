"""
flyer.py – Generate printable campaign PDF documents (A4/A5/A6).

Produces a one-page PDF flyer with configurable elements:
  - Candidate portrait image
  - Party / campaign logo
  - QR code linking to the candidate's website
  - Headline, tagline, call-to-action texts
  - Election date badge
  - Theme color accent

All visual elements can be toggled on/off via the `FlyerConfig` dataclass.
"""

import io
import os
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

import qrcode
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, A5, A6, landscape
from reportlab.lib.units import mm, cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from svglib.svglib import svg2rlg
from reportlab.graphics import renderPDF

UPLOAD_BASE = os.environ.get("UPLOAD_BASE", "/data/uploads")

# ── Page sizes ────────────────────────────────────────────────────
PAGE_SIZES = {
    "a4": A4,
    "a5": A5,
    "a6": A6,
}


@dataclass
class FlyerConfig:
    """All configurable options for the campaign flyer."""
    # Content
    candidate_name: str = ""
    party: str = ""
    tagline: str = ""
    election_date: str = ""
    headline: str = ""
    intro_text: str = ""
    cta_text: str = ""
    cta_sub: str = ""
    website_url: str = ""

    # Toggle which elements to show
    show_portrait: bool = True
    show_logo: bool = True
    show_qr: bool = True
    show_headline: bool = True
    show_intro: bool = True
    show_cta: bool = True
    show_election_date: bool = True
    show_tagline: bool = True
    show_website_url: bool = True
    show_topics: bool = True

    # Theme topics to show (list of {"title": ..., "color": ...})
    topics: list = field(default_factory=list)

    # Layout
    page_size: str = "a4"          # a4, a5, a6
    orientation: str = "portrait"  # portrait, landscape
    theme_color: str = "#1E6FB9"

    # File paths (resolved server-side)
    portrait_path: str = ""
    logo_path: str = ""


def _hex_to_rgb(hex_color: str) -> tuple:
    """Convert #RRGGBB to (r, g, b) floats 0..1."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return (0.12, 0.44, 0.73)  # fallback blue
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (r / 255.0, g / 255.0, b / 255.0)


def _darken(rgb: tuple, factor: float = 0.7) -> tuple:
    return tuple(max(0, c * factor) for c in rgb)


def _make_qr_image(url: str, size: int = 200) -> PILImage.Image:
    """Generate a QR code as a PIL Image."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    return img.resize((size, size), PILImage.LANCZOS)


def _resolve_image(slug: str, filename: str) -> str | None:
    """Find an uploaded image, return path or None."""
    path = os.path.join(UPLOAD_BASE, slug, filename)
    if os.path.isfile(path):
        return path
    return None


def _draw_rounded_rect(c, x, y, w, h, radius, fill_color=None, stroke_color=None):
    """Draw a rounded rectangle on the canvas."""
    p = c.beginPath()
    p.moveTo(x + radius, y)
    p.lineTo(x + w - radius, y)
    p.arcTo(x + w - radius, y, x + w, y + radius, radius)
    p.lineTo(x + w, y + h - radius)
    p.arcTo(x + w, y + h - radius, x + w - radius, y + h, radius)
    p.lineTo(x + radius, y + h)
    p.arcTo(x + radius, y + h, x, y + h - radius, radius)
    p.lineTo(x, y + radius)
    p.arcTo(x, y + radius, x + radius, y, radius)
    p.close()
    if fill_color:
        c.setFillColor(fill_color)
    if stroke_color:
        c.setStrokeColor(stroke_color)
    if fill_color and stroke_color:
        c.drawPath(p, fill=1, stroke=1)
    elif fill_color:
        c.drawPath(p, fill=1, stroke=0)
    elif stroke_color:
        c.drawPath(p, fill=0, stroke=1)


def generate_flyer_pdf(slug: str, config: FlyerConfig) -> bytes:
    """Generate a campaign flyer PDF and return the bytes."""
    # Resolve page size
    base_size = PAGE_SIZES.get(config.page_size, A4)
    if config.orientation == "landscape":
        page_w, page_h = landscape(base_size)
    else:
        page_w, page_h = base_size

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_w, page_h))
    c.setTitle(f"Flyer – {config.candidate_name}")

    theme_rgb = _hex_to_rgb(config.theme_color)
    theme_color = colors.Color(*theme_rgb)
    theme_dark = colors.Color(*_darken(theme_rgb, 0.65))

    margin = 15 * mm
    content_w = page_w - 2 * margin

    # Scale factor for smaller pages
    scale = min(page_w / A4[0], page_h / A4[1])

    # ── Top accent bar ────────────────────────────────────────────
    bar_h = 8 * mm * scale
    c.setFillColor(theme_color)
    c.rect(0, page_h - bar_h, page_w, bar_h, fill=1, stroke=0)

    # Gradient-like second bar
    c.setFillColor(theme_dark)
    c.rect(0, page_h - bar_h - 1.5 * mm, page_w, 1.5 * mm, fill=1, stroke=0)

    cursor_y = page_h - bar_h - 6 * mm

    # ── Header area: Portrait + Name/Party + Logo ─────────────────
    header_h = 38 * mm * scale
    header_top = cursor_y

    portrait_size = 32 * mm * scale
    portrait_x = margin
    portrait_y = header_top - portrait_size

    # Draw portrait
    if config.show_portrait:
        portrait_file = config.portrait_path or _resolve_image(slug, "portrait.jpg")
        if portrait_file and os.path.isfile(portrait_file):
            try:
                # Circular clip for portrait
                c.saveState()
                cx = portrait_x + portrait_size / 2
                cy = portrait_y + portrait_size / 2
                r = portrait_size / 2

                # Draw circular border
                c.setStrokeColor(theme_color)
                c.setLineWidth(1.5)
                c.circle(cx, cy, r + 1, fill=0, stroke=1)

                # Clip to circle
                p = c.beginPath()
                p.circle(cx, cy, r)
                p.close()
                c.clipPath(p, stroke=0)

                c.drawImage(
                    portrait_file, portrait_x, portrait_y,
                    width=portrait_size, height=portrait_size,
                    preserveAspectRatio=True, mask="auto",
                )
                c.restoreState()
                text_left = portrait_x + portrait_size + 5 * mm
            except Exception:
                text_left = margin
        else:
            text_left = margin
    else:
        text_left = margin

    # Candidate name
    name_y = header_top - 10 * mm * scale
    c.setFillColor(colors.Color(0.1, 0.1, 0.1))
    name_size = min(22 * scale, 22)
    name_size = max(name_size, 12)
    c.setFont("Helvetica-Bold", name_size)
    c.drawString(text_left, name_y, config.candidate_name)

    # Party line
    if config.party:
        party_y = name_y - (name_size + 3) * scale
        party_size = min(11 * scale, 11)
        party_size = max(party_size, 7)
        c.setFont("Helvetica", party_size)
        c.setFillColor(colors.Color(0.4, 0.4, 0.4))
        c.drawString(text_left, party_y, config.party)

    # Logo (top right)
    if config.show_logo:
        logo_file = config.logo_path
        if not logo_file:
            logo_file = _resolve_image(slug, "logo.svg")
            if not logo_file:
                logo_file = _resolve_image(slug, "logo.png")
        if logo_file and os.path.isfile(logo_file):
            try:
                logo_size = 22 * mm * scale
                logo_x = page_w - margin - logo_size
                logo_y = header_top - logo_size
                if logo_file.endswith(".svg"):
                    drawing = svg2rlg(logo_file)
                    if drawing:
                        sx = logo_size / drawing.width
                        sy = logo_size / drawing.height
                        s = min(sx, sy)
                        drawing.width = drawing.minWidth() * s
                        drawing.height = drawing.height * s
                        drawing.scale(s, s)
                        renderPDF.draw(drawing, c, logo_x, logo_y)
                else:
                    c.drawImage(
                        logo_file, logo_x, logo_y,
                        width=logo_size, height=logo_size,
                        preserveAspectRatio=True, mask="auto",
                    )
            except Exception:
                pass

    cursor_y = header_top - header_h

    # ── Election date badge ───────────────────────────────────────
    if config.show_election_date and config.election_date:
        badge_h = 8 * mm * scale
        badge_text = f"Wahl am {config.election_date}"
        badge_font_size = min(10 * scale, 10)
        badge_font_size = max(badge_font_size, 7)
        c.setFont("Helvetica-Bold", badge_font_size)
        badge_w = c.stringWidth(badge_text, "Helvetica-Bold", badge_font_size) + 8 * mm
        badge_x = margin
        badge_y = cursor_y

        _draw_rounded_rect(c, badge_x, badge_y, badge_w, badge_h,
                           3 * mm, fill_color=theme_color)
        c.setFillColor(colors.white)
        c.drawString(badge_x + 4 * mm, badge_y + 2.2 * mm * scale, badge_text)

        cursor_y -= badge_h + 5 * mm * scale

    # ── Tagline ───────────────────────────────────────────────────
    if config.show_tagline and config.tagline:
        tag_size = min(10 * scale, 10)
        tag_size = max(tag_size, 7)
        c.setFont("Helvetica-Oblique", tag_size)
        c.setFillColor(theme_color)
        c.drawString(margin, cursor_y, config.tagline)
        cursor_y -= tag_size + 4 * mm * scale

    # ── Headline ──────────────────────────────────────────────────
    if config.show_headline and config.headline:
        hl_size = min(20 * scale, 20)
        hl_size = max(hl_size, 11)
        c.setFont("Helvetica-Bold", hl_size)
        c.setFillColor(colors.Color(0.1, 0.1, 0.1))
        # Word wrap
        max_chars = int(content_w / (hl_size * 0.5))
        lines = textwrap.wrap(config.headline, width=max_chars)
        for line in lines[:3]:
            c.drawString(margin, cursor_y, line)
            cursor_y -= hl_size + 2
        cursor_y -= 3 * mm * scale

    # ── Intro text ────────────────────────────────────────────────
    if config.show_intro and config.intro_text:
        intro_size = min(10 * scale, 10)
        intro_size = max(intro_size, 7)
        c.setFont("Helvetica", intro_size)
        c.setFillColor(colors.Color(0.2, 0.2, 0.2))
        max_chars = int(content_w / (intro_size * 0.45))
        lines = textwrap.wrap(config.intro_text, width=max_chars)
        for line in lines[:6]:
            c.drawString(margin, cursor_y, line)
            cursor_y -= intro_size + 2
        cursor_y -= 4 * mm * scale

    # ── Topic tiles ───────────────────────────────────────────────
    if config.show_topics and config.topics:
        tile_h = 10 * mm * scale
        tile_gap = 3 * mm
        tile_font = min(10 * scale, 10)
        tile_font = max(tile_font, 7)

        # Arrange in 2 columns
        col_w = (content_w - tile_gap) / 2
        for i, topic in enumerate(config.topics[:6]):
            col = i % 2
            row = i // 2
            tx = margin + col * (col_w + tile_gap)
            ty = cursor_y - row * (tile_h + tile_gap)

            t_color = _hex_to_rgb(topic.get("color", config.theme_color))
            fill = colors.Color(*t_color, alpha=0.12)
            border = colors.Color(*t_color)

            # Tile background
            _draw_rounded_rect(c, tx, ty - tile_h, col_w, tile_h,
                               2.5 * mm, fill_color=fill)

            # Left color accent
            c.setFillColor(border)
            c.rect(tx, ty - tile_h, 3, tile_h, fill=1, stroke=0)

            # Tile text
            c.setFont("Helvetica-Bold", tile_font)
            c.setFillColor(colors.Color(*t_color))
            c.drawString(tx + 4 * mm, ty - tile_h + 3 * mm * scale, topic.get("title", ""))

        total_rows = (len(config.topics[:6]) + 1) // 2
        cursor_y -= total_rows * (tile_h + tile_gap) + 3 * mm * scale

    # ── CTA area ──────────────────────────────────────────────────
    if config.show_cta and config.cta_text:
        cta_box_h = 18 * mm * scale
        cta_y = cursor_y - cta_box_h

        _draw_rounded_rect(c, margin, cta_y, content_w, cta_box_h,
                           4 * mm, fill_color=colors.Color(*theme_rgb, alpha=0.08))

        # Left accent
        c.setFillColor(theme_color)
        c.rect(margin, cta_y, 3, cta_box_h, fill=1, stroke=0)

        cta_size = min(12 * scale, 12)
        cta_size = max(cta_size, 8)
        c.setFont("Helvetica-Bold", cta_size)
        c.setFillColor(colors.Color(0.15, 0.15, 0.15))
        max_chars = int((content_w - 8 * mm) / (cta_size * 0.5))
        lines = textwrap.wrap(config.cta_text, width=max_chars)
        text_y = cta_y + cta_box_h - 5 * mm * scale
        for line in lines[:2]:
            c.drawString(margin + 5 * mm, text_y, line)
            text_y -= cta_size + 2

        if config.cta_sub:
            sub_size = min(9 * scale, 9)
            sub_size = max(sub_size, 6)
            c.setFont("Helvetica", sub_size)
            c.setFillColor(colors.Color(0.4, 0.4, 0.4))
            c.drawString(margin + 5 * mm, text_y - 1, config.cta_sub)

        cursor_y = cta_y - 5 * mm * scale

    # ── Bottom area: QR + Website URL ─────────────────────────────
    bottom_h = 35 * mm * scale
    bottom_y = margin

    if config.show_qr and config.website_url:
        qr_size = min(28 * mm * scale, 28 * mm)
        qr_img = _make_qr_image(config.website_url, size=300)
        qr_reader = ImageReader(qr_img)

        # Center QR if no URL text, otherwise left-align
        if config.show_website_url:
            qr_x = margin
        else:
            qr_x = (page_w - qr_size) / 2

        c.drawImage(qr_reader, qr_x, bottom_y, width=qr_size, height=qr_size)

        # Draw a thin border around QR
        c.setStrokeColor(colors.Color(0.85, 0.85, 0.85))
        c.setLineWidth(0.5)
        c.rect(qr_x - 1, bottom_y - 1, qr_size + 2, qr_size + 2, fill=0, stroke=1)

        # URL text next to QR
        if config.show_website_url:
            url_x = qr_x + qr_size + 5 * mm
            url_size = min(9 * scale, 9)
            url_size = max(url_size, 6)

            # "Jetzt online besuchen:" label
            label_y = bottom_y + qr_size - 4 * mm * scale
            c.setFont("Helvetica-Bold", url_size + 1)
            c.setFillColor(colors.Color(0.15, 0.15, 0.15))
            c.drawString(url_x, label_y, "Jetzt online besuchen:")

            # URL
            c.setFont("Helvetica", url_size)
            c.setFillColor(theme_color)
            display_url = config.website_url.replace("https://", "").replace("http://", "")
            c.drawString(url_x, label_y - url_size - 3, display_url)

            # Feature bullets
            bullet_y = label_y - 2 * (url_size + 3) - 4
            bullet_size = min(8 * scale, 8)
            bullet_size = max(bullet_size, 6)
            c.setFont("Helvetica", bullet_size)
            c.setFillColor(colors.Color(0.3, 0.3, 0.3))

            bullets = []
            bullets.append("Abstimmen & Meinung sagen")
            bullets.append("Quiz mitmachen")
            bullets.append("Freitext hinterlassen")

            for bullet_text in bullets:
                c.setFillColor(theme_color)
                c.drawString(url_x, bullet_y, "\u2022")
                c.setFillColor(colors.Color(0.3, 0.3, 0.3))
                c.drawString(url_x + 4 * mm, bullet_y, bullet_text)
                bullet_y -= bullet_size + 3

    elif config.show_website_url and config.website_url:
        # Just URL, no QR
        url_size = min(10 * scale, 10)
        url_size = max(url_size, 7)
        c.setFont("Helvetica-Bold", url_size)
        c.setFillColor(theme_color)
        display_url = config.website_url.replace("https://", "").replace("http://", "")
        c.drawString(margin, bottom_y + 10 * mm, display_url)

    # ── Bottom accent bar ─────────────────────────────────────────
    c.setFillColor(theme_color)
    c.rect(0, 0, page_w, 3 * mm, fill=1, stroke=0)

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()
