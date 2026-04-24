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

    # Try to load cover_prompt from plan file
    plan_path = config.get_plan_path(theme)
    cover_prompt_from_plan = None
    if os.path.exists(plan_path):
        with open(plan_path) as f:
            plan = json.load(f)
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


def _render_sudoku_back_and_spine(
    cover: Image.Image,
    dims: dict,
    plan: dict,
    author: str,
    puzzles_path: str,
) -> None:
    """Paint the back cover + spine for a sudoku book.

    Matches the front's commercial navy + gold palette, renders three real
    sample grids (easy / medium / hard) pulled from sudoku_puzzles.json, shows
    feature bullets + description, and reserves the KDP barcode slot.
    """
    palette = plan.get("cover_palette", {}) or {}
    navy = _hex_to_rgb(palette.get("dominant", "#1B3A5C"))
    gold = _hex_to_rgb(palette.get("accent_primary", "#D4A857"))
    cream = _hex_to_rgb(palette.get("accent_secondary", "#F7F1E3"))
    red = (200, 40, 50)
    white = (255, 255, 255)
    navy_lighter = tuple(min(255, c + 14) for c in navy)

    d = ImageDraw.Draw(cover)
    H = dims["full_height_px"]
    bleed = dims["bleed_px"]
    back_x0, back_x1 = 0, dims["spine_start_x"]
    spine_x0, spine_x1 = dims["spine_start_x"], dims["front_start_x"]

    # --- Navy background for back + spine (full bleed) ---
    d.rectangle([back_x0, 0, spine_x1, H], fill=navy)

    # --- Subtle sudoku-grid watermark across back ---
    wm_cell = int(0.42 * config.DPI)
    for gx in range(bleed - wm_cell, back_x1 + wm_cell, wm_cell):
        d.line([(gx, 0), (gx, H)], fill=navy_lighter, width=1)
    for gy in range(bleed - wm_cell, H + wm_cell, wm_cell):
        d.line([(back_x0, gy), (back_x1, gy)], fill=navy_lighter, width=1)

    safe = dims["safe_px"]
    content_left = bleed + safe
    content_right = back_x1 - safe
    content_w = content_right - content_left

    # --- Top: gold "3 LEVELS" pill + red "GIFT EDITION" pill ---
    top_y = bleed + int(0.35 * config.DPI)
    pill_h = int(0.55 * config.DPI)

    red_font = get_font(int(0.22 * config.DPI), bold=True)
    red_text = "GIFT EDITION"
    bb = d.textbbox((0, 0), red_text, font=red_font)
    red_w = (bb[2] - bb[0]) + int(0.7 * config.DPI)
    d.rounded_rectangle(
        [content_left, top_y, content_left + red_w, top_y + pill_h],
        radius=pill_h // 2, fill=red,
    )
    d.text(
        (content_left + (red_w - (bb[2] - bb[0])) // 2 - bb[0],
         top_y + (pill_h - (bb[3] - bb[1])) // 2 - bb[1]),
        red_text, fill=white, font=red_font,
    )

    gold_font = get_font(int(0.22 * config.DPI), bold=True)
    gold_text = "240 PUZZLES"
    bb = d.textbbox((0, 0), gold_text, font=gold_font)
    gold_w = (bb[2] - bb[0]) + int(0.7 * config.DPI)
    d.rounded_rectangle(
        [content_right - gold_w, top_y, content_right, top_y + pill_h],
        radius=pill_h // 2, fill=gold,
    )
    d.text(
        (content_right - gold_w + (gold_w - (bb[2] - bb[0])) // 2 - bb[0],
         top_y + (pill_h - (bb[3] - bb[1])) // 2 - bb[1]),
        gold_text, fill=navy, font=gold_font,
    )

    # --- Headline (white) + subheadline (gold) ---
    headline = plan.get("back_headline") or "THE PERFECT RETIREMENT GIFT"
    subheadline = plan.get("back_subheadline") or "240 hand-verified large-print puzzles,"
    sub2 = "one thoughtful page at a time."

    headline_font = get_font(int(0.42 * config.DPI), bold=True)
    sub_font = get_font(int(0.26 * config.DPI), bold=False)

    hl_y = top_y + pill_h + int(0.45 * config.DPI)
    bb = d.textbbox((0, 0), headline, font=headline_font)
    # Shrink-to-fit
    while bb[2] - bb[0] > content_w and headline_font.size > 40:
        headline_font = get_font(headline_font.size - 4, bold=True)
        bb = d.textbbox((0, 0), headline, font=headline_font)
    d.text(
        (content_left + (content_w - (bb[2] - bb[0])) // 2 - bb[0], hl_y),
        headline, fill=white, font=headline_font,
    )

    sub_y = hl_y + (bb[3] - bb[1]) + int(0.15 * config.DPI)
    bb2 = d.textbbox((0, 0), subheadline, font=sub_font)
    d.text(
        (content_left + (content_w - (bb2[2] - bb2[0])) // 2 - bb2[0], sub_y),
        subheadline, fill=gold, font=sub_font,
    )
    sub_y2 = sub_y + (bb2[3] - bb2[1]) + int(0.06 * config.DPI)
    bb3 = d.textbbox((0, 0), sub2, font=sub_font)
    d.text(
        (content_left + (content_w - (bb3[2] - bb3[0])) // 2 - bb3[0], sub_y2),
        sub2, fill=gold, font=sub_font,
    )

    # --- Cream description panel ---
    panel_y0 = sub_y2 + (bb3[3] - bb3[1]) + int(0.45 * config.DPI)
    panel_h = int(2.4 * config.DPI)
    d.rounded_rectangle(
        [content_left, panel_y0, content_right, panel_y0 + panel_h],
        radius=int(0.12 * config.DPI), fill=cream,
    )

    # Feature bullets inside cream panel
    bullets = [
        "240 hand-verified puzzles  (60 easy · 120 medium · 60 hard)",
        "Large print · one puzzle per page · easy on the eyes",
        "Every grid has exactly one solution",
        "Complete answer key included at the back",
        "A calm, giftable edition for retirement and beyond",
    ]
    bullet_font = get_font(int(0.21 * config.DPI), bold=False)
    by = panel_y0 + int(0.35 * config.DPI)
    line_gap = int(0.44 * config.DPI)
    for b in bullets:
        # gold check-dot
        dot_r = int(0.08 * config.DPI)
        d.ellipse(
            [content_left + int(0.35 * config.DPI) - dot_r,
             by + int(0.12 * config.DPI) - dot_r,
             content_left + int(0.35 * config.DPI) + dot_r,
             by + int(0.12 * config.DPI) + dot_r],
            fill=gold,
        )
        d.text((content_left + int(0.6 * config.DPI), by), b,
               fill=navy, font=bullet_font)
        by += line_gap

    # --- Sample grids row (3 mini grids: easy / medium / hard) ---
    sample_labels = [("EASY", "easy"), ("MEDIUM", "medium"), ("HARD", "hard")]
    samples_by_diff: dict = {}
    try:
        with open(puzzles_path) as f:
            puzzles = json.load(f)
        for label, diff in sample_labels:
            for p in puzzles:
                if p.get("difficulty") == diff and p.get("puzzle"):
                    samples_by_diff[diff] = p["puzzle"]
                    break
    except Exception as e:
        print(f"  Warning: could not load sudoku puzzles for back cover: {e}")

    grid_top = panel_y0 + panel_h + int(0.45 * config.DPI)
    grid_size = int(1.55 * config.DPI)
    label_h = int(0.35 * config.DPI)
    slot_w = content_w // 3
    label_font = get_font(int(0.20 * config.DPI), bold=True)

    for i, (label, diff) in enumerate(sample_labels):
        slot_x0 = content_left + i * slot_w
        gx = slot_x0 + (slot_w - grid_size) // 2
        gy = grid_top + label_h

        # difficulty label in gold above the grid
        bb = d.textbbox((0, 0), label, font=label_font)
        d.text(
            (slot_x0 + (slot_w - (bb[2] - bb[0])) // 2 - bb[0], grid_top),
            label, fill=gold, font=label_font,
        )

        clues = samples_by_diff.get(diff)
        if clues:
            _draw_sudoku_grid_pil(cover, gx, gy, grid_size, clues,
                                  thick_px=4, thin_px=1)

    # --- Author credit bottom center ---
    author_line = author.upper() if author else ""
    if author_line:
        author_font = get_font(int(0.22 * config.DPI), bold=True)
        # Letter-spacing fake: insert spaces between chars
        spaced = "  ".join(author_line)
        bb = d.textbbox((0, 0), spaced, font=author_font)
        ay = H - bleed - safe - int(0.3 * config.DPI) - (bb[3] - bb[1])
        d.text(
            (content_left + (content_w - (bb[2] - bb[0])) // 2 - bb[0], ay),
            spaced, fill=gold, font=author_font,
        )

    # --- Spine: navy stays, add gold spine title if page count allows ---
    d.rectangle([spine_x0, 0, spine_x1, H], fill=navy)
    if dims.get("can_have_spine_text") and dims["spine_w_px"] >= int(0.125 * config.DPI):
        spine_title = plan.get("spine_title") or plan.get("title", "").upper()
        if spine_title:
            # Render title on transparent layer, then rotate and paste on spine.
            spine_len = H - 2 * bleed - 2 * int(SPINE_TEXT_CLEARANCE * config.DPI)
            # Font size ~60% of spine width
            spine_font = get_font(max(14, int(dims["spine_w_px"] * 0.45)), bold=True)
            bb = Image.new("L", (1, 1))
            dbb = ImageDraw.Draw(bb)
            tbb = dbb.textbbox((0, 0), spine_title, font=spine_font)
            tw, th = tbb[2] - tbb[0], tbb[3] - tbb[1]
            # Shrink to fit spine_len
            while tw > spine_len and spine_font.size > 10:
                spine_font = get_font(spine_font.size - 2, bold=True)
                tbb = dbb.textbbox((0, 0), spine_title, font=spine_font)
                tw, th = tbb[2] - tbb[0], tbb[3] - tbb[1]

            layer = Image.new("RGBA", (tw + 8, th + 8), (0, 0, 0, 0))
            ldraw = ImageDraw.Draw(layer)
            ldraw.text((4 - tbb[0], 4 - tbb[1]), spine_title, fill=gold + (255,), font=spine_font)
            # Rotate 90° counterclockwise (reads bottom-to-top on standing spine)
            rotated = layer.rotate(90, expand=True)
            # Paste centered in spine horizontally, vertically centered
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

    # Auto-detect page size from plan if not explicitly set
    plan_path = config.get_plan_path(theme)
    if size == config.DEFAULT_PAGE_SIZE and os.path.exists(plan_path):
        with open(plan_path) as f:
            plan_data_for_size = json.load(f)
            plan_size = plan_data_for_size.get("page_size")
            if plan_size and plan_size in config.PAGE_SIZES:
                size = plan_size
    # Also check theme config
    if size == config.DEFAULT_PAGE_SIZE and "page_size" in theme_config and theme_config["page_size"] in config.PAGE_SIZES:
        size = theme_config["page_size"]

    # Use page size dimensions for trim
    page_dims = config.get_page_dims(size)
    trim_w = page_dims["width_inches"]
    trim_h = page_dims["height_inches"]

    # Load author: CLI > plan.json > .env default
    if not author:
        plan_author_path = config.get_plan_path(theme)
        if os.path.exists(plan_author_path):
            with open(plan_author_path) as f:
                pa = json.load(f)
                author_obj = pa.get("author", {})
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

    # --- Generate and place front cover artwork ---
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
    plan_path = config.get_plan_path(theme)
    plan_desc = ""
    plan_audience = "adults"
    if os.path.exists(plan_path):
        with open(plan_path) as f:
            plan_data = json.load(f)
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
    plan_path_bt = config.get_plan_path(theme)
    book_type = "coloring"
    if os.path.exists(plan_path_bt):
        try:
            with open(plan_path_bt) as _f:
                _p = json.load(_f)
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
    plan_for_back: dict = {}
    plan_path_back = config.get_plan_path(theme)
    if os.path.exists(plan_path_back):
        try:
            with open(plan_path_back) as _f:
                plan_for_back = json.load(_f)
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
        print("Rendering sudoku-specific back cover + spine...")
        _render_sudoku_back_and_spine(cover, dims, plan_for_back, author, puzzles_path)
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
