#!/usr/bin/env python3
"""Assemble a KDP-ready Sudoku book interior PDF.

Renders every puzzle grid directly onto a reportlab canvas (vector output —
crisp, small file, no DPI issues). Includes front matter (title, copyright,
how-to-play), puzzle pages (1 per page), a solutions section (4 per page),
and a thank-you page. Enforces even page count (KDP requirement).

Reads:
  output/{theme_key}/sudoku_puzzles.json  (from generate_sudoku.py)
  output/{theme_key}/plan.json            (title, subtitle, author, etc.)

Writes:
  output/{theme_key}/interior.pdf

Usage:
  python3 scripts/build_sudoku_book.py --theme sudoku_golden_years
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import config  # noqa: E402

# 8.5 x 11 only for v1 (standard large-print sudoku trim).
PAGE_W = 8.5 * inch
PAGE_H = 11.0 * inch


# ---- Grid drawing ----

def draw_sudoku_grid(
    c: canvas.Canvas,
    x: float, y: float, size: float,
    clues: list[list[int]],
    clue_font: str = "Helvetica-Bold",
    clue_font_size: float | None = None,
    thick_w: float = 2.5,
    thin_w: float = 0.7,
) -> None:
    """Draw a 9x9 sudoku grid with (x, y) = bottom-left, `size` inches wide.

    `clues[r][c]` = 0 means empty cell. Row 0 is top of grid.
    """
    cell = size / 9
    if clue_font_size is None:
        # ~55% of cell height looks good
        clue_font_size = cell * 0.55 * 72 / 72  # already in points
        clue_font_size = cell * 0.55

    # Lines — thick on 3x3 box boundaries
    for i in range(10):
        w = thick_w if i % 3 == 0 else thin_w
        c.setLineWidth(w)
        c.line(x, y + i * cell, x + size, y + i * cell)
        c.line(x + i * cell, y, x + i * cell, y + size)

    # Clues
    c.setFont(clue_font, clue_font_size)
    for r in range(9):
        for col in range(9):
            n = clues[r][col]
            if n == 0:
                continue
            cx = x + col * cell + cell / 2
            # reportlab y is bottom-up; row 0 is visually top
            cy_top = y + size - r * cell
            text_y = cy_top - cell / 2 - clue_font_size / 3  # visual centering
            c.drawCentredString(cx, text_y, str(n))


# ---- Page builders ----

def build_title_page(c: canvas.Canvas, meta: dict) -> None:
    c.setFont("Times-Bold", 46)
    title = meta["title"]
    # Auto-wrap if very long
    c.drawCentredString(PAGE_W / 2, PAGE_H * 0.72, title)
    if meta.get("subtitle"):
        c.setFont("Times-Italic", 16)
        subtitle = meta["subtitle"]
        _draw_wrapped(c, subtitle, PAGE_W / 2, PAGE_H * 0.58, max_width=PAGE_W - 1.5 * inch,
                      font="Times-Italic", size=16, leading=22)
    author = meta.get("author", "")
    if author:
        c.setFont("Times-Roman", 14)
        c.drawCentredString(PAGE_W / 2, PAGE_H * 0.25, f"By {author}")
    c.showPage()


def build_copyright_page(c: canvas.Canvas, meta: dict) -> None:
    author = meta.get("author", "")
    year = datetime.date.today().year
    c.setFont("Times-Roman", 10)
    lines = [
        f"© {year} {author}. All rights reserved.",
        "",
        "No part of this publication may be reproduced, stored in a retrieval",
        "system, or transmitted in any form or by any means — electronic,",
        "mechanical, photocopying, recording, or otherwise — without prior",
        "written permission of the copyright holder, except for brief",
        "quotations used in reviews.",
        "",
        "Every puzzle in this book has been verified to have exactly one",
        "unique solution.",
        "",
        f"First printing, {year}.",
        f"Printed in the United States of America.",
    ]
    y = PAGE_H * 0.85
    for line in lines:
        c.drawString(1.0 * inch, y, line)
        y -= 16
    c.showPage()


def build_howto_page(c: canvas.Canvas) -> None:
    c.setFont("Times-Bold", 28)
    c.drawCentredString(PAGE_W / 2, PAGE_H * 0.88, "How to Play")

    c.setFont("Times-Roman", 12)
    body = [
        "Sudoku is a logic puzzle played on a 9 × 9 grid divided into nine",
        "3 × 3 boxes. Some cells are filled with numbers (the clues); the",
        "rest are empty.",
        "",
        "The goal is to fill in every empty cell so that three rules are",
        "all satisfied at once:",
        "",
        "   1.  Every row contains each of the numbers 1 through 9 exactly once.",
        "   2.  Every column contains each of the numbers 1 through 9 exactly once.",
        "   3.  Every 3 × 3 box contains each of the numbers 1 through 9 exactly once.",
        "",
        "Every puzzle in this book has exactly one correct solution, reached",
        "through pure logic — no guessing required.",
        "",
        "Work in pencil. Begin with the easier cells, where only one number",
        "can possibly fit. Use the clues you add to uncover more constraints.",
        "Breathe, take your time, and enjoy the quiet satisfaction of each",
        "completed grid.",
        "",
        "Full solutions are provided at the back of the book.",
    ]
    y = PAGE_H * 0.78
    for line in body:
        c.drawString(1.0 * inch, y, line)
        y -= 18
    c.showPage()


def build_puzzle_page(c: canvas.Canvas, puzzle: dict, page_num: int) -> None:
    # Header: Puzzle number + difficulty
    c.setFont("Helvetica", 11)
    header = f"Puzzle #{puzzle['id']:03d}   ·   {puzzle['difficulty'].upper()}"
    c.drawCentredString(PAGE_W / 2, PAGE_H - 0.55 * inch, header)

    # Grid — 6 inches wide, centered, shifted slightly above center for aesthetics
    grid_size = 6.0 * inch
    gx = (PAGE_W - grid_size) / 2
    gy = (PAGE_H - grid_size) / 2 - 0.2 * inch  # optical center
    draw_sudoku_grid(
        c, gx, gy, grid_size, puzzle["puzzle"],
        clue_font="Helvetica-Bold",
        clue_font_size=26,
        thick_w=3.0, thin_w=0.8,
    )

    # Page number (bottom)
    c.setFont("Helvetica", 9)
    c.drawCentredString(PAGE_W / 2, 0.45 * inch, str(page_num))
    c.showPage()


def build_solutions_divider(c: canvas.Canvas) -> None:
    c.setFont("Times-Bold", 56)
    c.drawCentredString(PAGE_W / 2, PAGE_H * 0.55, "Solutions")
    c.setFont("Times-Italic", 14)
    c.drawCentredString(PAGE_W / 2, PAGE_H * 0.46, "— in the order they appear —")
    c.showPage()


def build_solutions_page(c: canvas.Canvas, chunk: list[dict], page_num: int) -> None:
    """Render up to 4 solutions in a 2x2 grid on one page."""
    # Grid layout: 2 cols × 2 rows, with labels
    grid_size = 3.0 * inch
    gap_x = 0.5 * inch
    gap_y = 0.75 * inch
    total_w = 2 * grid_size + gap_x
    total_h = 2 * grid_size + gap_y
    start_x = (PAGE_W - total_w) / 2
    start_y = (PAGE_H - total_h) / 2 - 0.1 * inch  # slight shift for header

    for idx, puz in enumerate(chunk):
        row = idx // 2
        col = idx % 2
        gx = start_x + col * (grid_size + gap_x)
        # reportlab y = bottom-up; top row should be ABOVE bottom row
        gy = start_y + (1 - row) * (grid_size + gap_y)

        # Label above grid
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(
            gx + grid_size / 2, gy + grid_size + 0.12 * inch,
            f"#{puz['id']:03d}",
        )
        draw_sudoku_grid(
            c, gx, gy, grid_size, puz["solution"],
            clue_font="Helvetica",
            clue_font_size=12,
            thick_w=1.5, thin_w=0.4,
        )

    # Page number
    c.setFont("Helvetica", 9)
    c.drawCentredString(PAGE_W / 2, 0.45 * inch, str(page_num))
    c.showPage()


def build_thankyou_page(c: canvas.Canvas, meta: dict) -> None:
    c.setFont("Times-Italic", 22)
    c.drawCentredString(PAGE_W / 2, PAGE_H * 0.60, "Thank you for solving with us.")
    c.setFont("Times-Roman", 13)
    c.drawCentredString(
        PAGE_W / 2, PAGE_H * 0.50,
        "If this book brought you a moment of quiet focus,",
    )
    c.drawCentredString(
        PAGE_W / 2, PAGE_H * 0.475,
        "a short review on Amazon means the world to us.",
    )
    c.showPage()


def build_blank_page(c: canvas.Canvas) -> None:
    c.showPage()


# ---- Utilities ----

def _draw_wrapped(
    c: canvas.Canvas, text: str, x_center: float, y_start: float,
    max_width: float, font: str, size: float, leading: float,
) -> float:
    """Draw text word-wrapped at approximately `max_width` points, centered at x_center."""
    c.setFont(font, size)
    words = text.split()
    lines: list[list[str]] = [[]]
    for w in words:
        test = " ".join(lines[-1] + [w])
        if c.stringWidth(test, font, size) <= max_width:
            lines[-1].append(w)
        else:
            lines.append([w])
    y = y_start
    for line_words in lines:
        c.drawCentredString(x_center, y, " ".join(line_words))
        y -= leading
    return y


# ---- Main assembly ----

def assemble(theme: str) -> Path:
    theme_dir = Path(config.get_book_dir(theme))
    puzzles_path = theme_dir / "sudoku_puzzles.json"
    plan_path = Path(config.get_plan_path(theme))

    if not puzzles_path.exists():
        raise SystemExit(
            f"Missing {puzzles_path}. Run generate_sudoku.py first."
        )
    if not plan_path.exists():
        raise SystemExit(
            f"Missing {plan_path}. Create it with title/subtitle/author."
        )

    puzzles = json.loads(puzzles_path.read_text())
    plan = json.loads(plan_path.read_text())

    meta = {
        "title": plan["title"],
        "subtitle": plan.get("subtitle", ""),
        "author": plan.get("author", ""),
    }

    out_path = theme_dir / "interior.pdf"
    c = canvas.Canvas(str(out_path), pagesize=(PAGE_W, PAGE_H))
    c.setTitle(meta["title"])
    c.setAuthor(meta["author"])

    print(f"Assembling {out_path} …")

    # Count pages: title(1) + copyright(1) + howto(1) + puzzles(N) + sol_div(1) + sol_pages(ceil(N/4)) + thankyou(1)
    n_puzzles = len(puzzles)
    n_sol_pages = (n_puzzles + 3) // 4
    core_pages = 3 + n_puzzles + 1 + n_sol_pages + 1  # front + puzzles + sol_div + sols + thankyou
    # Enforce even page count
    pad_blank = 1 if core_pages % 2 != 0 else 0
    total_pages = core_pages + pad_blank

    # Front matter
    page_num = 1
    build_title_page(c, meta); page_num += 1
    build_copyright_page(c, meta); page_num += 1
    build_howto_page(c); page_num += 1

    # Puzzle pages
    for puz in puzzles:
        build_puzzle_page(c, puz, page_num)
        page_num += 1

    # Solutions
    build_solutions_divider(c); page_num += 1
    for i in range(0, len(puzzles), 4):
        chunk = puzzles[i:i + 4]
        build_solutions_page(c, chunk, page_num)
        page_num += 1

    # Thank-you
    build_thankyou_page(c, meta); page_num += 1

    # Pad to even
    if pad_blank:
        build_blank_page(c); page_num += 1

    c.save()

    print(f"✅ Wrote {total_pages} pages to {out_path}")
    print(f"   Front matter: 3 · Puzzles: {n_puzzles} · Solutions divider+pages: {1 + n_sol_pages} · Thank-you: 1"
          + (f" · Padding: {pad_blank}" if pad_blank else ""))
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--theme", required=True, help="theme_key (folder under output/)")
    args = parser.parse_args()
    assemble(args.theme)


if __name__ == "__main__":
    main()
