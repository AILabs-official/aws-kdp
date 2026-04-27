#!/usr/bin/env python3
"""KDP Category Finder — discover Amazon book categories where the #1 bestseller is weak.

Strategy:
  1. Search Amazon for a seed keyword inside a book_type bucket (coloring, sudoku, ...).
  2. From the top N organic products' bestsellersRank arrays, harvest every leaf
     sub-category they appear in.
  3. For each unique sub-category, fetch the #1 bestseller (1-item bestseller list call).
  4. Convert #1's BSR → daily sales → monthly royalty using kdp_config math.
  5. Rank categories ascending by monthly_royalty_mid (lowest = weakest #1 = easiest target)
     and persist to data/categories/ + categories table in data/kdp.db.

Data source priority (mirrors niche-hunter):
  Tier 1: Apify junglee/Amazon-crawler (when APIFY_API_TOKEN set)
  Tier 2: WebSearch fallback (less reliable; flagged in output)

Commands:
  scan <keyword> --book-type <type>     — full pipeline (discover + analyze + persist)
  list [--seed-keyword X] [--limit N]   — show ranked categories from DB
  show <category_id>                    — full row
  rank --book-type <type> --limit N     — show easiest-target leaf categories across DB

Examples:
  python3 scripts/category_finder.py scan "mandala coloring" --book-type coloring
  python3 scripts/category_finder.py scan "sudoku large print" --book-type sudoku --max-products 15
  python3 scripts/category_finder.py rank --book-type coloring --limit 20
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path
from typing import Any
from urllib import error, parse, request

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from env_loader import env  # type: ignore
from kdp_config import bsr_to_daily_sales, estimate_monthly_royalty  # type: ignore

# ────────────────────────────────────────────────────────
# Paths + constants
# ────────────────────────────────────────────────────────

ROOT = HERE.parent
DB_PATH = ROOT / "data" / "kdp.db"
RAW_DIR = ROOT / "data" / "categories" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

APIFY_BASE = "https://api.apify.com/v2"
DEFAULT_ACTOR = "junglee~Amazon-crawler"

DEFAULT_PRICE_USD = 9.99       # default list price assumption when product price is missing
DEFAULT_PAGE_COUNT = 100       # default page count assumption when missing

BOOK_TYPE_CHOICES = ("coloring", "low_content", "activity", "sudoku", "journal", "puzzle", "any")

# ─────────────────────────────────────────────────────────────
# WEAKNESS METRIC — "Cách B" (cross-leaf rank signal)
# ─────────────────────────────────────────────────────────────
# A leaf L is "easy to dethrone" when L's #1 product P holds rank=1 in L
# but is buried (rank > THRESHOLD) in the OTHER leaves it's listed in.
# Rationale: if P can't crack 50k in any sibling leaf, P only wins L because
# L itself has very thin competition — a new well-listed entrant can take #1.
#
# Metric: max_other_leaf_rank = max(rank for rank in P.bestsellerRanks
#                                   if category not in {"Books", L})
# - max_other_leaf_rank > 50_000 → EASY  (P is buried elsewhere → L is thin)
# - 10_001..50_000              → MODERATE
# - 1_001..10_000               → HARD
# - ≤ 1_000                     → VERY_HARD (P is strong everywhere)
# - None (no other leafs)       → UNKNOWN

WEAKNESS_THRESHOLD_DEFAULT = 50_000

WEAKNESS_TIERS_OTHER_LEAF = [
    (50_001, 99_999_999_999, "EASY"),
    (10_001, 50_000, "MODERATE"),
    (1_001, 10_000, "HARD"),
    (0, 1_000, "VERY_HARD"),
]


def _weakness(max_other_leaf_rank: int | None) -> str:
    if max_other_leaf_rank is None:
        return "UNKNOWN"
    for lo, hi, label in WEAKNESS_TIERS_OTHER_LEAF:
        if lo <= max_other_leaf_rank <= hi:
            return label
    return "UNKNOWN"


# ────────────────────────────────────────────────────────
# Apify wrapper (Tier 1)
# ────────────────────────────────────────────────────────

def _apify_token() -> str | None:
    return env("APIFY_API_TOKEN")


def _actor_run_sync(payload: dict, timeout: int = 240) -> list[dict]:
    token = _apify_token()
    if not token:
        raise RuntimeError("APIFY_API_TOKEN not set; cannot use Apify tier")
    actor = env("APIFY_DEFAULT_ACTOR", DEFAULT_ACTOR).replace("/", "~")
    url = f"{APIFY_BASE}/acts/{actor}/run-sync-get-dataset-items?token={token}"
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        msg = exc.read().decode("utf-8", errors="replace")
        print(f"❌ Apify HTTP {exc.code}: {msg[:300]}", file=sys.stderr)
        raise
    except error.URLError as exc:
        print(f"❌ Apify network error: {exc}", file=sys.stderr)
        raise


def apify_search(keyword: str, max_items: int = 20, scrape_details: bool = True) -> list[dict]:
    """Search Amazon for a keyword in the Books category, return product list with details."""
    encoded = parse.quote_plus(keyword)
    payload = {
        # i=stripbooks restricts the search to the Books department, which gives us
        # category breadcrumbs that are book-tree leafs (not generic merch).
        "categoryOrProductUrls": [
            {"url": f"https://www.amazon.com/s?k={encoded}&i=stripbooks"}
        ],
        "maxItemsPerStartUrl": max_items,
        "scrapeProductVariantPrices": False,
        "scrapeProductDetails": scrape_details,
        "useCaptchaSolver": False,
    }
    return _actor_run_sync(payload)


def apify_bestseller_top1(category_url: str) -> dict | None:
    """Fetch the #1 product from a bestsellers category URL."""
    payload = {
        "categoryOrProductUrls": [{"url": category_url}],
        "maxItemsPerStartUrl": 1,
        "scrapeProductDetails": True,
    }
    items = _actor_run_sync(payload, timeout=180)
    return items[0] if items else None


def apify_product(asin: str) -> dict | None:
    """Fetch full product details for one ASIN."""
    payload = {
        "categoryOrProductUrls": [{"url": f"https://www.amazon.com/dp/{asin}"}],
        "maxItemsPerStartUrl": 1,
        "scrapeProductDetails": True,
    }
    items = _actor_run_sync(payload, timeout=120)
    return items[0] if items else None


# ────────────────────────────────────────────────────────
# Field extraction (junglee actor responses vary by version)
# ────────────────────────────────────────────────────────

def _to_int(val: Any) -> int | None:
    if val is None:
        return None
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    s = str(val).replace(",", "").replace("#", "").strip()
    m = re.search(r"-?\d+", s)
    return int(m.group()) if m else None


def _to_float(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace(",", "").replace("$", "").strip()
    m = re.search(r"-?\d+(\.\d+)?", s)
    return float(m.group()) if m else None


def extract_max_other_leaf_rank(item: dict, leaf_name: str) -> tuple[int | None, str | None]:
    """Cross-leaf weakness signal (Cách B).

    Among the item's bestsellerRanks, exclude the OVERALL "Books" entry and
    the leaf the item is being scored as #1 of (leaf_name). From what's left,
    return (max_rank, category_name_at_that_rank).

    Interpretation: a high max means this product is buried deep in some
    sibling/cousin leaf — i.e. it only wins leaf_name because leaf_name is
    thin. (None, None) means no other leaves were listed → unknown signal.
    """
    leaf_lower = (leaf_name or "").strip().lower()
    best_rank: int | None = None
    best_cat: str | None = None
    for key in ("bestsellerRanks", "bestsellersRank", "bestSellersRank"):
        val = item.get(key)
        if not isinstance(val, list):
            continue
        for entry in val:
            if not isinstance(entry, dict):
                continue
            cat = entry.get("category") or entry.get("Category")
            if not cat:
                continue
            cat = str(cat).strip()
            cat_lower = cat.lower()
            # Exclude the OVERALL Books rank (used for revenue math elsewhere).
            if cat_lower == "books":
                continue
            # Exclude the leaf we're scoring (rank in own leaf is 1 by construction).
            parts = [p.strip() for p in cat.split(">") if p.strip()]
            this_leaf = (parts[-1] if parts else cat).lower()
            if this_leaf == leaf_lower:
                continue
            rank = _to_int(entry.get("rank") or entry.get("Rank"))
            if not rank:
                continue
            if best_rank is None or rank > best_rank:
                best_rank = rank
                best_cat = parts[-1] if parts else cat
    return best_rank, best_cat


def extract_overall_bsr(item: dict) -> int | None:
    """Get the OVERALL Books rank (the one used for revenue math)."""
    for key in ("bestsellerRanks", "bestsellersRank", "bsr", "bestSellersRank"):
        val = item.get(key)
        if val is None:
            continue
        if isinstance(val, int):
            return val
        if isinstance(val, str):
            n = _to_int(val)
            if n:
                return n
        if isinstance(val, list) and val:
            for entry in val:
                if isinstance(entry, dict):
                    cat = (entry.get("category") or entry.get("Category") or "").lower()
                    if "books" in cat and ">" not in cat:
                        rank = entry.get("rank") or entry.get("Rank")
                        n = _to_int(rank)
                        if n:
                            return n
            first = val[0]
            if isinstance(first, dict):
                rank = first.get("rank") or first.get("Rank")
                n = _to_int(rank)
                if n:
                    return n
    return None


_NODE_ID_RE = re.compile(r"/(?:gp/bestsellers|zgbs)/books/(\d+)")


def normalize_zgbs_url(raw_url: str | None) -> tuple[str | None, str | None]:
    """Extract the Amazon node ID and return (fetchable_url, node_id).

    junglee/Amazon-crawler (current build) only accepts /s (search) and /dp
    (product) URLs — it rejects both /gp/bestsellers/books/<id>/ and
    /Best-Sellers-Books/zgbs/books/<id> with "INVALID START URL". So we
    convert the bestseller URL into a search-restricted-to-node URL sorted
    by salesrank, which the actor accepts and which returns the same #1.
    """
    if not raw_url:
        return None, None
    m = _NODE_ID_RE.search(raw_url)
    if not m:
        return raw_url, None
    node = m.group(1)
    return (
        f"https://www.amazon.com/s?i=stripbooks&rh=n%3A{node}&s=salesrank",
        node,
    )


def extract_categories(item: dict) -> list[dict]:
    """Pull every sub-category breadcrumb the item ranks in.

    Returns list of {name, breadcrumb, rank, url, node_id}. URL is normalized to
    the canonical zgbs form so junglee/Amazon-crawler accepts it.
    """
    out: list[dict] = []
    for key in ("bestsellerRanks", "bestsellersRank", "bestSellersRank"):
        val = item.get(key)
        if not isinstance(val, list):
            continue
        for entry in val:
            if not isinstance(entry, dict):
                continue
            cat = entry.get("category") or entry.get("Category")
            if not cat:
                continue
            cat = str(cat).strip()
            # The OVERALL "Books" entry is the revenue-math BSR — skip as a leaf.
            if cat.lower() == "books":
                continue
            # Most leaf entries look like "Books > Crafts > Coloring Books > Mandala".
            parts = [p.strip() for p in cat.split(">") if p.strip()]
            leaf = parts[-1] if parts else cat
            rank = _to_int(entry.get("rank") or entry.get("Rank"))
            raw_url = entry.get("url") or entry.get("URL") or entry.get("categoryUrl")
            url, node_id = normalize_zgbs_url(raw_url)
            out.append({
                "name": leaf,
                "breadcrumb": " > ".join(parts) if parts else cat,
                "rank": rank,
                "url": url,
                "node_id": node_id,
            })
    return out


# ────────────────────────────────────────────────────────
# DB helpers (sqlite3 direct — db.py CLI is JSON-payload heavy)
# ────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def upsert_category(row: dict) -> int:
    """Insert or update a category row. Conflict key is (name, seed_book_type)."""
    cols = list(row.keys())
    placeholders = ", ".join("?" for _ in cols)
    update_clause = ", ".join(f"{c}=excluded.{c}" for c in cols if c not in ("name", "seed_book_type"))
    sql = (
        f"INSERT INTO categories ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT(name, seed_book_type) DO UPDATE SET {update_clause}, scanned_at=CURRENT_TIMESTAMP"
    )
    conn = _conn()
    cur = conn.execute(sql, tuple(row.values()))
    conn.commit()
    if cur.lastrowid:
        return cur.lastrowid
    # On UPDATE, lastrowid is 0 — re-query.
    found = conn.execute(
        "SELECT id FROM categories WHERE name = ? AND COALESCE(seed_book_type,'') = COALESCE(?,'')",
        (row["name"], row.get("seed_book_type")),
    ).fetchone()
    return found["id"] if found else 0


# ────────────────────────────────────────────────────────
# Pipeline
# ────────────────────────────────────────────────────────

def scan(keyword: str, book_type: str, max_products: int,
         dry_run: bool = False) -> list[dict]:
    """Full pipeline. Returns list of category dicts written/would-write."""
    if not _apify_token():
        print("❌ APIFY_API_TOKEN not set. WebSearch fallback not implemented yet.", file=sys.stderr)
        print("   Set APIFY_API_TOKEN in .env (mirrors niche-hunter Tier 1).", file=sys.stderr)
        sys.exit(2)

    print(f"🔎 Searching Amazon Books for: '{keyword}' (top {max_products}, type={book_type})")
    products = apify_search(keyword, max_items=max_products, scrape_details=True)
    print(f"   → {len(products)} products returned")

    if not products:
        print("⚠️  No products returned. Try a broader keyword.")
        return []

    # Save raw response for audit trail.
    today = date.today().isoformat()
    slug = re.sub(r"[^a-z0-9]+", "_", keyword.lower()).strip("_")[:60]
    raw_path = RAW_DIR / f"{today}_{slug}.json"
    with raw_path.open("w") as f:
        json.dump({"keyword": keyword, "book_type": book_type, "products": products}, f, indent=2)
    print(f"   📁 Raw saved → {raw_path.relative_to(ROOT)}")

    # Aggregate categories across all products. For each leaf category, track:
    #   - the seed product with the LOWEST rank-in-category (closest to #1)
    #   - that product's overall BSR (which IS #1's BSR when rank-in-cat == 1,
    #     or an upper bound on #1's BSR when rank-in-cat > 1)
    cat_map: dict[str, dict] = {}
    for prod in products:
        prod_overall_bsr = extract_overall_bsr(prod)
        cats = extract_categories(prod)
        for c in cats:
            key = c["name"].lower()
            slot = cat_map.setdefault(key, {
                "name": c["name"],
                "breadcrumb": c["breadcrumb"],
                "node_ids": set(),
                "best_rank_in_cat": None,
                "best_product": None,
                "best_product_bsr": None,
                "product_count": 0,
            })
            if c.get("node_id"):
                slot["node_ids"].add(c["node_id"])
            slot["product_count"] += 1
            r = c.get("rank")
            if r and (slot["best_rank_in_cat"] is None or r < slot["best_rank_in_cat"]):
                slot["best_rank_in_cat"] = r
                slot["best_product"] = prod
                slot["best_product_bsr"] = prod_overall_bsr

    if not cat_map:
        print("⚠️  No category breadcrumbs found in product details. Apify actor may need updating.")
        return []

    print(f"   📚 {len(cat_map)} unique sub-categories surfaced")
    print(f"   ↳ using seed-product rank-in-category as proxy for #1 BSR")
    print(f"     (rank=1 → exact #1; rank>1 → upper bound on #1 BSR)")

    rows: list[dict] = []
    for i, (key, data) in enumerate(cat_map.items(), start=1):
        name = data["name"]
        breadcrumb = data["breadcrumb"]
        node_id = next(iter(data["node_ids"]), None)
        bestseller_url = (
            f"https://www.amazon.com/Best-Sellers-Books/zgbs/books/{node_id}"
            if node_id else None
        )
        best_rank = data["best_rank_in_cat"]
        best_prod = data["best_product"]
        seed_bsr = data["best_product_bsr"]

        top_asin = top_title = top_publish = None
        top_bsr = top_pages = top_reviews = None
        top_price = top_rating = None
        royalty_mid = daily_mid = None
        weakness = "UNKNOWN"
        notes_parts: list[str] = []

        if best_prod and seed_bsr and best_rank:
            top_asin = best_prod.get("asin") or best_prod.get("ASIN")
            top_title = best_prod.get("title") or best_prod.get("Title")
            top_pages = _to_int(best_prod.get("numberOfPages") or best_prod.get("pageCount") or best_prod.get("pages"))
            price_obj = best_prod.get("price") or best_prod.get("listPrice")
            if isinstance(price_obj, dict):
                top_price = _to_float(price_obj.get("value"))
            else:
                top_price = _to_float(price_obj)
            top_rating = _to_float(best_prod.get("stars") or best_prod.get("rating"))
            top_reviews = _to_int(best_prod.get("reviewsCount") or best_prod.get("reviews"))
            top_publish = best_prod.get("publicationDate") or best_prod.get("publishDate")

            if best_rank == 1:
                # Confirmed: this seed product IS #1 in the category.
                top_bsr = seed_bsr
                notes_parts.append("seed_is_#1")
            else:
                # Seed is at rank N > 1. We don't have #1's BSR directly, but
                # by definition #1 has a SMALLER overall BSR than position N.
                # Record seed's rank as a comparison anchor; mark BSR as upper bound.
                top_bsr = seed_bsr  # upper bound: #1's BSR ≤ this
                notes_parts.append(f"seed_rank_in_cat={best_rank}_bsr_is_upper_bound")

            price_for_math = top_price if top_price and top_price >= 5.99 else DEFAULT_PRICE_USD
            pages_for_math = top_pages if top_pages and top_pages > 0 else DEFAULT_PAGE_COUNT
            sales = bsr_to_daily_sales(top_bsr)
            daily_mid = sales["mid"]
            royalty = estimate_monthly_royalty(top_bsr, price_for_math, pages_for_math, color=False)
            royalty_mid = royalty["monthly_mid_usd"]
            # Weakness via cross-leaf signal (Cách B): how buried is the #1 in
            # OTHER leaves it ranks in? High max_rank in others → this leaf is thin.
            max_other_rank, anchor_cat = extract_max_other_leaf_rank(best_prod, name)
            weakness = _weakness(max_other_rank)
            if max_other_rank is not None:
                notes_parts.append(f"max_other_leaf_rank={max_other_rank:,}@{anchor_cat}")
            else:
                notes_parts.append("only_leaf_listed")
            if not top_price or top_price < 5.99:
                notes_parts.append(f"price_default=${price_for_math}")
            if not top_pages:
                notes_parts.append(f"pages_default={pages_for_math}")
        else:
            notes_parts.append("no_seed_with_rank_in_this_category")

        row = {
            "node_id": node_id,
            "name": name,
            "breadcrumb": breadcrumb,
            "bestseller_url": bestseller_url,
            "top_asin": top_asin,
            "top_title": top_title,
            "top_bsr": top_bsr,
            "top_price_usd": top_price,
            "top_pages": top_pages,
            "top_rating_avg": top_rating,
            "top_reviews_count": top_reviews,
            "top_publish_date": top_publish,
            "top_daily_sales_mid": daily_mid,
            "top_monthly_royalty_usd": royalty_mid,
            "weakness_label": weakness,
            "seed_keyword": keyword,
            "seed_book_type": book_type,
            "source": "apify:junglee/amazon-crawler",
            "raw_json_path": str(raw_path.relative_to(ROOT)),
            "notes": "; ".join(notes_parts) if notes_parts else None,
        }

        if not dry_run:
            cat_id = upsert_category(row)
            row["id"] = cat_id

        rows.append(row)

    # Sort weakest-first for display.
    rows.sort(key=lambda r: (r["top_monthly_royalty_usd"] is None, r.get("top_monthly_royalty_usd") or 0))

    print()
    print(f"📊 Ranking ({len(rows)} categories) — weakest #1 first")
    print(f"   {'#':<3} {'Weak':<10} {'BSR':>10} {'$/mo':>10}  Category")
    for i, r in enumerate(rows, start=1):
        bsr = r["top_bsr"] or 0
        roy = r["top_monthly_royalty_usd"] or 0
        weak = r["weakness_label"] or "—"
        print(f"   {i:<3} {weak:<10} {bsr:>10,} {roy:>10,.0f}  {r['breadcrumb'][:60]}")

    if dry_run:
        print()
        print("   (dry-run: nothing written to DB)")
    else:
        print()
        print(f"   ✅ {len(rows)} rows written to data/kdp.db → categories")
    return rows


# ────────────────────────────────────────────────────────
# Read commands
# ────────────────────────────────────────────────────────

def cmd_list(args):
    conn = _conn()
    where = []
    params: list[Any] = []
    if args.seed_keyword:
        where.append("seed_keyword = ?")
        params.append(args.seed_keyword)
    if args.book_type and args.book_type != "any":
        where.append("seed_book_type = ?")
        params.append(args.book_type)
    sql = "SELECT * FROM categories"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY (top_monthly_royalty_usd IS NULL), top_monthly_royalty_usd ASC LIMIT ?"
    params.append(args.limit)
    rows = conn.execute(sql, tuple(params)).fetchall()
    if not rows:
        print("(empty)")
        return
    print(f"{'ID':<5} {'Weak':<10} {'BSR':>10} {'$/mo':>10}  {'Type':<12}  Category")
    for r in rows:
        weak = r["weakness_label"] or "—"
        bsr = r["top_bsr"] or 0
        roy = r["top_monthly_royalty_usd"] or 0
        bt = r["seed_book_type"] or "—"
        print(f"{r['id']:<5} {weak:<10} {bsr:>10,} {roy:>10,.0f}  {bt:<12}  {(r['breadcrumb'] or r['name'])[:60]}")


def cmd_show(args):
    conn = _conn()
    row = conn.execute("SELECT * FROM categories WHERE id = ?", (args.category_id,)).fetchone()
    if not row:
        print(f"category id={args.category_id} not found")
        sys.exit(1)
    print(json.dumps(dict(row), indent=2, default=str))


def cmd_rank(args):
    conn = _conn()
    where = ""
    params: list[Any] = []
    if args.book_type and args.book_type != "any":
        where = " WHERE seed_book_type = ?"
        params.append(args.book_type)
    sql = (
        f"SELECT id, name, breadcrumb, seed_book_type, top_bsr, top_monthly_royalty_usd, weakness_label, top_asin "
        f"FROM categories{where} "
        f"WHERE top_bsr IS NOT NULL AND top_monthly_royalty_usd IS NOT NULL "
        f"ORDER BY top_monthly_royalty_usd ASC LIMIT ?"
    )
    if where:
        sql = sql.replace("WHERE top_bsr", "AND top_bsr")
    params.append(args.limit)
    rows = conn.execute(sql, tuple(params)).fetchall()
    if not rows:
        print("No scored categories yet. Run: scan <keyword> --book-type <type>")
        return
    print(f"🥇 Easiest-target categories ({args.book_type or 'all types'})")
    print(f"   {'#':<3} {'Weak':<10} {'BSR':>10} {'$/mo':>10}  ASIN          Category")
    for i, r in enumerate(rows, start=1):
        weak = r["weakness_label"] or "—"
        bsr = r["top_bsr"] or 0
        roy = r["top_monthly_royalty_usd"] or 0
        asin = r["top_asin"] or "—"
        path = r["breadcrumb"] or r["name"]
        print(f"   {i:<3} {weak:<10} {bsr:>10,} {roy:>10,.0f}  {asin:<13} {path[:60]}")


def cmd_scan(args):
    scan(
        keyword=args.keyword,
        book_type=args.book_type,
        max_products=args.max_products,
        dry_run=args.dry_run,
    )


# ────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(prog="category_finder", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="Discover + analyze categories from a seed keyword")
    s.add_argument("keyword", help="Seed search term, eg 'mandala coloring'")
    s.add_argument("--book-type", choices=BOOK_TYPE_CHOICES, default="any")
    s.add_argument("--max-products", type=int, default=20,
                   help="How many top organic products to harvest categories from (default 20)")
    s.add_argument("--dry-run", action="store_true", help="Don't write to DB")
    s.set_defaults(func=cmd_scan)

    l = sub.add_parser("list", help="List previously scanned categories")
    l.add_argument("--seed-keyword")
    l.add_argument("--book-type", choices=BOOK_TYPE_CHOICES)
    l.add_argument("--limit", type=int, default=30)
    l.set_defaults(func=cmd_list)

    sh = sub.add_parser("show", help="Show full row for one category id")
    sh.add_argument("category_id", type=int)
    sh.set_defaults(func=cmd_show)

    r = sub.add_parser("rank", help="Top-N easiest-target categories across DB")
    r.add_argument("--book-type", choices=BOOK_TYPE_CHOICES)
    r.add_argument("--limit", type=int, default=20)
    r.set_defaults(func=cmd_rank)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
