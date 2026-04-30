"""
Configuration for KDP Coloring Book Generator.
All measurements based on Amazon KDP paperback specifications.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# --- Author (from .env) ---
DEFAULT_AUTHOR_FIRST = os.getenv("AUTHOR_FIRST_NAME", "").strip()
DEFAULT_AUTHOR_LAST = os.getenv("AUTHOR_LAST_NAME", "").strip()
DEFAULT_AUTHOR = f"{DEFAULT_AUTHOR_FIRST} {DEFAULT_AUTHOR_LAST}".strip()

# --- Page Dimensions ---
# Supported page sizes for KDP
PAGE_SIZES = {
    "8.5x11": {
        "width": 8.5,
        "height": 11.0,
        "aspect_ratio": "3:4",       # For Gemini API
        "ai33_aspect_ratio": "3:4",  # For AI33 API
        "bimai_aspect_ratio": "9:16",  # For Bimai API
        "kie_aspect_ratio": "3:4",    # For Kie.ai API
        "label": "8.5\" x 11\" (Portrait)",
    },
    "8.5x8.5": {
        "width": 8.5,
        "height": 8.5,
        "aspect_ratio": "1:1",       # For Gemini API
        "ai33_aspect_ratio": "1:1",  # For AI33 API
        "bimai_aspect_ratio": "1:1",  # For Bimai API
        "kie_aspect_ratio": "1:1",    # For Kie.ai API
        "label": "8.5\" x 8.5\" (Square)",
    },
}

# Default page size
DEFAULT_PAGE_SIZE = "8.5x11"

# Legacy defaults (8.5x11) — used when --size is not specified
PAGE_WIDTH_INCHES = 8.5
PAGE_HEIGHT_INCHES = 11.0
DPI = 300
MARGIN_INCHES = 0.25  # Outside, top, bottom margins
GUTTER_MARGIN_INCHES = 0.25  # Default gutter (overridden by get_gutter_margin)

# Derived pixel dimensions (default 8.5x11)
PAGE_WIDTH_PX = int(PAGE_WIDTH_INCHES * DPI)   # 2550
PAGE_HEIGHT_PX = int(PAGE_HEIGHT_INCHES * DPI)  # 3300
MARGIN_PX = int(MARGIN_INCHES * DPI)            # 75

# Safe drawing area (inside margins)
SAFE_WIDTH_PX = PAGE_WIDTH_PX - (2 * MARGIN_PX)   # 2400
SAFE_HEIGHT_PX = PAGE_HEIGHT_PX - (2 * MARGIN_PX)  # 3150


def get_gutter_margin(page_count: int) -> float:
    """Return required gutter (inside) margin in inches based on KDP page count rules.

    KDP requirements:
    - 24-150 pages:  0.375"
    - 151-300 pages: 0.500"
    - 301-500 pages: 0.625"
    - 501-700 pages: 0.750"
    - 701-828 pages: 0.875"
    - <24 pages:     0.25" (standard)
    """
    if page_count >= 701:
        return 0.875
    elif page_count >= 501:
        return 0.75
    elif page_count >= 301:
        return 0.625
    elif page_count >= 151:
        return 0.5
    elif page_count >= 24:
        return 0.375
    else:
        return 0.25


def get_page_dims(size_key: str = DEFAULT_PAGE_SIZE, page_count: int = 0) -> dict:
    """Return pixel dimensions for a given page size key.

    If page_count > 0, includes gutter_margin calculated from KDP rules.
    """
    ps = PAGE_SIZES[size_key]
    w = int(ps["width"] * DPI)
    h = int(ps["height"] * DPI)
    m = int(MARGIN_INCHES * DPI)
    gutter = get_gutter_margin(page_count) if page_count > 0 else MARGIN_INCHES
    gutter_px = int(gutter * DPI)
    return {
        "width_inches": ps["width"],
        "height_inches": ps["height"],
        "width_px": w,
        "height_px": h,
        "margin_px": m,
        "margin_inches": MARGIN_INCHES,
        "gutter_margin_inches": gutter,
        "gutter_margin_px": gutter_px,
        "safe_width_px": w - m - gutter_px,
        "safe_height_px": h - 2 * m,
        "aspect_ratio": ps["aspect_ratio"],
        "ai33_aspect_ratio": ps["ai33_aspect_ratio"],
        "bimai_aspect_ratio": ps["bimai_aspect_ratio"],
    }

# --- Gemini API ---
GEMINI_MODEL = "gemini-3.1-flash-image-preview"  # Nano Banana Pro - fast image generation
REQUEST_DELAY_SECONDS = 3  # Min delay between API calls (20 requests/min)
MAX_PARALLEL_WORKERS = 6   # Concurrent image generation threads
MAX_RETRIES = 3

# --- AI33 API ---
AI33_API_URL = "https://api.ai33.pro/v1i/task/generate-image"
AI33_STATUS_URL = "https://api.ai33.pro/v1/task"
AI33_MODEL_ID = "gemini-3.1-flash-image-preview"
AI33_RESOLUTION = "2K"
AI33_ASPECT_RATIO = "3:4"  # Portrait for coloring books
AI33_POLL_INTERVAL = 5  # Seconds between status polls
AI33_POLL_TIMEOUT = 300  # Max seconds to wait for image generation

# --- Bimai API (app.bimai.vn) ---
BIMAI_API_URL = "https://api.bimai.vn/api/v1/generate"
BIMAI_STATUS_URL = "https://api.bimai.vn/api/v1/tasks"
BIMAI_DISPLAY_NAME = "Google Flow"
BIMAI_PROVIDER = "Google Flow"
BIMAI_MODEL = "Google Flow"
BIMAI_POLL_INTERVAL = 5   # Seconds between status polls
BIMAI_POLL_TIMEOUT = 300  # Max seconds to wait for image generation

# --- Kie.ai API ---
KIE_API_URL = "https://api.kie.ai/api/v1/jobs/createTask"
KIE_STATUS_URL = "https://api.kie.ai/api/v1/jobs/recordInfo"
KIE_MODEL = "nano-banana-2"
KIE_RESOLUTION = "1K"
KIE_POLL_INTERVAL = 5
KIE_POLL_TIMEOUT = 300

# --- NanoPic API (nanoai.pics) ---
NANOPIC_API_URL = "https://flow-api.nanoai.pics/api/v2/images/create"
NANOPIC_STATUS_URL = "https://flow-api.nanoai.pics/api/v2/task"
NANOPIC_MODEL = "GEM_PIX_2"
NANOPIC_POLL_INTERVAL = 5
NANOPIC_POLL_TIMEOUT = 300
NANOPIC_ASPECT_RATIOS = {
    "1:1": "IMAGE_ASPECT_RATIO_SQUARE",
    "3:4": "IMAGE_ASPECT_RATIO_PORTRAIT",
    "9:16": "IMAGE_ASPECT_RATIO_PORTRAIT",
    "4:3": "IMAGE_ASPECT_RATIO_LANDSCAPE",
    "16:9": "IMAGE_ASPECT_RATIO_LANDSCAPE",
}

# --- Book Settings ---
COLORING_PAGES_PER_BOOK = 30
TARGET_AGE = "6-12"

# --- Paths ---
OUTPUT_DIR = "output"


def get_book_dir(theme_key: str) -> str:
    """Return the output directory for a book: output/{theme_key}/"""
    return os.path.join(OUTPUT_DIR, theme_key)


def get_images_dir(theme_key: str) -> str:
    """Return the images directory: output/{theme_key}/images/"""
    return os.path.join(OUTPUT_DIR, theme_key, "images")


def get_bookinfo_path(theme_key: str) -> str:
    """Return the canonical book metadata path: output/{theme_key}/bookinfo.md

    bookinfo.md is the SINGLE source of truth per book. It carries:
      - A JSON code fence at the top with structured pipeline data (page_size,
        prompts, difficulty, recommended_categories_2026, kdp_listing, etc.)
      - A human-readable markdown body underneath, optimized for copy/paste
        directly into kdp.amazon.com → Paperback → Add Title.

    Pipeline reads via load_bookinfo(); humans open the file in an IDE / editor
    and copy fields straight into Amazon. Replaces the older split between
    plan.json + bookinfo.json + bookinfo.md + listing.md.
    """
    return os.path.join(OUTPUT_DIR, theme_key, "bookinfo.md")


def get_plan_path(theme_key: str) -> str:
    """Return path to the canonical metadata file (legacy alias).

    Resolution order:
      1. output/{theme_key}/bookinfo.md  (canonical)
      2. output/{theme_key}/bookinfo.json (intermediate format, kept for fallback)
      3. output/{theme_key}/plan.json     (legacy)

    NOTE: Direct json.load() on the result will FAIL for bookinfo.md. Callers
    that need the parsed dict should use load_bookinfo(theme_key) instead;
    this function exists only for code paths that still need a path string
    (e.g. existence checks, copy operations).
    """
    md = get_bookinfo_path(theme_key)
    if os.path.exists(md):
        return md
    json_path = os.path.join(OUTPUT_DIR, theme_key, "bookinfo.json")
    if os.path.exists(json_path):
        return json_path
    return os.path.join(OUTPUT_DIR, theme_key, "plan.json")


_JSON_FENCE_RE = re.compile(
    r"<!--\s*BOOKINFO_DATA[^>]*-->\s*```json\s*\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)


def load_bookinfo_from_path(path: str | os.PathLike) -> dict:
    """Parse a metadata file (bookinfo.md / bookinfo.json / plan.json) into a dict.

    Drop-in replacement for `with open(p) as f: data = json.load(f)` patterns —
    handles both the new bookinfo.md (JSON code fence) and legacy JSON files
    transparently. Raises FileNotFoundError if missing, ValueError if bookinfo.md
    has no recoverable JSON fence.
    """
    p = str(path)
    if not os.path.exists(p):
        raise FileNotFoundError(p)
    text = Path(p).read_text(encoding="utf-8")
    if p.endswith(".md"):
        m = _JSON_FENCE_RE.search(text)
        if not m:
            # Tolerant fallback: any ```json fence (in case BOOKINFO_DATA marker was edited away)
            m = re.search(r"```json\s*\n(.*?)\n```", text, re.DOTALL)
        if not m:
            raise ValueError(f"bookinfo.md missing JSON fence: {p}")
        return json.loads(m.group(1))
    return json.loads(text)


def load_bookinfo(theme_key: str) -> dict | None:
    """Load book metadata for a theme as a dict.

    Tries (in order):
      1. bookinfo.md  (canonical, JSON fence under BOOKINFO_DATA markers)
      2. bookinfo.json (intermediate format)
      3. plan.json    (legacy)

    Returns None if no metadata file exists.
    """
    book_dir = os.path.join(OUTPUT_DIR, theme_key)
    for name in ("bookinfo.md", "bookinfo.json", "plan.json"):
        p = os.path.join(book_dir, name)
        if os.path.exists(p):
            return load_bookinfo_from_path(p)
    return None


def _render_bookinfo_md(data: dict) -> str:
    """Render a dict as the canonical bookinfo.md (data fence + readable body)."""
    theme_key = data.get("theme_key", "unknown")
    kdp = data.get("kdp_listing") or {}
    rec = data.get("recommended_categories_2026") or {}

    title = kdp.get("title") or data.get("title") or theme_key
    subtitle = kdp.get("subtitle") or data.get("subtitle") or ""
    author = kdp.get("author") or {}
    if isinstance(author, str):
        parts = author.split(maxsplit=1)
        author = {"first_name": parts[0] if parts else "", "last_name": parts[1] if len(parts) > 1 else ""}
    desc_html = kdp.get("description_html") or ""
    keywords = kdp.get("keywords_7") or []
    cats_block = kdp.get("categories_paperback_2026") or {}
    audience = kdp.get("primary_audience") or {}
    print_opts = kdp.get("print_options") or {}
    pricing = kdp.get("pricing") or {}
    files = kdp.get("files") or {}
    imprint = kdp.get("imprint") or data.get("imprint", "")

    cat_rows = []
    for tier, label in (("primary", "🥇 Primary"), ("secondary", "🥈 Secondary"), ("tertiary", "🥉 Tertiary")):
        tier_data = rec.get(tier) or {}
        path = (cats_block.get(tier) if cats_block else None) or tier_data.get("kdp_path", "—")
        node = tier_data.get("amazon_node_id", "—")
        bsr = tier_data.get("top_bsr", "—")
        roy = tier_data.get("top_monthly_royalty_usd", "—")
        cat_rows.append(f"| {label} | `{path}` | `{node}` | {bsr} | {roy} |")

    kw_lines = "\n".join(f"{i+1}. {kw}" for i, kw in enumerate(keywords))
    age_min = audience.get("reading_age_min")
    age_max = audience.get("reading_age_max")
    age_str = f"{age_min}–{age_max}" if age_min and age_max else "Leave blank (adult audience)"

    json_block = json.dumps(data, indent=2, ensure_ascii=False)

    return f"""<!-- BOOKINFO_DATA — pipeline reads the JSON below. Regenerate via:
     python3 scripts/migrate_to_bookinfo.py --apply --force --book {theme_key}
     Edits to the markdown body further down do NOT propagate back to this fence. -->
```json
{json_block}
```

<!-- END_BOOKINFO_DATA -->

---

# {title}

> Single-file source of truth for **{theme_key}**. Copy fields below directly into kdp.amazon.com → Paperback → Add Title.

---

## 📌 Title (≤ 200 chars)

```
{title}
```

## 📌 Subtitle (≤ 200 chars)

```
{subtitle}
```

## ✍️ Author / Imprint

- **First name:** `{author.get("first_name", "")}`
- **Last name:** `{author.get("last_name", "")}`
- **Imprint:** `{imprint}`

## 📝 Description (HTML — paste into KDP description box)

```html
{desc_html}
```

## 🔑 Keywords (7 backend, ≤ 50 chars each)

{kw_lines if kw_lines else "_(none)_"}

## 🗂️ Categories — Paperback Browse Paths (3 picks)

| Tier | KDP Browse Path | Node ID | Top BSR | Top $/mo |
|---|---|---|---|---|
{chr(10).join(cat_rows)}

> Selection rule: topic match (sudoku/puzzle/logic) > paperback format > Blue Ocean weakness > audience overlap. See `recommended_categories_2026.rejected_options` in the JSON above for what was deliberately excluded.

## 👤 Primary Audience

- **Sexually Explicit:** `{"Yes" if audience.get("sexually_explicit") else "No"}`
- **Low-content book:** `{"Yes" if audience.get("low_content_book") else "No"}`
- **Large-print book:** `{"Yes" if audience.get("large_print_book") else "No"}`
- **Reading age:** {age_str}
- **Audience label (internal):** `{audience.get("audience_label", "")}`

## 🖨️ Print Options

- **Ink & paper:** {print_opts.get("ink_paper", "Black & white interior with white paper")}
- **Trim size:** {print_opts.get("trim_size", "8.5 x 11 in")}
- **Bleed:** {print_opts.get("bleed", "No Bleed")}
- **Cover finish:** {print_opts.get("cover_finish", "Matte")}

## 💰 Pricing

| Market | Price |
|---|---|
| 🇺🇸 USD | ${pricing.get("list_price_usd", 9.99)} |
| 🇬🇧 GBP | £{pricing.get("list_price_gbp", "—")} |
| 🇪🇺 EUR | €{pricing.get("list_price_eur", "—")} |
| 🇨🇦 CAD | CA${pricing.get("list_price_cad", "—")} |
| 🇦🇺 AUD | AU${pricing.get("list_price_aud", "—")} |

## 📁 Files to Upload

- **Interior PDF:** `output/{theme_key}/{files.get("interior_pdf", "interior.pdf")}`
- **Cover PDF:** `output/{theme_key}/{files.get("cover_pdf", "cover.pdf")}`

## ✅ Launch Checklist

- [ ] Enroll in **KDP Select** ({"Yes" if kdp.get("kdp_select_enrollment") else "No"})
- [ ] Enable **Expanded Distribution** ({"Yes" if kdp.get("expanded_distribution") else "No"})
- [ ] Cover includes barcode? **{"Yes" if kdp.get("barcode_on_cover") else "No (KDP adds one)"}**
- [ ] After live: request 4th–5th categories via KDP support (see `recommended_categories_2026.post_publish_category_requests` in JSON)
"""


def save_bookinfo(theme_key: str, data: dict) -> str:
    """Write book metadata to output/{theme_key}/bookinfo.md.

    The file contains a JSON code fence (pipeline-readable, in <!-- BOOKINFO_DATA -->
    markers) plus a human-readable markdown body rendered from data['kdp_listing']
    for paste-ready KDP upload. Returns the path written.
    """
    book_dir = os.path.join(OUTPUT_DIR, theme_key)
    os.makedirs(book_dir, exist_ok=True)
    md_path = os.path.join(book_dir, "bookinfo.md")
    Path(md_path).write_text(_render_bookinfo_md(data), encoding="utf-8")
    return md_path


def get_prompts_path(theme_key: str) -> str:
    """Return the prompts file path: output/{theme_key}/prompts.txt"""
    return os.path.join(OUTPUT_DIR, theme_key, "prompts.txt")


def get_interior_pdf_path(theme_key: str) -> str:
    """Return the interior PDF path: output/{theme_key}/interior.pdf"""
    return os.path.join(OUTPUT_DIR, theme_key, "interior.pdf")


def get_cover_png_path(theme_key: str) -> str:
    """Return the cover PNG path: output/{theme_key}/cover.png"""
    return os.path.join(OUTPUT_DIR, theme_key, "cover.png")


def get_cover_pdf_path(theme_key: str) -> str:
    """Return the cover PDF path: output/{theme_key}/cover.pdf"""
    return os.path.join(OUTPUT_DIR, theme_key, "cover.pdf")


# --- Themes ---
# Legacy themes only (no plan.json). All other themes are auto-loaded from output/{theme}/plan.json
_LEGACY_THEMES = {
    "cute_animals": {
        "name": "Cute Animals",
        "book_title": "Adorable Animals Coloring Book for Kids Ages 6-12",
        "prompt_file": "prompts/cute_animals.txt",
    },
    "dinosaurs": {
        "name": "Dinosaurs",
        "book_title": "Amazing Dinosaurs Coloring Book for Kids Ages 6-12",
        "prompt_file": "prompts/dinosaurs.txt",
    },
    "vehicles": {
        "name": "Vehicles",
        "book_title": "Cool Vehicles Coloring Book for Kids Ages 6-12",
        "prompt_file": "prompts/vehicles.txt",
    },
    "unicorn_fantasy": {
        "name": "Unicorn & Fantasy",
        "book_title": "Magical Unicorns & Fantasy Coloring Book for Kids Ages 6-12",
        "prompt_file": "prompts/unicorn_fantasy.txt",
    },
    "cozy_cat_cafe": {
        "name": "Cozy Cat Cafe",
        "book_title": "Cozy Cat Cafe: Coloring Book for Adults and Teens",
        "prompt_file": "output/cozy_cat_cafe/prompts.txt",
    },
}


def get_theme(theme_key: str) -> dict | None:
    """Get theme config by key. Reads from plan.json first, falls back to _LEGACY_THEMES.

    Returns dict with keys: name, book_title, prompt_file, and optionally page_size.
    Returns None if theme not found.
    """
    # Try plan.json first
    plan_path = get_plan_path(theme_key)
    if os.path.exists(plan_path):
        with open(plan_path) as f:
            plan = json.load(f)
        result = {
            "name": plan.get("concept", theme_key),
            "book_title": plan.get("title", theme_key),
            "prompt_file": get_prompts_path(theme_key),
        }
        if plan.get("page_size"):
            result["page_size"] = plan["page_size"]
        return result

    # Fall back to legacy themes
    if theme_key in _LEGACY_THEMES:
        return _LEGACY_THEMES[theme_key]

    # Check if prompts.txt exists in output dir (theme without plan.json)
    prompts_path = get_prompts_path(theme_key)
    if os.path.exists(prompts_path):
        return {
            "name": theme_key.replace("_", " ").title(),
            "book_title": theme_key.replace("_", " ").title(),
            "prompt_file": prompts_path,
        }

    return None


def list_themes() -> list[str]:
    """List all available theme keys: legacy themes + output dirs with bookinfo.json / plan.json / prompts.txt."""
    themes = set(_LEGACY_THEMES.keys())
    if os.path.isdir(OUTPUT_DIR):
        for d in os.listdir(OUTPUT_DIR):
            theme_dir = os.path.join(OUTPUT_DIR, d)
            if os.path.isdir(theme_dir):
                if os.path.exists(os.path.join(theme_dir, "bookinfo.json")) or \
                   os.path.exists(os.path.join(theme_dir, "plan.json")) or \
                   os.path.exists(os.path.join(theme_dir, "prompts.txt")):
                    themes.add(d)
    return sorted(themes)


# Backward compatibility: THEMES dict-like object that loads dynamically
class _ThemesProxy(dict):
    """Proxy that loads themes dynamically from plan.json files."""

    def __getitem__(self, key):
        result = get_theme(key)
        if result is None:
            raise KeyError(key)
        return result

    def get(self, key, default=None):
        result = get_theme(key)
        return result if result is not None else default

    def __contains__(self, key):
        return get_theme(key) is not None

    def keys(self):
        return list_themes()

    def __iter__(self):
        return iter(list_themes())

    def __len__(self):
        return len(list_themes())


THEMES = _ThemesProxy()

# --- Base Prompt ---
BASE_PROMPT = """Create a children's coloring book page in PORTRAIT orientation (taller than wide). Requirements:
- PORTRAIT layout - the image must be taller than it is wide
- Black and white line art ONLY
- NO shading, NO gray tones, NO gradients, NO filled areas
- Thick, clean, bold outlines
- Simple enough for kids ages {age} to color
- White background
- The drawing should fill most of the page vertically
- Leave adequate spacing from edges
- Style: cute, friendly, appealing to children
- Single subject centered on page
- IMPORTANT: The illustration must NOT have any border, frame, or rectangular outline around the edges. The artwork should extend naturally with NO enclosing box or boundary line.

Subject: {subject}"""
