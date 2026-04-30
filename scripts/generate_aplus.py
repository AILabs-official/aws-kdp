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


def _icon_brain(d: ImageDraw.ImageDraw, cx: int, cy: int, size: int, color: tuple) -> None:
    """Stylized brain — 4 overlapping ellipses (lobes) + central groove."""
    half = size // 2
    lobe_r = size // 3
    # 4 lobes
    d.ellipse([cx - half, cy - lobe_r, cx, cy + lobe_r // 2], fill=color)            # back-left
    d.ellipse([cx, cy - lobe_r, cx + half, cy + lobe_r // 2], fill=color)             # back-right
    d.ellipse([cx - lobe_r, cy - lobe_r - 8, cx + lobe_r // 2, cy + lobe_r // 4], fill=color)   # top-left
    d.ellipse([cx - lobe_r // 2, cy - lobe_r - 8, cx + lobe_r, cy + lobe_r // 4], fill=color)   # top-right
    # Central groove (white wave line)
    d.line([(cx, cy - lobe_r), (cx, cy + lobe_r // 3)], fill=(255, 255, 255), width=3)


def _icon_eye(d: ImageDraw.ImageDraw, cx: int, cy: int, size: int, color: tuple) -> None:
    """Stylized eye — almond outline + iris."""
    half = size // 2
    # Almond outline (two arcs forming eye shape)
    d.ellipse([cx - half, cy - half // 2, cx + half, cy + half // 2], outline=color, width=4, fill=None)
    # Iris (filled circle center)
    iris_r = size // 4
    d.ellipse([cx - iris_r, cy - iris_r, cx + iris_r, cy + iris_r], fill=color)
    # Pupil highlight (white dot)
    pup_r = max(2, iris_r // 4)
    d.ellipse([cx - pup_r - 2, cy - pup_r - 2, cx + pup_r - 2, cy + pup_r - 2], fill=(255, 255, 255))


def _icon_check(d: ImageDraw.ImageDraw, cx: int, cy: int, size: int, color: tuple) -> None:
    """Checkmark stroke (used for inline list items)."""
    s = size
    w = max(3, s // 6)
    d.line([(cx - s // 2, cy + s // 8), (cx - s // 8, cy + s // 2 - 2)], fill=color, width=w)
    d.line([(cx - s // 8, cy + s // 2 - 2), (cx + s // 2, cy - s // 2 + 4)], fill=color, width=w)


ICON_RENDERERS = {
    "gift": _icon_gift,
    "calendar": _icon_calendar,
    "heart": _icon_heart,
    "flower": _icon_flower,
    "umbrella": _icon_umbrella,
    "book": _icon_book,
    "plane": _icon_plane,
    "brain": _icon_brain,
    "eye": _icon_eye,
    "check": _icon_check,
}


# ──────────────────────────────────────────────────────────
# v2 helpers — grid background, verified stamp, difficulty card
# ──────────────────────────────────────────────────────────

def _draw_grid_bg(draw: ImageDraw.ImageDraw, x0: int, y0: int, x1: int, y1: int,
                  cell: int = 60, line_color: tuple = (255, 255, 255), opacity: int = 22) -> None:
    """Draw a 9x9-ish grid texture overlay onto an existing canvas region.

    `opacity` is the alpha (0-255) — caller should ensure draw is on RGBA layer
    if true alpha is needed. For simplicity we draw faint gray lines on RGB
    canvases by mixing line_color toward bg manually (caller passes pre-mixed).
    """
    # Vertical lines
    x = x0
    while x <= x1:
        draw.line([(x, y0), (x, y1)], fill=line_color + (opacity,) if len(line_color) == 3 and isinstance(line_color, tuple) and False else line_color, width=1)
        x += cell
    # Horizontal lines
    y = y0
    while y <= y1:
        draw.line([(x0, y), (x1, y)], fill=line_color, width=1)
        y += cell


def _grid_overlay(canvas: Image.Image, cell: int = 60, alpha: int = 28,
                  thick_every: int = 3, thick_alpha: int = 55) -> Image.Image:
    """Composite a sudoku-style grid overlay onto canvas. Returns new RGB image.

    Uses a transparent RGBA layer so alpha is honored even on RGB base.
    """
    W, H = canvas.size
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    # Thin lines
    x = 0
    i = 0
    while x <= W:
        a = thick_alpha if i % thick_every == 0 else alpha
        w = 2 if i % thick_every == 0 else 1
        od.line([(x, 0), (x, H)], fill=(255, 255, 255, a), width=w)
        x += cell
        i += 1
    y = 0
    i = 0
    while y <= H:
        a = thick_alpha if i % thick_every == 0 else alpha
        w = 2 if i % thick_every == 0 else 1
        od.line([(0, y), (W, y)], fill=(255, 255, 255, a), width=w)
        y += cell
        i += 1
    base = canvas.convert("RGBA")
    base.alpha_composite(overlay)
    return base.convert("RGB")


def _draw_verified_stamp(canvas: Image.Image, cx: int, cy: int, radius: int = 65,
                          rotation: int = 10,
                          ring_color: tuple = (245, 200, 66),
                          fill_color: tuple = (200, 32, 46),
                          text_color: tuple = (255, 255, 255)) -> Image.Image:
    """Render a circular 'VERIFIED BY HAND' stamp and paste it onto canvas."""
    d = radius * 2 + 12
    stamp = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    sd = ImageDraw.Draw(stamp)
    # Outer ring
    sd.ellipse([0, 0, d - 1, d - 1], fill=ring_color)
    # Inner red fill
    inner = 8
    sd.ellipse([inner, inner, d - 1 - inner, d - 1 - inner], fill=fill_color)
    # White text band — "VERIFIED" top arc, "BY HAND" bottom (we draw straight stacked for legibility)
    f1 = _heavy_font(max(14, radius // 3))
    f2 = _heavy_font(max(11, radius // 4))
    t1 = "VERIFIED"
    t2 = "BY HAND"
    b1 = sd.textbbox((0, 0), t1, font=f1)
    b2 = sd.textbbox((0, 0), t2, font=f2)
    sd.text((d // 2 - (b1[2] - b1[0]) // 2 - b1[0],
             d // 2 - (b1[3] - b1[1]) - 4 - b1[1]),
            t1, font=f1, fill=text_color)
    sd.text((d // 2 - (b2[2] - b2[0]) // 2 - b2[0],
             d // 2 + 4 - b2[1]),
            t2, font=f2, fill=text_color)
    # Star top + star bottom
    star_r = max(4, radius // 8)
    import math as _m
    for star_cx, star_cy in [(d // 2, 14), (d // 2, d - 14)]:
        pts = []
        for j in range(10):
            a = -_m.pi / 2 + j * _m.pi / 5
            rr = star_r if j % 2 == 0 else star_r * 0.45
            pts.append((star_cx + rr * _m.cos(a), star_cy + rr * _m.sin(a)))
        sd.polygon(pts, fill=text_color)
    if rotation:
        stamp = stamp.rotate(rotation, expand=True, resample=Image.BICUBIC)
    base = canvas.convert("RGBA")
    base.alpha_composite(stamp, (cx - stamp.size[0] // 2, cy - stamp.size[1] // 2))
    return base.convert("RGB")


def _draw_difficulty_card(canvas: Image.Image, x: int, y: int, w: int, h: int,
                           card_color: tuple, ink_color: tuple,
                           level_label: str, count_text: str, footer_text: str,
                           clues: list[list[int]] | None,
                           shadow: bool = True) -> None:
    """Big colored difficulty card with header band + mini sudoku grid + footer."""
    d = ImageDraw.Draw(canvas)
    if shadow:
        sh = Image.new("RGBA", (w + 30, h + 30), (0, 0, 0, 0))
        sd = ImageDraw.Draw(sh)
        sd.rectangle([10, 10, w + 20, h + 20], fill=(0, 0, 0, 90))
        canvas_rgba = canvas.convert("RGBA")
        canvas_rgba.alpha_composite(sh, (x - 10, y - 5))
        # Re-render base
        canvas.paste(canvas_rgba.convert("RGB"))
        d = ImageDraw.Draw(canvas)
    # Card body
    d.rectangle([x, y, x + w, y + h], fill=card_color)
    # Header band — level label
    band_h = int(h * 0.18)
    f = _heavy_font(int(band_h * 0.65))
    bb = d.textbbox((0, 0), level_label, font=f)
    d.text((x + w // 2 - (bb[2] - bb[0]) // 2 - bb[0],
            y + band_h // 2 - (bb[3] - bb[1]) // 2 - bb[1]),
           level_label, font=f, fill=ink_color)
    # Mini grid area
    grid_top = y + band_h + 10
    grid_bottom = y + h - int(h * 0.22)  # leave room for footer
    grid_size = min(w - 30, grid_bottom - grid_top)
    grid_x = x + (w - grid_size) // 2
    cell = grid_size / 9
    # White card under grid for readability
    d.rectangle([grid_x - 6, grid_top - 6, grid_x + grid_size + 6, grid_top + grid_size + 6],
                fill=(255, 255, 255))
    # Grid lines
    for i in range(10):
        lw = 2 if i % 3 == 0 else 1
        d.line([(grid_x, grid_top + round(i * cell)),
                (grid_x + grid_size, grid_top + round(i * cell))],
               fill=(20, 20, 20), width=lw)
        d.line([(grid_x + round(i * cell), grid_top),
                (grid_x + round(i * cell), grid_top + grid_size)],
               fill=(20, 20, 20), width=lw)
    if clues:
        nf = _heavy_font(max(8, int(cell * 0.55)))
        for r in range(9):
            for c in range(9):
                n = clues[r][c]
                if not n:
                    continue
                cxn = grid_x + round(c * cell + cell / 2)
                cyn = grid_top + round(r * cell + cell / 2)
                nbb = d.textbbox((0, 0), str(n), font=nf)
                d.text((cxn - (nbb[2] - nbb[0]) // 2 - nbb[0],
                        cyn - (nbb[3] - nbb[1]) // 2 - nbb[1]),
                       str(n), fill=(20, 20, 20), font=nf)
    # Count badge top-right
    if count_text:
        bf = _heavy_font(16)
        bw = d.textbbox((0, 0), count_text, font=bf)
        bw_w = bw[2] - bw[0] + 16
        bw_h = bw[3] - bw[1] + 10
        bx = x + w - bw_w - 10
        by = y + 10
        d.rectangle([bx, by, bx + bw_w, by + bw_h], fill=(255, 255, 255))
        d.text((bx + 8 - bw[0], by + 5 - bw[1]), count_text, font=bf, fill=card_color)
    # Footer text band
    foot_h = int(h * 0.18)
    foot_y = y + h - foot_h
    ff = _heavy_font(int(foot_h * 0.55))
    fbb = d.textbbox((0, 0), footer_text, font=ff)
    while (fbb[2] - fbb[0]) > w - 20 and ff.size > 12:
        ff = _heavy_font(ff.size - 2)
        fbb = d.textbbox((0, 0), footer_text, font=ff)
    d.text((x + w // 2 - (fbb[2] - fbb[0]) // 2 - fbb[0],
            foot_y + foot_h // 2 - (fbb[3] - fbb[1]) // 2 - fbb[1]),
           footer_text, font=ff, fill=ink_color)


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
    """v2 1464x600 hero — dark grid bg + 3D mockup + yellow heading + verified stamp + bottom strip."""
    W, H = 1464, 600
    scheme_name = (plan.get("front_color_scheme") or "green").lower()
    scheme = SUDOKU_FRONT_COLOR_SCHEMES.get(scheme_name, SUDOKU_FRONT_COLOR_SCHEMES["green"])
    bg = _hex_to_rgb(scheme["bg"])
    accent = _hex_to_rgb(scheme["puzzle_pill_bg"])  # red
    accent_ink = _hex_to_rgb(scheme["puzzle_pill_ink"])  # white
    label_yellow = _hex_to_rgb(scheme["label_color"])  # F5C842 — bestseller yellow

    img = Image.new("RGB", (W, H), bg)
    # Apply sudoku-grid texture overlay first
    img = _grid_overlay(img, cell=58, alpha=18, thick_every=3, thick_alpha=42)
    d = ImageDraw.Draw(img)

    # Right-side cream panel for text (slightly translucent feel — solid cream is fine on print)
    panel_w = int(W * 0.50)
    panel_x0 = W - panel_w
    cream = (252, 246, 230)
    d.rectangle([panel_x0, 0, W, H], fill=cream)
    # Re-overlay grid lines on cream panel only at very faint opacity for cohesion
    panel_only = Image.new("RGB", (panel_w, H), cream)
    panel_only = _grid_overlay(panel_only, cell=58, alpha=10, thick_every=3, thick_alpha=20)
    img.paste(panel_only, (panel_x0, 0))
    d = ImageDraw.Draw(img)

    # 3D book mockup on the left dark side (cropped from cover.png)
    cover_full_path = config.get_cover_png_path(theme)
    if os.path.exists(cover_full_path):
        cv = Image.open(cover_full_path)
        cv_w, cv_h = cv.size
        front_left_frac = 0.54
        front_crop = cv.crop((int(cv_w * front_left_frac), 0, cv_w, cv_h))
        target_h = int(H * 0.82)
        ratio = target_h / front_crop.size[1]
        target_w = int(front_crop.size[0] * ratio)
        front_crop = front_crop.resize((target_w, target_h), Image.Resampling.LANCZOS)
        # Slight tilt for "3D" feel
        front_rot = front_crop.rotate(-6, expand=True, resample=Image.BICUBIC, fillcolor=None)
        cx = (panel_x0 - front_rot.size[0]) // 2 + 20
        cy = (H - front_rot.size[1]) // 2
        # Hard drop shadow
        sh = Image.new("RGBA", (front_rot.size[0] + 40, front_rot.size[1] + 40), (0, 0, 0, 0))
        sd = ImageDraw.Draw(sh)
        sd.rectangle([20, 28, front_rot.size[0] + 18, front_rot.size[1] + 26], fill=(0, 0, 0, 140))
        img_rgba = img.convert("RGBA")
        img_rgba.alpha_composite(sh, (cx - 8, cy - 12))
        # Soft yellow outer glow
        glow = Image.new("RGBA", (front_rot.size[0] + 60, front_rot.size[1] + 60), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.rectangle([28, 28, front_rot.size[0] + 32, front_rot.size[1] + 32],
                     outline=(*label_yellow, 80), width=8)
        img_rgba.alpha_composite(glow, (cx - 28, cy - 28))
        img = img_rgba.convert("RGB")
        # Paste actual mockup (without alpha to avoid transparent rotation corners)
        if front_rot.mode == "RGBA":
            img.paste(front_rot, (cx, cy), front_rot)
        else:
            img.paste(front_rot, (cx, cy))
        d = ImageDraw.Draw(img)

    # Headline + sub in cream panel
    headline = mod.get("headline", "Extra Large Print Sudoku")
    sub = mod.get("body_text", "")

    pad_x = panel_x0 + 40
    pad_w = W - pad_x - 40

    # Headline — bold dark green (since panel is cream); upper-case for impact
    # Reserve right edge for the verified stamp (top-right ~150px wide)
    headline_pad_w = pad_w - 110  # narrower so first lines clear the stamp
    headline_up = headline.upper()
    hl_font_size = 46
    hl_font = _heavy_font(hl_font_size)
    hl_lines = _wrap_text(headline_up, hl_font, headline_pad_w, d)
    # Shrink until both line count <=4 AND every line fits within headline_pad_w
    def _max_line_w(lines, font):
        return max((d.textbbox((0, 0), l, font=font)[2] - d.textbbox((0, 0), l, font=font)[0]) for l in lines) if lines else 0
    while (len(hl_lines) > 4 or _max_line_w(hl_lines, hl_font) > headline_pad_w) and hl_font_size > 22:
        hl_font_size -= 2
        hl_font = _heavy_font(hl_font_size)
        hl_lines = _wrap_text(headline_up, hl_font, headline_pad_w, d)
    # Sub in body
    sub_font = _heavy_font(22)
    sub_lines = _wrap_text(sub, sub_font, pad_w, d)

    # Position vertically — leave room for bottom strip
    bottom_strip_h = 56
    avail_h = H - bottom_strip_h - 40
    total_h = sum((d.textbbox((0, 0), l, font=hl_font)[3] - d.textbbox((0, 0), l, font=hl_font)[1]) + 6 for l in hl_lines)
    total_h += 22
    total_h += sum((d.textbbox((0, 0), l, font=sub_font)[3] - d.textbbox((0, 0), l, font=sub_font)[1]) + 4 for l in sub_lines)
    cur_y = max(20, (avail_h - total_h) // 2)

    text_color = bg  # dark forest green on cream
    for line in hl_lines:
        bb = d.textbbox((0, 0), line, font=hl_font)
        d.text((pad_x - bb[0], cur_y - bb[1]), line, font=hl_font, fill=text_color)
        cur_y += (bb[3] - bb[1]) + 6
    cur_y += 16
    sub_color = (60, 60, 60)
    for line in sub_lines:
        bb = d.textbbox((0, 0), line, font=sub_font)
        d.text((pad_x - bb[0], cur_y - bb[1]), line, font=sub_font, fill=sub_color)
        cur_y += (bb[3] - bb[1]) + 4

    # Bottom strip — red ribbon spanning full width with key claims
    strip_h = bottom_strip_h
    d.rectangle([0, H - strip_h, W, H], fill=accent)
    strip_text = "BRAND NEW 2026 EDITION  •  EASY ON EYES  •  PREMIUM EDITION"
    sf = _heavy_font(22)
    sbb = d.textbbox((0, 0), strip_text, font=sf)
    while (sbb[2] - sbb[0]) > W - 60 and sf.size > 14:
        sf = _heavy_font(sf.size - 2)
        sbb = d.textbbox((0, 0), strip_text, font=sf)
    d.text((W // 2 - (sbb[2] - sbb[0]) // 2 - sbb[0],
            H - strip_h // 2 - (sbb[3] - sbb[1]) // 2 - sbb[1]),
           strip_text, font=sf, fill=accent_ink)

    # Verified-by-hand stamp top-right
    img = _draw_verified_stamp(img, cx=W - 105, cy=85, radius=70, rotation=10,
                                ring_color=label_yellow, fill_color=accent, text_color=(255, 255, 255))

    # Top accent ribbon — yellow→gold gradient (simulated as solid yellow band 8px tall)
    d2 = ImageDraw.Draw(img)
    d2.rectangle([0, 0, W, 8], fill=label_yellow)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", dpi=(300, 300))
    print(f"  ✓ {out_path.name} ({W}x{H})")


def render_module_2_difficulty_cards(theme: str, plan: dict, mod: dict, out_path: Path) -> None:
    """v2 970x600 — 3 colored difficulty cards (Easy green / Medium gold / Hard red)
    with mini sample grids + count badge + footer caption."""
    W, H = 970, 600
    scheme_name = (plan.get("front_color_scheme") or "green").lower()
    scheme = SUDOKU_FRONT_COLOR_SCHEMES.get(scheme_name, SUDOKU_FRONT_COLOR_SCHEMES["green"])
    bg = _hex_to_rgb(scheme["bg"])
    label_yellow = _hex_to_rgb(scheme["label_color"])

    img = Image.new("RGB", (W, H), bg)
    img = _grid_overlay(img, cell=50, alpha=18, thick_every=3, thick_alpha=42)
    d = ImageDraw.Draw(img)

    # Headline
    headline = (mod.get("headline", "From Easy to Hard — Find Your Level")).upper()
    sub = mod.get("body_text", "Train your brain across all 3 difficulty levels")

    hf = _heavy_font(40)
    hbb = d.textbbox((0, 0), headline, font=hf)
    while (hbb[2] - hbb[0]) > W - 60 and hf.size > 22:
        hf = _heavy_font(hf.size - 2)
        hbb = d.textbbox((0, 0), headline, font=hf)
    d.text((W // 2 - (hbb[2] - hbb[0]) // 2 - hbb[0], 25 - hbb[1]),
           headline, font=hf, fill=label_yellow)

    # Sub
    sf = _heavy_font(20)
    sbb = d.textbbox((0, 0), sub, font=sf)
    while (sbb[2] - sbb[0]) > W - 80 and sf.size > 14:
        sf = _heavy_font(sf.size - 1)
        sbb = d.textbbox((0, 0), sub, font=sf)
    d.text((W // 2 - (sbb[2] - sbb[0]) // 2 - sbb[0], 78 - sbb[1]),
           sub, font=sf, fill=(255, 255, 255))

    # Difficulty distribution from plan
    dist = plan.get("difficulty_distribution", {}) or {}
    n_easy = dist.get("easy", 35)
    n_med = dist.get("medium", 40)
    n_hard = dist.get("hard", 25)

    # Sample puzzles (one per difficulty)
    puzzles_path = Path(config.get_book_dir(theme)) / "sudoku_puzzles.json"
    samples = _pick_sample_puzzles(puzzles_path, ["easy", "medium", "hard"])
    sample_map = {diff: clues for diff, clues in samples}

    # Card layout
    card_w = 280
    card_h = 400
    gap = 22
    total_w = card_w * 3 + gap * 2
    start_x = (W - total_w) // 2
    card_y = 130

    cards = [
        {"color": (46, 139, 87), "ink": (255, 255, 255), "label": "EASY",
         "count": f"{n_easy} PUZZLES", "footer": "START HERE",
         "clues": sample_map.get("easy")},
        {"color": (245, 200, 66), "ink": (40, 40, 40), "label": "MEDIUM",
         "count": f"{n_med} PUZZLES", "footer": "CHALLENGE YOURSELF",
         "clues": sample_map.get("medium")},
        {"color": (200, 32, 46), "ink": (255, 255, 255), "label": "HARD",
         "count": f"{n_hard} PUZZLES", "footer": "BECOME A PRO",
         "clues": sample_map.get("hard")},
    ]
    for i, c in enumerate(cards):
        x = start_x + i * (card_w + gap)
        _draw_difficulty_card(img, x, card_y, card_w, card_h,
                               card_color=c["color"], ink_color=c["ink"],
                               level_label=c["label"], count_text=c["count"],
                               footer_text=c["footer"], clues=c["clues"], shadow=True)

    # Top accent ribbon
    ImageDraw.Draw(img).rectangle([0, 0, W, 6], fill=label_yellow)

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
    """v2 970x600 — interior page mockup (left 65%) + checkmark feature list (right 35%)."""
    W, H = 970, 600
    scheme_name = (plan.get("front_color_scheme") or "green").lower()
    scheme = SUDOKU_FRONT_COLOR_SCHEMES.get(scheme_name, SUDOKU_FRONT_COLOR_SCHEMES["green"])
    bg = _hex_to_rgb(scheme["bg"])
    accent = _hex_to_rgb(scheme["puzzle_pill_bg"])
    title_color = _hex_to_rgb(scheme["title_color"])  # white
    label_yellow = _hex_to_rgb(scheme["label_color"])

    img = Image.new("RGB", (W, H), bg)
    img = _grid_overlay(img, cell=50, alpha=18, thick_every=3, thick_alpha=42)
    d = ImageDraw.Draw(img)

    # Headline (yellow)
    hf = _heavy_font(36)
    headline = (mod.get("headline", "Designed for Comfort")).upper()
    hbb = d.textbbox((0, 0), headline, font=hf)
    while (hbb[2] - hbb[0]) > W - 60 and hf.size > 18:
        hf = _heavy_font(hf.size - 2)
        hbb = d.textbbox((0, 0), headline, font=hf)
    d.text((W // 2 - (hbb[2] - hbb[0]) // 2 - hbb[0], 28 - hbb[1]),
           headline, font=hf, fill=label_yellow)

    # Sub (white)
    sub = "Actual page layout — every puzzle gets a full page"
    sf = _heavy_font(18)
    sbb = d.textbbox((0, 0), sub, font=sf)
    d.text((W // 2 - (sbb[2] - sbb[0]) // 2 - sbb[0], 78 - sbb[1]),
           sub, font=sf, fill=title_color)

    # ---- Left 65% — interior page mockup (single big page card) ----
    puzzles_path = Path(config.get_book_dir(theme)) / "sudoku_puzzles.json"
    samples = _pick_sample_puzzles(puzzles_path, ["easy", "medium"])
    left_w = int(W * 0.62)
    canvas_rgba = img.convert("RGBA")

    if samples:
        # Two pages overlapping at small angle
        page_w = 220
        page_h = 350
        center_x = left_w // 2
        center_y = H // 2 + 40
        positions = [
            {"angle": -6, "x_off": -85, "y_off": 10, "header_prefix": "PAGE  12", "diff": samples[0][0], "clues": samples[0][1]},
            {"angle": 5,  "x_off": 85,  "y_off": -10, "header_prefix": "PAGE  68", "diff": samples[1][0] if len(samples) > 1 else "medium",
             "clues": samples[1][1] if len(samples) > 1 else samples[0][1]},
        ]
        for pos in positions:
            card_img = Image.new("RGBA", (page_w + 40, page_h + 40), (0, 0, 0, 0))
            _draw_sudoku_card(
                card_img, 20, 20, page_w, page_h, pos["clues"], pos["diff"],
                bg_color=accent, title_color=(255, 255, 255), pad=10, shadow=True,
                header_prefix=pos["header_prefix"],
            )
            if pos["angle"] != 0:
                card_img = card_img.rotate(-pos["angle"], expand=True, resample=Image.BICUBIC)
            cx = center_x - card_img.size[0] // 2 + pos["x_off"]
            cy = center_y - card_img.size[1] // 2 + pos["y_off"]
            canvas_rgba.alpha_composite(card_img, (cx, cy))

    img = canvas_rgba.convert("RGB")
    d = ImageDraw.Draw(img)

    # ---- Right 35% — yellow checkmark feature list ----
    list_x = left_w + 30
    list_w = W - list_x - 25
    list_y = 140
    items = [
        "30-Point Numerals",
        "1 Puzzle Per Page",
        "Generous Margins",
        "Solutions in Back",
        "Hand-Verified",
    ]
    item_h = 62
    for i, t in enumerate(items):
        y = list_y + i * item_h
        # Yellow circle with white check
        circle_d = 38
        cx_c = list_x + circle_d // 2 + 4
        cy_c = y + circle_d // 2 + 4
        d.ellipse([list_x + 4, y + 4, list_x + 4 + circle_d, y + 4 + circle_d],
                  fill=label_yellow)
        _icon_check(d, cx_c, cy_c, circle_d - 12, (255, 255, 255))
        # Label text
        tf = _heavy_font(20)
        tbb = d.textbbox((0, 0), t, font=tf)
        while (tbb[2] - tbb[0]) > list_w - 60 and tf.size > 13:
            tf = _heavy_font(tf.size - 1)
            tbb = d.textbbox((0, 0), t, font=tf)
        d.text((list_x + circle_d + 18 - tbb[0],
                cy_c - (tbb[3] - tbb[1]) // 2 - tbb[1]),
               t, font=tf, fill=(255, 255, 255))

    # Top accent ribbon
    ImageDraw.Draw(img).rectangle([0, 0, W, 6], fill=label_yellow)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", dpi=(300, 300))
    print(f"  ✓ {out_path.name} ({W}x{H})")


def render_module_5_size_compare(theme: str, plan: dict, mod: dict, out_path: Path) -> None:
    """v2 970x300 — small '5' (cream cell) vs huge '5' (dark cell) with magnifier + arrow."""
    W, H = 970, 300
    scheme_name = (plan.get("front_color_scheme") or "green").lower()
    scheme = SUDOKU_FRONT_COLOR_SCHEMES.get(scheme_name, SUDOKU_FRONT_COLOR_SCHEMES["green"])
    bg = _hex_to_rgb(scheme["bg"])
    accent = _hex_to_rgb(scheme["puzzle_pill_bg"])
    label_yellow = _hex_to_rgb(scheme["label_color"])
    title_color = _hex_to_rgb(scheme["title_color"])

    img = Image.new("RGB", (W, H), bg)
    img = _grid_overlay(img, cell=46, alpha=18, thick_every=3, thick_alpha=42)
    d = ImageDraw.Draw(img)

    hf = _heavy_font(30)
    headline = mod.get("headline", "14-Point vs 30-Point — The Visible Difference").upper()
    hbb = d.textbbox((0, 0), headline, font=hf)
    while (hbb[2] - hbb[0]) > W - 60 and hf.size > 16:
        hf = _heavy_font(hf.size - 2)
        hbb = d.textbbox((0, 0), headline, font=hf)
    d.text((W // 2 - (hbb[2] - hbb[0]) // 2 - hbb[0], 22 - hbb[1]),
           headline, font=hf, fill=label_yellow)

    cell_y = 80
    cell_h = 165
    cell_w = 230
    s_text = "5"

    # Left cell — small numeral on cream
    left_x = 90
    d.rectangle([left_x, cell_y, left_x + cell_w, cell_y + cell_h],
                fill=(252, 246, 230), outline=(40, 40, 40), width=3)
    sf = _heavy_font(60)
    sbb = d.textbbox((0, 0), s_text, font=sf)
    d.text((left_x + cell_w // 2 - (sbb[2] - sbb[0]) // 2 - sbb[0],
            cell_y + cell_h // 2 - (sbb[3] - sbb[1]) // 2 - sbb[1]),
           s_text, font=sf, fill=(40, 40, 40))
    lf = _heavy_font(16)
    lt = "STANDARD 14-PT"
    lbb = d.textbbox((0, 0), lt, font=lf)
    d.text((left_x + cell_w // 2 - (lbb[2] - lbb[0]) // 2 - lbb[0],
            cell_y + cell_h + 8 - lbb[1]),
           lt, font=lf, fill=title_color)

    # Right cell — huge numeral on dark, yellow border
    right_x = W - 90 - cell_w
    d.rectangle([right_x, cell_y, right_x + cell_w, cell_y + cell_h],
                fill=(20, 60, 40), outline=label_yellow, width=4)
    bf_30 = _heavy_font(170)
    bbb = d.textbbox((0, 0), s_text, font=bf_30)
    d.text((right_x + cell_w // 2 - (bbb[2] - bbb[0]) // 2 - bbb[0],
            cell_y + cell_h // 2 - (bbb[3] - bbb[1]) // 2 - bbb[1]),
           s_text, font=bf_30, fill=(255, 255, 255))
    lt2 = "OUR 30-PT — 2x LARGER"
    lbb2 = d.textbbox((0, 0), lt2, font=lf)
    d.text((right_x + cell_w // 2 - (lbb2[2] - lbb2[0]) // 2 - lbb2[0],
            cell_y + cell_h + 8 - lbb2[1]),
           lt2, font=lf, fill=label_yellow)

    # Magnifier icon between cells (yellow circle + handle on red rect arrow)
    mid_x = (left_x + cell_w + right_x) // 2
    mag_y = cell_y + cell_h // 2
    mag_r = 28
    d.ellipse([mid_x - mag_r, mag_y - mag_r, mid_x + mag_r, mag_y + mag_r],
              outline=label_yellow, width=5, fill=(20, 60, 40))
    # Plus inside magnifier
    d.line([(mid_x - 10, mag_y), (mid_x + 10, mag_y)], fill=label_yellow, width=4)
    d.line([(mid_x, mag_y - 10), (mid_x, mag_y + 10)], fill=label_yellow, width=4)
    # Handle
    d.line([(mid_x + mag_r - 4, mag_y + mag_r - 4),
            (mid_x + mag_r + 14, mag_y + mag_r + 14)],
           fill=label_yellow, width=6)
    # Curved arrow from magnifier to right cell (small arc segment)
    d.line([(mid_x + mag_r + 16, mag_y + mag_r + 8), (right_x - 12, mag_y + 30)],
           fill=accent, width=4)

    # Top accent ribbon
    d.rectangle([0, 0, W, 5], fill=label_yellow)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", dpi=(300, 300))
    print(f"  ✓ {out_path.name} ({W}x{H})")


def render_module_6_verified(theme: str, plan: dict, mod: dict, out_path: Path) -> None:
    """v2 970x300 — Why Hand-Verified Matters: bad case (multiple solutions) vs good case (1 solution)."""
    W, H = 970, 300
    scheme_name = (plan.get("front_color_scheme") or "green").lower()
    scheme = SUDOKU_FRONT_COLOR_SCHEMES.get(scheme_name, SUDOKU_FRONT_COLOR_SCHEMES["green"])
    bg = _hex_to_rgb(scheme["bg"])
    accent = _hex_to_rgb(scheme["puzzle_pill_bg"])  # red
    label_yellow = _hex_to_rgb(scheme["label_color"])
    title_color = _hex_to_rgb(scheme["title_color"])
    green_good = (46, 139, 87)

    img = Image.new("RGB", (W, H), bg)
    img = _grid_overlay(img, cell=46, alpha=18, thick_every=3, thick_alpha=42)
    d = ImageDraw.Draw(img)

    # Headline
    hf = _heavy_font(30)
    headline = (mod.get("headline", "Why Hand-Verified Matters")).upper()
    hbb = d.textbbox((0, 0), headline, font=hf)
    while (hbb[2] - hbb[0]) > W - 60 and hf.size > 16:
        hf = _heavy_font(hf.size - 2)
        hbb = d.textbbox((0, 0), headline, font=hf)
    d.text((W // 2 - (hbb[2] - hbb[0]) // 2 - hbb[0], 22 - hbb[1]),
           headline, font=hf, fill=label_yellow)

    # Two cells side-by-side (BAD vs GOOD)
    cell_y = 78
    cell_h = 175
    cell_w = 290

    # Mini grid renderer — local helper for tiny grids inside cells
    def _mini_grid(cx_g, cy_g, size, clues=None, overlay_color=None,
                    show_check=False, all_filled=False):
        """Render a small sudoku grid centered at (cx_g, cy_g) with optional overlays."""
        cell = size / 9
        x0 = cx_g - size // 2
        y0 = cy_g - size // 2
        # White card behind
        d.rectangle([x0 - 3, y0 - 3, x0 + size + 3, y0 + size + 3], fill=(255, 255, 255))
        # Lines
        for i in range(10):
            lw = 2 if i % 3 == 0 else 1
            d.line([(x0, y0 + round(i * cell)), (x0 + size, y0 + round(i * cell))], fill=(20, 20, 20), width=lw)
            d.line([(x0 + round(i * cell), y0), (x0 + round(i * cell), y0 + size)], fill=(20, 20, 20), width=lw)
        # Clues / fill
        nf = _heavy_font(max(6, int(cell * 0.55)))
        if all_filled:
            # Pseudo-fill — write small numerals for 81 cells deterministically
            seq = [
                [5,3,4,6,7,8,9,1,2],
                [6,7,2,1,9,5,3,4,8],
                [1,9,8,3,4,2,5,6,7],
                [8,5,9,7,6,1,4,2,3],
                [4,2,6,8,5,3,7,9,1],
                [7,1,3,9,2,4,8,5,6],
                [9,6,1,5,3,7,2,8,4],
                [2,8,7,4,1,9,6,3,5],
                [3,4,5,2,8,6,1,7,9],
            ]
            for r in range(9):
                for c in range(9):
                    n = seq[r][c]
                    cxn = x0 + round(c * cell + cell / 2)
                    cyn = y0 + round(r * cell + cell / 2)
                    nbb = d.textbbox((0, 0), str(n), font=nf)
                    d.text((cxn - (nbb[2] - nbb[0]) // 2 - nbb[0],
                            cyn - (nbb[3] - nbb[1]) // 2 - nbb[1]),
                           str(n), fill=(40, 40, 40), font=nf)
        elif clues:
            for r in range(9):
                for c in range(9):
                    n = clues[r][c]
                    if not n:
                        continue
                    cxn = x0 + round(c * cell + cell / 2)
                    cyn = y0 + round(r * cell + cell / 2)
                    nbb = d.textbbox((0, 0), str(n), font=nf)
                    d.text((cxn - (nbb[2] - nbb[0]) // 2 - nbb[0],
                            cyn - (nbb[3] - nbb[1]) // 2 - nbb[1]),
                           str(n), fill=(40, 40, 40), font=nf)
        # Overlay diagonal lines (red — multiple solutions)
        if overlay_color:
            for i in range(3):
                offset = i * 18 - 18
                d.line([(x0 + 4, y0 + 4 + offset),
                        (x0 + size - 4, y0 + size - 4 + offset)],
                       fill=overlay_color, width=3)
        # Big check mark across the grid
        if show_check:
            check_size = size // 2
            cxn = cx_g
            cyn = cy_g + 4
            w_chk = 8
            d.line([(cxn - check_size // 2, cyn),
                    (cxn - 4, cyn + check_size // 2)],
                   fill=green_good, width=w_chk)
            d.line([(cxn - 4, cyn + check_size // 2),
                    (cxn + check_size // 2, cyn - check_size // 4)],
                   fill=green_good, width=w_chk)

    # Sample puzzle
    puzzles_path = Path(config.get_book_dir(theme)) / "sudoku_puzzles.json"
    sample_pair = _pick_sample_puzzles(puzzles_path, ["medium"])
    sample_clues = sample_pair[0][1] if sample_pair else None

    # Left cell — BAD (cream bg, red overlay)
    left_x = 50
    d.rectangle([left_x, cell_y, left_x + cell_w, cell_y + cell_h],
                fill=(252, 246, 230), outline=(40, 40, 40), width=3)
    grid_sz = cell_h - 50
    _mini_grid(left_x + 60, cell_y + cell_h // 2 - 10, grid_sz,
               clues=sample_clues, overlay_color=accent)
    # Speech bubble
    bub_x = left_x + cell_w - 110
    bub_y = cell_y + 14
    d.rectangle([bub_x, bub_y, bub_x + 100, bub_y + 70], fill=(255, 255, 255), outline=accent, width=2)
    bf = _heavy_font(11)
    for i, line in enumerate(["Solution 1", "Solution 2", "Solution 3..."]):
        bbb = d.textbbox((0, 0), line, font=bf)
        d.text((bub_x + 50 - (bbb[2] - bbb[0]) // 2 - bbb[0], bub_y + 10 + i * 18 - bbb[1]),
               line, font=bf, fill=accent)
    # Bad label below cell
    lf = _heavy_font(13)
    lt = "ALGORITHM-ONLY: MULTIPLE SOLUTIONS"
    lbb = d.textbbox((0, 0), lt, font=lf)
    while (lbb[2] - lbb[0]) > cell_w - 10 and lf.size > 9:
        lf = _heavy_font(lf.size - 1)
        lbb = d.textbbox((0, 0), lt, font=lf)
    d.text((left_x + cell_w // 2 - (lbb[2] - lbb[0]) // 2 - lbb[0],
            cell_y + cell_h + 6 - lbb[1]),
           lt, font=lf, fill=accent)

    # Right cell — GOOD (white bg, green check, yellow stamp corner)
    right_x = W - 50 - cell_w
    d.rectangle([right_x, cell_y, right_x + cell_w, cell_y + cell_h],
                fill=(255, 255, 255), outline=green_good, width=3)
    _mini_grid(right_x + cell_w // 2, cell_y + cell_h // 2 - 8, grid_sz,
               all_filled=True, show_check=True)
    # Yellow VERIFIED stamp top-right of cell
    stamp_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    img = _draw_verified_stamp(img, cx=right_x + cell_w - 32, cy=cell_y + 32,
                                radius=30, rotation=8,
                                ring_color=label_yellow,
                                fill_color=accent,
                                text_color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    # Good label below cell
    lt2 = "OUR BOOK: ONE UNIQUE SOLUTION"
    lf2 = _heavy_font(13)
    lbb2 = d.textbbox((0, 0), lt2, font=lf2)
    while (lbb2[2] - lbb2[0]) > cell_w - 10 and lf2.size > 9:
        lf2 = _heavy_font(lf2.size - 1)
        lbb2 = d.textbbox((0, 0), lt2, font=lf2)
    d.text((right_x + cell_w // 2 - (lbb2[2] - lbb2[0]) // 2 - lbb2[0],
            cell_y + cell_h + 6 - lbb2[1]),
           lt2, font=lf2, fill=green_good)

    # Center arrow (red→green)
    arrow_y = cell_y + cell_h // 2
    arrow_x1 = left_x + cell_w + 8
    arrow_x2 = right_x - 8
    # Gradient simulated as 3 segments
    seg_w = (arrow_x2 - arrow_x1) // 3
    for i, color in enumerate([accent, label_yellow, green_good]):
        d.line([(arrow_x1 + i * seg_w, arrow_y),
                (arrow_x1 + (i + 1) * seg_w, arrow_y)],
               fill=color, width=6)
    # Arrowhead green
    d.polygon([(arrow_x2, arrow_y),
               (arrow_x2 - 14, arrow_y - 10),
               (arrow_x2 - 14, arrow_y + 10)],
              fill=green_good)

    # Top accent ribbon
    ImageDraw.Draw(img).rectangle([0, 0, W, 5], fill=label_yellow)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", dpi=(300, 300))
    print(f"  ✓ {out_path.name} ({W}x{H})")


def render_module_7_three_col_benefits(theme: str, plan: dict, mod: dict, out_path: Path) -> None:
    """v2 970x400 — 3 columns: Cognitive Boost / Easy on Eyes / Perfect Gift."""
    W, H = 970, 400
    scheme_name = (plan.get("front_color_scheme") or "green").lower()
    scheme = SUDOKU_FRONT_COLOR_SCHEMES.get(scheme_name, SUDOKU_FRONT_COLOR_SCHEMES["green"])
    bg = _hex_to_rgb(scheme["bg"])
    accent = _hex_to_rgb(scheme["puzzle_pill_bg"])
    label_yellow = _hex_to_rgb(scheme["label_color"])
    title_color = _hex_to_rgb(scheme["title_color"])

    img = Image.new("RGB", (W, H), bg)
    img = _grid_overlay(img, cell=46, alpha=18, thick_every=3, thick_alpha=42)
    d = ImageDraw.Draw(img)

    # Headline
    hf = _heavy_font(34)
    headline = (mod.get("headline", "Built for the Reader — Not the Pageant")).upper()
    hbb = d.textbbox((0, 0), headline, font=hf)
    while (hbb[2] - hbb[0]) > W - 60 and hf.size > 18:
        hf = _heavy_font(hf.size - 2)
        hbb = d.textbbox((0, 0), headline, font=hf)
    d.text((W // 2 - (hbb[2] - hbb[0]) // 2 - hbb[0], 28 - hbb[1]),
           headline, font=hf, fill=label_yellow)

    cols = [
        {"icon": "brain", "heading": "COGNITIVE BOOST",
         "body": "Daily logic training builds memory and focus. Backed by research on adult brain plasticity."},
        {"icon": "eye", "heading": "EASY ON EYES",
         "body": "True 30-point numerals — bigger than any other large-print sudoku on Amazon."},
        {"icon": "gift", "heading": "PERFECT GIFT",
         "body": "Mother's Day, birthdays, holidays, get-well boxes. Pair with a soft-grip pencil."},
    ]
    col_w = (W - 80) // 3
    col_y = 100

    for i, c in enumerate(cols):
        cx_col = 40 + i * col_w + col_w // 2
        # Yellow circle icon background
        circle_d = 92
        d.ellipse([cx_col - circle_d // 2, col_y, cx_col + circle_d // 2, col_y + circle_d],
                  fill=label_yellow)
        renderer = ICON_RENDERERS.get(c["icon"])
        if renderer:
            renderer(d, cx_col, col_y + circle_d // 2, int(circle_d * 0.55), (255, 255, 255))

        # Heading
        hcf = _heavy_font(22)
        hcbb = d.textbbox((0, 0), c["heading"], font=hcf)
        while (hcbb[2] - hcbb[0]) > col_w - 20 and hcf.size > 14:
            hcf = _heavy_font(hcf.size - 1)
            hcbb = d.textbbox((0, 0), c["heading"], font=hcf)
        d.text((cx_col - (hcbb[2] - hcbb[0]) // 2 - hcbb[0],
                col_y + circle_d + 18 - hcbb[1]),
               c["heading"], font=hcf, fill=label_yellow)

        # Body — wrap
        bf = _heavy_font(15)
        body_lines = _wrap_text(c["body"], bf, col_w - 30, d)
        cur_y = col_y + circle_d + 60
        for line in body_lines[:5]:
            bbb = d.textbbox((0, 0), line, font=bf)
            d.text((cx_col - (bbb[2] - bbb[0]) // 2 - bbb[0],
                    cur_y - bbb[1]),
                   line, font=bf, fill=title_color)
            cur_y += (bbb[3] - bbb[1]) + 4

    # Top accent ribbon
    ImageDraw.Draw(img).rectangle([0, 0, W, 5], fill=label_yellow)

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

    # Detect schema version: v2 has IMAGE_TEXT_OVERLAY at module_id 2
    # (FROM EASY TO HARD difficulty cards). v1 has FOUR_IMAGE_HIGHLIGHT at id 2.
    m2_raw = _get_module(modules, 2)
    is_v2 = m2_raw is not None and m2_raw.get("module_type") == "IMAGE_TEXT_OVERLAY" \
            and "level" in (m2_raw.get("headline", "").lower() + m2_raw.get("body_text", "").lower())

    # Module 1 — Header
    m1 = _get_module(modules, 1) or _get_module_by_type(modules, "HEADER_IMAGE_TEXT")
    if m1:
        render_module_1_header(theme, plan, m1, out_dir / "module_1_header.png")

    # Module 2 — Difficulty cards (v2) OR 4 highlights (v1 fallback)
    if m2_raw:
        if is_v2:
            render_module_2_difficulty_cards(theme, plan, m2_raw, out_dir / "module_2_difficulty.png")
        else:
            render_module_2_highlights(theme, plan, m2_raw, out_dir)

    # Module 4 — Inside
    m4 = _get_module(modules, 4)
    if m4:
        render_module_4_inside(theme, plan, m4, out_dir / "module_4_inside.png")

    # Module 5 — Size comparison (v1 + v2 same)
    m5 = _get_module(modules, 5)
    if m5:
        scheme_name = (plan.get("front_color_scheme") or "green").lower()
        if scheme_name == "green":
            render_module_5_size_compare(theme, plan, m5, out_dir / "module_5_size_compare.png")
        else:
            render_module_5_ladder(theme, plan, m5, out_dir / "module_5_ladder.png")

    # Module 6 — v2: Why Hand-Verified (green scheme); v1: gift scenarios
    m6 = _get_module(modules, 6)
    if m6:
        scheme_name = (plan.get("front_color_scheme") or "green").lower()
        m6_type = (m6.get("module_type") or "")
        m6_headline = (m6.get("headline") or "").lower()
        if is_v2 and ("verif" in m6_headline or "hand" in m6_headline):
            render_module_6_verified(theme, plan, m6, out_dir / "module_6_verified.png")
        elif scheme_name == "green":
            icons = [
                {"icon": "gift",     "label": "MOM/DAD",    "sub": "Mother's & Father's Day"},
                {"icon": "calendar", "label": "HOLIDAYS",   "sub": "Christmas & birthdays"},
                {"icon": "heart",    "label": "GET WELL",   "sub": "Recovery & care packages"},
                {"icon": "flower",   "label": "RETIREMENT", "sub": "A daily ritual"},
            ]
            render_module_6_scenarios(theme, plan, m6, out_dir / "module_6_gift.png", icons)
        else:
            icons = [
                {"icon": "umbrella", "label": "RAINY DAYS",  "sub": "Indoor focus"},
                {"icon": "book",     "label": "HOMESCHOOL",  "sub": "STEM-aligned"},
                {"icon": "plane",    "label": "ROAD TRIPS",  "sub": "Plane & car"},
            ]
            render_module_6_scenarios(theme, plan, m6, out_dir / "module_6_use_cases.png", icons)

    # Module 7 — v2 only: 3-col benefits (Cognitive / Eyes / Gift)
    m7 = _get_module(modules, 7)
    if m7 and (m7.get("module_type") in ("THREE_IMAGES_TEXT", "STANDARD_THREE_IMAGES_TEXT")
               or "built for the reader" in (m7.get("headline") or "").lower()):
        render_module_7_three_col_benefits(theme, plan, m7, out_dir / "module_7_benefits.png")

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
