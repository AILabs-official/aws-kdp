#!/usr/bin/env python3
"""Export N sample sudoku pages as PNG thumbnails for use on the back cover.

Renders the same visual layout as the interior (1 puzzle centered, large grid)
so back-cover thumbnails match what readers will actually see inside.

Output: output/{theme_key}/images/page_NNN.png  (PNG, 300 DPI, 8.5×11 layout)

Usage:
  python3 scripts/export_sudoku_samples.py --theme sudoku_golden_years --count 8
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import config  # noqa: E402

DPI = 300


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    paths_bold = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    paths_regular = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for p in (paths_bold if bold else paths_regular):
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def render_puzzle_png(puzzle: dict, page_w_in: float = 8.5, page_h_in: float = 11.0) -> Image.Image:
    w_px = int(page_w_in * DPI)
    h_px = int(page_h_in * DPI)
    img = Image.new("RGB", (w_px, h_px), "white")
    draw = ImageDraw.Draw(img)

    # Header
    header_font = _load_font(33, bold=False)
    header = f"Puzzle #{puzzle['id']:03d}   ·   {puzzle['difficulty'].upper()}"
    bbox = draw.textbbox((0, 0), header, font=header_font)
    draw.text(((w_px - (bbox[2] - bbox[0])) // 2, int(0.5 * DPI)), header, fill="black", font=header_font)

    # Grid — 6 inches, centered, slightly above middle
    grid_size = int(6.0 * DPI)
    gx = (w_px - grid_size) // 2
    gy = (h_px - grid_size) // 2 - int(0.2 * DPI)
    cell = grid_size / 9

    clue_font = _load_font(int(cell * 0.55), bold=True)

    for i in range(10):
        w = 9 if i % 3 == 0 else 3
        draw.line([(gx, gy + int(i * cell)), (gx + grid_size, gy + int(i * cell))], fill="black", width=w)
        draw.line([(gx + int(i * cell), gy), (gx + int(i * cell), gy + grid_size)], fill="black", width=w)

    for r in range(9):
        for col in range(9):
            n = puzzle["puzzle"][r][col]
            if n == 0:
                continue
            cx = gx + col * cell + cell / 2
            cy = gy + r * cell + cell / 2
            b = draw.textbbox((0, 0), str(n), font=clue_font)
            tw = b[2] - b[0]
            th = b[3] - b[1]
            draw.text((cx - tw / 2, cy - th / 2 - b[1]), str(n), fill="black", font=clue_font)

    return img


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--theme", required=True)
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument("--difficulty-order", default="easy,medium,hard",
                        help="Comma-separated preferred order for samples (first few difficulties first)")
    args = parser.parse_args()

    theme_dir = Path(config.get_book_dir(args.theme))
    puzzles = json.loads((theme_dir / "sudoku_puzzles.json").read_text())

    # Pick samples: try to include each difficulty bucket
    prefs = [d.strip() for d in args.difficulty_order.split(",")]
    pool: dict[str, list[dict]] = {}
    for p in puzzles:
        pool.setdefault(p["difficulty"], []).append(p)

    samples: list[dict] = []
    # Round-robin across preferred difficulties
    i = 0
    while len(samples) < args.count:
        d = prefs[i % len(prefs)]
        bucket = pool.get(d, [])
        if bucket:
            samples.append(bucket.pop(0))
        i += 1
        # Safety: break if all pools empty
        if i > args.count * 4 and not any(pool.values()):
            break

    images_dir = theme_dir / "images"
    images_dir.mkdir(exist_ok=True)

    for idx, puz in enumerate(samples, 1):
        out = images_dir / f"page_{idx:03d}.png"
        img = render_puzzle_png(puz)
        img.save(out, dpi=(DPI, DPI))
        print(f"  ✓ {out.name}  puzzle #{puz['id']:03d}  {puz['difficulty']}")

    print(f"✅ Exported {len(samples)} sample puzzle PNGs to {images_dir}")


if __name__ == "__main__":
    main()
