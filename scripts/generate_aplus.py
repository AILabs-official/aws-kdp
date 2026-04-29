#!/usr/bin/env python3
"""Generate KDP A+ Content image assets for sudoku books.

Renders the 5 image-bearing modules referenced in `listings.a_plus_modules`
(modules 1, 2, 4, 5, 6 — modules 0/3/7 are text-only). Reuses color schemes,
typography, and grid renderers from `generate_cover.py` so the A+ assets
visually match the cover and reinforce the brand.

Output paths:
    output/{theme}/aplus/module_1_header.png        1464 x 600
    output/{theme}/aplus/module_2_highlight_{1..4}.png  970 x 600 each
    output/{theme}/aplus/module_4_inside.png        970 x 600
    output/{theme}/aplus/module_5_*.png             970 x 300
    output/{theme}/aplus/module_6_*.png             970 x 300

Usage:
    python3 scripts/generate_aplus.py --theme extra_large_print_sudoku
    python3 scripts/generate_aplus.py --theme sudoku_for_kids_8_12
    python3 scripts/generate_aplus.py --all-sudoku   # batch all sudoku books
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import config  # noqa: E402
from generate_cover import (  # noqa: E402
    SUDOKU_FRONT_COLOR_SCHEMES,
    _hex_to_rgb,
    _heavy_font,
    _wrap_text,
)


def _get_listing_aplus(book_id: int) -> list[dict]:
    """Pull a_plus_modules JSON from the listings table for this book."""
    out = subprocess.run(
        ["python3", str(HERE / "db.py"), "listings", "list", "--book_id", str(book_id)],
        capture_output=True, text=True, check=True,
    )
    rows = json.loads(out.stdout)
    if not rows:
        raise SystemExit(f"No listings row for book_id={book_id}")
    return rows[0].get("a_plus_modules") or []


def _get_book_id_from_theme(theme: str) -> int:
    out = subprocess.run(
        ["python3", str(HERE / "db.py"), "books", "list"],
        capture_output=True, text=True, check=True,
    )
    rows = json.loads(out.stdout)
    for r in rows:
        if r.get("theme_key") == theme:
            return r["id"]
    raise SystemExit(f"No book row for theme_key={theme}")


def _get_module(modules: list[dict], module_id: int) -> dict | None:
    for m in modules:
        if m.get("module_id") == module_id:
            return m
    return None


def _get_module_by_type(modules: list[dict], mtype: str, idx: int = 0) -> dict | None:
    """Get N-th module of a given type (0-indexed)."""
    matches = [m for m in modules if m.get("module_type") == mtype]
    return matches[idx] if idx < len(matches) else None


# ──────────────────────────────────────────────────────────
# Icon primitives (programmatic — fonts can't reliably render emoji)
# ──────────────────────────────────────────────────────────

def _icon_gift(d: ImageDraw.ImageDraw, cx: int, cy: int, size: int, color: tuple) -> None:
    """Gift box: square + ribbon cross + bow."""
    half = size // 2
    box_top = cy - half // 2
    # Box
    d.rectangle([cx - half, box_top, cx + half, cy + half], fill=color)
    # Ribbon vertical
    rw = max(3, size // 12)
    d.rectangle([cx - rw, box_top, cx + rw, cy + half], fill=(255, 255, 255))
    # Ribbon horizontal
    d.rectangle([cx - half, box_top + half // 2 - rw, cx + half, box_top + half // 2 + rw], fill=(255, 255, 255))
    # Bow loops
    bow_r = size // 6
    d.ellipse([cx - bow_r - rw, box_top - bow_r * 2, cx - rw, box_top], fill=color)
    d.ellipse([cx + rw, box_top - bow_r * 2, cx + bow_r + rw, box_top], fill=color)


def _icon_calendar(d: ImageDraw.ImageDraw, cx: int, cy: int, size: int, color: tuple) -> None:
    """Calendar with header bar + date star."""
    half = size // 2
    d.rectangle([cx - half, cy - half + 4, cx + half, cy + half], fill=color)
    # Header bar
    d.rectangle([cx - half, cy - half + 4, cx + half, cy - half + 14], fill=(255, 255, 255))
    # Star center (date)
    star_r = size // 4
    pts = []
    import math as _m
    for i in range(10):
        a = -_m.pi / 2 + i * _m.pi / 5
        rr = star_r if i % 2 == 0 else star_r * 0.4
        pts.append((cx + rr * _m.cos(a), cy + 4 + rr * _m.sin(a)))
    d.polygon(pts, fill=(255, 255, 255))


def _icon_heart(d: ImageDraw.ImageDraw, cx: int, cy: int, size: int, color: tuple) -> None:
    """Heart shape using two ellipses + triangle."""
    r = size // 3
    # Two top circles
    d.ellipse([cx - r * 2, cy - r, cx, cy + r], fill=color)
    d.ellipse([cx, cy - r, cx + r * 2, cy + r], fill=color)
    # Bottom triangle
    d.polygon([(cx - r * 2, cy + r // 2),
               (cx + r * 2, cy + r // 2),
               (cx, cy + r * 2)], fill=color)


def _icon_flower(d: ImageDraw.ImageDraw, cx: int, cy: int, size: int, color: tuple) -> None:
    """5-petal flower."""
    import math as _m
    petal_r = size // 4
    for i in range(5):
        a = -_m.pi / 2 + i * 2 * _m.pi / 5
        px = cx + (size // 4) * _m.cos(a)
        py = cy + (size // 4) * _m.sin(a)
        d.ellipse([px - petal_r, py - petal_r, px + petal_r, py + petal_r], fill=color)
    # Center
    cr = size // 8
    d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=(255, 255, 255))


def _icon_umbrella(d: ImageDraw.ImageDraw, cx: int, cy: int, size: int, color: tuple) -> None:
    """Umbrella: half-circle dome + handle."""
    half = size // 2
    # Dome
    d.pieslice([cx - half, cy - half, cx + half, cy + half // 2],
               start=180, end=360, fill=color)
    # Handle
    handle_w = max(3, size // 14)
    d.rectangle([cx - handle_w, cy, cx + handle_w, cy + half], fill=color)
    # Handle hook (curve at bottom)
    hook_r = size // 8
    d.ellipse([cx - hook_r * 2 - handle_w, cy + half - hook_r,
               cx - handle_w, cy + half + hook_r], fill=color)


def _icon_book(d: ImageDraw.ImageDraw, cx: int, cy: int, size: int, color: tuple) -> None:
    """Open book silhouette."""
    half = size // 2
    # Book pages (V-shape, two halves)
    # Left page
    d.polygon([(cx - half, cy - half // 2),
               (cx, cy - half // 3),
               (cx, cy + half // 2),
               (cx - half, cy + half // 2)], fill=color)
    # Right page
    d.polygon([(cx + half, cy - half // 2),
               (cx, cy - half // 3),
               (cx, cy + half // 2),
               (cx + half, cy + half // 2)], fill=color)
    # Center fold line
    d.line([(cx, cy - half // 3), (cx, cy + half // 2)], fill=(255, 255, 255), width=2)


def _icon_plane(d: ImageDraw.ImageDraw, cx: int, cy: int, size: int, color: tuple) -> None:
    """Paper plane."""
    half = size // 2
    # Body — triangle pointing right
    d.polygon([(cx - half, cy + half // 4),
               (cx + half, cy),
               (cx - half, cy - half // 4),
               (cx - half // 4, cy)], fill=color)
    # Inner fold line
    d.line([(cx - half, cy), (cx - half // 4, cy)], fill=(255, 255, 255), width=2)


ICON_RENDERERS = {
    "gift": _icon_gift,
    "calendar": _icon_calendar,
    "heart": _icon_heart,
    "flower": _icon_flower,
    "umbrella": _icon_umbrella,
    "book": _icon_book,
    "plane": _icon_plane,
}


# ──────────────────────────────────────────────────────────
# Watermark helper (subtler than cover — A+ bg should breathe)
# ──────────────────────────────────────────────────────────

def _draw_digit_watermark(draw, x0, y0, x1, y1, color, seed: int, density: int = 25):
    rng = random.Random(seed ^ 0xA1F5)
    font = _heavy_font(int(0.40 * config.DPI))
    for _ in range(density):
        x = rng.randint(x0, x1 - 60)
        y = rng.randint(y0, y1 - 60)
        d = str(rng.randint(1, 9))
        draw.text((x, y), d, font=font, fill=color)


# ──────────────────────────────────────────────────────────
# Sudoku mini-grid renderer (white card with header bar)
# ──────────────────────────────────────────────────────────

def _draw_sudoku_card(
    canvas: Image.Image,
    x: int, y: int, w: int, h: int,
    clues: list[list[int]],
    diff_label: str,
    bg_color: tuple,
    title_color: tuple,
    pad: int = 12,
    shadow: bool = True,
    header_prefix: str = "SUDOKU",
) -> None:
    """Render a single white 'page card' with a colored header + sudoku grid.

    Set header_prefix="" to show only the difficulty label (useful when card
    is narrow and "SUDOKU MEDIUM" would overflow / collide with adjacent cards).
    """
    d = ImageDraw.Draw(canvas)
    # Drop shadow
    if shadow:
        d.rectangle([x + 6, y + 6, x + w + 6, y + h + 6], fill=(0, 0, 0, 60) if canvas.mode == "RGBA" else (180, 180, 180))
    # Card bg
    d.rectangle([x, y, x + w, y + h], fill=(255, 255, 255))
    # Header bar
    header_h = int(h * 0.13)
    d.rectangle([x, y, x + w, y + header_h], fill=bg_color)
    # Header text — auto-shrink to fit so wider headers don't bleed into
    # neighbor cards when these are pasted close together with rotation
    hf_size = max(14, int(header_h * 0.55))
    hf = _heavy_font(hf_size)
    ht = f"{header_prefix}  {diff_label.upper()}".strip()
    hbb = d.textbbox((0, 0), ht, font=hf)
    while (hbb[2] - hbb[0]) > w - 16 and hf_size > 10:
        hf_size -= 2
        hf = _heavy_font(hf_size)
        hbb = d.textbbox((0, 0), ht, font=hf)
    d.text(
        (x + (w - (hbb[2] - hbb[0])) // 2 - hbb[0],
         y + (header_h - (hbb[3] - hbb[1])) // 2 - hbb[1]),
        ht, font=hf, fill=title_color,
    )
    # Grid area
    grid_top = y + header_h + pad
    grid_bottom = y + h - pad - int(h * 0.06)  # leave room for tiny page-num
    grid_size = min(w - 2 * pad, grid_bottom - grid_top)
    grid_x = x + (w - grid_size) // 2
    cell = grid_size / 9
    line_color = (20, 20, 20)
    for i in range(10):
        lw = max(2, int(cell * 0.07)) if i % 3 == 0 else 1
        d.line([(grid_x, grid_top + round(i * cell)),
                (grid_x + grid_size, grid_top + round(i * cell))],
               fill=line_color, width=lw)
        d.line([(grid_x + round(i * cell), grid_top),
                (grid_x + round(i * cell), grid_top + grid_size)],
               fill=line_color, width=lw)
    nf = _heavy_font(max(10, int(cell * 0.55)))
    for r in range(9):
        for c in range(9):
            n = clues[r][c]
            if not n:
                continue
            cxn = grid_x + round(c * cell + cell / 2)
            cyn = grid_top + round(r * cell + cell / 2)
            nbb = d.textbbox((0, 0), str(n), font=nf)
            d.text(
                (cxn - (nbb[2] - nbb[0]) // 2 - nbb[0],
                 cyn - (nbb[3] - nbb[1]) // 2 - nbb[1]),
                str(n), fill=line_color, font=nf,
            )


def _pick_sample_puzzles(puzzles_path: Path, want: list[str]) -> list[tuple[str, list[list[int]]]]:
    """Return one (difficulty, grid) per requested difficulty if available."""
    out = []
    try:
        puzzles = json.loads(puzzles_path.read_text())
    except Exception:
        return out
    seen_ids = set()
    for diff in want:
        for p in puzzles:
            if (p.get("difficulty") == diff
                    and isinstance(p.get("puzzle"), list)
                    and len(p["puzzle"]) == 9
                    and p.get("id") not in seen_ids):
                out.append((diff, p["puzzle"]))
                seen_ids.add(p.get("id"))
                break
    # Pad with whatever's available
    while len(out) < len(want) and puzzles:
        added = False
        for p in puzzles:
            if (isinstance(p.get("puzzle"), list)
                    and len(p["puzzle"]) == 9
                    and p.get("id") not in seen_ids):
                out.append((p.get("difficulty", "easy"), p["puzzle"]))
                seen_ids.add(p.get("id"))
                added = True
                break
        if not added:
            break
    return out


# ──────────────────────────────────────────────────────────
# Module renderers
# ──────────────────────────────────────────────────────────

def render_module_1_header(theme: str, plan: dict, mod: dict, out_path: Path) -> None:
    """1464 x 600 hero banner: theme-color half + cream half, cover floating, headline + body."""
    W, H = 1464, 600
    scheme_name = (plan.get("front_color_scheme") or "green").lower()
    scheme = SUDOKU_FRONT_COLOR_SCHEMES.get(scheme_name, SUDOKU_FRONT_COLOR_SCHEMES["green"])
    bg = _hex_to_rgb(scheme["bg"])
    accent = _hex_to_rgb(scheme["puzzle_pill_bg"])
    accent_ink = _hex_to_rgb(scheme["puzzle_pill_ink"])
    watermark = _hex_to_rgb(scheme["watermark"])
    title_color = _hex_to_rgb(scheme["title_color"])

    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)

    # Watermark digits
    _draw_digit_watermark(d, 0, 0, W, H, watermark, seed=hash(theme) & 0xFFFF, density=45)

    # Right-side cream panel for text
    panel_w = int(W * 0.55)
    panel_x0 = W - panel_w
    cream = (252, 246, 230) if scheme_name == "green" else (255, 255, 255)
    d.rectangle([panel_x0, 0, W, H], fill=cream)

    # Cover image (floating on left, theme bg side)
    cover_path = config.get_cover_png_path(theme).replace("/cover.png", "/front_artwork.png")
    # Better: compose using just the front portion of cover.png (right half)
    cover_full_path = config.get_cover_png_path(theme)
    if os.path.exists(cover_full_path):
        cv = Image.open(cover_full_path)
        cv_w, cv_h = cv.size
        # Front portion is roughly the right ~46% of the wrap (after back + spine)
        front_left_frac = 0.54
        front_crop = cv.crop((int(cv_w * front_left_frac), 0, cv_w, cv_h))
        # Resize to fit comfortably on left side
        target_h = int(H * 0.78)
        ratio = target_h / front_crop.size[1]
        target_w = int(front_crop.size[0] * ratio)
        front_crop = front_crop.resize((target_w, target_h), Image.Resampling.LANCZOS)
        # Paste with shadow
        cx = (panel_x0 - target_w) // 2
        cy = (H - target_h) // 2
        # Soft shadow
        sh = Image.new("RGBA", (target_w + 30, target_h + 30), (0, 0, 0, 0))
        sd = ImageDraw.Draw(sh)
        sd.rectangle([15, 15, target_w + 15 + 8, target_h + 15 + 8], fill=(0, 0, 0, 90))
        img_rgba = img.convert("RGBA")
        img_rgba.alpha_composite(sh, (cx - 15, cy - 15))
        img = img_rgba.convert("RGB")
        img.paste(front_crop, (cx, cy))
        d = ImageDraw.Draw(img)

    # Headline + body in cream panel
    headline = mod.get("headline", "")
    body = mod.get("body_text", "")

    pad_x = panel_x0 + 50
    pad_w = W - pad_x - 50

    hl_font_size = 56
    hl_font = _heavy_font(hl_font_size)
    hl_lines = _wrap_text(headline, hl_font, pad_w, d)
    while sum(d.textbbox((0, 0), l, font=hl_font)[2] - d.textbbox((0, 0), l, font=hl_font)[0]
              for l in hl_lines) / max(1, len(hl_lines)) > pad_w * 1.05 and hl_font_size > 28:
        hl_font_size -= 4
        hl_font = _heavy_font(hl_font_size)
        hl_lines = _wrap_text(headline, hl_font, pad_w, d)

    body_font = _heavy_font(22)
    body_lines = _wrap_text(body, body_font, pad_w, d)

    total_h = sum((d.textbbox((0, 0), l, font=hl_font)[3] - d.textbbox((0, 0), l, font=hl_font)[1]) + 8 for l in hl_lines)
    total_h += 30
    total_h += sum((d.textbbox((0, 0), l, font=body_font)[3] - d.textbbox((0, 0), l, font=body_font)[1]) + 6 for l in body_lines)

    cur_y = (H - total_h) // 2
    text_color = _hex_to_rgb(scheme["bg"]) if cream != bg else title_color
    for line in hl_lines:
        bb = d.textbbox((0, 0), line, font=hl_font)
        d.text((pad_x - bb[0], cur_y - bb[1]), line, font=hl_font, fill=text_color)
        cur_y += (bb[3] - bb[1]) + 8
    cur_y += 20
    body_color = (60, 60, 60) if cream != bg else title_color
    for line in body_lines:
        bb = d.textbbox((0, 0), line, font=body_font)
        d.text((pad_x - bb[0], cur_y - bb[1]), line, font=body_font, fill=body_color)
        cur_y += (bb[3] - bb[1]) + 6

    # Accent ribbon top corner
    ribbon_h = 12
    d.rectangle([0, 0, W, ribbon_h], fill=accent)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", dpi=(300, 300))
    print(f"  ✓ {out_path.name} ({W}x{H})")


def render_module_2_highlights(theme: str, plan: dict, mod: dict, out_dir: Path) -> None:
    """Four 970x600 highlight panels — one per benefit. Saves as separate files."""
    W, H = 970, 600
    scheme_name = (plan.get("front_color_scheme") or "green").lower()
    scheme = SUDOKU_FRONT_COLOR_SCHEMES.get(scheme_name, SUDOKU_FRONT_COLOR_SCHEMES["green"])
    bg = _hex_to_rgb(scheme["bg"])
    accent = _hex_to_rgb(scheme["puzzle_pill_bg"])
    accent_ink = _hex_to_rgb(scheme["puzzle_pill_ink"])
    title_color = _hex_to_rgb(scheme["title_color"])

    # Default 4 highlights — pull from mod or use sensible defaults
    highlights = mod.get("highlights") or mod.get("panels")
    if not highlights:
        # Derive from headline + body fallback
        if scheme_name == "green":  # book #8
            highlights = [
                {"title": "30-Point Numerals", "body": "Giant digits readable without a magnifier."},
                {"title": "One Puzzle / Page", "body": "Generous margins, plenty of writing room."},
                {"title": "100 Verified Puzzles", "body": "Every grid has exactly one solution."},
                {"title": "Solutions Included", "body": "Full answer key at the back."},
            ]
        else:  # book #9
            highlights = [
                {"title": "Builds Logic", "body": "Number-sense and pattern reasoning."},
                {"title": "Screen-Free", "body": "Calm focus — no apps, no distractions."},
                {"title": "Confidence Ladder", "body": "Easy first, then harder. Kids finish."},
                {"title": "Sticker Rewards", "body": "Celebrate progress between sections."},
            ]

    out_dir.mkdir(parents=True, exist_ok=True)
    for i, hl in enumerate(highlights[:4], start=1):
        img = Image.new("RGB", (W, H), bg)
        d = ImageDraw.Draw(img)
        _draw_digit_watermark(d, 0, 0, W, H, _hex_to_rgb(scheme["watermark"]), seed=hash((theme, i)) & 0xFFFF, density=20)

        # Big number badge top
        badge_d = 130
        cx, cy = W // 2, 130
        d.ellipse([cx - badge_d // 2, cy - badge_d // 2, cx + badge_d // 2, cy + badge_d // 2], fill=accent)
        nf = _heavy_font(64)
        nt = str(i)
        nbb = d.textbbox((0, 0), nt, font=nf)
        d.text((cx - (nbb[2] - nbb[0]) // 2 - nbb[0], cy - (nbb[3] - nbb[1]) // 2 - nbb[1]),
               nt, font=nf, fill=accent_ink)

        # Title
        tf = _heavy_font(48)
        title_text = hl["title"].upper()
        tbb = d.textbbox((0, 0), title_text, font=tf)
        # Auto-shrink
        while (tbb[2] - tbb[0]) > W - 80 and tf.size > 24:
            tf = _heavy_font(tf.size - 4)
            tbb = d.textbbox((0, 0), title_text, font=tf)
        d.text((W // 2 - (tbb[2] - tbb[0]) // 2 - tbb[0], 280 - tbb[1]),
               title_text, font=tf, fill=title_color)

        # Body wrapped
        body = hl.get("body", "")
        bf = _heavy_font(24)
        body_lines = _wrap_text(body, bf, W - 100, d)
        cur_y = 380
        for line in body_lines:
            bb = d.textbbox((0, 0), line, font=bf)
            d.text((W // 2 - (bb[2] - bb[0]) // 2 - bb[0], cur_y - bb[1]),
                   line, font=bf, fill=title_color)
            cur_y += (bb[3] - bb[1]) + 8

        path = out_dir / f"module_2_highlight_{i}.png"
        img.save(path, "PNG", dpi=(300, 300))
        print(f"  ✓ {path.name} ({W}x{H})")


def render_module_4_inside(theme: str, plan: dict, mod: dict, out_path: Path) -> None:
    """970x600 — three sample sudoku page cards overlapping."""
    W, H = 970, 600
    scheme_name = (plan.get("front_color_scheme") or "green").lower()
    scheme = SUDOKU_FRONT_COLOR_SCHEMES.get(scheme_name, SUDOKU_FRONT_COLOR_SCHEMES["green"])
    bg = _hex_to_rgb(scheme["bg"])
    accent = _hex_to_rgb(scheme["puzzle_pill_bg"])
    accent_ink = _hex_to_rgb(scheme["puzzle_pill_ink"])
    title_color = _hex_to_rgb(scheme["title_color"])
    watermark = _hex_to_rgb(scheme["watermark"])

    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    _draw_digit_watermark(d, 0, 0, W, H, watermark, seed=hash((theme, "inside")) & 0xFFFF, density=22)

    # Headline strip top
    hf = _heavy_font(38)
    headline = mod.get("headline", "A Real Look Inside")
    hbb = d.textbbox((0, 0), headline, font=hf)
    while (hbb[2] - hbb[0]) > W - 60 and hf.size > 18:
        hf = _heavy_font(hf.size - 2)
        hbb = d.textbbox((0, 0), headline, font=hf)
    d.text((W // 2 - (hbb[2] - hbb[0]) // 2 - hbb[0], 30 - hbb[1]),
           headline.upper(), font=hf, fill=title_color)

    # Sample puzzle cards (mockup interior pages)
    puzzles_path = Path(config.get_book_dir(theme)) / "sudoku_puzzles.json"
    samples = _pick_sample_puzzles(puzzles_path, ["easy", "medium", "hard"])

    if samples:
        canvas_rgba = img.convert("RGBA")
        # Card layout: 3 cards in a fan with enough horizontal spread so headers don't collide
        card_w = 230
        card_h = 330
        center_y = H // 2 + 35
        # Use just the difficulty label on the header (drop "SUDOKU" prefix) so it always fits
        positions = [
            {"angle": -10, "x_off": -300, "y_off": 25},
            {"angle": 0,   "x_off": 0,    "y_off": -10},
            {"angle": 10,  "x_off": 300,  "y_off": 25},
        ]
        order = [0, 2, 1] if len(positions) >= 3 else list(range(len(positions)))
        for idx in order:
            if idx >= len(samples):
                continue
            diff_label, clues = samples[idx]
            pos = positions[idx]
            card_img = Image.new("RGBA", (card_w + 40, card_h + 40), (0, 0, 0, 0))
            # Use simple label (just difficulty) — full "SUDOKU MEDIUM" is too wide for narrow card
            _draw_sudoku_card(
                card_img, 20, 20, card_w, card_h, clues, diff_label,
                bg_color=bg, title_color=title_color, pad=10, shadow=True,
                header_prefix="",  # drop "SUDOKU" prefix
            )
            if pos["angle"] != 0:
                card_img = card_img.rotate(-pos["angle"], expand=True, resample=Image.BICUBIC)
            cx = W // 2 - card_img.size[0] // 2 + pos["x_off"]
            cy = center_y - card_img.size[1] // 2 + pos["y_off"]
            canvas_rgba.alpha_composite(card_img, (cx, cy))
        img = canvas_rgba.convert("RGB")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", dpi=(300, 300))
    print(f"  ✓ {out_path.name} ({W}x{H})")


def render_module_5_size_compare(theme: str, plan: dict, mod: dict, out_path: Path) -> None:
    """970x300 — '5' digit at 14pt vs 30pt visual comparison (book #8)."""
    W, H = 970, 300
    scheme_name = (plan.get("front_color_scheme") or "green").lower()
    scheme = SUDOKU_FRONT_COLOR_SCHEMES.get(scheme_name, SUDOKU_FRONT_COLOR_SCHEMES["green"])
    bg = _hex_to_rgb(scheme["bg"])
    accent = _hex_to_rgb(scheme["puzzle_pill_bg"])
    accent_ink = _hex_to_rgb(scheme["puzzle_pill_ink"])
    title_color = _hex_to_rgb(scheme["title_color"])

    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)

    # Headline top
    hf = _heavy_font(34)
    headline = mod.get("headline", "14-Point vs. 30-Point: The Visible Difference").upper()
    hbb = d.textbbox((0, 0), headline, font=hf)
    while (hbb[2] - hbb[0]) > W - 60 and hf.size > 16:
        hf = _heavy_font(hf.size - 2)
        hbb = d.textbbox((0, 0), headline, font=hf)
    d.text((W // 2 - (hbb[2] - hbb[0]) // 2 - hbb[0], 25 - hbb[1]),
           headline, font=hf, fill=title_color)

    # Two side-by-side comparison cells
    cell_y = 90
    cell_h = 170
    cell_w = 250

    # Left cell — 14pt (small)
    left_x = 130
    d.rectangle([left_x, cell_y, left_x + cell_w, cell_y + cell_h], fill=(255, 255, 255), outline=(40, 40, 40), width=3)
    sf = _heavy_font(80)  # representational of "14pt scaled"
    s_text = "5"
    sbb = d.textbbox((0, 0), s_text, font=sf)
    d.text((left_x + cell_w // 2 - (sbb[2] - sbb[0]) // 2 - sbb[0],
            cell_y + cell_h // 2 - (sbb[3] - sbb[1]) // 2 - sbb[1]),
           s_text, font=sf, fill=(40, 40, 40))
    # Label below
    lf = _heavy_font(20)
    lt = "STANDARD 14-POINT"
    lbb = d.textbbox((0, 0), lt, font=lf)
    d.text((left_x + cell_w // 2 - (lbb[2] - lbb[0]) // 2 - lbb[0],
            cell_y + cell_h + 10 - lbb[1]),
           lt, font=lf, fill=title_color)

    # Right cell — 30pt (big)
    right_x = W - 130 - cell_w
    d.rectangle([right_x, cell_y, right_x + cell_w, cell_y + cell_h], fill=(255, 255, 255), outline=(40, 40, 40), width=3)
    bf_30 = _heavy_font(180)  # representational of "30pt scaled"
    bbb = d.textbbox((0, 0), s_text, font=bf_30)
    d.text((right_x + cell_w // 2 - (bbb[2] - bbb[0]) // 2 - bbb[0],
            cell_y + cell_h // 2 - (bbb[3] - bbb[1]) // 2 - bbb[1]),
           s_text, font=bf_30, fill=(40, 40, 40))
    lt2 = "OUR 30-POINT"
    lbb2 = d.textbbox((0, 0), lt2, font=lf)
    d.text((right_x + cell_w // 2 - (lbb2[2] - lbb2[0]) // 2 - lbb2[0],
            cell_y + cell_h + 10 - lbb2[1]),
           lt2, font=lf, fill=accent)

    # Arrow between
    arrow_y = cell_y + cell_h // 2
    d.line([(left_x + cell_w + 30, arrow_y), (right_x - 30, arrow_y)],
           fill=accent, width=6)
    # Arrowhead
    d.polygon([(right_x - 30, arrow_y),
               (right_x - 50, arrow_y - 12),
               (right_x - 50, arrow_y + 12)],
              fill=accent)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", dpi=(300, 300))
    print(f"  ✓ {out_path.name} ({W}x{H})")


def render_module_5_ladder(theme: str, plan: dict, mod: dict, out_path: Path) -> None:
    """970x300 — confidence-first difficulty ladder (book #9)."""
    W, H = 970, 300
    scheme_name = (plan.get("front_color_scheme") or "green").lower()
    scheme = SUDOKU_FRONT_COLOR_SCHEMES.get(scheme_name, SUDOKU_FRONT_COLOR_SCHEMES["green"])
    bg = _hex_to_rgb(scheme["bg"])
    accent = _hex_to_rgb(scheme["puzzle_pill_bg"])
    accent_ink = _hex_to_rgb(scheme["puzzle_pill_ink"])
    title_color = _hex_to_rgb(scheme["title_color"])

    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)

    hf = _heavy_font(30)
    headline = mod.get("headline", "Confidence-First Difficulty Ladder").upper()
    hbb = d.textbbox((0, 0), headline, font=hf)
    while (hbb[2] - hbb[0]) > W - 60 and hf.size > 16:
        hf = _heavy_font(hf.size - 2)
        hbb = d.textbbox((0, 0), headline, font=hf)
    d.text((W // 2 - (hbb[2] - hbb[0]) // 2 - hbb[0], 25 - hbb[1]),
           headline, font=hf, fill=title_color)

    # 3 stair steps: EASY 70 → MEDIUM 50 → SOLVER ✓
    diff_dist = plan.get("difficulty_distribution", {}) or {}
    steps = [
        {"label": "EASY",   "count": diff_dist.get("easy", 70),   "h": 110},
        {"label": "MEDIUM", "count": diff_dist.get("medium", 50), "h": 150},
        {"label": "SOLVER", "count": None,                         "h": 190},
    ]
    step_w = 200
    gap = 30
    total_w = step_w * 3 + gap * 2
    start_x = (W - total_w) // 2
    base_y = H - 25  # bottom of steps

    # Render each step as a stack: rectangle from base_y - height up to base_y
    for i, step in enumerate(steps):
        sx = start_x + i * (step_w + gap)
        sy_top = base_y - step["h"]
        # Step rectangle
        d.rectangle([sx, sy_top, sx + step_w, base_y], fill=accent)

        # Vertical layout INSIDE step: LABEL at top, big NUMBER center, "PUZZLES" small bottom
        # Reserve zones with explicit y coordinates so they never overlap
        label_y_center = sy_top + 22       # LABEL band
        number_y_center = sy_top + 60      # big number band
        puzzles_y_center = sy_top + 100    # "PUZZLES" small band

        # LABEL (top)
        lf = _heavy_font(24)
        lt = step["label"]
        lbb = d.textbbox((0, 0), lt, font=lf)
        d.text((sx + step_w // 2 - (lbb[2] - lbb[0]) // 2 - lbb[0],
                label_y_center - (lbb[3] - lbb[1]) // 2 - lbb[1]),
               lt, font=lf, fill=accent_ink)

        if step["count"] is not None:
            # Big number
            cf = _heavy_font(40)
            ct = str(step["count"])
            cbb = d.textbbox((0, 0), ct, font=cf)
            d.text((sx + step_w // 2 - (cbb[2] - cbb[0]) // 2 - cbb[0],
                    number_y_center - (cbb[3] - cbb[1]) // 2 - cbb[1]),
                   ct, font=cf, fill=accent_ink)
            # PUZZLES sublabel
            sf2 = _heavy_font(14)
            st = "PUZZLES"
            sbb = d.textbbox((0, 0), st, font=sf2)
            d.text((sx + step_w // 2 - (sbb[2] - sbb[0]) // 2 - sbb[0],
                    puzzles_y_center - (sbb[3] - sbb[1]) // 2 - sbb[1]),
                   st, font=sf2, fill=accent_ink)
        else:
            # SOLVER step — just a checkmark, no number
            checkmark_size = 50
            cmx = sx + step_w // 2
            cmy = number_y_center + 10
            d.line([(cmx - checkmark_size // 2, cmy),
                    (cmx - 5, cmy + checkmark_size // 2)],
                   fill=accent_ink, width=8)
            d.line([(cmx - 5, cmy + checkmark_size // 2),
                    (cmx + checkmark_size // 2, cmy - checkmark_size // 4)],
                   fill=accent_ink, width=8)

    # Arrows between steps (positioned at base of step, BELOW all text)
    for i in range(2):
        ax1 = start_x + step_w + i * (step_w + gap) + 5
        ax2 = ax1 + gap - 10
        ay = base_y - 25  # near base of shorter step
        d.line([(ax1, ay), (ax2, ay)], fill=accent, width=5)
        d.polygon([(ax2, ay), (ax2 - 10, ay - 8), (ax2 - 10, ay + 8)], fill=accent)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", dpi=(300, 300))
    print(f"  ✓ {out_path.name} ({W}x{H})")


def render_module_6_scenarios(theme: str, plan: dict, mod: dict, out_path: Path,
                               icons: list[dict]) -> None:
    """970x300 — N icon + label scenarios (gift occasions or use cases)."""
    W, H = 970, 300
    scheme_name = (plan.get("front_color_scheme") or "green").lower()
    scheme = SUDOKU_FRONT_COLOR_SCHEMES.get(scheme_name, SUDOKU_FRONT_COLOR_SCHEMES["green"])
    bg = _hex_to_rgb(scheme["bg"])
    accent = _hex_to_rgb(scheme["puzzle_pill_bg"])
    accent_ink = _hex_to_rgb(scheme["puzzle_pill_ink"])
    title_color = _hex_to_rgb(scheme["title_color"])

    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)

    hf = _heavy_font(30)
    headline = mod.get("headline", "Perfect For").upper()
    hbb = d.textbbox((0, 0), headline, font=hf)
    while (hbb[2] - hbb[0]) > W - 60 and hf.size > 16:
        hf = _heavy_font(hf.size - 2)
        hbb = d.textbbox((0, 0), headline, font=hf)
    d.text((W // 2 - (hbb[2] - hbb[0]) // 2 - hbb[0], 22 - hbb[1]),
           headline, font=hf, fill=title_color)

    # Icons row
    n = len(icons)
    item_w = (W - 80) // n
    icon_y = 105
    icon_d = 80
    for i, item in enumerate(icons):
        ix = 40 + i * item_w + (item_w - icon_d) // 2
        cx_icon = ix + icon_d // 2
        cy_icon = icon_y + icon_d // 2
        # Circle bg
        d.ellipse([ix, icon_y, ix + icon_d, icon_y + icon_d], fill=accent)
        # Icon shape (programmatic — emoji glyphs render as tofu in Arial Black)
        icon_kind = item.get("icon", "gift")
        renderer = ICON_RENDERERS.get(icon_kind)
        if renderer:
            renderer(d, cx_icon, cy_icon, int(icon_d * 0.55), accent_ink)
        else:
            # Fallback: draw a numbered badge with the index
            f = _heavy_font(int(icon_d * 0.5))
            txt = str(i + 1)
            tbb = d.textbbox((0, 0), txt, font=f)
            d.text((cx_icon - (tbb[2] - tbb[0]) // 2 - tbb[0],
                    cy_icon - (tbb[3] - tbb[1]) // 2 - tbb[1]),
                   txt, font=f, fill=accent_ink)
        # Label below
        lf = _heavy_font(20)
        label = item["label"].upper()
        lbb = d.textbbox((0, 0), label, font=lf)
        # Auto-shrink
        while (lbb[2] - lbb[0]) > item_w - 20 and lf.size > 12:
            lf = _heavy_font(lf.size - 1)
            lbb = d.textbbox((0, 0), label, font=lf)
        d.text((40 + i * item_w + item_w // 2 - (lbb[2] - lbb[0]) // 2 - lbb[0],
                icon_y + icon_d + 18 - lbb[1]),
               label, font=lf, fill=title_color)

        # Sub-text
        st = item.get("sub", "")
        if st:
            sf = _heavy_font(14)
            sbb = d.textbbox((0, 0), st, font=sf)
            while (sbb[2] - sbb[0]) > item_w - 20 and sf.size > 10:
                sf = _heavy_font(sf.size - 1)
                sbb = d.textbbox((0, 0), st, font=sf)
            d.text((40 + i * item_w + item_w // 2 - (sbb[2] - sbb[0]) // 2 - sbb[0],
                    icon_y + icon_d + 50 - sbb[1]),
                   st, font=sf, fill=title_color)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", dpi=(300, 300))
    print(f"  ✓ {out_path.name} ({W}x{H})")


# ──────────────────────────────────────────────────────────
# Main entry — orchestrate per book
# ──────────────────────────────────────────────────────────

def render_aplus_assets(theme: str) -> None:
    print(f"\n=== A+ rendering: {theme} ===")
    plan_path = Path(config.get_plan_path(theme))
    if not plan_path.exists():
        raise SystemExit(f"Missing {plan_path}")
    plan = json.loads(plan_path.read_text())

    book_id = _get_book_id_from_theme(theme)
    modules = _get_listing_aplus(book_id)
    if not modules:
        raise SystemExit(f"listings.a_plus_modules is empty for book_id={book_id}")

    out_dir = Path(config.get_book_dir(theme)) / "aplus"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Module 1 — Header
    m1 = _get_module_by_type(modules, "HEADER_IMAGE_TEXT") or _get_module(modules, 1)
    if m1:
        render_module_1_header(theme, plan, m1, out_dir / "module_1_header.png")

    # Module 2 — 4 highlights
    m2 = _get_module_by_type(modules, "FOUR_IMAGE_HIGHLIGHT") or _get_module(modules, 2)
    if m2:
        render_module_2_highlights(theme, plan, m2, out_dir)

    # Module 4 — Inside
    m4 = _get_module_by_type(modules, "IMAGE_TEXT_OVERLAY") or _get_module(modules, 4)
    if m4:
        render_module_4_inside(theme, plan, m4, out_dir / "module_4_inside.png")

    # Module 5 — Theme-specific (size compare for #8, ladder for #9)
    m5 = _get_module(modules, 5)
    if m5:
        scheme_name = (plan.get("front_color_scheme") or "green").lower()
        if scheme_name == "green":  # book #8 — size comparison
            render_module_5_size_compare(theme, plan, m5, out_dir / "module_5_size_compare.png")
        else:  # book #9 — confidence ladder
            render_module_5_ladder(theme, plan, m5, out_dir / "module_5_ladder.png")

    # Module 6 — Scenarios (gift / use cases)
    m6 = _get_module(modules, 6)
    if m6:
        scheme_name = (plan.get("front_color_scheme") or "green").lower()
        if scheme_name == "green":  # book #8 — gift occasions
            icons = [
                {"icon": "gift",     "label": "MOM/DAD",    "sub": "Mother's & Father's Day"},
                {"icon": "calendar", "label": "HOLIDAYS",   "sub": "Christmas & birthdays"},
                {"icon": "heart",    "label": "GET WELL",   "sub": "Recovery & care packages"},
                {"icon": "flower",   "label": "RETIREMENT", "sub": "A daily ritual"},
            ]
            render_module_6_scenarios(theme, plan, m6, out_dir / "module_6_gift.png", icons)
        else:  # book #9 — use cases
            icons = [
                {"icon": "umbrella", "label": "RAINY DAYS",  "sub": "Indoor focus"},
                {"icon": "book",     "label": "HOMESCHOOL",  "sub": "STEM-aligned"},
                {"icon": "plane",    "label": "ROAD TRIPS",  "sub": "Plane & car"},
            ]
            render_module_6_scenarios(theme, plan, m6, out_dir / "module_6_use_cases.png", icons)

    print(f"=== Done: {out_dir} ===")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--theme", help="theme_key (folder under output/)")
    parser.add_argument("--all-sudoku", action="store_true",
                        help="Render for all books with book_type=sudoku in DB")
    args = parser.parse_args()

    if args.all_sudoku:
        out = subprocess.run(
            ["python3", str(HERE / "db.py"), "books", "list"],
            capture_output=True, text=True, check=True,
        )
        rows = json.loads(out.stdout)
        for r in rows:
            tk = r.get("theme_key")
            if not tk:
                continue
            plan_path = Path(config.get_plan_path(tk))
            if not plan_path.exists():
                continue
            try:
                p = json.loads(plan_path.read_text())
            except Exception:
                continue
            if p.get("book_type") == "sudoku":
                try:
                    render_aplus_assets(tk)
                except Exception as e:
                    print(f"  ERROR rendering {tk}: {e}")
    elif args.theme:
        render_aplus_assets(args.theme)
    else:
        parser.error("Specify --theme <theme_key> or --all-sudoku")


if __name__ == "__main__":
    main()
