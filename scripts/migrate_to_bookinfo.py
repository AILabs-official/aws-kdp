#!/usr/bin/env python3
"""Migrate split plan.json + bookinfo.json + listing.md → single bookinfo.md per book.

bookinfo.md is the single source of truth for every book under output/. It
carries:
  - JSON code fence at top (pipeline-readable structured data: plan + recommended
    categories + kdp_listing block)
  - Human-readable markdown body underneath, optimized for copy/paste into
    kdp.amazon.com → Paperback → Add Title.

Usage:
  python3 scripts/migrate_to_bookinfo.py                # dry-run preview
  python3 scripts/migrate_to_bookinfo.py --apply        # write bookinfo.md files
  python3 scripts/migrate_to_bookinfo.py --apply --delete-old  # also remove plan.json / bookinfo.json / listing.md
  python3 scripts/migrate_to_bookinfo.py --apply --force        # rebuild kdp_listing block even if bookinfo.md exists

Idempotent: re-running on an already-migrated book skips it (without --force).
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
DB_PATH = ROOT / "data" / "kdp.db"

sys.path.insert(0, str(ROOT / "scripts"))
import config  # noqa: E402,F401  — provides save_bookinfo(theme_key, data) → bookinfo.md


# ---------- bookinfo.md / listing.md parsers ----------

def _slice_section(md: str, header_re: str) -> str | None:
    """Return the body text under a markdown header, until the next ## header / --- divider / EOF."""
    m = re.search(header_re, md, re.IGNORECASE | re.MULTILINE)
    if not m:
        return None
    start = m.end()
    nxt_h = re.search(r"^##\s", md[start:], re.MULTILINE)
    nxt_hr = re.search(r"^---+\s*$", md[start:], re.MULTILINE)
    candidates = [c.start() for c in (nxt_h, nxt_hr) if c]
    end = min(candidates) if candidates else len(md) - start
    body = md[start:start + end] if candidates else md[start:]
    return body.strip()


def _strip_code_fence(text: str) -> str:
    """Strip ```html ... ``` or ``` ... ``` fences if present."""
    m = re.search(r"```(?:html)?\s*\n(.*?)\n```", text, re.DOTALL)
    return m.group(1).strip() if m else text.strip()


def parse_bookinfo_md(path: Path) -> dict:
    """Best-effort parser for bookinfo.md → dict of KDP fields."""
    if not path.exists():
        return {}
    md = path.read_text(encoding="utf-8")
    out: dict = {}

    title = _slice_section(md, r"^##\s*Book Title\s*$")
    if title:
        out["title"] = title.strip()

    subtitle = _slice_section(md, r"^##\s*Subtitle\s*$")
    if subtitle:
        out["subtitle"] = subtitle.strip()

    author = _slice_section(md, r"^##\s*Author\s*$")
    if author:
        first = re.search(r"\*\*First Name\*\*\s*:\s*(.+)", author)
        last = re.search(r"\*\*Last Name\*\*\s*:\s*(.+)", author)
        if first and last:
            out["author"] = {"first_name": first.group(1).strip(), "last_name": last.group(1).strip()}

    desc = _slice_section(md, r"^##\s*Description\s*$")
    if desc:
        out["description_html"] = _strip_code_fence(desc)

    kw = _slice_section(md, r"^##\s*Keywords\s*$")
    if kw:
        keywords = []
        for line in kw.splitlines():
            m = re.match(r"\d+\.\s*(.+)", line.strip())
            if m:
                keywords.append(m.group(1).strip())
        if keywords:
            out["keywords_7"] = keywords

    print_opts = _slice_section(md, r"^##\s*Print Options\s*$")
    if print_opts:
        po: dict = {}
        for label, key in [
            (r"Ink and Paper Type", "ink_paper"),
            (r"Trim Size", "trim_size"),
            (r"Bleed Settings", "bleed"),
            (r"Paperback Cover Finish", "cover_finish"),
        ]:
            m = re.search(rf"\*\*{label}\*\*\s*:\s*(.+)", print_opts)
            if m:
                po[key] = m.group(1).strip()
        if po:
            out["print_options"] = po

    return out


def parse_listing_md(path: Path) -> dict:
    """Best-effort parser for listing.md (sudoku_logic_only_200 style) → dict."""
    if not path.exists():
        return {}
    md = path.read_text(encoding="utf-8")
    out: dict = {}

    for header_re, key in [
        (r"^##\s*Title\b", "title"),
        (r"^##\s*Subtitle\b", "subtitle"),
        (r"^##\s*Author\b", "author_str"),
    ]:
        body = _slice_section(md, header_re)
        if body:
            body = _strip_code_fence(body)
            body = re.sub(r"\*\d+\s*chars?\*", "", body).strip()
            if key == "author_str":
                out["author"] = {"first_name": body.split()[0], "last_name": " ".join(body.split()[1:])}
            else:
                out[key] = body

    desc = _slice_section(md, r"^##\s*Description")
    if desc:
        out["description_html"] = _strip_code_fence(desc)

    kw_section = _slice_section(md, r"^##\s*7?\s*Backend Keywords")
    if kw_section:
        keywords = []
        for line in kw_section.splitlines():
            m = re.match(r"\|\s*\d+\s*\|\s*(.+?)\s*\|", line.strip())
            if m:
                keywords.append(m.group(1).strip())
        if keywords:
            out["keywords_7"] = keywords[:7]

    return out


# ---------- DB fallback for listings ----------

def fetch_db_listing(theme_key: str) -> dict:
    """Pull listing from data/kdp.db if a row exists for this book."""
    if not DB_PATH.exists():
        return {}
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cur = conn.execute("""
            SELECT l.title, l.subtitle, l.description_html, l.description_plain, l.keywords,
                   l.list_price_usd, l.primary_category_bisac, l.secondary_category_bisac
            FROM listings l
            JOIN books b ON l.book_id = b.id
            WHERE b.theme_key = ?
            ORDER BY l.updated_at DESC
            LIMIT 1
        """, (theme_key,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return {}
        out: dict = {}
        if row["title"]:
            out["title"] = row["title"]
        if row["subtitle"]:
            out["subtitle"] = row["subtitle"]
        if row["description_html"] and not row["description_html"].startswith("see "):
            out["description_html"] = row["description_html"]
        kw = row["keywords"]
        if kw:
            if isinstance(kw, str):
                kw = kw.strip()
                if kw.startswith("["):
                    try:
                        kw = json.loads(kw)
                    except Exception:
                        kw = [k.strip() for k in kw.split("|")]
                elif "|" in kw:
                    kw = [k.strip() for k in kw.split("|")]
                else:
                    kw = [k.strip() for k in kw.split(",")]
            out["keywords_7"] = kw[:7]
        if row["list_price_usd"]:
            out["list_price_usd"] = row["list_price_usd"]
        return out
    except sqlite3.Error:
        return {}


# ---------- bookinfo.json builder ----------

def build_kdp_listing(plan: dict, theme_key: str, book_dir: Path) -> dict:
    """Construct the kdp_listing block from plan + sidecar md files + DB."""
    md_data = parse_bookinfo_md(book_dir / "bookinfo.md")
    listing_data = parse_listing_md(book_dir / "listing.md")
    db_data = fetch_db_listing(theme_key)

    # Priority: explicit MD > plan.json > DB > defaults
    def pick(key, *sources):
        for s in sources:
            v = s.get(key) if isinstance(s, dict) else None
            if v:
                return v
        return None

    title = pick("title", md_data, listing_data, plan, db_data)
    subtitle = pick("subtitle", md_data, listing_data, plan, db_data)

    author_obj = md_data.get("author") or listing_data.get("author")
    if not author_obj:
        plan_author = plan.get("author")
        if isinstance(plan_author, dict):
            author_obj = plan_author
        elif isinstance(plan_author, str) and plan_author:
            parts = plan_author.split(maxsplit=1)
            author_obj = {"first_name": parts[0], "last_name": parts[1] if len(parts) > 1 else ""}

    description = pick("description_html", md_data, listing_data, db_data) or plan.get("description_html") or plan.get("description_plain") or ""

    keywords = (md_data.get("keywords_7") or listing_data.get("keywords_7")
                or db_data.get("keywords_7") or plan.get("secondary_keywords") or [])
    keywords = keywords[:7] if isinstance(keywords, list) else []

    rec = plan.get("recommended_categories_2026") or {}

    audience = plan.get("audience", "") or ""
    is_kids = "kid" in audience or "children" in audience
    title_subtitle = ((title or "") + " " + (subtitle or "")).lower()
    is_large_print = (
        bool(plan.get("large_print"))
        or re.search(r"\blarge[\s-]?print\b", title_subtitle) is not None
        or re.search(r"\bextra[\s-]?large\b", title_subtitle) is not None
        or re.search(r"\bbig[\s-]?print\b", title_subtitle) is not None
        or re.search(r"\bgiant[\s-]?print\b", title_subtitle) is not None
    )

    # Reading age: derive from theme_key, audience, title/subtitle pattern "Ages N-M"
    reading_age_min, reading_age_max = None, None
    age_match = re.search(r"\bages?\s*(\d+)\s*(?:-|to|–|—)\s*(\d+)\b", title_subtitle, re.IGNORECASE)
    if age_match:
        reading_age_min, reading_age_max = int(age_match.group(1)), int(age_match.group(2))
    elif is_kids:
        reading_age_min, reading_age_max = 8, 12  # generic kid default

    print_options = md_data.get("print_options") or {
        "ink_paper": "Black & white interior with white paper",
        "trim_size": plan.get("page_size", "8.5x11").replace("x", " x ") + " in",
        "bleed": "No Bleed",
        "cover_finish": "Matte",
    }

    list_price = plan.get("list_price_usd") or db_data.get("list_price_usd") or 9.99

    kdp_listing = {
        "_intent": "Single source of truth for KDP upload form. Paste fields directly into kdp.amazon.com → Paperback → Add Title.",
        "title": title or theme_key,
        "subtitle": subtitle or "",
        "author": author_obj or {"first_name": "", "last_name": ""},
        "imprint": plan.get("imprint", ""),
        "description_html": description or "",
        "keywords_7": keywords,
        "categories_paperback_2026": {
            "primary": rec.get("primary", {}).get("kdp_path") if rec else None,
            "secondary": rec.get("secondary", {}).get("kdp_path") if rec else None,
            "tertiary": rec.get("tertiary", {}).get("kdp_path") if rec else None,
            "_full_block_with_node_ids": "see recommended_categories_2026 above for amazon_node_id + URL + weakness analysis",
        },
        "primary_audience": {
            "sexually_explicit": False,
            "low_content_book": True,  # puzzle / sudoku / activity / coloring all qualify
            "large_print_book": is_large_print,
            "reading_age_min": reading_age_min,
            "reading_age_max": reading_age_max,
            "audience_label": audience,
        },
        "print_options": print_options,
        "pricing": {
            "list_price_usd": list_price,
            "list_price_gbp": round(list_price * 0.95, 2),
            "list_price_eur": list_price,
            "list_price_cad": round(list_price * 1.35, 2),
            "list_price_aud": round(list_price * 1.60, 2),
            "_note": "Pricing matrix — adjust per current FX. KDP enforces min/max per market.",
        },
        "files": {
            "interior_pdf": "interior.pdf",
            "cover_pdf": "cover.pdf",
            "front_artwork": "front_artwork.png",
        },
        "kdp_select_enrollment": True,
        "expanded_distribution": True,
        "barcode_on_cover": False,
    }

    return kdp_listing


def migrate_book(book_dir: Path, apply: bool, delete_old: bool) -> dict:
    """Migrate a single book directory. Returns a status dict."""
    theme_key = book_dir.name
    plan_path = book_dir / "plan.json"
    bookinfo_json = book_dir / "bookinfo.json"
    bookinfo_md = book_dir / "bookinfo.md"
    legacy_bookinfo_md_human = book_dir / "bookinfo.legacy.md"  # safety: never auto-delete a hand-written human .md
    listing_md = book_dir / "listing.md"
    force = getattr(migrate_book, "_force", False)

    status = {"theme_key": theme_key, "actions": []}

    has_md = bookinfo_md.exists() and "BOOKINFO_DATA" in bookinfo_md.read_text(encoding="utf-8")[:200]
    has_json = bookinfo_json.exists()
    has_plan = plan_path.exists()

    if not (has_md or has_json or has_plan):
        status["skipped"] = "no plan.json / bookinfo.json / bookinfo.md"
        return status

    if has_md and not force:
        status["skipped"] = "already migrated (bookinfo.md exists, no --force)"
        if delete_old and apply:
            for f in (bookinfo_json, plan_path, listing_md):
                if f.exists():
                    f.unlink()
                    status["actions"].append(f"deleted {f.name}")
        return status

    # Load source plan
    if has_md:
        text = bookinfo_md.read_text(encoding="utf-8")
        m = re.search(r"```json\s*\n(.*?)\n```", text, re.DOTALL)
        plan = json.loads(m.group(1)) if m else {}
    elif has_json:
        plan = json.loads(bookinfo_json.read_text())
    else:
        plan = json.loads(plan_path.read_text())

    if "kdp_listing" not in plan or force:
        plan["kdp_listing"] = build_kdp_listing(plan, theme_key, book_dir)
        status["actions"].append("built kdp_listing block")

    if apply:
        config.save_bookinfo(theme_key, plan)
        status["actions"].append(f"wrote {bookinfo_md.name}")
        if delete_old:
            for f in (bookinfo_json, plan_path, listing_md):
                if f.exists() and f != legacy_bookinfo_md_human:
                    f.unlink()
                    status["actions"].append(f"deleted {f.name}")
    else:
        status["actions"].append(f"would write {bookinfo_md.name}")
        if delete_old:
            for f in (bookinfo_json, plan_path, listing_md):
                if f.exists():
                    status["actions"].append(f"would delete {f.name}")

    return status


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="actually write changes (default: dry-run)")
    ap.add_argument("--delete-old", action="store_true", help="remove plan.json / bookinfo.md / listing.md after successful migration")
    ap.add_argument("--book", help="only migrate this theme_key (default: all)")
    ap.add_argument("--force", action="store_true", help="rebuild kdp_listing block even if bookinfo.json already exists")
    args = ap.parse_args()
    migrate_book._force = args.force

    if not OUTPUT_DIR.is_dir():
        print(f"output/ not found: {OUTPUT_DIR}", file=sys.stderr)
        return 1

    if args.book:
        targets = [OUTPUT_DIR / args.book]
    else:
        targets = sorted(d for d in OUTPUT_DIR.iterdir() if d.is_dir())

    print(f"{'APPLY' if args.apply else 'DRY-RUN'} — {len(targets)} books to scan")
    print(f"delete_old = {args.delete_old}\n")

    for book_dir in targets:
        result = migrate_book(book_dir, apply=args.apply, delete_old=args.delete_old)
        if "skipped" in result:
            print(f"  [skip] {result['theme_key']}: {result['skipped']}")
            for a in result.get("actions", []):
                print(f"         · {a}")
        else:
            print(f"  [ok]   {result['theme_key']}")
            for a in result["actions"]:
                print(f"         · {a}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
