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
import random
import sys
from pathlib import Path

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
    grid_size: int = 9,
    box_rows: int = 3,
    box_cols: int = 3,
    clue_font: str = "Helvetica-Bold",
    clue_font_size: float | None = None,
    thick_w: float = 2.5,
    thin_w: float = 0.7,
) -> None:
    """Draw a sudoku grid with (x, y) = bottom-left, `size` inches wide.

    Supports two configurations:
      • 9×9 grid with 3×3 boxes  (grid_size=9, box_rows=3, box_cols=3)  — default
      • 6×6 grid with 2×3 boxes  (grid_size=6, box_rows=2, box_cols=3)  — warm-up

    `clues[r][col]` = 0 means empty cell. Row 0 is the top of the grid.
    Thick lines are drawn on 3×3 (or 2×3) box boundaries; thin lines elsewhere.
    """
    cell = size / grid_size
    if clue_font_size is None:
        clue_font_size = cell * 0.55  # ~55% of cell height reads well

    # Horizontal lines: thick on box-row boundaries (rows 0, box_rows, 2*box_rows, ...)
    for i in range(grid_size + 1):
        w = thick_w if i % box_rows == 0 else thin_w
        c.setLineWidth(w)
        c.line(x, y + i * cell, x + size, y + i * cell)

    # Vertical lines: thick on box-col boundaries (cols 0, box_cols, 2*box_cols, ...)
    for i in range(grid_size + 1):
        w = thick_w if i % box_cols == 0 else thin_w
        c.setLineWidth(w)
        c.line(x + i * cell, y, x + i * cell, y + size)

    # Clues
    c.setFont(clue_font, clue_font_size)
    for r in range(grid_size):
        for col in range(grid_size):
            n = clues[r][col]
            if n == 0:
                continue
            cx = x + col * cell + cell / 2
            # reportlab y is bottom-up; row 0 is visually top
            cy_top = y + size - r * cell
            text_y = cy_top - cell / 2 - clue_font_size / 3  # visual centering
            c.drawCentredString(cx, text_y, str(n))


# Helper: pick box dims from puzzle dict (puzzles created with grid_size from generate_sudoku.py)
def _grid_dims(puzzle: dict) -> tuple[int, int, int]:
    """Return (grid_size, box_rows, box_cols) for a puzzle dict."""
    sz = puzzle.get("grid_size", 9)
    if sz == 6:
        return 6, 2, 3
    return 9, 3, 3


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


def _draw_journal_strip(
    c: canvas.Canvas,
    x_center: float,
    y: float,
    width: float = 5.0 * inch,
    font_size: float = 9,
) -> None:
    """Draw a one-line Brain Training Journal footer below a puzzle grid.

    Layout:  Time: ___ : ___   |   Date: __ / __ / ____   |   Rate ___ / 5

    Pure ASCII (uses pipe separator) so it renders cleanly with reportlab
    standard fonts — no Unicode glyph dependencies.
    """
    c.setFont("Helvetica", font_size)
    text = "Time: ___ : ___       |       Date: __ / __ / ____       |       Rate ___ / 5"
    c.drawCentredString(x_center, y, text)


def build_puzzle_page_1up(c: canvas.Canvas, puzzle: dict, page_num: int) -> None:
    """1 puzzle per page — extra-large grid (6" wide). Used for Easy tier
    (Senior-Friendly Large-Print USP). Includes Brain Journal strip below grid."""
    gs, br, bc = _grid_dims(puzzle)

    # Header: Puzzle number + difficulty
    c.setFont("Helvetica", 11)
    header = f"Puzzle #{puzzle['id']:03d}   ·   {puzzle['difficulty'].upper()}"
    c.drawCentredString(PAGE_W / 2, PAGE_H - 0.55 * inch, header)

    # Grid — 6 inches wide, centered, shifted slightly above center for aesthetics
    grid_w = 6.0 * inch
    gx = (PAGE_W - grid_w) / 2
    gy = (PAGE_H - grid_w) / 2 - 0.05 * inch  # near-center, leaves room for journal
    draw_sudoku_grid(
        c, gx, gy, grid_w, puzzle["puzzle"],
        grid_size=gs, box_rows=br, box_cols=bc,
        clue_font="Helvetica-Bold",
        clue_font_size=26,
        thick_w=3.0, thin_w=0.8,
    )

    # Brain Journal strip
    _draw_journal_strip(c, PAGE_W / 2, gy - 0.40 * inch, font_size=10)

    # Page number (bottom)
    c.setFont("Helvetica", 9)
    c.drawCentredString(PAGE_W / 2, 0.45 * inch, str(page_num))
    c.showPage()


# Backwards-compat alias (older callers)
build_puzzle_page = build_puzzle_page_1up


def build_puzzle_page_2up(c: canvas.Canvas, puzzles: list[dict], page_num: int) -> None:
    """2 puzzles per page — vertically stacked. Used for Medium tier.
    Each puzzle gets its own header and Brain Journal strip."""
    grid_w = 3.6 * inch
    gx = (PAGE_W - grid_w) / 2

    # ---- Top puzzle ----
    p1 = puzzles[0]
    gs, br, bc = _grid_dims(p1)
    c.setFont("Helvetica", 11)
    c.drawCentredString(
        PAGE_W / 2, PAGE_H - 0.50 * inch,
        f"Puzzle #{p1['id']:03d}   ·   {p1['difficulty'].upper()}",
    )
    gy_top = PAGE_H - 0.75 * inch - grid_w
    draw_sudoku_grid(
        c, gx, gy_top, grid_w, p1["puzzle"],
        grid_size=gs, box_rows=br, box_cols=bc,
        clue_font="Helvetica-Bold",
        clue_font_size=16,
        thick_w=2.4, thin_w=0.6,
    )
    _draw_journal_strip(c, PAGE_W / 2, gy_top - 0.30 * inch, font_size=8)

    # ---- Bottom puzzle ----
    if len(puzzles) > 1:
        p2 = puzzles[1]
        gs2, br2, bc2 = _grid_dims(p2)
        # Header for bottom puzzle (mid-page)
        c.setFont("Helvetica", 11)
        c.drawCentredString(
            PAGE_W / 2, PAGE_H * 0.46,
            f"Puzzle #{p2['id']:03d}   ·   {p2['difficulty'].upper()}",
        )
        gy_bot = 1.0 * inch
        draw_sudoku_grid(
            c, gx, gy_bot, grid_w, p2["puzzle"],
            grid_size=gs2, box_rows=br2, box_cols=bc2,
            clue_font="Helvetica-Bold",
            clue_font_size=16,
            thick_w=2.4, thin_w=0.6,
        )
        _draw_journal_strip(c, PAGE_W / 2, gy_bot - 0.30 * inch, font_size=8)

    # Page number
    c.setFont("Helvetica", 9)
    c.drawCentredString(PAGE_W / 2, 0.45 * inch, str(page_num))
    c.showPage()


def build_puzzle_page_4up(c: canvas.Canvas, puzzles: list[dict], page_num: int) -> None:
    """4 puzzles per page — 2×2 grid layout. Used for Warmup (6×6),
    Hard (9×9), and Expert (9×9) tiers. Headers per puzzle; no journal
    strip here (cells too small — journal is only on 1-up and 2-up pages)."""
    grid_w = 3.0 * inch
    gap_x = 0.45 * inch
    gap_y = 0.55 * inch
    cols = 2
    rows = 2

    total_w = cols * grid_w + (cols - 1) * gap_x
    total_h = rows * grid_w + (rows - 1) * gap_y + (rows * 0.20 * inch)
    start_x = (PAGE_W - total_w) / 2
    start_y = (PAGE_H - total_h) / 2 - 0.05 * inch

    for idx, puz in enumerate(puzzles[:4]):
        gs, br, bc = _grid_dims(puz)
        row = idx // cols
        col = idx % cols
        gx = start_x + col * (grid_w + gap_x)
        # reportlab y = bottom-up; row 0 should be visually highest
        gy = start_y + (rows - 1 - row) * (grid_w + gap_y + 0.20 * inch)

        # Header above each grid
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(
            gx + grid_w / 2,
            gy + grid_w + 0.12 * inch,
            f"Puzzle #{puz['id']:03d}",
        )

        # Cell font scales by grid: 6×6 (warmup) gets bigger digits than 9×9
        cell_pt = grid_w / gs
        clue_pt = cell_pt * 0.55
        draw_sudoku_grid(
            c, gx, gy, grid_w, puz["puzzle"],
            grid_size=gs, box_rows=br, box_cols=bc,
            clue_font="Helvetica-Bold",
            clue_font_size=clue_pt,
            thick_w=1.8, thin_w=0.5,
        )

    # Page number
    c.setFont("Helvetica", 9)
    c.drawCentredString(PAGE_W / 2, 0.45 * inch, str(page_num))
    c.showPage()


def build_solutions_divider(c: canvas.Canvas) -> None:
    c.setFont("Times-Bold", 56)
    c.drawCentredString(PAGE_W / 2, PAGE_H * 0.55, "Solutions")
    c.setFont("Times-Italic", 16)
    c.drawCentredString(PAGE_W / 2, PAGE_H * 0.48, "Tier 3 — Full Solutions")
    c.setFont("Times-Italic", 13)
    c.drawCentredString(
        PAGE_W / 2, PAGE_H * 0.42,
        "Use these to verify your answer once the puzzle is complete.",
    )
    c.showPage()


# ---------------------------------------------------------------------------
# Hint System — Progressive 3-tier (USP #2)
# ---------------------------------------------------------------------------
#
# Tier 1 (5 extra clues per puzzle)   →  compact text, ~22 puzzles per page
# Tier 2 (10 extra clues per puzzle)  →  compact text, ~14 puzzles per page
# Tier 3 (full solution grid)         →  existing solutions section, 6 grids/page
#
# Each tier has its own divider so readers can skip ahead.
# ---------------------------------------------------------------------------

# Per-grid-size hint counts. Warmup has only ~10-14 empty cells so 5 hints
# would reveal 36-50% — too generous. Use smaller counts for 6×6.
HINT_COUNTS = {
    9: {"tier1": 5, "tier2_total": 10},   # 9×9 standard puzzles
    6: {"tier1": 2, "tier2_total": 4},    # 6×6 warm-up
}


def _generate_hint_cells(
    puzzle: dict,
    n_hints: int,
    rng: random.Random,
    exclude: set[tuple[int, int]] | None = None,
) -> list[tuple[int, int, int]]:
    """Pick `n_hints` empty cells from a puzzle using greedy spread sampling.

    Greedy spread: each new hint is preferentially picked from a row, column,
    AND 3×3 box that's different from already-chosen hints (and excluded
    cells). When no fully-fresh candidate exists, falls back to any candidate.
    This avoids the "4 hints in the same row" cluster failure mode.

    `exclude` is a set of (r, c) cells already revealed by a previous tier;
    new hints are picked outside this set, and the spread constraint also
    avoids the rows/cols/boxes those excluded cells already occupy.

    Returns sorted (row, col, value) triples (0-indexed; display layer adds +1).
    Caps at total_empty - 1 so at least one cell always remains for the solver.
    """
    grid_size = puzzle.get("grid_size", 9)
    box_rows = 2 if grid_size == 6 else 3
    box_cols = 3
    exclude = exclude or set()

    # All currently-empty cells (i.e., not yet revealed by puzzle clues)
    candidates = [
        (r, c) for r in range(grid_size) for c in range(grid_size)
        if puzzle["puzzle"][r][c] == 0 and (r, c) not in exclude
    ]
    total_empty = sum(
        1 for r in range(grid_size) for c in range(grid_size)
        if puzzle["puzzle"][r][c] == 0
    )

    # Leave at least 1 unrevealed cell; account for cells already excluded.
    max_new = max(0, (total_empty - 1) - len(exclude))
    cap = max(0, min(n_hints, max_new, len(candidates)))
    if cap == 0:
        return []

    # Track already-occupied rows / cols / boxes (from exclude set)
    used_rows = {r for r, _ in exclude}
    used_cols = {c for _, c in exclude}
    used_boxes = {(r // box_rows, c // box_cols) for r, c in exclude}

    available = candidates[:]
    rng.shuffle(available)

    chosen: list[tuple[int, int]] = []
    while len(chosen) < cap and available:
        # Prefer cells that share NEITHER row, col, NOR box with already-used set
        ideal = [
            (r, c) for (r, c) in available
            if r not in used_rows
            and c not in used_cols
            and (r // box_rows, c // box_cols) not in used_boxes
        ]
        if ideal:
            pick = ideal[0]  # already shuffled, so this is random within ideals
        else:
            # No fully-fresh option → relax to "different row" only
            partial = [(r, c) for (r, c) in available if r not in used_rows]
            pick = partial[0] if partial else available[0]

        chosen.append(pick)
        used_rows.add(pick[0])
        used_cols.add(pick[1])
        used_boxes.add((pick[0] // box_rows, pick[1] // box_cols))
        available.remove(pick)

    chosen.sort()  # stable display order
    return [(r, c, puzzle["solution"][r][c]) for (r, c) in chosen]


def compute_tier_hints(
    puzzles: list[dict],
    seed: int,
) -> tuple[dict[int, list], dict[int, list]]:
    """Pre-compute Tier 1 and Tier 2 hints for every puzzle.

    Tier 2 is CUMULATIVE: it includes all of Tier 1's cells plus enough new
    cells (also picked with spread) to reach the per-size Tier 2 target.

    Returns (tier1_by_id, tier2_by_id).
    """
    rng_t1 = random.Random((seed << 1) ^ 0xA5A5)
    rng_t2 = random.Random((seed << 1) ^ 0x5A5A)

    tier1: dict[int, list] = {}
    tier2: dict[int, list] = {}

    for puz in puzzles:
        gs = puz.get("grid_size", 9)
        counts = HINT_COUNTS.get(gs, HINT_COUNTS[9])
        n_t1 = counts["tier1"]
        n_t2 = counts["tier2_total"]

        # Tier 1
        t1_cells = _generate_hint_cells(puz, n_t1, rng_t1)
        tier1[puz["id"]] = t1_cells

        # Tier 2 = Tier 1 cells + (n_t2 - len(t1)) more, picked fresh with exclude
        t1_coords = {(r, c) for r, c, _ in t1_cells}
        n_extra = max(0, n_t2 - len(t1_cells))
        extra_cells = _generate_hint_cells(puz, n_extra, rng_t2, exclude=t1_coords)
        # Combine + sort by (row, col) for clean display order
        combined = sorted(t1_cells + extra_cells, key=lambda x: (x[0], x[1]))
        tier2[puz["id"]] = combined

    return tier1, tier2


def _format_hint_line(puzzle_id: int, hints: list[tuple[int, int, int]]) -> str:
    """Compact format: '#001:  R3C4=7   R5C2=3   R7C8=9   R1C5=2   R8C1=6'"""
    cells = "   ".join(f"R{r+1}C{c+1}={v}" for r, c, v in hints)
    return f"#{puzzle_id:03d}:   {cells}"


def build_hints_master_divider(c: canvas.Canvas) -> None:
    """Top-level divider explaining the 3-tier hint system."""
    c.setFont("Times-Bold", 50)
    c.drawCentredString(PAGE_W / 2, PAGE_H * 0.78, "Stuck?")
    c.setFont("Times-Italic", 22)
    c.drawCentredString(PAGE_W / 2, PAGE_H * 0.71, "A 3-Tier Hint System")

    c.setLineWidth(0.7)
    c.line(2.5 * inch, PAGE_H * 0.66, PAGE_W - 2.5 * inch, PAGE_H * 0.66)

    c.setFont("Times-Roman", 13)
    intro = [
        "Every puzzle in this book is solvable by pure logic, with no",
        "guessing required. But sometimes the next move is hiding in",
        "plain sight, and a small nudge is all you need.",
        "",
        "We provide three progressive levels of help so you can",
        "choose how much you want revealed:",
    ]
    y = PAGE_H * 0.60
    for line in intro:
        c.drawCentredString(PAGE_W / 2, y, line)
        y -= 17

    # Tier blurbs
    tiers = [
        ("Tier 1 — Five Extra Clues",
         "Five additional cells revealed. Just enough to break a logjam."),
        ("Tier 2 — Ten Extra Clues",
         "Twice the help. Use this when Tier 1 still leaves you stuck."),
        ("Tier 3 — Full Solution",
         "The complete grid. For verification when you have finished."),
    ]
    y -= 12
    for label, blurb in tiers:
        c.setFont("Times-Bold", 14)
        c.drawCentredString(PAGE_W / 2, y, label)
        y -= 18
        c.setFont("Times-Italic", 12)
        c.drawCentredString(PAGE_W / 2, y, blurb)
        y -= 28

    c.setFont("Times-Italic", 11)
    c.drawCentredString(
        PAGE_W / 2, 0.7 * inch,
        "Each hint references a cell as RxCy (Row x, Column y).",
    )
    c.showPage()


def build_hint_tier_divider(
    c: canvas.Canvas,
    tier_label: str,
    n_clues: int,
    blurb: str,
) -> None:
    """Section divider for a single hint tier."""
    c.setFont("Times-Bold", 48)
    c.drawCentredString(PAGE_W / 2, PAGE_H * 0.62, tier_label)
    c.setFont("Times-Italic", 18)
    c.drawCentredString(PAGE_W / 2, PAGE_H * 0.55, f"{n_clues} extra clues per puzzle")
    c.setFont("Times-Roman", 22)
    c.drawCentredString(PAGE_W / 2, PAGE_H * 0.49, "❦")
    c.setFont("Times-Italic", 13)
    _draw_wrapped(
        c, blurb, PAGE_W / 2, PAGE_H * 0.42,
        max_width=PAGE_W - 2.5 * inch,
        font="Times-Italic", size=13, leading=20,
    )
    c.showPage()


HINT_SLOTS_PER_PAGE = 38  # constant — both rendering & TOC math use this


def _hint_items(puzzles: list[dict]) -> list[dict]:
    """Build the ordered list of items to render in a hint section.

    Section headers are inserted between difficulty groups so the reader sees
    "── Warm-Up Puzzles (6×6) ──" before the warmup hint lines, etc.
    """
    DIFF_ORDER = ["warmup", "easy", "medium", "hard", "expert"]
    DIFF_LABEL_HINTS = {
        "warmup": "Warm-Up Puzzles  (6×6)",
        "easy":   "Easy Puzzles",
        "medium": "Medium Puzzles",
        "hard":   "Hard Puzzles",
        "expert": "Expert Puzzles",
    }
    by_diff: dict[str, list[dict]] = {d: [] for d in DIFF_ORDER}
    for puz in puzzles:
        by_diff.setdefault(puz.get("difficulty", "medium"), []).append(puz)

    items: list[dict] = []
    for d in DIFF_ORDER:
        group = by_diff.get(d, [])
        if not group:
            continue
        items.append({
            "type": "section",
            "label": DIFF_LABEL_HINTS[d],
            "count": len(group),
            "difficulty": d,
        })
        for puz in group:
            items.append({"type": "puzzle", "puzzle": puz})
    return items


def _slot_cost(item: dict) -> int:
    return 2 if item["type"] == "section" else 1


def count_hint_pages(puzzles: list[dict]) -> int:
    """Mirror the page-break logic of build_hint_pages WITHOUT rendering.

    Uses identical slot accounting so TOC entries built upfront stay
    accurate. A section header must always be followed by at least one
    puzzle line on the same page (no orphaned headers).
    """
    items = _hint_items(puzzles)
    n_pages = 0
    i = 0
    while i < len(items):
        n_pages += 1
        slots = 0
        while i < len(items):
            cost = _slot_cost(items[i])
            if slots + cost > HINT_SLOTS_PER_PAGE:
                break
            # Don't leave a section header as the last thing on a page
            if (items[i]["type"] == "section"
                    and slots + cost + 1 > HINT_SLOTS_PER_PAGE):
                break
            slots += cost
            i += 1
    return n_pages


def _format_hint_cells(hints: list[tuple[int, int, int]]) -> str:
    """Compact monospace formatting: 'R1C2=3  R3C7=9  R5C5=4'."""
    return "  ".join(f"R{r+1}C{c+1}={v}" for r, c, v in hints)


def build_hint_pages(
    c: canvas.Canvas,
    puzzles: list[dict],
    hints_by_id: dict[int, list[tuple[int, int, int]]],
    tier_label: str,
    tier_subtext: str,
    starting_page_num: int,
) -> int:
    """Render hint pages with section sub-headers and per-puzzle compact lines.

    `hints_by_id` is pre-computed by `compute_tier_hints` so Tier 2 can be
    cumulative on top of Tier 1 (same cells reappear in Tier 2 + extras).

    Mirrors `count_hint_pages` slot accounting exactly so TOC math is precise.
    """
    items = _hint_items(puzzles)
    line_h = 13.0      # 9pt Courier with 1.4× leading
    section_h = 26.0   # section header takes 2 slots' worth of vertical space
    body_top = PAGE_H - 1.0 * inch
    body_left = 0.55 * inch

    page_num = starting_page_num
    i = 0
    while i < len(items):
        # ---- Page header ----
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(PAGE_W / 2, PAGE_H - 0.50 * inch, tier_label)
        c.setFont("Helvetica-Oblique", 10)
        c.drawCentredString(PAGE_W / 2, PAGE_H - 0.72 * inch, tier_subtext)
        # Decorative thin rule under header
        c.setLineWidth(0.4)
        c.line(2.0 * inch, PAGE_H - 0.82 * inch, PAGE_W - 2.0 * inch, PAGE_H - 0.82 * inch)

        # ---- Body ----
        y = body_top - 0.20 * inch
        slots = 0
        while i < len(items):
            cost = _slot_cost(items[i])
            if slots + cost > HINT_SLOTS_PER_PAGE:
                break
            if (items[i]["type"] == "section"
                    and slots + cost + 1 > HINT_SLOTS_PER_PAGE):
                break

            it = items[i]
            if it["type"] == "section":
                # Section sub-header  "──  Easy Puzzles  ──    (60 puzzles)"
                c.setFont("Helvetica-Bold", 11)
                label = f"──  {it['label']}  ──"
                c.drawString(body_left, y, label)
                w = c.stringWidth(label, "Helvetica-Bold", 11)
                c.setFont("Helvetica-Oblique", 9)
                c.drawString(body_left + w + 6, y, f"({it['count']} puzzles)")
                y -= section_h
                slots += 2
            else:
                puz = it["puzzle"]
                gs = puz.get("grid_size", 9)
                hints = hints_by_id.get(puz["id"], [])
                marker = "" if gs == 9 else " (6×6)"
                cells_str = _format_hint_cells(hints)
                line = f"#{puz['id']:03d}{marker}:   {cells_str}"
                c.setFont("Courier", 9)
                c.drawString(body_left, y, line)
                y -= line_h
                slots += 1

            i += 1

        # ---- Page number ----
        c.setFont("Helvetica", 9)
        c.drawCentredString(PAGE_W / 2, 0.45 * inch, str(page_num))
        c.showPage()
        page_num += 1

    return page_num


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

        # Label above grid (mark warm-up entries so readers can locate them)
        gs, br, bc = _grid_dims(puz)
        label = f"#{puz['id']:03d}" + ("  (6×6)" if gs == 6 else "")
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(
            gx + grid_size / 2, gy + grid_size + 0.10 * inch, label,
        )
        # Cell font scales by grid: 6×6 cells are bigger so digits can be larger
        clue_pt = (grid_size / gs) * 0.45
        draw_sudoku_grid(
            c, gx, gy, grid_size, puz["solution"],
            grid_size=gs, box_rows=br, box_cols=bc,
            clue_font="Helvetica",
            clue_font_size=clue_pt,
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

    # ---- Group puzzles by difficulty (preserves generator order) ----
    DIFF_ORDER = ["warmup", "easy", "medium", "hard", "expert"]
    DIFF_LABEL = {
        "warmup": "Warm-Up Puzzles (6×6)",
        "easy":   "Easy Puzzles",
        "medium": "Medium Puzzles",
        "hard":   "Hard Puzzles",
        "expert": "Expert Puzzles",
    }
    DIFF_BLURB = {
        "warmup": "A gentle introduction on smaller 6×6 grids. Use these to ease into the rhythm of logical solving.",
        "easy":   "Most cells reveal themselves with a single, calm pass. Take your time and enjoy.",
        "medium": "A pleasant challenge. You will need to look twice and follow the clues a step further.",
        "hard":   "Now we think carefully. Patience and a sharp pencil are your best friends.",
        "expert": "The deepest puzzles in this book. Take your time — the answer is always reachable by logic.",
    }
    DEFAULT_LAYOUT = {"warmup": 4, "easy": 1, "medium": 2, "hard": 4, "expert": 4}
    layout_map: dict[str, int] = {**DEFAULT_LAYOUT, **plan.get("layout_per_difficulty", {})}

    by_diff: dict[str, list[dict]] = {d: [] for d in DIFF_ORDER}
    for puz in puzzles:
        d = puz.get("difficulty", "medium")
        by_diff.setdefault(d, []).append(puz)
    sections = [(d, by_diff[d]) for d in DIFF_ORDER if by_diff.get(d)]

    n_puzzles = len(puzzles)
    n_section_dividers = len(sections)

    # Pages per puzzle section (depends on layout: 1/2/4 puzzles per page)
    section_pages: dict[str, int] = {}
    for d, group in sections:
        per_page = layout_map.get(d, 1)
        section_pages[d] = (len(group) + per_page - 1) // per_page
    n_puzzle_body_pages = sum(section_pages.values())

    # Hint section: 1 master divider + 2 tier dividers + tier1 + tier2 hint pages
    n_hint_t1_pages = (n_puzzles + HINT_LINES_PER_PAGE - 1) // HINT_LINES_PER_PAGE
    n_hint_t2_pages = n_hint_t1_pages
    n_hint_total = 1 + 1 + n_hint_t1_pages + 1 + n_hint_t2_pages

    # Solutions: 1 divider + ceil(N/6) at 6 grids/page  (Tier 3 of hint system)
    n_sol_pages = (n_puzzles + 5) // 6

    # Front matter: title + bookplate + copyright + howto×2 + TOC = 6 pages
    front_pages = 6
    core_pages = (
        front_pages
        + n_section_dividers + n_puzzle_body_pages
        + n_hint_total
        + 1 + n_sol_pages
        + 1   # thank-you
    )
    pad_blank = 1 if core_pages % 2 != 0 else 0
    total_pages = core_pages + pad_blank

    # ---- First pass: compute absolute page numbers for TOC entries ----
    toc_entries: list[dict] = []
    page_cursor = front_pages + 1  # first page after front matter
    for d, group in sections:
        per_page = layout_map.get(d, 1)
        divider_page = page_cursor
        body_start = divider_page + 1
        body_end = body_start + section_pages[d] - 1
        toc_entries.append({
            "label": DIFF_LABEL[d],
            "page_str": f"{divider_page}",
            "subtitle": f"{len(group)} puzzles · {per_page}/page · pages {body_start}–{body_end}",
        })
        page_cursor = body_end + 1

    hints_master_page = page_cursor
    toc_entries.append({
        "label": "Stuck?  Hint System (3 Tiers)",
        "page_str": f"{hints_master_page}",
        "subtitle": "5 extra clues  ·  10 extra clues  ·  full solutions",
    })
    page_cursor += 1                          # master divider
    page_cursor += 1 + n_hint_t1_pages         # Tier 1 divider + body
    page_cursor += 1 + n_hint_t2_pages         # Tier 2 divider + body

    solutions_divider_page = page_cursor
    sol_first = solutions_divider_page + 1
    sol_last = solutions_divider_page + n_sol_pages
    toc_entries.append({
        "label": "Tier 3 — Full Solutions",
        "page_str": f"{solutions_divider_page}",
        "subtitle": f"{n_puzzles} solutions · pages {sol_first}–{sol_last}",
    })

    # ---- Second pass: emit pages ----
    page_num = 1
    build_title_page(c, meta); page_num += 1
    build_bookplate_page(c); page_num += 1
    build_copyright_page(c, meta); page_num += 1
    build_howto_page_1(c); page_num += 1
    build_howto_page_2(c); page_num += 1
    build_toc_page(c, toc_entries); page_num += 1

    # Puzzle sections — dispatch by per-difficulty layout
    for d, group in sections:
        per_page = layout_map.get(d, 1)
        build_section_divider(c, DIFF_LABEL[d], len(group), DIFF_BLURB[d])
        page_num += 1
        for i in range(0, len(group), per_page):
            chunk = group[i:i + per_page]
            if per_page == 1:
                build_puzzle_page_1up(c, chunk[0], page_num)
            elif per_page == 2:
                build_puzzle_page_2up(c, chunk, page_num)
            else:  # 4-up (and any larger spec falls back here)
                build_puzzle_page_4up(c, chunk, page_num)
            page_num += 1

    # Hint section (Tier 1 + Tier 2). Seed RNG from plan so hints are reproducible.
    hint_seed = plan.get("seed", 42)
    rng_t1 = random.Random((hint_seed << 1) ^ 0xA5A5)
    rng_t2 = random.Random((hint_seed << 1) ^ 0x5A5A)

    build_hints_master_divider(c); page_num += 1

    build_hint_tier_divider(
        c, "Tier 1", 5,
        "Five extra cells revealed for each puzzle. Just enough to break a "
        "logjam without giving the answer away.",
    ); page_num += 1
    page_num = build_hint_pages(c, puzzles, 5, rng_t1, page_num)

    build_hint_tier_divider(
        c, "Tier 2", 10,
        "Ten extra cells revealed. When Tier 1 still leaves you stuck, "
        "this should put you firmly back on the path.",
    ); page_num += 1
    page_num = build_hint_pages(c, puzzles, 10, rng_t2, page_num)

    # Tier 3: Full Solutions
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
        f"   Front matter: {front_pages} · "
        f"Puzzle dividers: {n_section_dividers} · Puzzle bodies: {n_puzzle_body_pages} · "
        f"Hints (master+T1+T2 dividers + {n_hint_t1_pages}+{n_hint_t2_pages} bodies): {n_hint_total} · "
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
