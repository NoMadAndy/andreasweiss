"""
flyer.py – Generate printable campaign PDF documents (A4/A5/A6).

Produces a one-page PDF flyer focused on quiz participation & engagement:
  - Candidate portrait image
  - Party / campaign logo (SVG + raster support via cairosvg)
  - Large, prominent QR code encouraging scanning
  - Catchy headline encouraging quiz participation
  - Configurable text areas and elements
  - Optional longer descriptive text with bullet points

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

UPLOAD_BASE = os.environ.get("UPLOAD_BASE", "/data/uploads")
STATIC_DIR = os.environ.get("STATIC_DIR", "/static/assets/img")

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
    extra_text: str = ""

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
    show_links: bool = True

    # Theme topics to show (list of {"title": ..., "color": ...})
    topics: list = field(default_factory=list)

    # External links to show as QR codes at the bottom (list of {"label": ..., "url": ...})
    links: list = field(default_factory=list)

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


def _make_qr_image(url: str, size: int = 400) -> PILImage.Image:
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


def _find_logo(slug: str, config_path: str = "") -> str | None:
    """Find logo file: config path -> uploads -> static fallback."""
    if config_path and os.path.isfile(config_path):
        return config_path
    # Check uploads
    for ext in ("svg", "png", "jpg", "jpeg", "webp"):
        p = os.path.join(UPLOAD_BASE, slug, f"logo.{ext}")
        if os.path.isfile(p):
            return p
    # Fallback: static assets directory
    for name in ("logo.svg", "logo.png", "spd-logo.svg", "spd-logo.png"):
        p = os.path.join(STATIC_DIR, name)
        if os.path.isfile(p):
            return p
    return None


def _load_image_reader(filepath: str, target_size: int = 400) -> ImageReader | None:
    """Load an image file (including SVG) and return an ImageReader.

    SVG files are rasterized via cairosvg; raster formats are used directly.
    """
    if filepath.lower().endswith(".svg"):
        try:
            import cairosvg
            png_bytes = cairosvg.svg2png(
                url=filepath,
                output_width=target_size,
                output_height=target_size,
            )
            img = PILImage.open(io.BytesIO(png_bytes)).convert("RGBA")
            return ImageReader(img)
        except Exception:
            return None
    else:
        try:
            return ImageReader(filepath)
        except Exception:
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
    theme_light = colors.Color(*theme_rgb, alpha=0.08)

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

    # Logo (top right) – with SVG support
    if config.show_logo:
        logo_file = _find_logo(slug, config.logo_path)
        if logo_file:
            reader = _load_image_reader(logo_file, target_size=400)
            if reader:
                try:
                    logo_size = 22 * mm * scale
                    logo_x = page_w - margin - logo_size
                    logo_y = header_top - logo_size
                    c.drawImage(
                        reader, logo_x, logo_y,
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

    # ── Headline (quiz-focused) ──────────────────────────────────
    if config.show_headline and config.headline:
        hl_size = min(22 * scale, 22)
        hl_size = max(hl_size, 12)
        c.setFont("Helvetica-Bold", hl_size)
        c.setFillColor(colors.Color(0.1, 0.1, 0.1))
        max_chars = int(content_w / (hl_size * 0.5))
        lines = textwrap.wrap(config.headline, width=max_chars)
        for line in lines[:3]:
            c.drawString(margin, cursor_y, line)
            cursor_y -= hl_size + 2
        cursor_y -= 2 * mm * scale

    # ── Intro text ────────────────────────────────────────────────
    if config.show_intro and config.intro_text:
        intro_size = min(10 * scale, 10)
        intro_size = max(intro_size, 7)
        c.setFont("Helvetica", intro_size)
        c.setFillColor(colors.Color(0.2, 0.2, 0.2))
        max_chars = int(content_w / (intro_size * 0.45))
        lines = textwrap.wrap(config.intro_text, width=max_chars)
        for line in lines[:5]:
            c.drawString(margin, cursor_y, line)
            cursor_y -= intro_size + 2
        cursor_y -= 3 * mm * scale

    # ── QR Code Centerpiece ───────────────────────────────────────
    # This is the main action area – big QR + call-to-action
    if config.show_qr and config.website_url:
        qr_size = min(55 * mm * scale, 55 * mm)

        # Calculate box dimensions
        box_padding = 6 * mm * scale
        cta_label_size = min(13 * scale, 13)
        cta_label_size = max(cta_label_size, 9)
        bullet_size = min(9 * scale, 9)
        bullet_size = max(bullet_size, 6)

        bullet_texts = [
            "Quiz spielen & Wissen testen",
            "Zu lokalen Themen abstimmen",
            "Persoenliche Nachricht hinterlassen",
        ]
        num_bullets = len(bullet_texts)

        # Box height: padding + QR + gap + CTA label + bullets + padding
        cta_gap = 4 * mm * scale
        bullet_line_h = bullet_size + 3
        box_h = (box_padding + qr_size + cta_gap
                 + cta_label_size + 4
                 + num_bullets * bullet_line_h
                 + box_padding)

        box_y = cursor_y - box_h

        # Draw the highlighted box
        _draw_rounded_rect(c, margin, box_y, content_w, box_h,
                           5 * mm, fill_color=colors.Color(*theme_rgb, alpha=0.06))
        # Left accent stripe
        c.setFillColor(theme_color)
        c.rect(margin, box_y, 3.5, box_h, fill=1, stroke=0)

        # QR code – centered in box
        qr_img = _make_qr_image(config.website_url, size=500)
        qr_reader = ImageReader(qr_img)

        qr_x = margin + (content_w - qr_size) / 2
        qr_y = box_y + box_h - box_padding - qr_size

        c.drawImage(qr_reader, qr_x, qr_y, width=qr_size, height=qr_size)

        # Thin border around QR
        c.setStrokeColor(colors.Color(0.8, 0.8, 0.8))
        c.setLineWidth(0.75)
        c.rect(qr_x - 1.5, qr_y - 1.5,
               qr_size + 3, qr_size + 3, fill=0, stroke=1)

        # CTA text below QR – centered
        cta_label = "Jetzt scannen & mitmachen!"
        c.setFont("Helvetica-Bold", cta_label_size)
        c.setFillColor(colors.Color(0.12, 0.12, 0.12))
        label_w = c.stringWidth(cta_label, "Helvetica-Bold", cta_label_size)
        label_x = margin + (content_w - label_w) / 2
        label_y = qr_y - cta_gap - cta_label_size
        c.drawString(label_x, label_y, cta_label)

        # Bullet points – centered block
        c.setFont("Helvetica", bullet_size)
        # Calculate max bullet width for centering
        max_bullet_w = 0
        for bt in bullet_texts:
            bw = c.stringWidth(bt, "Helvetica", bullet_size) + 5 * mm
            if bw > max_bullet_w:
                max_bullet_w = bw
        bullets_x = margin + (content_w - max_bullet_w) / 2

        bullet_y = label_y - 5
        for bt in bullet_texts:
            bullet_y -= bullet_line_h
            c.setFillColor(theme_color)
            c.drawString(bullets_x, bullet_y, "\u2713")
            c.setFillColor(colors.Color(0.3, 0.3, 0.3))
            c.drawString(bullets_x + 4 * mm, bullet_y, bt)

        cursor_y = box_y - 5 * mm * scale

    # ── Topic tiles (optional, compact) ───────────────────────────
    if config.show_topics and config.topics:
        tile_h = 9 * mm * scale
        tile_gap = 3 * mm
        tile_font = min(9 * scale, 9)
        tile_font = max(tile_font, 6)

        col_w = (content_w - tile_gap) / 2
        for i, topic in enumerate(config.topics[:6]):
            col = i % 2
            row = i // 2
            tx = margin + col * (col_w + tile_gap)
            ty = cursor_y - row * (tile_h + tile_gap)

            t_color = _hex_to_rgb(topic.get("color", config.theme_color))
            fill = colors.Color(*t_color, alpha=0.12)
            border = colors.Color(*t_color)

            _draw_rounded_rect(c, tx, ty - tile_h, col_w, tile_h,
                               2.5 * mm, fill_color=fill)

            # Left color accent
            c.setFillColor(border)
            c.rect(tx, ty - tile_h, 3, tile_h, fill=1, stroke=0)

            # Tile text
            c.setFont("Helvetica-Bold", tile_font)
            c.setFillColor(colors.Color(*t_color))
            c.drawString(tx + 4 * mm, ty - tile_h + 2.5 * mm * scale,
                         topic.get("title", ""))

        total_rows = (len(config.topics[:6]) + 1) // 2
        cursor_y -= total_rows * (tile_h + tile_gap) + 3 * mm * scale

    # ── Extra text (longer text with bullet points) ───────────────
    if config.extra_text and config.extra_text.strip():
        extra_size = min(9 * scale, 9)
        extra_size = max(extra_size, 6)
        max_chars = int(content_w / (extra_size * 0.45))
        line_h = extra_size + 2.5

        raw_lines = config.extra_text.strip().splitlines()
        for raw_line in raw_lines[:10]:
            raw_line = raw_line.strip()
            if not raw_line:
                cursor_y -= line_h * 0.5
                continue

            # Detect bullet points (- or * or •)
            is_bullet = False
            if raw_line.startswith(("- ", "* ", "\u2022 ")):
                is_bullet = True
                raw_line = raw_line.lstrip("-*\u2022 ").strip()

            wrapped = textwrap.wrap(raw_line, width=max_chars)
            for j, wl in enumerate(wrapped[:3]):
                if is_bullet and j == 0:
                    c.setFillColor(theme_color)
                    c.setFont("Helvetica-Bold", extra_size)
                    c.drawString(margin, cursor_y, "\u2022")
                    c.setFillColor(colors.Color(0.2, 0.2, 0.2))
                    c.setFont("Helvetica", extra_size)
                    c.drawString(margin + 4 * mm, cursor_y, wl)
                elif is_bullet:
                    c.setFont("Helvetica", extra_size)
                    c.setFillColor(colors.Color(0.2, 0.2, 0.2))
                    c.drawString(margin + 4 * mm, cursor_y, wl)
                else:
                    c.setFont("Helvetica", extra_size)
                    c.setFillColor(colors.Color(0.2, 0.2, 0.2))
                    c.drawString(margin, cursor_y, wl)
                cursor_y -= line_h
        cursor_y -= 2 * mm * scale

    # ── CTA area ──────────────────────────────────────────────────
    if config.show_cta and config.cta_text:
        cta_box_h = 16 * mm * scale
        cta_y = cursor_y - cta_box_h

        # Ensure CTA doesn't overlap bottom bar
        if cta_y < 8 * mm:
            cta_y = 8 * mm

        _draw_rounded_rect(c, margin, cta_y, content_w, cta_box_h,
                           4 * mm, fill_color=colors.Color(*theme_rgb, alpha=0.08))

        # Left accent
        c.setFillColor(theme_color)
        c.rect(margin, cta_y, 3, cta_box_h, fill=1, stroke=0)

        cta_size = min(11 * scale, 11)
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
            sub_size = min(8 * scale, 8)
            sub_size = max(sub_size, 6)
            c.setFont("Helvetica", sub_size)
            c.setFillColor(colors.Color(0.4, 0.4, 0.4))
            c.drawString(margin + 5 * mm, text_y - 1, config.cta_sub)

        cursor_y = cta_y - 3 * mm * scale

    # ── Links with QR codes ───────────────────────────────────────
    if config.show_links and config.links:
        valid_links = [lnk for lnk in config.links if lnk.get("url")]
        if valid_links:
            qr_item_size = min(22 * mm * scale, 22 * mm)
            label_font_size = min(6 * scale, 6)
            label_font_size = max(label_font_size, 5)
            item_gap = 4 * mm * scale

            num_links = len(valid_links)
            item_w = qr_item_size
            total_w = num_links * item_w + (num_links - 1) * item_gap
            # Clamp to content width: limit number of items that fit
            max_items_per_row = max(1, int((content_w + item_gap) / (item_w + item_gap)))
            rows_needed = (num_links + max_items_per_row - 1) // max_items_per_row

            section_label = "Weitere Links"
            section_font_size = min(7 * scale, 7)
            section_font_size = max(section_font_size, 5)
            label_line_h = label_font_size + 2

            row_h = qr_item_size + label_line_h + 2
            section_total_h = section_font_size + 3 * mm * scale + rows_needed * (row_h + 2 * mm * scale)

            # Only draw if there is room above the bottom bar
            if cursor_y - section_total_h > 8 * mm:
                # Section header
                c.setFont("Helvetica-Bold", section_font_size)
                c.setFillColor(colors.Color(0.4, 0.4, 0.4))
                c.drawString(margin, cursor_y, section_label)
                cursor_y -= section_font_size + 2 * mm * scale

                for row_idx in range(rows_needed):
                    row_links = valid_links[row_idx * max_items_per_row:(row_idx + 1) * max_items_per_row]
                    n = len(row_links)
                    row_total_w = n * item_w + (n - 1) * item_gap
                    start_x = margin + (content_w - row_total_w) / 2

                    for col_idx, lnk in enumerate(row_links):
                        ix = start_x + col_idx * (item_w + item_gap)
                        iy = cursor_y - qr_item_size

                        # Draw small QR code
                        try:
                            lnk_qr = _make_qr_image(lnk["url"], size=200)
                            lnk_reader = ImageReader(lnk_qr)
                            # Thin border
                            c.setStrokeColor(colors.Color(0.8, 0.8, 0.8))
                            c.setLineWidth(0.5)
                            c.rect(ix - 0.75, iy - 0.75, item_w + 1.5, qr_item_size + 1.5, fill=0, stroke=1)
                            c.drawImage(lnk_reader, ix, iy, width=item_w, height=qr_item_size)
                        except Exception:
                            pass

                        # Draw label below QR
                        raw_label = lnk.get("label") or lnk.get("url", "")
                        max_label_chars = max(1, int(item_w / (label_font_size * 0.45)))
                        label_text = textwrap.shorten(raw_label, width=max_label_chars, placeholder="…")
                        c.setFont("Helvetica", label_font_size)
                        c.setFillColor(colors.Color(0.3, 0.3, 0.3))
                        label_w = c.stringWidth(label_text, "Helvetica", label_font_size)
                        label_x = ix + (item_w - label_w) / 2
                        c.drawString(label_x, iy - label_line_h, label_text)

                    cursor_y -= qr_item_size + label_line_h + 2 * mm * scale

                cursor_y -= 2 * mm * scale

    # ── Website URL (small, at bottom) ────────────────────────────
    if config.show_website_url and config.website_url:
        url_size = min(8 * scale, 8)
        url_size = max(url_size, 6)
        display_url = config.website_url.replace("https://", "").replace("http://", "")
        c.setFont("Helvetica", url_size)
        c.setFillColor(theme_color)
        url_w = c.stringWidth(display_url, "Helvetica", url_size)
        url_x = (page_w - url_w) / 2
        c.drawString(url_x, 5 * mm, display_url)

    # ── Bottom accent bar ─────────────────────────────────────────
    c.setFillColor(theme_color)
    c.rect(0, 0, page_w, 3 * mm, fill=1, stroke=0)

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()
