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
    title = meta["title"]
    max_width = PAGE_W - 1.0 * inch  # 0.5" margin each side

    # Auto-shrink, then wrap if still too wide
    title_size = 46
    while title_size > 30 and c.stringWidth(title, "Times-Bold", title_size) > max_width:
        title_size -= 2

    title_y_top = PAGE_H * 0.78
    if c.stringWidth(title, "Times-Bold", title_size) <= max_width:
        c.setFont("Times-Bold", title_size)
        c.drawCentredString(PAGE_W / 2, title_y_top - title_size, title)
    else:
        # Still too wide → wrap to multi-line
        _draw_wrapped(
            c, title, PAGE_W / 2, title_y_top - title_size,
            max_width=max_width, font="Times-Bold",
            size=title_size, leading=title_size * 1.15,
        )

    if meta.get("subtitle"):
        subtitle = meta["subtitle"]
        _draw_wrapped(
            c, subtitle, PAGE_W / 2, PAGE_H * 0.55,
            max_width=PAGE_W - 1.5 * inch, font="Times-Italic",
            size=16, leading=22,
        )
    author = meta.get("author", "")
    if author:
        c.setFont("Times-Roman", 14)
        c.drawCentredString(PAGE_W / 2, PAGE_H * 0.20, f"By {author}")
    c.showPage()


def build_bookplate_page(c: canvas.Canvas) -> None:
    """\"This book belongs to ___\" page — adds personal value, common in
    senior-targeted puzzle books. Hand-fillable lines."""
    c.setFont("Times-Bold", 30)
    c.drawCentredString(PAGE_W / 2, PAGE_H * 0.82, "This Book Belongs To")

    # Decorative ornament
    c.setFont("Times-Italic", 16)
    c.drawCentredString(PAGE_W / 2, PAGE_H * 0.76, "❦")

    # Name line
    c.setFont("Times-Roman", 14)
    line_y = PAGE_H * 0.62
    line_w = 4.5 * inch
    line_x = (PAGE_W - line_w) / 2
    c.setLineWidth(0.6)
    c.line(line_x, line_y, line_x + line_w, line_y)
    c.drawCentredString(PAGE_W / 2, line_y - 18, "Name")

    # If found / contact
    line_y2 = PAGE_H * 0.46
    c.line(line_x, line_y2, line_x + line_w, line_y2)
    c.drawCentredString(PAGE_W / 2, line_y2 - 18, "If found, please return to (optional)")

    # Started / Completed dates
    c.setFont("Times-Roman", 12)
    label_y = PAGE_H * 0.30
    half = (PAGE_W - 2.0 * inch) / 2
    # Started
    sx1 = 1.0 * inch
    c.line(sx1, label_y, sx1 + half - 0.25 * inch, label_y)
    c.drawCentredString(sx1 + (half - 0.25 * inch) / 2, label_y - 16, "Started")
    # Completed
    sx2 = sx1 + half + 0.25 * inch
    c.line(sx2, label_y, sx2 + half - 0.25 * inch, label_y)
    c.drawCentredString(sx2 + (half - 0.25 * inch) / 2, label_y - 16, "Completed")

    # Dedication line
    c.setFont("Times-Italic", 11)
    c.drawCentredString(
        PAGE_W / 2, PAGE_H * 0.13,
        "May every quiet hour with this book bring focus, calm, and a smile.",
    )
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


def build_howto_page_1(c: canvas.Canvas) -> None:
    """Page 1 of How to Play — the rules + how to start."""
    c.setFont("Times-Bold", 32)
    c.drawCentredString(PAGE_W / 2, PAGE_H * 0.90, "How to Play")

    c.setFont("Times-Roman", 13)
    body = [
        "Sudoku is a logic puzzle played on a 9 × 9 grid divided into",
        "nine smaller 3 × 3 boxes. Some cells are filled with numbers",
        "(the clues); the rest are empty.",
        "",
        "The goal is to fill every empty cell so that all three rules",
        "are satisfied at once:",
        "",
        "   1.   Every row contains each of the numbers 1 – 9 exactly once.",
        "   2.   Every column contains each of the numbers 1 – 9 exactly once.",
        "   3.   Every 3 × 3 box contains each of the numbers 1 – 9 exactly once.",
        "",
        "Every puzzle in this book has been verified to have exactly",
        "one correct solution, reached by logic alone — no guessing.",
        "",
        "",
        "Tips for getting started",
        "",
        "•  Work in pencil. You will change your mind, and that is",
        "    a normal part of solving.",
        "",
        "•  Look for rows, columns, or 3 × 3 boxes that already have",
        "    many clues. They are easier to complete first.",
        "",
        "•  When you find a number that can go in only one place,",
        "    write it firmly. Each new entry tightens the puzzle.",
        "",
        "•  If you feel stuck, take a short break. A fresh look",
        "    often reveals the next move.",
    ]
    y = PAGE_H * 0.81
    for line in body:
        c.drawString(0.85 * inch, y, line)
        y -= 18
    c.showPage()


def build_howto_page_2(c: canvas.Canvas) -> None:
    """Page 2 of How to Play — a worked example showing the scanning technique."""
    c.setFont("Times-Bold", 28)
    c.drawCentredString(PAGE_W / 2, PAGE_H * 0.92, "A Helpful Technique: Scanning")

    c.setFont("Times-Roman", 12)
    intro = [
        "Pick a number — say, the digit 5 — and look at where it already appears.",
        "Each row, column, and 3 × 3 box can contain only one 5. By eliminating",
        "the rows, columns, and boxes that already have a 5, you often find that",
        "only one cell is left where another 5 can go.",
    ]
    y = PAGE_H * 0.86
    for line in intro:
        c.drawCentredString(PAGE_W / 2, y, line)
        y -= 16

    # Worked-example mini grid showing where a 5 must go
    example_grid = [
        [0, 0, 0, 0, 5, 0, 0, 0, 0],
        [0, 5, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 5],
        [5, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0],  # row 4 = the row we are solving
        [0, 0, 0, 0, 0, 0, 5, 0, 0],
        [0, 0, 5, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 5, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 5, 0, 0, 0],
    ]
    grid_size = 4.2 * inch
    gx = (PAGE_W - grid_size) / 2
    gy = PAGE_H * 0.30
    draw_sudoku_grid(
        c, gx, gy, grid_size, example_grid,
        clue_font="Helvetica-Bold",
        clue_font_size=18,
        thick_w=2.2, thin_w=0.6,
    )

    # Explanation below the grid
    c.setFont("Times-Italic", 12)
    explain = [
        "In this snapshot, look at row 5 (the empty middle row). Columns 1, 4,",
        "and 9 already have a 5 elsewhere in the puzzle, and so does the",
        "middle 3 × 3 box. Cross those out, and only one cell in row 5 can",
        "hold a 5. That is your next confident entry.",
    ]
    y = gy - 0.40 * inch
    for line in explain:
        c.drawCentredString(PAGE_W / 2, y, line)
        y -= 15

    # Footer
    c.setFont("Times-Roman", 11)
    c.drawCentredString(
        PAGE_W / 2, 0.55 * inch,
        "Full solutions are provided at the back of the book.",
    )
    c.showPage()


def build_toc_page(
    c: canvas.Canvas,
    sections: list[dict],
) -> None:
    """Table of Contents grouped by difficulty section.

    `sections` is a list of dicts: {label, count, divider_page, first_puzzle_page,
    last_puzzle_page}. Solutions section is appended at the end by the caller.
    """
    c.setFont("Times-Bold", 32)
    c.drawCentredString(PAGE_W / 2, PAGE_H * 0.90, "Table of Contents")

    # Decorative rule
    c.setLineWidth(0.7)
    c.line(2.5 * inch, PAGE_H * 0.86, PAGE_W - 2.5 * inch, PAGE_H * 0.86)

    c.setFont("Times-Roman", 14)
    label_x = 1.4 * inch
    page_x = PAGE_W - 1.4 * inch
    y = PAGE_H * 0.78

    for sec in sections:
        label = sec["label"]
        page_str = sec["page_str"]
        c.drawString(label_x, y, label)
        # Dotted leader between label and page number
        leader_start = label_x + c.stringWidth(label, "Times-Roman", 14) + 6
        leader_end = page_x - c.stringWidth(page_str, "Times-Roman", 14) - 6
        c.setFont("Times-Roman", 14)
        if leader_end > leader_start:
            dot_y = y + 3
            for dx in range(int(leader_start), int(leader_end), 6):
                c.drawString(dx, dot_y - 3, ".")
        c.drawRightString(page_x, y, page_str)
        # Sub-line: count of puzzles
        if sec.get("subtitle"):
            c.setFont("Times-Italic", 10)
            c.drawString(label_x + 0.2 * inch, y - 14, sec["subtitle"])
            c.setFont("Times-Roman", 14)
        y -= 38

    c.setFont("Times-Italic", 11)
    c.drawCentredString(
        PAGE_W / 2, 0.65 * inch,
        "Each puzzle prints one per page in extra-large numbers.",
    )
    c.showPage()


def build_section_divider(
    c: canvas.Canvas,
    label: str,
    count: int,
    blurb: str,
) -> None:
    """Full-page section divider for a difficulty band."""
    c.setFont("Times-Bold", 56)
    c.drawCentredString(PAGE_W / 2, PAGE_H * 0.62, label)

    c.setFont("Times-Italic", 18)
    c.drawCentredString(PAGE_W / 2, PAGE_H * 0.54, f"{count} Puzzles")

    # Decorative ornament
    c.setFont("Times-Roman", 22)
    c.drawCentredString(PAGE_W / 2, PAGE_H * 0.46, "❦")

    c.setFont("Times-Italic", 13)
    _draw_wrapped(
        c, blurb, PAGE_W / 2, PAGE_H * 0.38,
        max_width=PAGE_W - 2.5 * inch,
        font="Times-Italic", size=13, leading=20,
    )
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
    """Render up to 6 solutions in a 3 rows × 2 cols layout on one page.

    Each grid is 2.85 in. wide; numbers stay legible (~10 pt) which is fine
    for reference-only solution check (not for solving)."""
    grid_size = 2.85 * inch
    gap_x = 0.45 * inch
    gap_y = 0.55 * inch
    cols = 2
    rows = 3
    total_w = cols * grid_size + (cols - 1) * gap_x
    total_h = rows * grid_size + (rows - 1) * gap_y + (rows * 0.20 * inch)  # extra for labels
    start_x = (PAGE_W - total_w) / 2
    start_y = (PAGE_H - total_h) / 2 - 0.05 * inch

    for idx, puz in enumerate(chunk):
        row = idx // cols
        col = idx % cols
        gx = start_x + col * (grid_size + gap_x)
        # reportlab y = bottom-up; top row should be visually highest
        gy = start_y + (rows - 1 - row) * (grid_size + gap_y + 0.20 * inch)

        # Label above grid
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(
            gx + grid_size / 2, gy + grid_size + 0.10 * inch,
            f"#{puz['id']:03d}",
        )
        draw_sudoku_grid(
            c, gx, gy, grid_size, puz["solution"],
            clue_font="Helvetica",
            clue_font_size=11,
            thick_w=1.3, thin_w=0.35,
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

    # ---- Group puzzles by difficulty (preserves insertion order) ----
    DIFF_ORDER = ["easy", "medium", "hard", "expert"]
    DIFF_LABEL = {
        "easy":   "Easy Puzzles",
        "medium": "Medium Puzzles",
        "hard":   "Hard Puzzles",
        "expert": "Expert Puzzles",
    }
    DIFF_BLURB = {
        "easy":   "A gentle warm-up. Most cells reveal themselves with a single, calm pass.",
        "medium": "A pleasant challenge. You will need to look twice and follow the clues a step further.",
        "hard":   "Now we think carefully. Patience and a sharp pencil are your best friends.",
        "expert": "The deepest puzzles in this book. Take your time — the answer is always reachable by logic.",
    }
    by_diff: dict[str, list[dict]] = {d: [] for d in DIFF_ORDER}
    for puz in puzzles:
        d = puz.get("difficulty", "medium")
        by_diff.setdefault(d, []).append(puz)
    sections = [(d, by_diff[d]) for d in DIFF_ORDER if by_diff.get(d)]

    n_puzzles = len(puzzles)
    n_sol_pages = (n_puzzles + 5) // 6  # 6 solutions per page now
    n_section_dividers = sum(1 for _, group in sections if group)

    # Front matter: title + bookplate + copyright + howto×2 + TOC = 6 pages
    front_pages = 6
    core_pages = (
        front_pages
        + n_section_dividers + n_puzzles      # difficulty divider + its puzzles
        + 1 + n_sol_pages                      # solutions divider + solutions
        + 1                                    # thank-you
    )
    pad_blank = 1 if core_pages % 2 != 0 else 0
    total_pages = core_pages + pad_blank

    # ---- First pass: compute the absolute page number where each section starts ----
    # We need this to render the TOC on page 6 with the right numbers.
    toc_entries: list[dict] = []
    page_cursor = front_pages + 1  # first page after the front matter (the first divider)
    for diff, group in sections:
        if not group:
            continue
        divider_page = page_cursor
        first_puzzle_page = page_cursor + 1
        last_puzzle_page = first_puzzle_page + len(group) - 1
        toc_entries.append({
            "label": DIFF_LABEL[diff],
            "page_str": f"{divider_page}",
            "subtitle": f"{len(group)} puzzles · pages {first_puzzle_page}–{last_puzzle_page}",
        })
        page_cursor = last_puzzle_page + 1

    # Solutions section in TOC
    solutions_divider_page = page_cursor
    solutions_first_page = solutions_divider_page + 1
    solutions_last_page = solutions_divider_page + n_sol_pages
    toc_entries.append({
        "label": "Solutions",
        "page_str": f"{solutions_divider_page}",
        "subtitle": f"{n_puzzles} solutions · pages {solutions_first_page}–{solutions_last_page}",
    })

    # ---- Second pass: actually emit the pages ----
    page_num = 1
    build_title_page(c, meta); page_num += 1
    build_bookplate_page(c); page_num += 1
    build_copyright_page(c, meta); page_num += 1
    build_howto_page_1(c); page_num += 1
    build_howto_page_2(c); page_num += 1
    build_toc_page(c, toc_entries); page_num += 1

    # Puzzle sections
    for diff, group in sections:
        if not group:
            continue
        build_section_divider(c, DIFF_LABEL[diff], len(group), DIFF_BLURB[diff])
        page_num += 1
        for puz in group:
            build_puzzle_page(c, puz, page_num)
            page_num += 1

    # Solutions
    build_solutions_divider(c); page_num += 1
    for i in range(0, len(puzzles), 6):
        chunk = puzzles[i:i + 6]
        build_solutions_page(c, chunk, page_num)
        page_num += 1

    # Thank-you
    build_thankyou_page(c, meta); page_num += 1

    # Pad to even
    if pad_blank:
        build_blank_page(c); page_num += 1

    c.save()

    print(f"✅ Wrote {total_pages} pages to {out_path}")
    print(
        f"   Title + bookplate + copyright + howto×2 + TOC: {front_pages} · "
        f"Section dividers: {n_section_dividers} · Puzzles: {n_puzzles} · "
        f"Solutions (divider + {n_sol_pages} @ 6/pg): {1 + n_sol_pages} · "
        f"Thank-you: 1" + (f" · Padding: {pad_blank}" if pad_blank else "")
    )
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--theme", required=True, help="theme_key (folder under output/)")
    args = parser.parse_args()
    assemble(args.theme)


if __name__ == "__main__":
    main()
