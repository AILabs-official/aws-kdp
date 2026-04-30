#!/usr/bin/env python3
"""
Generate a KDP-ready full cover (front + spine + back) for coloring books.
Uses AI33 API to generate front cover artwork, then composites with text.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time

import requests

from dotenv import load_dotenv

from PIL import Image, ImageDraw, ImageFont

import config
from image_providers import generate_image, RENDERER_CHOICES, DEFAULT_RENDERER, get_nanopic_pool

load_dotenv()

# --- Cover Dimensions ---
BLEED_INCHES = 0.125
PAPER_THICKNESS = 0.002252  # White paper, inches per page
TRIM_WIDTH = config.PAGE_WIDTH_INCHES   # default 8.5"
TRIM_HEIGHT = config.PAGE_HEIGHT_INCHES  # default 11"
SAFE_MARGIN = 0.375  # Keep important content this far from trim edge
SPINE_TEXT_CLEARANCE = 0.0625  # KDP requires 0.0625" clearance on each side of spine text
MIN_PAGES_FOR_SPINE_TEXT = 79  # KDP minimum pages to allow spine text


def calculate_cover_dimensions(total_pages: int, trim_w: float = TRIM_WIDTH, trim_h: float = TRIM_HEIGHT) -> dict:
    """Calculate full cover dimensions based on page count."""
    spine_width = total_pages * PAPER_THICKNESS

    full_width = (2 * trim_w) + spine_width + (2 * BLEED_INCHES)
    full_height = trim_h + (2 * BLEED_INCHES)

    # Use round() to avoid truncation — int() can make cover 1-2 px too small,
    # which KDP flags as insufficient bleed.
    bleed_px = round(BLEED_INCHES * config.DPI)
    trim_w_px = round(trim_w * config.DPI)
    spine_w_px = round(spine_width * config.DPI)
    safe_px = round(SAFE_MARGIN * config.DPI)

    # Derive full dimensions from components to avoid rounding mismatch
    full_width_px = 2 * bleed_px + 2 * trim_w_px + spine_w_px
    full_height_px = 2 * bleed_px + round(trim_h * config.DPI)

    return {
        "total_pages": total_pages,
        "spine_width_inches": spine_width,
        "full_width_inches": full_width,
        "full_height_inches": full_height,
        "full_width_px": full_width_px,
        "full_height_px": full_height_px,
        "bleed_px": bleed_px,
        "trim_w_px": trim_w_px,
        "spine_w_px": spine_w_px,
        "safe_px": safe_px,
        # Region x-coordinates
        "back_start_x": bleed_px,
        "spine_start_x": bleed_px + trim_w_px,
        "front_start_x": bleed_px + trim_w_px + spine_w_px,
        "can_have_spine_text": total_pages >= 79,
    }


def count_pages(theme: str) -> int:
    """Count total pages. Prefers the assembled interior.pdf (authoritative)
    and falls back to the coloring-book image-count heuristic."""
    interior_pdf = config.get_interior_pdf_path(theme)
    if os.path.exists(interior_pdf):
        try:
            from pypdf import PdfReader
            return len(PdfReader(interior_pdf).pages)
        except Exception:
            try:
                from PyPDF2 import PdfReader  # legacy fallback
                return len(PdfReader(interior_pdf).pages)
            except Exception:
                pass  # fall through to heuristic

    image_dir = config.get_images_dir(theme)
    if not os.path.exists(image_dir):
        return config.COLORING_PAGES_PER_BOOK * 2 + 3  # Estimate

    num_images = len([f for f in os.listdir(image_dir) if f.endswith(".png")])
    if num_images == 0:
        num_images = config.COLORING_PAGES_PER_BOOK

    total = 2 + (num_images * 2) + 1  # title + copyright + pages*2 + thankyou
    if total % 2 != 0:
        total += 1
    return total


def generate_front_artwork(theme: str, title: str = "", author: str = "", renderer: str = DEFAULT_RENDERER, size: str = config.DEFAULT_PAGE_SIZE) -> Image.Image | None:
    """Generate front cover artwork using the selected renderer."""
    theme_config = config.THEMES[theme]

    # Build author text instruction
    author_instruction = ""
    if author:
        author_instruction = f' Above the title, include the author name "{author}" in a smaller, elegant font as part of the design.'

    # Try to load cover_prompt from book metadata
    plan = config.load_bookinfo(theme) or {}
    cover_prompt_from_plan = plan.get("cover_prompt")

    if cover_prompt_from_plan:
        prompt = cover_prompt_from_plan
        prompt = prompt.replace("DO NOT include any text, letters, or words in the generated image.", "")
        prompt += f'\n\nIMPORTANT: Include the book title "{title}" as beautiful, large, decorative text integrated into the artwork at the top of the image. The title text should be stylish, readable, and part of the cover design.{author_instruction} Do NOT include any placeholder text, subtitle text, or extra text besides the title and author name.'
    else:
        theme_subjects = {
            "cute_animals": "a cute cat, puppy, and bunny playing together in a colorful flower garden with butterflies",
            "dinosaurs": "a friendly T-Rex, Triceratops, and baby Pterodactyl in a vibrant prehistoric jungle with volcano",
            "vehicles": "a bright red fire truck, rocket ship, and yellow airplane flying over a cheerful city",
            "unicorn_fantasy": "a magical unicorn with rainbow mane, a fairy with sparkly wings, and a baby dragon in an enchanted garden",
        }
        subject = theme_subjects.get(theme, "cute cartoon characters for children")
        prompt = f"""Create a colorful, vibrant book cover illustration for a coloring book.
Theme: {theme_config['name']}
Title: {title}
Style: Bright, cheerful, eye-catching, cartoon style, professional book cover art.
The image should feature {subject}.
IMPORTANT: Include the book title "{title}" as beautiful, large, decorative text integrated into the artwork at the top. The title should be stylish, readable, and part of the cover design.{author_instruction} Do NOT include any placeholder text, subtitle text, or extra text besides the title and author name.
The artwork should be high quality, detailed, and appealing.
Use a clean, attractive background with vibrant colors."""

    print(f"Generating front cover artwork (renderer: {renderer})...")
    ar_key = "bimai_aspect_ratio" if renderer == "bimai" else "ai33_aspect_ratio"
    ar = config.PAGE_SIZES[size][ar_key]
    return generate_image(prompt, renderer=renderer, aspect_ratio=ar)


def colorize_page(image_path: str, renderer: str = DEFAULT_RENDERER) -> Image.Image | None:
    """Colorize a line art coloring page using NanoPic image-to-image (sends original image as base64)."""
    import base64

    basename = os.path.basename(image_path)

    try:
        api_key = os.getenv("NANOPIC_API_KEY")
        pool = get_nanopic_pool()
        if not api_key or pool.size == 0:
            print(f"  Warning: NANOPIC keys not found, skipping colorize for {basename}")
            return None

        # Read original image and convert to base64
        with open(image_path, "rb") as f:
            image_data = f.read()
        b64_image = f"data:image/png;base64,{base64.b64encode(image_data).decode()}"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        prompt = (
            "Colorize this black and white coloring page with vibrant, cheerful colors. "
            "Fill all white areas with appropriate solid colors. Keep the black outlines intact. "
            "Use a warm, inviting color palette. Make it look professionally colored."
        )

        print(f"  Colorizing {basename} via NanoPic image-to-image...")

        for attempt in range(config.MAX_RETRIES):
            access_token = pool.next()
            try:
                payload = {
                    "accessToken": access_token,
                    "promptText": prompt,
                    "imageUrls": [b64_image],
                    "aspectRatio": "IMAGE_ASPECT_RATIO_SQUARE",
                    "imageModel": config.NANOPIC_MODEL,
                }
                resp = requests.post(config.NANOPIC_API_URL, headers=headers, json=payload)
                resp.raise_for_status()
                result = resp.json()

                if not result.get("success"):
                    print(f"  NanoPic colorize submit failed (attempt {attempt + 1}): {result}")
                    continue

                task_id = result.get("taskId") or result.get("data", {}).get("taskId")
                if not task_id:
                    for key in result:
                        if "task" in key.lower() and isinstance(result[key], str):
                            task_id = result[key]
                            break
                if not task_id:
                    print(f"  NanoPic colorize: no taskId in response")
                    continue

                print(f"  NanoPic colorize task: {task_id}")

                elapsed = 0
                while elapsed < config.NANOPIC_POLL_TIMEOUT:
                    time.sleep(config.NANOPIC_POLL_INTERVAL)
                    elapsed += config.NANOPIC_POLL_INTERVAL

                    status_resp = requests.get(
                        f"{config.NANOPIC_STATUS_URL}?taskId={task_id}",
                        headers=headers,
                    )
                    status_resp.raise_for_status()
                    status = status_resp.json()
                    code = status.get("code", "")
                    data = status.get("data") or {}

                    if code == "success" and data.get("fifeUrl"):
                        img_resp = requests.get(data["fifeUrl"])
                        img_resp.raise_for_status()
                        img = Image.open(io.BytesIO(img_resp.content)).convert("RGB")
                        print(f"  Colorized successfully: {basename}")
                        return img

                    if code in ("error", "failed", "fail"):
                        error_msg = status.get("message", "Unknown error")
                        detail = data.get("error") or {}
                        if detail:
                            error_msg = f"{error_msg} ({detail.get('status', '')}: {detail.get('message', '')})"
                        print(f"  NanoPic colorize error: {error_msg}")
                        break

                    if elapsed % 15 == 0:
                        print(f"  Polling... status={code or 'pending'}")

                if elapsed >= config.NANOPIC_POLL_TIMEOUT:
                    print(f"  Timeout waiting for NanoPic colorize task {task_id}")

            except Exception as e:
                print(f"  Colorize error (attempt {attempt + 1}/{config.MAX_RETRIES}): {e}")
                if attempt < config.MAX_RETRIES - 1:
                    time.sleep(config.REQUEST_DELAY_SECONDS)

        return None
    except Exception as e:
        print(f"  Warning: Colorize failed for {basename}: {e}")
        return None


def get_sample_pages(theme: str, count: int = 6) -> list[str]:
    """Select evenly spaced sample pages from the theme.

    Returns [] when the theme has no images/ directory (e.g. sudoku/puzzle
    books rendered straight to PDF), which signals `build_cover()` to skip
    the back-cover sample-pages grid.
    """
    image_dir = config.get_images_dir(theme)
    if not os.path.exists(image_dir):
        return []
    pages = sorted([
        os.path.join(image_dir, f)
        for f in os.listdir(image_dir)
        if f.endswith(".png")
    ])
    return pages[:count]


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Get a font, falling back to default if custom fonts unavailable."""
    # Try common system fonts on macOS
    font_paths = []
    if bold:
        font_paths = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
    else:
        font_paths = [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]

    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue

    return ImageFont.load_default()


def draw_text_with_outline(
    draw: ImageDraw.ImageDraw,
    position: tuple,
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: str = "white",
    outline_color: str = "black",
    outline_width: int = 3,
):
    """Draw text with outline for readability on any background."""
    x, y = position
    # Draw outline
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx * dx + dy * dy <= outline_width * outline_width:
                draw.text((x + dx, y + dy), text, font=font, fill=outline_color)
    # Draw main text
    draw.text(position, text, font=font, fill=fill)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    s = hex_color.lstrip("#")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def _draw_sudoku_grid_pil(
    cover: Image.Image,
    x: int,
    y: int,
    size_px: int,
    clues: list[list[int]],
    thick_px: int = 4,
    thin_px: int = 1,
    bg: tuple = (255, 255, 255),
    line: tuple = (20, 20, 20),
    ink: tuple = (20, 20, 20),
) -> None:
    """Draw a 9x9 sudoku grid onto `cover` at (x, y) with width=size_px."""
    cell = size_px / 9
    d = ImageDraw.Draw(cover)
    d.rectangle([x, y, x + size_px, y + size_px], fill=bg)
    for i in range(10):
        w = thick_px if i % 3 == 0 else thin_px
        # horizontal
        d.line([(x, y + round(i * cell)), (x + size_px, y + round(i * cell))], fill=line, width=w)
        # vertical
        d.line([(x + round(i * cell), y), (x + round(i * cell), y + size_px)], fill=line, width=w)
    font_size = max(10, int(cell * 0.55))
    font = get_font(font_size, bold=True)
    for r in range(9):
        for c in range(9):
            n = clues[r][c]
            if not n:
                continue
            cx = x + round(c * cell + cell / 2)
            cy = y + round(r * cell + cell / 2)
            bbox = d.textbbox((0, 0), str(n), font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            d.text((cx - tw // 2 - bbox[0], cy - th // 2 - bbox[1]), str(n), fill=ink, font=font)


def _shift_color(rgb: tuple[int, int, int], delta: int) -> tuple[int, int, int]:
    """Lighten (delta>0) or darken (delta<0) an RGB color, clipped to [0,255]."""
    return tuple(max(0, min(255, c + delta)) for c in rgb)


def _is_light(rgb: tuple[int, int, int]) -> bool:
    """Rough perceived-luminance check. True for pale backgrounds."""
    r, g, b = rgb
    return (0.299 * r + 0.587 * g + 0.114 * b) > 160


_DIFF_LABEL_OVERRIDES = {
    "warmup": "WARM-UP",
    "warm-up": "WARM-UP",
    "warm_up": "WARM-UP",
}


def _render_sudoku_back_and_spine(
    cover: Image.Image,
    dims: dict,
    plan: dict,
    author: str,
    puzzles_path: str,
) -> None:
    """Paint the back cover + spine for a sudoku book.

    Plan-driven: every text block, the puzzle count, the palette, and the sample
    difficulties come from plan.json so the back stays consistent with the front
    and reflects the book's actual contents (no hardcoded "240 PUZZLES").
    """
    # --- Derive puzzle count from plan ---
    diff_dist = plan.get("difficulty_distribution", {}) or {}
    puzzle_count = (
        plan.get("puzzle_count")
        or (sum(diff_dist.values()) if diff_dist else 0)
        or 0
    )

    # --- Palette: prefer new semantic keys, fall back to legacy navy/gold ---
    palette = plan.get("cover_palette", {}) or {}
    legacy_dominant = palette.get("dominant", "#1B3A5C")
    legacy_accent = palette.get("accent_primary", "#D4A857")
    legacy_secondary = palette.get("accent_secondary", "#F7F1E3")

    bg = _hex_to_rgb(palette.get("back_bg", legacy_dominant))
    light_bg = _is_light(bg)
    # On a dark navy-style bg the ink defaults to white; on a cream bg it
    # defaults to deep navy so text stays legible.
    default_ink = "#FFFFFF" if not light_bg else legacy_dominant
    ink = _hex_to_rgb(palette.get("back_ink", default_ink))
    accent = _hex_to_rgb(palette.get("back_accent", legacy_accent))
    panel_bg = _hex_to_rgb(palette.get("back_panel_bg", legacy_secondary))
    panel_ink = _hex_to_rgb(palette.get("back_panel_ink", legacy_dominant))
    pill_left_bg_default = "#C82832" if not light_bg else legacy_dominant
    pill_left_bg = _hex_to_rgb(palette.get("back_pill_left_bg", pill_left_bg_default))
    pill_left_ink = _hex_to_rgb(palette.get("back_pill_left_ink", "#FFFFFF"))
    pill_right_bg = _hex_to_rgb(palette.get("back_pill_right_bg", legacy_accent))
    pill_right_ink = _hex_to_rgb(palette.get("back_pill_right_ink", legacy_dominant))

    grid_bg = _hex_to_rgb(palette.get("back_grid_bg", "#FFFFFF"))
    grid_line = _hex_to_rgb(palette.get("back_grid_line", "#202020"))
    grid_ink = _hex_to_rgb(palette.get("back_grid_ink", legacy_dominant))

    spine_bg = _hex_to_rgb(palette.get("spine_bg", palette.get("back_bg", legacy_dominant)))
    spine_ink = _hex_to_rgb(
        palette.get("spine_ink", palette.get("back_accent", legacy_accent))
    )

    watermark = _shift_color(bg, -10 if light_bg else 14)

    d = ImageDraw.Draw(cover)
    H = dims["full_height_px"]
    bleed = dims["bleed_px"]
    back_x0, back_x1 = 0, dims["spine_start_x"]
    spine_x0, spine_x1 = dims["spine_start_x"], dims["front_start_x"]

    # --- Background fill for back + spine (full bleed) ---
    d.rectangle([back_x0, 0, spine_x1, H], fill=bg)

    # --- Subtle sudoku-grid watermark across back ---
    wm_cell = int(0.42 * config.DPI)
    for gx in range(bleed - wm_cell, back_x1 + wm_cell, wm_cell):
        d.line([(gx, 0), (gx, H)], fill=watermark, width=1)
    for gy in range(bleed - wm_cell, H + wm_cell, wm_cell):
        d.line([(back_x0, gy), (back_x1, gy)], fill=watermark, width=1)

    safe = dims["safe_px"]
    content_left = bleed + safe
    content_right = back_x1 - safe
    content_w = content_right - content_left

    # --- Top: two pill badges (left + right), text from plan ---
    top_y = bleed + int(0.35 * config.DPI)
    pill_h = int(0.55 * config.DPI)
    pill_font = get_font(int(0.22 * config.DPI), bold=True)

    pill_left_text = plan.get("back_pill_left", "GIFT EDITION")
    bb = d.textbbox((0, 0), pill_left_text, font=pill_font)
    pl_w = (bb[2] - bb[0]) + int(0.7 * config.DPI)
    d.rounded_rectangle(
        [content_left, top_y, content_left + pl_w, top_y + pill_h],
        radius=pill_h // 2, fill=pill_left_bg,
    )
    d.text(
        (content_left + (pl_w - (bb[2] - bb[0])) // 2 - bb[0],
         top_y + (pill_h - (bb[3] - bb[1])) // 2 - bb[1]),
        pill_left_text, fill=pill_left_ink, font=pill_font,
    )

    pill_right_text = plan.get(
        "back_pill_right",
        f"{puzzle_count} PUZZLES" if puzzle_count else "BIG PRINT",
    )
    bb = d.textbbox((0, 0), pill_right_text, font=pill_font)
    pr_w = (bb[2] - bb[0]) + int(0.7 * config.DPI)
    d.rounded_rectangle(
        [content_right - pr_w, top_y, content_right, top_y + pill_h],
        radius=pill_h // 2, fill=pill_right_bg,
    )
    d.text(
        (content_right - pr_w + (pr_w - (bb[2] - bb[0])) // 2 - bb[0],
         top_y + (pill_h - (bb[3] - bb[1])) // 2 - bb[1]),
        pill_right_text, fill=pill_right_ink, font=pill_font,
    )

    # --- Headline + subheadlines (plan-driven) ---
    headline = plan.get("back_headline") or "BRAIN-FRIENDLY SUDOKU"

    # Accept either back_subheadline (string) or back_subheadlines (list of lines)
    sub_lines = plan.get("back_subheadlines")
    if not sub_lines:
        legacy_sub = plan.get("back_subheadline")
        if legacy_sub:
            sub_lines = [legacy_sub]
        elif puzzle_count:
            sub_lines = [
                f"{puzzle_count} hand-verified large-print puzzles,",
                "one thoughtful page at a time.",
            ]
        else:
            sub_lines = ["Hand-verified puzzles in comfortable large print."]

    headline_font = get_font(int(0.42 * config.DPI), bold=True)
    sub_font = get_font(int(0.26 * config.DPI), bold=False)

    hl_y = top_y + pill_h + int(0.45 * config.DPI)
    bb = d.textbbox((0, 0), headline, font=headline_font)
    while bb[2] - bb[0] > content_w and headline_font.size > 40:
        headline_font = get_font(headline_font.size - 4, bold=True)
        bb = d.textbbox((0, 0), headline, font=headline_font)
    d.text(
        (content_left + (content_w - (bb[2] - bb[0])) // 2 - bb[0], hl_y),
        headline, fill=ink, font=headline_font,
    )

    cur_y = hl_y + (bb[3] - bb[1]) + int(0.15 * config.DPI)
    last_h = 0
    for line in sub_lines:
        bb_line = d.textbbox((0, 0), line, font=sub_font)
        d.text(
            (content_left + (content_w - (bb_line[2] - bb_line[0])) // 2 - bb_line[0], cur_y),
            line, fill=accent, font=sub_font,
        )
        last_h = bb_line[3] - bb_line[1]
        cur_y += last_h + int(0.06 * config.DPI)
    sub_block_end = cur_y - int(0.06 * config.DPI)

    # --- Description panel (bullets) ---
    panel_y0 = sub_block_end + int(0.45 * config.DPI)
    panel_h = int(2.4 * config.DPI)
    d.rounded_rectangle(
        [content_left, panel_y0, content_right, panel_y0 + panel_h],
        radius=int(0.12 * config.DPI), fill=panel_bg,
    )

    # Bullets: prefer explicit back_bullets, then plan["usps"], then derive from puzzle_count
    bullets = plan.get("back_bullets") or plan.get("usps")
    if not bullets:
        diff_summary_parts = []
        for k, v in diff_dist.items():
            if not v:
                continue
            diff_summary_parts.append(f"{v} {k}")
        diff_summary = " · ".join(diff_summary_parts)
        bullets = [
            (f"{puzzle_count} hand-verified puzzles" + (f"  ({diff_summary})" if diff_summary else ""))
            if puzzle_count else "Hand-verified puzzles, fully solvable",
            "Large print · one puzzle per page · easy on the eyes",
            "Every grid has exactly one solution",
            "Complete answer key included at the back",
            "A calm, giftable edition for relaxing brain training",
        ]
    bullets = list(bullets)[:5]

    bullet_font = get_font(int(0.21 * config.DPI), bold=False)
    by = panel_y0 + int(0.35 * config.DPI)
    line_gap = int(0.44 * config.DPI)
    for b in bullets:
        dot_r = int(0.08 * config.DPI)
        d.ellipse(
            [content_left + int(0.35 * config.DPI) - dot_r,
             by + int(0.12 * config.DPI) - dot_r,
             content_left + int(0.35 * config.DPI) + dot_r,
             by + int(0.12 * config.DPI) + dot_r],
            fill=accent,
        )
        d.text((content_left + int(0.6 * config.DPI), by), b,
               fill=panel_ink, font=bullet_font)
        by += line_gap

    # --- Sample grids row (plan-driven sample difficulties) ---
    sample_diffs = plan.get("back_sample_difficulties") or ["easy", "medium", "hard"]
    samples_by_diff: dict = {}
    try:
        with open(puzzles_path) as f:
            puzzles = json.load(f)
        for diff in sample_diffs:
            for p in puzzles:
                grid = p.get("puzzle")
                # Only 9x9 grids fit the back-cover sample renderer
                if (
                    p.get("difficulty") == diff
                    and grid
                    and len(grid) == 9
                    and len(grid[0]) == 9
                ):
                    samples_by_diff[diff] = grid
                    break
    except Exception as e:
        print(f"  Warning: could not load sudoku puzzles for back cover: {e}")

    grid_top = panel_y0 + panel_h + int(0.45 * config.DPI)
    grid_size = int(1.55 * config.DPI)
    label_h = int(0.35 * config.DPI)
    slot_w = content_w // max(1, len(sample_diffs))
    label_font = get_font(int(0.20 * config.DPI), bold=True)

    for i, diff in enumerate(sample_diffs):
        slot_x0 = content_left + i * slot_w
        gx = slot_x0 + (slot_w - grid_size) // 2
        gy = grid_top + label_h

        label_text = _DIFF_LABEL_OVERRIDES.get(diff.lower(), diff.upper())
        bb = d.textbbox((0, 0), label_text, font=label_font)
        d.text(
            (slot_x0 + (slot_w - (bb[2] - bb[0])) // 2 - bb[0], grid_top),
            label_text, fill=accent, font=label_font,
        )

        clues = samples_by_diff.get(diff)
        if clues:
            _draw_sudoku_grid_pil(
                cover, gx, gy, grid_size, clues,
                thick_px=4, thin_px=1,
                bg=grid_bg, line=grid_line, ink=grid_ink,
            )

    # --- Author / imprint credit, sitting ABOVE the KDP barcode placeholder ---
    # The barcode (drawn later in build_cover) is bleed+safe+1.2" from the
    # bottom-right of the back. Anchor the credit above that band so it
    # never gets clipped by the barcode rectangle.
    credit_text = (plan.get("imprint") or author or "").upper()
    if credit_text:
        author_font = get_font(int(0.22 * config.DPI), bold=True)
        spaced = "  ".join(credit_text)
        bb = d.textbbox((0, 0), spaced, font=author_font)
        if bb[2] - bb[0] > content_w:
            spaced = " ".join(credit_text)
            bb = d.textbbox((0, 0), spaced, font=author_font)
        if bb[2] - bb[0] > content_w:
            spaced = credit_text
            bb = d.textbbox((0, 0), spaced, font=author_font)
        while bb[2] - bb[0] > content_w and author_font.size > 24:
            author_font = get_font(author_font.size - 2, bold=True)
            bb = d.textbbox((0, 0), spaced, font=author_font)

        barcode_h = int(1.2 * config.DPI)
        barcode_top = H - bleed - safe - barcode_h
        ay = barcode_top - int(0.35 * config.DPI) - (bb[3] - bb[1])
        d.text(
            (content_left + (content_w - (bb[2] - bb[0])) // 2 - bb[0], ay),
            spaced, fill=accent, font=author_font,
        )

    # --- Spine ---
    d.rectangle([spine_x0, 0, spine_x1, H], fill=spine_bg)
    if dims.get("can_have_spine_text") and dims["spine_w_px"] >= int(0.125 * config.DPI):
        spine_title = plan.get("spine_title") or plan.get("title", "").upper()
        if spine_title:
            spine_len = H - 2 * bleed - 2 * int(SPINE_TEXT_CLEARANCE * config.DPI)
            spine_font = get_font(max(14, int(dims["spine_w_px"] * 0.45)), bold=True)
            bb = Image.new("L", (1, 1))
            dbb = ImageDraw.Draw(bb)
            tbb = dbb.textbbox((0, 0), spine_title, font=spine_font)
            tw, th = tbb[2] - tbb[0], tbb[3] - tbb[1]
            while tw > spine_len and spine_font.size > 10:
                spine_font = get_font(spine_font.size - 2, bold=True)
                tbb = dbb.textbbox((0, 0), spine_title, font=spine_font)
                tw, th = tbb[2] - tbb[0], tbb[3] - tbb[1]

            layer = Image.new("RGBA", (tw + 8, th + 8), (0, 0, 0, 0))
            ldraw = ImageDraw.Draw(layer)
            ldraw.text((4 - tbb[0], 4 - tbb[1]), spine_title, fill=spine_ink + (255,), font=spine_font)
            rotated = layer.rotate(90, expand=True)
            rx = spine_x0 + (dims["spine_w_px"] - rotated.size[0]) // 2
            ry = (H - rotated.size[1]) // 2
            cover.paste(rotated, (rx, ry), rotated)


# ────────────────────────────────────────────────────────────────────
# Sudoku FRONT cover (programmatic bestseller-style template)
# ────────────────────────────────────────────────────────────────────

SUDOKU_FRONT_COLOR_SCHEMES = {
    "green": {  # Image 1 / 4 style — seniors / large print
        "bg": "#1B5E3F",
        "watermark": "#216445",  # subtle delta from bg (was #2A7048)
        "title_color": "#FFFFFF",
        "year_pill_bg": "#C8202E",
        "year_pill_ink": "#FFFFFF",
        "puzzle_pill_bg": "#C8202E",
        "puzzle_pill_ink": "#FFFFFF",
        "tagline_band_bg": "#C8202E",
        "tagline_band_ink": "#FFFFFF",
        "imprint_color": "#D4A857",  # gold — matches bestseller image 5
        "label_color": "#F5C842",    # difficulty labels under fan grids
        "stars": ["#C0C0C0", "#F5C842", "#DC2828"],
    },
    "blue": {  # Image 2 style — kids / bright
        "bg": "#1E5DD8",
        "watermark": "#2462DC",  # subtle delta from bg (was #2D6FE8)
        "title_color": "#FFFFFF",
        "year_pill_bg": "#FACC15",
        "year_pill_ink": "#1A1A1A",
        "puzzle_pill_bg": "#FACC15",
        "puzzle_pill_ink": "#1A1A1A",
        "tagline_band_bg": "#FACC15",
        "tagline_band_ink": "#1A1A1A",
        "imprint_color": "#FACC15",
        "label_color": "#FACC15",
        "stars": ["#C0C0C0", "#F5C842", "#DC2828"],
    },
    "orange": {
        "bg": "#E26B2A",
        "watermark": "#E97231",  # subtle delta from bg (was #F07F3F)
        "title_color": "#FFFFFF",
        "year_pill_bg": "#1A1A1A",
        "year_pill_ink": "#F5C842",
        "puzzle_pill_bg": "#1A1A1A",
        "puzzle_pill_ink": "#F5C842",
        "tagline_band_bg": "#1A1A1A",
        "tagline_band_ink": "#F5C842",
        "imprint_color": "#FFFFFF",
        "label_color": "#FFFFFF",
        "stars": ["#C0C0C0", "#F5C842", "#DC2828"],
    },
    "purple": {
        "bg": "#5B21B6",
        "watermark": "#6228BE",  # subtle delta from bg (was #6D2DCF)
        "title_color": "#FFFFFF",
        "year_pill_bg": "#FACC15",
        "year_pill_ink": "#1A1A1A",
        "puzzle_pill_bg": "#FACC15",
        "puzzle_pill_ink": "#1A1A1A",
        "tagline_band_bg": "#FACC15",
        "tagline_band_ink": "#1A1A1A",
        "imprint_color": "#FACC15",
        "label_color": "#FACC15",
        "stars": ["#C0C0C0", "#F5C842", "#DC2828"],
    },
}


def _heavy_font(size: int) -> ImageFont.FreeTypeFont:
    """Heaviest available sans-serif — for SUDOKU hero typography."""
    paths = [
        "/System/Library/Fonts/Supplemental/Arial Black.ttf",
        "/System/Library/Fonts/Supplemental/Impact.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _derive_sudoku_spine_title(plan: dict) -> str:
    """Build a distinctive spine title from plan — strips redundant 'PUZZLE BOOK',
    appends year if not already present.

    Examples:
      title="Extra Large Print Sudoku Puzzle Book" -> "EXTRA LARGE PRINT SUDOKU  2026"
      title="Sudoku for Kids Ages 8-12"            -> "SUDOKU FOR KIDS AGES 8-12  2026"
      title="Sudoku Variety Pack"                  -> "SUDOKU VARIETY PACK  2026"

    When books sit side-by-side on a shelf, the spine must be distinctive —
    a generic "SUDOKU 2026" makes a series indistinguishable.
    """
    title = (plan.get("title") or "SUDOKU").upper()
    # Strip redundant suffixes — spine context already implies "puzzle book"
    for redundant in ("PUZZLE BOOKS", "PUZZLE BOOK", "PUZZLES BOOK"):
        if title.endswith(" " + redundant):
            title = title[: -(len(redundant) + 1)]
            break
        if " " + redundant + " " in (" " + title + " "):
            title = title.replace(redundant, "").strip()
            break
    title = " ".join(title.split())  # collapse whitespace
    year = (plan.get("front_year_text") or "").strip()
    if year and year not in title:
        title = f"{title}  {year}"
    return title


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int,
               draw_obj: ImageDraw.ImageDraw) -> list[str]:
    """Word-wrap a string into lines that fit max_width (px)."""
    words = (text or "").split()
    if not words:
        return []
    lines = []
    current = [words[0]]
    for word in words[1:]:
        test = " ".join(current + [word])
        bb = draw_obj.textbbox((0, 0), test, font=font)
        if (bb[2] - bb[0]) > max_width:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines


def _draw_star(draw_obj: ImageDraw.ImageDraw, cx: int, cy: int, r: int,
               fill: tuple, outline: tuple = None, outline_width: int = 0) -> None:
    """5-pointed star centered at (cx, cy) with outer radius r."""
    import math
    pts = []
    for i in range(10):
        angle = -math.pi / 2 + i * math.pi / 5
        radius = r if i % 2 == 0 else r * 0.4
        pts.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    if outline and outline_width > 0:
        draw_obj.polygon(pts, fill=fill, outline=outline)
    else:
        draw_obj.polygon(pts, fill=fill)


def _render_sudoku_front_cover(
    cover: Image.Image,
    dims: dict,
    plan: dict,
    puzzles_path: str,
) -> None:
    """Bestseller-style programmatic front cover for sudoku books.

    Layout (top → bottom):
      1. Year pill (top-left) + Levels/count badge (top-right, optional 3 stars)
      2. Hero "SUDOKU" massive white sans-serif (centered)
      3. Sub-line ("PUZZLE BOOK" / "FOR KIDS" / etc.)
      4. Puzzle count colored pill
      5. 3 sample sudoku grids overlapping with rotation (proof of content)
      6. Audience tagline band
      7. Tiny imprint at very bottom
    """
    DPI = config.DPI
    H = dims["full_height_px"]
    bleed = dims["bleed_px"]
    front_x0 = dims["front_start_x"]
    front_x1 = dims["full_width_px"]
    safe = dims["safe_px"]

    # Live area on front (inside trim, with safe inset)
    live_x0 = front_x0 + safe
    live_x1 = front_x0 + dims["trim_w_px"] - safe
    live_y0 = bleed + safe
    live_y1 = H - bleed - safe
    live_w = live_x1 - live_x0

    # Color scheme
    scheme_name = (plan.get("front_color_scheme") or "green").lower()
    scheme = SUDOKU_FRONT_COLOR_SCHEMES.get(scheme_name, SUDOKU_FRONT_COLOR_SCHEMES["green"])
    bg = _hex_to_rgb(scheme["bg"])
    watermark = _hex_to_rgb(scheme["watermark"])
    title_color = _hex_to_rgb(scheme["title_color"])
    year_bg = _hex_to_rgb(scheme["year_pill_bg"])
    year_ink = _hex_to_rgb(scheme["year_pill_ink"])
    puzzle_bg = _hex_to_rgb(scheme["puzzle_pill_bg"])
    puzzle_ink = _hex_to_rgb(scheme["puzzle_pill_ink"])
    tagline_bg = _hex_to_rgb(scheme["tagline_band_bg"])
    tagline_ink = _hex_to_rgb(scheme["tagline_band_ink"])
    star_colors = [_hex_to_rgb(c) for c in scheme["stars"]]
    label_color = _hex_to_rgb(scheme.get("label_color", scheme["title_color"]))

    d = ImageDraw.Draw(cover)

    # ── 1. Background fill (extends through full bleed on right + top + bottom) ──
    d.rectangle([front_x0, 0, front_x1, H], fill=bg)

    # ── 2. Watermark — scattered faded sudoku digits (subtle density) ──
    import random
    seed = int(plan.get("seed", 42)) ^ 0xBEEF
    rng = random.Random(seed)
    wm_font = _heavy_font(int(0.50 * DPI))
    for _ in range(55):
        x = rng.randint(front_x0, front_x1 - int(0.3 * DPI))
        y = rng.randint(0, H - int(0.3 * DPI))
        digit = str(rng.randint(1, 9))
        d.text((x, y), digit, font=wm_font, fill=watermark)

    # ── 3. Top zone: year pill (left) + levels badge (right) ──
    top_y = live_y0
    pill_h = int(0.62 * DPI)
    pill_font = _heavy_font(int(0.32 * DPI))

    year_text = plan.get("front_year_text", "2026")
    bb = d.textbbox((0, 0), year_text, font=pill_font)
    yp_w = (bb[2] - bb[0]) + int(0.7 * DPI)
    d.rounded_rectangle(
        [live_x0, top_y, live_x0 + yp_w, top_y + pill_h],
        radius=pill_h // 2, fill=year_bg,
    )
    d.text(
        (live_x0 + (yp_w - (bb[2] - bb[0])) // 2 - bb[0],
         top_y + (pill_h - (bb[3] - bb[1])) // 2 - bb[1]),
        year_text, fill=year_ink, font=pill_font,
    )

    levels_text = plan.get("front_levels_text", "3 LEVELS")
    levels_font = _heavy_font(int(0.30 * DPI))
    bb_lv = d.textbbox((0, 0), levels_text, font=levels_font)
    levels_w = bb_lv[2] - bb_lv[0]

    show_stars = "LEVEL" in levels_text.upper()
    star_r = int(0.18 * DPI)
    star_gap = int(0.12 * DPI)
    star_block_w = 3 * (2 * star_r) + 2 * star_gap if show_stars else 0
    text_to_stars_gap = int(0.3 * DPI) if show_stars else 0

    lv_y = top_y + (pill_h - (bb_lv[3] - bb_lv[1])) // 2 - bb_lv[1]
    full_block_w = levels_w + text_to_stars_gap + star_block_w
    block_x0 = live_x1 - full_block_w
    d.text((block_x0 - bb_lv[0], lv_y), levels_text, fill=title_color, font=levels_font)
    if show_stars:
        sx_start = block_x0 + levels_w + text_to_stars_gap + star_r
        sy = top_y + pill_h // 2
        for i, c in enumerate(star_colors):
            _draw_star(d, sx_start + i * (2 * star_r + star_gap), sy, star_r, fill=c)

    # ── 4. Hero title block: "SUDOKU" massive + sub-line ──
    full_title = (plan.get("title", "Sudoku Puzzle Book") or "").upper()
    if "SUDOKU" in full_title:
        hero_word = "SUDOKU"
        sub_words = full_title.replace("SUDOKU", "").strip()
    else:
        # Fallback — use first big word as hero
        parts = full_title.split()
        hero_word = parts[0] if parts else "SUDOKU"
        sub_words = " ".join(parts[1:]) if len(parts) > 1 else "PUZZLE BOOK"

    if not sub_words:
        sub_words = "PUZZLE BOOK"

    hero_y_start = top_y + pill_h + int(0.55 * DPI)

    # Auto-fit hero font
    hero_font_size = int(1.65 * DPI)
    hero_font = _heavy_font(hero_font_size)
    bb_h = d.textbbox((0, 0), hero_word, font=hero_font)
    while (bb_h[2] - bb_h[0]) > live_w * 0.95 and hero_font_size > 60:
        hero_font_size -= 20
        hero_font = _heavy_font(hero_font_size)
        bb_h = d.textbbox((0, 0), hero_word, font=hero_font)
    hero_w_px = bb_h[2] - bb_h[0]
    hero_h_px = bb_h[3] - bb_h[1]
    hero_x = live_x0 + (live_w - hero_w_px) // 2 - bb_h[0]
    d.text((hero_x, hero_y_start - bb_h[1]), hero_word, font=hero_font, fill=title_color)

    # Sub-line — may need wrapping if long (e.g. "FOR KIDS AGES 8-12")
    sub_y = hero_y_start + hero_h_px + int(0.05 * DPI)
    sub_font_size = int(0.80 * DPI)
    sub_font = _heavy_font(sub_font_size)
    bb_s = d.textbbox((0, 0), sub_words, font=sub_font)
    while (bb_s[2] - bb_s[0]) > live_w * 0.95 and sub_font_size > 28:
        sub_font_size -= 8
        sub_font = _heavy_font(sub_font_size)
        bb_s = d.textbbox((0, 0), sub_words, font=sub_font)
    sub_w_px = bb_s[2] - bb_s[0]
    sub_h_px = bb_s[3] - bb_s[1]
    sub_x = live_x0 + (live_w - sub_w_px) // 2 - bb_s[0]
    d.text((sub_x, sub_y - bb_s[1]), sub_words, font=sub_font, fill=title_color)

    title_block_bottom = sub_y + sub_h_px

    # ── 5. Puzzle count colored pill ──
    puzzle_count = plan.get("puzzle_count") or 0
    if puzzle_count:
        pc_text = f"{puzzle_count} PUZZLES"
        pc_font = _heavy_font(int(0.42 * DPI))
        pc_bb = d.textbbox((0, 0), pc_text, font=pc_font)
        pc_w = (pc_bb[2] - pc_bb[0]) + int(0.8 * DPI)
        pc_h = int(0.78 * DPI)
        pc_x0 = live_x0 + (live_w - pc_w) // 2
        pc_y0 = title_block_bottom + int(0.35 * DPI)
        d.rounded_rectangle(
            [pc_x0, pc_y0, pc_x0 + pc_w, pc_y0 + pc_h],
            radius=pc_h // 2, fill=puzzle_bg,
        )
        d.text(
            (pc_x0 + (pc_w - (pc_bb[2] - pc_bb[0])) // 2 - pc_bb[0],
             pc_y0 + (pc_h - (pc_bb[3] - pc_bb[1])) // 2 - pc_bb[1]),
            pc_text, fill=puzzle_ink, font=pc_font,
        )
        sample_y_start = pc_y0 + pc_h + int(0.4 * DPI)
    else:
        sample_y_start = title_block_bottom + int(0.5 * DPI)

    # ── 6. Sample sudoku grids (3 overlapping with rotation) ──
    tagline_band_h = int(0.85 * DPI)
    tagline_y0 = live_y1 - tagline_band_h - int(0.25 * DPI)
    sample_zone_y1 = tagline_y0 - int(0.3 * DPI)
    sample_zone_h = sample_zone_y1 - sample_y_start

    sample_grids = []
    try:
        with open(puzzles_path) as f:
            puzzles = json.load(f)
        seen_ids = set()
        for diff in ["easy", "medium", "hard"]:
            for p in puzzles:
                if (
                    p.get("difficulty") == diff
                    and isinstance(p.get("puzzle"), list)
                    and len(p["puzzle"]) == 9
                    and p.get("id") not in seen_ids
                ):
                    sample_grids.append((diff, p["puzzle"]))
                    seen_ids.add(p.get("id"))
                    break
        # Pad to 3 if some difficulties missing
        for p in puzzles:
            if len(sample_grids) >= 3:
                break
            if (
                isinstance(p.get("puzzle"), list)
                and len(p["puzzle"]) == 9
                and p.get("id") not in seen_ids
            ):
                sample_grids.append((p.get("difficulty", "easy"), p["puzzle"]))
                seen_ids.add(p.get("id"))
    except Exception as e:
        print(f"  Warning: could not load puzzles for front cover sample: {e}")

    if sample_grids and sample_zone_h > int(1.5 * DPI):
        # Bigger center grid (was 2.6 DPI) + reserve space for difficulty labels below
        label_h = int(0.32 * DPI)
        grid_size_px = min(int(2.95 * DPI), sample_zone_h - int(0.4 * DPI) - label_h)
        positions = []
        if len(sample_grids) >= 3:
            positions = [
                {"angle": -14, "x_off": -int(1.85 * DPI), "y_off": int(0.20 * DPI), "size": int(grid_size_px * 0.80)},
                {"angle": 0,   "x_off": 0,                "y_off": 0,                "size": grid_size_px},
                {"angle": 14,  "x_off": int(1.85 * DPI),  "y_off": int(0.20 * DPI), "size": int(grid_size_px * 0.80)},
            ]
        elif len(sample_grids) == 2:
            positions = [
                {"angle": -10, "x_off": -int(1.0 * DPI), "y_off": 0, "size": grid_size_px},
                {"angle": 10,  "x_off": int(1.0 * DPI),  "y_off": 0, "size": grid_size_px},
            ]
        else:
            positions = [{"angle": 0, "x_off": 0, "y_off": 0, "size": grid_size_px}]

        center_x = (live_x0 + live_x1) // 2
        center_y = sample_y_start + sample_zone_h // 2 - label_h // 2

        # Z-order: outer first, center on top
        if len(positions) == 3:
            order = [(0, positions[0]), (2, positions[2]), (1, positions[1])]
        else:
            order = list(enumerate(positions))

        # Track label anchor positions per grid (drawn AFTER all grids to sit on top)
        label_anchors = []  # list of (label_text, x_center, y_top)

        for idx, pos in order:
            if idx >= len(sample_grids):
                continue
            diff_label, clues = sample_grids[idx]
            sz = pos["size"]
            pad = int(0.12 * DPI)
            grid_img = Image.new("RGBA", (sz + 2 * pad, sz + 2 * pad), (0, 0, 0, 0))
            sdraw = ImageDraw.Draw(grid_img)
            # Drop shadow
            sdraw.rectangle(
                [pad + 8, pad + 8, pad + sz + 8, pad + sz + 8],
                fill=(0, 0, 0, 110),
            )
            # White grid background
            sdraw.rectangle([pad, pad, pad + sz, pad + sz], fill=(255, 255, 255, 255))
            # Grid lines
            cell = sz / 9
            for i in range(10):
                w = 5 if i % 3 == 0 else 1
                sdraw.line(
                    [(pad, pad + round(i * cell)), (pad + sz, pad + round(i * cell))],
                    fill=(20, 20, 20, 255), width=w,
                )
                sdraw.line(
                    [(pad + round(i * cell), pad), (pad + round(i * cell), pad + sz)],
                    fill=(20, 20, 20, 255), width=w,
                )
            # Numbers
            num_font = _heavy_font(max(12, int(cell * 0.55)))
            for r in range(9):
                for c in range(9):
                    n = clues[r][c]
                    if not n:
                        continue
                    cxn = pad + round(c * cell + cell / 2)
                    cyn = pad + round(r * cell + cell / 2)
                    nbb = sdraw.textbbox((0, 0), str(n), font=num_font)
                    tw = nbb[2] - nbb[0]
                    th = nbb[3] - nbb[1]
                    sdraw.text(
                        (cxn - tw // 2 - nbb[0], cyn - th // 2 - nbb[1]),
                        str(n), fill=(20, 20, 20, 255), font=num_font,
                    )
            # Rotate
            if pos["angle"] != 0:
                grid_img = grid_img.rotate(-pos["angle"], expand=True, resample=Image.BICUBIC)
            gx = center_x + pos["x_off"] - grid_img.size[0] // 2
            gy = center_y + pos["y_off"] - grid_img.size[1] // 2
            cover.paste(grid_img, (gx, gy), grid_img)

            # Track label anchor: x = grid center, y = bottom of grid + small gap
            label_anchors.append((
                diff_label.upper(),
                center_x + pos["x_off"],
                gy + grid_img.size[1] - int(0.05 * DPI),
            ))

        # Draw difficulty labels (EASY / MEDIUM / HARD) only if all distinct.
        # If duplicates (e.g. kids book has only easy+medium), skip labels —
        # claiming 3 distinct levels with duplicate labels reads dishonest.
        unique_labels = {l for l, _, _ in label_anchors}
        if label_anchors and len(unique_labels) == len(label_anchors):
            label_font = _heavy_font(int(0.24 * DPI))
            for label_text, lx, ly in label_anchors:
                lbb = d.textbbox((0, 0), label_text, font=label_font)
                d.text(
                    (lx - (lbb[2] - lbb[0]) // 2 - lbb[0], ly - lbb[1]),
                    label_text, fill=label_color, font=label_font,
                )

    # ── 7. Audience tagline band ──
    d2 = ImageDraw.Draw(cover)
    tagline = plan.get("front_audience_tag", "")
    if tagline:
        d2.rectangle(
            [front_x0, tagline_y0, front_x1, tagline_y0 + tagline_band_h],
            fill=tagline_bg,
        )
        tag_font_size = int(0.36 * DPI)
        tag_font = _heavy_font(tag_font_size)
        tbb = d2.textbbox((0, 0), tagline, font=tag_font)
        while (tbb[2] - tbb[0]) > (live_w - int(0.3 * DPI)) and tag_font_size > 18:
            tag_font_size -= 4
            tag_font = _heavy_font(tag_font_size)
            tbb = d2.textbbox((0, 0), tagline, font=tag_font)
        d2.text(
            (live_x0 + (live_w - (tbb[2] - tbb[0])) // 2 - tbb[0],
             tagline_y0 + (tagline_band_h - (tbb[3] - tbb[1])) // 2 - tbb[1]),
            tagline, fill=tagline_ink, font=tag_font,
        )

    # ── 8. Imprint just below tagline band, letter-spaced for elegance ──
    imprint = plan.get("imprint", "")
    if imprint:
        imp_color = _hex_to_rgb(scheme.get("imprint_color", scheme["title_color"]))
        imp_font = _heavy_font(int(0.20 * DPI))
        imp_text = imprint.upper()
        imp_bb = d2.textbbox((0, 0), imp_text, font=imp_font)
        imp_y = live_y1 - (imp_bb[3] - imp_bb[1]) - int(0.05 * DPI)
        d2.text(
            (live_x0 + (live_w - (imp_bb[2] - imp_bb[0])) // 2 - imp_bb[0], imp_y - imp_bb[1]),
            imp_text, fill=imp_color, font=imp_font,
        )


# ────────────────────────────────────────────────────────────────────
# Sudoku BACK + SPINE — unified theme (matches front color scheme)
# ────────────────────────────────────────────────────────────────────

def _render_sudoku_unified_back_spine(
    cover: Image.Image,
    dims: dict,
    plan: dict,
    author: str,
    puzzles_path: str,
) -> None:
    """Bestseller-style back + spine for sudoku books — unified with front theme.

    Same color scheme + same digit watermark as front. Mirrors top badges,
    repeats SUDOKU brand smaller, shows 2 inner-page mockups (not isolated grids),
    bullets with checkmarks, imprint near barcode area, white SUDOKU on spine.
    """
    DPI = config.DPI
    H = dims["full_height_px"]
    bleed = dims["bleed_px"]
    safe = dims["safe_px"]

    back_x0 = 0
    back_x1 = dims["spine_start_x"]
    spine_x0 = dims["spine_start_x"]
    spine_x1 = dims["front_start_x"]

    # SAME palette as front for visual unity
    scheme_name = (plan.get("front_color_scheme") or "green").lower()
    scheme = SUDOKU_FRONT_COLOR_SCHEMES.get(scheme_name, SUDOKU_FRONT_COLOR_SCHEMES["green"])
    bg = _hex_to_rgb(scheme["bg"])
    watermark = _hex_to_rgb(scheme["watermark"])
    title_color = _hex_to_rgb(scheme["title_color"])
    pill_bg = _hex_to_rgb(scheme["year_pill_bg"])
    pill_ink = _hex_to_rgb(scheme["year_pill_ink"])
    accent_bg = _hex_to_rgb(scheme["puzzle_pill_bg"])
    star_colors_list = [_hex_to_rgb(c) for c in scheme["stars"]]

    d = ImageDraw.Draw(cover)

    # ── 1. Background fill (back + spine, full bleed) ──
    d.rectangle([back_x0, 0, spine_x1, H], fill=bg)

    # ── 2. Watermark digits (subtle density, smaller font) ──
    import random
    rng = random.Random(int(plan.get("seed", 42)) ^ 0xCAFE)
    wm_font = _heavy_font(int(0.50 * DPI))
    for _ in range(70):
        x = rng.randint(0, back_x1 - int(0.3 * DPI))
        y = rng.randint(0, H - int(0.3 * DPI))
        d.text((x, y), str(rng.randint(1, 9)), font=wm_font, fill=watermark)

    # Live area on back
    live_x0 = back_x0 + bleed + safe
    live_x1 = back_x1 - safe
    live_y0 = bleed + safe
    live_w = live_x1 - live_x0

    # ── 3. Top zone: year pill + levels (mirror of front, 80% scale) ──
    top_y = live_y0
    pill_h = int(0.5 * DPI)
    pill_font = _heavy_font(int(0.26 * DPI))

    year_text = plan.get("front_year_text", "2026")
    bb = d.textbbox((0, 0), year_text, font=pill_font)
    yp_w = (bb[2] - bb[0]) + int(0.6 * DPI)
    d.rounded_rectangle(
        [live_x0, top_y, live_x0 + yp_w, top_y + pill_h],
        radius=pill_h // 2, fill=pill_bg,
    )
    d.text(
        (live_x0 + (yp_w - (bb[2] - bb[0])) // 2 - bb[0],
         top_y + (pill_h - (bb[3] - bb[1])) // 2 - bb[1]),
        year_text, fill=pill_ink, font=pill_font,
    )

    levels_text = plan.get("front_levels_text", "3 LEVELS")
    levels_font = _heavy_font(int(0.24 * DPI))
    bb_lv = d.textbbox((0, 0), levels_text, font=levels_font)
    levels_w = bb_lv[2] - bb_lv[0]
    show_stars = "LEVEL" in levels_text.upper()
    star_r = int(0.14 * DPI)
    star_gap = int(0.10 * DPI)
    star_block_w = 3 * (2 * star_r) + 2 * star_gap if show_stars else 0
    text_to_stars_gap = int(0.25 * DPI) if show_stars else 0
    full_block_w = levels_w + text_to_stars_gap + star_block_w
    block_x0 = live_x1 - full_block_w
    lv_y = top_y + (pill_h - (bb_lv[3] - bb_lv[1])) // 2 - bb_lv[1]
    d.text((block_x0 - bb_lv[0], lv_y), levels_text, fill=title_color, font=levels_font)
    if show_stars:
        sx_start = block_x0 + levels_w + text_to_stars_gap + star_r
        sy = top_y + pill_h // 2
        for i, c in enumerate(star_colors_list):
            _draw_star(d, sx_start + i * (2 * star_r + star_gap), sy, star_r, fill=c)

    cur_y = top_y + pill_h + int(0.4 * DPI)

    # ── 4. SUDOKU brand mark (smaller than front) ──
    brand_font_size = int(0.95 * DPI)
    brand_font = _heavy_font(brand_font_size)
    bb_b = d.textbbox((0, 0), "SUDOKU", font=brand_font)
    while (bb_b[2] - bb_b[0]) > live_w * 0.92 and brand_font_size > 40:
        brand_font_size -= 10
        brand_font = _heavy_font(brand_font_size)
        bb_b = d.textbbox((0, 0), "SUDOKU", font=brand_font)
    d.text(
        (live_x0 + (live_w - (bb_b[2] - bb_b[0])) // 2 - bb_b[0], cur_y - bb_b[1]),
        "SUDOKU", fill=title_color, font=brand_font,
    )
    cur_y += (bb_b[3] - bb_b[1]) + int(0.05 * DPI)

    # ── 5. Sub-line: book sub-title ──
    full_title = (plan.get("title", "") or "").upper()
    sub_words = full_title.replace("SUDOKU", "").strip() or "PUZZLE BOOK"
    sub_font_size = int(0.36 * DPI)
    sub_font = _heavy_font(sub_font_size)
    bb_s = d.textbbox((0, 0), sub_words, font=sub_font)
    while (bb_s[2] - bb_s[0]) > live_w * 0.95 and sub_font_size > 18:
        sub_font_size -= 4
        sub_font = _heavy_font(sub_font_size)
        bb_s = d.textbbox((0, 0), sub_words, font=sub_font)
    d.text(
        (live_x0 + (live_w - (bb_s[2] - bb_s[0])) // 2 - bb_s[0], cur_y - bb_s[1]),
        sub_words, fill=title_color, font=sub_font,
    )
    cur_y += (bb_s[3] - bb_s[1]) + int(0.35 * DPI)

    # ── 5b. Optional GIFT EDITION / NEW / etc. accent badge ──
    extra_badge = plan.get("back_extra_badge")
    if extra_badge:
        eb_font = _heavy_font(int(0.24 * DPI))
        eb_bb = d.textbbox((0, 0), extra_badge, font=eb_font)
        eb_w = (eb_bb[2] - eb_bb[0]) + int(0.7 * DPI)
        eb_h = int(0.5 * DPI)
        eb_x0 = live_x0 + (live_w - eb_w) // 2
        d.rounded_rectangle(
            [eb_x0, cur_y, eb_x0 + eb_w, cur_y + eb_h],
            radius=eb_h // 2, fill=pill_bg,
        )
        d.text(
            (eb_x0 + (eb_w - (eb_bb[2] - eb_bb[0])) // 2 - eb_bb[0],
             cur_y + (eb_h - (eb_bb[3] - eb_bb[1])) // 2 - eb_bb[1]),
            extra_badge, fill=pill_ink, font=eb_font,
        )
        cur_y += eb_h + int(0.3 * DPI)
    else:
        cur_y += int(0.15 * DPI)

    # ── 6. Description blurb (centered, white text, no panel) ──
    blurb = plan.get("back_blurb")
    if not blurb:
        diff_dist = plan.get("difficulty_distribution", {}) or {}
        active = [k for k, v in diff_dist.items() if v]
        if not active:
            active = ["easy", "medium", "hard"]
        blurb = (
            f"Stay sharp and entertained with this {plan.get('puzzle_count', 100)}-puzzle "
            f"sudoku collection — {', '.join(active).title()} levels. "
            f"Hand-verified, single-solution puzzles, large print, one puzzle per page."
        )
    blurb_font = _heavy_font(int(0.20 * DPI))
    blurb_lines = _wrap_text(blurb, blurb_font, int(live_w * 0.92), d)
    for line in blurb_lines:
        bb_line = d.textbbox((0, 0), line, font=blurb_font)
        d.text(
            (live_x0 + (live_w - (bb_line[2] - bb_line[0])) // 2 - bb_line[0],
             cur_y - bb_line[1]),
            line, fill=title_color, font=blurb_font,
        )
        cur_y += (bb_line[3] - bb_line[1]) + int(0.07 * DPI)
    cur_y += int(0.3 * DPI)

    # ── 7. Bullet checkmarks (3 short benefits) ──
    bullets = plan.get("back_bullets")
    if not bullets:
        diff_dist = plan.get("difficulty_distribution", {}) or {}
        diff_summary = " · ".join(f"{v} {k}" for k, v in diff_dist.items() if v)
        bullets = [
            f"{plan.get('puzzle_count', 100)} hand-verified puzzles" + (f" ({diff_summary})" if diff_summary else ""),
            "Large print · one puzzle per page",
            "Complete answer key included",
        ]
    bullets = list(bullets)[:4]
    bullet_font = _heavy_font(int(0.21 * DPI))
    check_size = int(0.22 * DPI)

    for b in bullets:
        b_text = b.lstrip("✓✔ -•").strip()
        bb_bb = d.textbbox((0, 0), b_text, font=bullet_font)
        bullet_w = check_size + int(0.15 * DPI) + (bb_bb[2] - bb_bb[0])
        bx = live_x0 + (live_w - bullet_w) // 2
        # Checkmark "V" using two lines in accent color
        cyy = cur_y + (bb_bb[3] - bb_bb[1]) // 2 - bb_bb[1]
        d.line([(bx, cyy), (bx + check_size // 3, cyy + check_size // 3)],
               fill=accent_bg, width=5)
        d.line([(bx + check_size // 3, cyy + check_size // 3),
                (bx + check_size, cyy - check_size // 2)],
               fill=accent_bg, width=5)
        d.text(
            (bx + check_size + int(0.15 * DPI) - bb_bb[0], cur_y - bb_bb[1]),
            b_text, fill=title_color, font=bullet_font,
        )
        cur_y += (bb_bb[3] - bb_bb[1]) + int(0.18 * DPI)
    cur_y += int(0.2 * DPI)

    # ── 8. Inner page mockups (2 overlapping rectangles showing actual content) ──
    barcode_h = int(1.2 * DPI)
    imprint_zone_h = int(0.45 * DPI)
    barcode_zone_top = H - bleed - safe - barcode_h - imprint_zone_h
    mockup_zone_h = barcode_zone_top - cur_y

    if mockup_zone_h > int(1.8 * DPI):
        sample_pages = []
        try:
            with open(puzzles_path) as f:
                puzzles = json.load(f)
            picked_ids = set()
            for diff in ["easy", "medium", "hard"]:
                for p in puzzles:
                    if (p.get("difficulty") == diff
                            and isinstance(p.get("puzzle"), list)
                            and len(p["puzzle"]) == 9
                            and p.get("id") not in picked_ids):
                        sample_pages.append((diff, p["puzzle"]))
                        picked_ids.add(p.get("id"))
                        break
                if len(sample_pages) >= 2:
                    break
            while len(sample_pages) < 2 and puzzles:
                added = False
                for p in puzzles:
                    if (isinstance(p.get("puzzle"), list)
                            and len(p["puzzle"]) == 9
                            and p.get("id") not in picked_ids):
                        sample_pages.append((p.get("difficulty", "easy"), p["puzzle"]))
                        picked_ids.add(p.get("id"))
                        added = True
                        break
                if not added:
                    break
        except Exception as e:
            print(f"  Warning: could not load puzzles for back mockup: {e}")

        if sample_pages:
            # Mockup is portrait — like an actual interior page (8.5x11 ratio, scaled small)
            mock_aspect = 11.0 / 8.5  # height / width
            mock_w_target = int(2.5 * DPI)
            mock_h_target = int(mock_w_target * mock_aspect)
            if mock_h_target > mockup_zone_h - int(0.3 * DPI):
                mock_h_target = mockup_zone_h - int(0.3 * DPI)
                mock_w_target = int(mock_h_target / mock_aspect)
            mock_w = mock_w_target
            mock_h = mock_h_target

            center_x = (live_x0 + live_x1) // 2
            center_y = cur_y + mockup_zone_h // 2

            positions = [
                {"angle": -7, "x_off": -int(0.75 * DPI), "y_off": int(0.1 * DPI)},
                {"angle": 7,  "x_off": int(0.75 * DPI),  "y_off": -int(0.1 * DPI)},
            ]

            for idx in [0, 1]:
                if idx >= len(sample_pages):
                    continue
                diff_label, clues = sample_pages[idx]
                pos = positions[idx]
                pad = int(0.15 * DPI)
                page_img = Image.new("RGBA", (mock_w + 2 * pad, mock_h + 2 * pad), (0, 0, 0, 0))
                pdraw = ImageDraw.Draw(page_img)
                # Drop shadow
                pdraw.rectangle(
                    [pad + 8, pad + 8, pad + mock_w + 8, pad + mock_h + 8],
                    fill=(0, 0, 0, 110),
                )
                # White page bg
                pdraw.rectangle([pad, pad, pad + mock_w, pad + mock_h], fill=(255, 255, 255, 255))
                # Header bar (matches book theme)
                header_h = int(0.4 * DPI)
                pdraw.rectangle([pad, pad, pad + mock_w, pad + header_h], fill=bg + (255,))
                header_font = _heavy_font(int(0.18 * DPI))
                ht = f"SUDOKU  {diff_label.upper()}"
                hbb = pdraw.textbbox((0, 0), ht, font=header_font)
                pdraw.text(
                    (pad + (mock_w - (hbb[2] - hbb[0])) // 2 - hbb[0],
                     pad + (header_h - (hbb[3] - hbb[1])) // 2 - hbb[1]),
                    ht, font=header_font, fill=title_color + (255,),
                )
                # Sample sudoku grid (centered below header)
                grid_top = pad + header_h + int(0.3 * DPI)
                grid_max_w = mock_w - int(0.4 * DPI)
                grid_max_h = mock_h - header_h - int(1.0 * DPI)
                grid_size = min(grid_max_w, grid_max_h)
                grid_x = pad + (mock_w - grid_size) // 2
                cell = grid_size / 9
                for i in range(10):
                    w = 4 if i % 3 == 0 else 1
                    pdraw.line(
                        [(grid_x, grid_top + round(i * cell)),
                         (grid_x + grid_size, grid_top + round(i * cell))],
                        fill=(20, 20, 20, 255), width=w,
                    )
                    pdraw.line(
                        [(grid_x + round(i * cell), grid_top),
                         (grid_x + round(i * cell), grid_top + grid_size)],
                        fill=(20, 20, 20, 255), width=w,
                    )
                num_font = _heavy_font(max(10, int(cell * 0.55)))
                for r in range(9):
                    for c in range(9):
                        n = clues[r][c]
                        if not n:
                            continue
                        cxn = grid_x + round(c * cell + cell / 2)
                        cyn = grid_top + round(r * cell + cell / 2)
                        nbb = pdraw.textbbox((0, 0), str(n), font=num_font)
                        pdraw.text(
                            (cxn - (nbb[2] - nbb[0]) // 2 - nbb[0],
                             cyn - (nbb[3] - nbb[1]) // 2 - nbb[1]),
                            str(n), fill=(20, 20, 20, 255), font=num_font,
                        )
                # Page number footer
                pn_font = _heavy_font(int(0.13 * DPI))
                pn_text = f"#{idx + 1}"
                pnbb = pdraw.textbbox((0, 0), pn_text, font=pn_font)
                pdraw.text(
                    (pad + mock_w - (pnbb[2] - pnbb[0]) - int(0.18 * DPI),
                     pad + mock_h - (pnbb[3] - pnbb[1]) - int(0.12 * DPI)),
                    pn_text, fill=(120, 120, 120, 255), font=pn_font,
                )

                if pos["angle"] != 0:
                    page_img = page_img.rotate(-pos["angle"], expand=True, resample=Image.BICUBIC)
                px = center_x + pos["x_off"] - page_img.size[0] // 2
                py = center_y + pos["y_off"] - page_img.size[1] // 2
                cover.paste(page_img, (px, py), page_img)

    # ── 9. Imprint (centered, letter-spaced, gold/yellow — bestseller image 5 style) ──
    imprint = plan.get("imprint", "") or author
    if imprint:
        imp_color = _hex_to_rgb(scheme.get("imprint_color", scheme["title_color"]))
        imp_font = _heavy_font(int(0.24 * DPI))
        # Letter-spaced uppercase: "B R A I N C R A F T   P U B L I S H I N G"
        imp_text = " ".join(imprint.upper())
        imp_bb = d.textbbox((0, 0), imp_text, font=imp_font)
        # Auto-shrink if it overflows live width
        while (imp_bb[2] - imp_bb[0]) > live_w and imp_font.size > 14:
            imp_font = _heavy_font(imp_font.size - 2)
            imp_bb = d.textbbox((0, 0), imp_text, font=imp_font)
        imp_y = barcode_zone_top + (imprint_zone_h - (imp_bb[3] - imp_bb[1])) // 2 - imp_bb[1]
        d.text(
            (live_x0 + (live_w - (imp_bb[2] - imp_bb[0])) // 2 - imp_bb[0], imp_y),
            imp_text, fill=imp_color, font=imp_font,
        )

    # ── 10. Spine (same bg, white SUDOKU vertical) ──
    d.rectangle([spine_x0, 0, spine_x1, H], fill=bg)
    if dims.get("can_have_spine_text") and dims["spine_w_px"] >= int(0.125 * config.DPI):
        spine_title = plan.get("spine_title") or _derive_sudoku_spine_title(plan)
        spine_len = H - 2 * bleed - 2 * int(SPINE_TEXT_CLEARANCE * config.DPI)
        spine_font = _heavy_font(max(14, int(dims["spine_w_px"] * 0.45)))
        tbb_dummy_img = Image.new("L", (1, 1))
        tbb_d = ImageDraw.Draw(tbb_dummy_img)
        tbb = tbb_d.textbbox((0, 0), spine_title, font=spine_font)
        tw, th = tbb[2] - tbb[0], tbb[3] - tbb[1]
        while tw > spine_len and spine_font.size > 10:
            spine_font = _heavy_font(spine_font.size - 2)
            tbb = tbb_d.textbbox((0, 0), spine_title, font=spine_font)
            tw, th = tbb[2] - tbb[0], tbb[3] - tbb[1]
        layer = Image.new("RGBA", (tw + 8, th + 8), (0, 0, 0, 0))
        ldraw = ImageDraw.Draw(layer)
        ldraw.text((4 - tbb[0], 4 - tbb[1]), spine_title,
                   fill=title_color + (255,), font=spine_font)
        rotated = layer.rotate(90, expand=True)
        rx = spine_x0 + (dims["spine_w_px"] - rotated.size[0]) // 2
        ry = (H - rotated.size[1]) // 2
        cover.paste(rotated, (rx, ry), rotated)


def build_cover(
    theme: str,
    author: str = "",
    custom_title: str | None = None,
    kdp_width: float | None = None,
    kdp_height: float | None = None,
    size: str = config.DEFAULT_PAGE_SIZE,
    renderer: str = DEFAULT_RENDERER,
    regenerate_artwork: bool = False,
):
    """Build the complete cover image."""
    theme_config = config.THEMES.get(theme)
    if not theme_config:
        print(f"Error: Unknown theme '{theme}'")
        sys.exit(1)

    # Auto-detect page size from book metadata if not explicitly set
    _plan_for_size = config.load_bookinfo(theme) or {}
    if size == config.DEFAULT_PAGE_SIZE:
        plan_size = _plan_for_size.get("page_size")
        if plan_size and plan_size in config.PAGE_SIZES:
            size = plan_size
    # Also check theme config
    if size == config.DEFAULT_PAGE_SIZE and "page_size" in theme_config and theme_config["page_size"] in config.PAGE_SIZES:
        size = theme_config["page_size"]

    # Use page size dimensions for trim
    page_dims = config.get_page_dims(size)
    trim_w = page_dims["width_inches"]
    trim_h = page_dims["height_inches"]

    # Load author: CLI > bookinfo > .env default
    if not author:
        author_obj = (_plan_for_size.get("author")
                      or (_plan_for_size.get("kdp_listing", {}) or {}).get("author")
                      or {})
        if isinstance(author_obj, dict):
            author = f"{author_obj.get('first_name', '')} {author_obj.get('last_name', '')}".strip()
        elif isinstance(author_obj, str):
            author = author_obj
    if not author:
        author = config.DEFAULT_AUTHOR

    title = custom_title or theme_config["book_title"]
    total_pages = count_pages(theme)

    if kdp_width and kdp_height:
        # Use exact KDP dimensions — back-calculate spine from total width
        spine_width = kdp_width - (2 * trim_w) - (2 * BLEED_INCHES)
        bleed_px = round(BLEED_INCHES * config.DPI)
        trim_w_px = round(trim_w * config.DPI)
        spine_w_px = round(spine_width * config.DPI)
        safe_px = round(SAFE_MARGIN * config.DPI)
        # Derive full px from components so regions tile without gaps
        full_w_px = 2 * bleed_px + 2 * trim_w_px + spine_w_px
        full_h_px = 2 * bleed_px + round(trim_h * config.DPI)
        dims = {
            "total_pages": total_pages,
            "spine_width_inches": spine_width,
            "full_width_inches": kdp_width,
            "full_height_inches": kdp_height,
            "full_width_px": full_w_px,
            "full_height_px": full_h_px,
            "bleed_px": bleed_px,
            "trim_w_px": trim_w_px,
            "spine_w_px": spine_w_px,
            "safe_px": safe_px,
            "back_start_x": bleed_px,
            "spine_start_x": bleed_px + trim_w_px,
            "front_start_x": bleed_px + trim_w_px + spine_w_px,
            "can_have_spine_text": total_pages >= 79,
        }
        print("(Using exact KDP dimensions)")
    else:
        dims = calculate_cover_dimensions(total_pages, trim_w=trim_w, trim_h=trim_h)

    print(f"Theme: {theme_config['name']}")
    print(f"Title: {title}")
    print(f"Pages: {dims['total_pages']}")
    print(f"Spine: {dims['spine_width_inches']:.3f}\"")
    print(f"Trim:  {trim_w}\" x {trim_h}\"  |  Bleed: {BLEED_INCHES}\" each side")
    print(f"Cover: {dims['full_width_inches']:.3f}\" x {dims['full_height_inches']:.3f}\" (with bleed)")
    print(f"Pixels: {dims['full_width_px']} x {dims['full_height_px']} @ {config.DPI} DPI")
    print()

    # Ensure book directory exists
    book_dir = config.get_book_dir(theme)
    os.makedirs(book_dir, exist_ok=True)

    # Create full cover canvas (white background)
    cover = Image.new("RGB", (dims["full_width_px"], dims["full_height_px"]), (255, 255, 255))
    draw = ImageDraw.Draw(cover)

    # --- Detect sudoku books early so we skip AI artwork (programmatic front instead) ---
    try:
        plan_data_early = config.load_bookinfo(theme) or {}
    except Exception:
        plan_data_early = {}
    early_book_type = (
        plan_data_early.get("book_type")
        or plan_data_early.get("style")
        or "coloring"
    ).lower()
    puzzles_path_early = os.path.join(book_dir, "sudoku_puzzles.json")
    is_sudoku_book_early = early_book_type == "sudoku" or os.path.exists(puzzles_path_early)

    # --- Generate and place front cover artwork (coloring books only) ---
    if is_sudoku_book_early:
        print("Sudoku book detected — skipping AI front artwork (programmatic template will paint front later).")
    else:
        front_artwork_path = os.path.join(book_dir, "front_artwork.png")
        artwork = None

        # Reuse saved front artwork if available (unless regenerate requested)
        if not regenerate_artwork and os.path.exists(front_artwork_path):
            print(f"Reusing saved front artwork: {front_artwork_path}")
            artwork = Image.open(front_artwork_path)
        else:
            artwork = generate_front_artwork(theme, title, author=author, renderer=renderer, size=size)
            if artwork:
                # Save front artwork for future reuse
                artwork.save(front_artwork_path, "PNG", dpi=(config.DPI, config.DPI))
                print(f"Front artwork saved: {front_artwork_path}")

        if artwork:
            # Resize artwork to fit front cover area (including right bleed)
            front_w = dims["full_width_px"] - dims["front_start_x"]
            front_h = dims["full_height_px"]
            artwork = artwork.convert("RGB")
            artwork = artwork.resize((front_w, front_h), Image.Resampling.LANCZOS)
            cover.paste(artwork, (dims["front_start_x"], 0))
            print("Front artwork placed.")
        else:
            # Fallback: solid color background for front
            print("Warning: Could not generate artwork. Using solid color.")
            front_colors = {
                "cute_animals": (255, 200, 220),
                "dinosaurs": (200, 230, 200),
                "vehicles": (200, 220, 255),
                "unicorn_fantasy": (230, 200, 255),
            }
            color = front_colors.get(theme, (200, 220, 255))
            draw.rectangle(
                [dims["front_start_x"], 0, dims["full_width_px"], dims["full_height_px"]],
                fill=color,
            )

    # --- Back cover: light gradient/solid (coloring-book default) ---
    back_colors = {
        "cute_animals": (255, 245, 248),
        "dinosaurs": (245, 255, 245),
        "vehicles": (240, 248, 255),
        "unicorn_fantasy": (248, 240, 255),
    }
    back_color = back_colors.get(theme, (248, 248, 255))
    draw.rectangle(
        [0, 0, dims["spine_start_x"], dims["full_height_px"]],
        fill=back_color,
    )

    # --- Spine: slightly darker ---
    spine_color = tuple(max(0, c - 30) for c in back_color)
    draw.rectangle(
        [
            dims["spine_start_x"],
            0,
            dims["front_start_x"],
            dims["full_height_px"],
        ],
        fill=spine_color,
    )

    # Author name is now included in the AI-generated front artwork via prompt

    # --- Back cover: sample pages grid + text ---
    back_center_x = dims["bleed_px"] + dims["trim_w_px"] // 2
    back_font = get_font(32, bold=False)
    back_title_font = get_font(44, bold=True)
    safe = dims["safe_px"]

    # Back title — truncate to fit within back cover width
    back_max_w = dims["trim_w_px"] - 2 * safe - 40  # leave padding
    back_title = f"{config.THEMES[theme]['name']}"
    # Truncate title if too long
    bbox = draw.textbbox((0, 0), back_title, font=back_title_font)
    while bbox[2] - bbox[0] > back_max_w and len(back_title) > 10:
        back_title = back_title[:len(back_title) - 4].rstrip() + "..."
        bbox = draw.textbbox((0, 0), back_title, font=back_title_font)
    bt_w = bbox[2] - bbox[0]
    title_y = dims["bleed_px"] + safe + 60
    draw.text(
        (back_center_x - bt_w // 2, title_y),
        back_title,
        font=back_title_font,
        fill=(40, 40, 40),
    )

    # Short description below title
    desc_font = get_font(28, bold=False)

    # Count actual images
    image_dir = config.get_images_dir(theme)
    num_images = len([f for f in os.listdir(image_dir) if f.endswith(".png")]) if os.path.exists(image_dir) else 0

    # Load plan for description
    plan_data = config.load_bookinfo(theme) or {}
    plan_desc = plan_data.get("description", "")
    plan_audience = plan_data.get("audience", "adults")

    back_desc_lines = [
        f"{num_images} unique coloring pages",
        "Bold, easy-to-color designs",
        "Single-sided pages to prevent bleed-through",
        "Hours of creative relaxation!",
    ]
    desc_y = title_y + 70
    for line in back_desc_lines:
        # Truncate each line to fit
        bbox = draw.textbbox((0, 0), line, font=desc_font)
        while bbox[2] - bbox[0] > back_max_w and len(line) > 10:
            line = line[:len(line) - 4].rstrip() + "..."
            bbox = draw.textbbox((0, 0), line, font=desc_font)
        line_w = bbox[2] - bbox[0]
        draw.text(
            (back_center_x - line_w // 2, desc_y),
            line,
            font=desc_font,
            fill=(80, 80, 80),
        )
        desc_y += 42

    # --- Sample pages grid (3 colored + 3 line art) ---
    sample_paths = get_sample_pages(theme, 6)

    # Decide whether to colorize: only coloring books have "line art" pages worth
    # colorizing for the back cover. Sudoku / puzzle / journal samples are already
    # their final visual form — colorizing them would produce garbage and waste
    # renderer credits.
    book_type = "coloring"
    try:
        _p = config.load_bookinfo(theme) or {}
        book_type = (_p.get("book_type") or _p.get("style") or _p.get("content_method") or "coloring").lower()
    except Exception:
        pass
    should_colorize = book_type in {"coloring"}

    if sample_paths:
        print(f"Generating sample page previews for back cover (book_type={book_type}, colorize={should_colorize})...")
        colored_count = min(3, len(sample_paths)) if should_colorize else 0
        sample_images = []

        import time
        for i, path in enumerate(sample_paths):
            if i < colored_count:
                print(f"  Colorizing sample {i + 1}/{colored_count}: {os.path.basename(path)}...")
                colored = colorize_page(path, renderer=renderer)
                if colored:
                    sample_images.append(("colored", colored))
                else:
                    # Fallback: use line art
                    sample_images.append(("lineart", Image.open(path).convert("RGB")))
                if i < colored_count - 1:
                    time.sleep(config.REQUEST_DELAY_SECONDS)
            else:
                sample_images.append(("lineart", Image.open(path).convert("RGB")))

        # Layout: 2 rows x 3 cols grid
        grid_cols = 3
        grid_rows = 2
        back_area_w = dims["trim_w_px"] - 2 * safe
        grid_top = desc_y + 30
        # Leave space for barcode at bottom
        barcode_h = int(1.2 * config.DPI)
        grid_bottom = dims["full_height_px"] - dims["bleed_px"] - safe - barcode_h - 60
        grid_avail_h = grid_bottom - grid_top

        padding = 30  # Between thumbnails
        thumb_w = (back_area_w - (grid_cols - 1) * padding) // grid_cols
        thumb_h = (grid_avail_h - (grid_rows - 1) * padding) // grid_rows

        # Keep aspect ratio based on book size (1.0 for square, ~1.294 for portrait)
        page_dims_for_ratio = config.get_page_dims(size)
        page_ratio = page_dims_for_ratio["height_px"] / page_dims_for_ratio["width_px"]
        if thumb_h / thumb_w > page_ratio:
            thumb_h = int(thumb_w * page_ratio)
        else:
            thumb_w = int(thumb_h / page_ratio)

        # Recalculate grid dimensions to center
        grid_w = grid_cols * thumb_w + (grid_cols - 1) * padding
        grid_h = grid_rows * thumb_h + (grid_rows - 1) * padding
        grid_x_start = dims["bleed_px"] + (dims["trim_w_px"] - grid_w) // 2
        grid_y_start = grid_top + (grid_avail_h - grid_h) // 2

        for idx, (img_type, img) in enumerate(sample_images[:grid_cols * grid_rows]):
            row = idx // grid_cols
            col = idx % grid_cols
            x = grid_x_start + col * (thumb_w + padding)
            y = grid_y_start + row * (thumb_h + padding)

            # Resize to thumbnail
            thumb = img.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)

            # Add thin border
            border = 3
            bordered = Image.new("RGB", (thumb_w + 2 * border, thumb_h + 2 * border), (180, 180, 180))
            bordered.paste(thumb, (border, border))

            # Add subtle shadow
            shadow_offset = 4
            draw.rectangle(
                [x + shadow_offset, y + shadow_offset,
                 x + thumb_w + 2 * border + shadow_offset, y + thumb_h + 2 * border + shadow_offset],
                fill=(200, 200, 200),
            )

            cover.paste(bordered, (x, y))

        # Refresh draw after pasting images
        draw = ImageDraw.Draw(cover)

        print(f"  Placed {len(sample_images)} sample pages on back cover.")

    # --- Book-type-aware back cover overlay (runs AFTER generic back to overwrite) ---
    try:
        plan_for_back: dict = config.load_bookinfo(theme) or {}
    except Exception:
        plan_for_back = {}
    back_book_type = (
        plan_for_back.get("book_type")
        or plan_for_back.get("style")
        or plan_for_back.get("content_method")
        or "coloring"
    ).lower()

    puzzles_path = os.path.join(config.get_book_dir(theme), "sudoku_puzzles.json")
    is_sudoku_book = back_book_type == "sudoku" or os.path.exists(puzzles_path)

    if is_sudoku_book:
        print("Rendering sudoku-specific UNIFIED back cover + spine (matches front theme)...")
        _render_sudoku_unified_back_spine(cover, dims, plan_for_back, author, puzzles_path)
        print("Rendering sudoku-specific front cover (programmatic bestseller template)...")
        _render_sudoku_front_cover(cover, dims, plan_for_back, puzzles_path)
        draw = ImageDraw.Draw(cover)

    # Barcode placeholder (KDP adds barcode here)
    barcode_w = int(2 * config.DPI)
    barcode_h = int(1.2 * config.DPI)
    barcode_x = dims["bleed_px"] + dims["trim_w_px"] - safe - barcode_w
    barcode_y = dims["full_height_px"] - dims["bleed_px"] - safe - barcode_h
    draw.rectangle(
        [barcode_x, barcode_y, barcode_x + barcode_w, barcode_y + barcode_h],
        fill="white",
        outline=(200, 200, 200),
    )
    # No text in barcode area — KDP auto-generates the barcode here.
    # Leaving template text like "BARCODE AREA" triggers manual review rejection.

    # --- Save PNG + PDF ---
    book_dir = config.get_book_dir(theme)
    os.makedirs(book_dir, exist_ok=True)
    png_path = config.get_cover_png_path(theme)
    pdf_path = config.get_cover_pdf_path(theme)

    cover.save(png_path, "PNG", dpi=(config.DPI, config.DPI))

    # Save as PDF (KDP requires PDF for cover upload)
    cover_cmyk = cover.convert("RGB")
    cover_cmyk.save(pdf_path, "PDF", resolution=config.DPI)

    print(f"\nCover saved:")
    print(f"  PNG: {png_path}")
    print(f"  PDF: {pdf_path} (upload this to KDP)")
    print(f"Size: {cover.size[0]} x {cover.size[1]} px")

    return pdf_path


def main():
    parser = argparse.ArgumentParser(description="Generate KDP coloring book cover")
    parser.add_argument(
        "--theme",
        required=True,
        choices=config.THEMES.keys(),
        help="Coloring book theme",
    )
    parser.add_argument(
        "--author",
        type=str,
        default="",
        help="Author name to display on cover",
    )
    parser.add_argument(
        "--title",
        type=str,
        default=None,
        help="Custom book title (default: from config)",
    )
    parser.add_argument(
        "--kdp-width",
        type=float,
        default=None,
        help="Exact cover width in inches from KDP (overrides calculated width)",
    )
    parser.add_argument(
        "--kdp-height",
        type=float,
        default=None,
        help="Exact cover height in inches from KDP (overrides calculated height)",
    )
    parser.add_argument(
        "--size",
        choices=config.PAGE_SIZES.keys(),
        default=config.DEFAULT_PAGE_SIZE,
        help=f"Page size (default: {config.DEFAULT_PAGE_SIZE})",
    )
    parser.add_argument(
        "--renderer",
        choices=RENDERER_CHOICES,
        default=DEFAULT_RENDERER,
        help=f"Image renderer (default: {DEFAULT_RENDERER} from .env)",
    )
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Force regenerate front artwork even if saved version exists",
    )
    args = parser.parse_args()

    build_cover(args.theme, args.author, args.title, args.kdp_width, args.kdp_height, args.size, args.renderer, args.regenerate)


if __name__ == "__main__":
    main()
