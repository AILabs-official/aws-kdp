"""One-off: re-fetch actual top-1 product per category node and update DB rows.

Uses the search-restricted-to-node URL form that the Apify actor accepts:
  https://www.amazon.com/s?i=stripbooks&rh=n:<node>&s=salesrank

Updates: top_asin, top_title, top_bsr, top_price_usd, top_pages, top_rating_avg,
top_reviews_count, top_publish_date, top_daily_sales_mid, top_monthly_royalty_usd,
weakness_label, notes.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from category_finder import (  # type: ignore
    DEFAULT_PAGE_COUNT,
    DEFAULT_PRICE_USD,
    _to_float,
    _to_int,
    _weakness,
    extract_overall_bsr,
)
from env_loader import env  # type: ignore
from kdp_config import bsr_to_daily_sales, estimate_monthly_royalty  # type: ignore

DB_PATH = HERE.parent / "data" / "kdp.db"
TOKEN = env("APIFY_API_TOKEN")
ACTOR = env("APIFY_DEFAULT_ACTOR", "junglee~Amazon-crawler").replace("/", "~")
APIFY_URL = f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items?token={TOKEN}"


def fetch_top1(node_id: str) -> dict | None:
    url = f"https://www.amazon.com/s?i=stripbooks&rh=n%3A{node_id}&s=salesrank"
    payload = {
        "categoryOrProductUrls": [{"url": url}],
        "maxItemsPerStartUrl": 1,
        "scrapeProductDetails": True,
        "useCaptchaSolver": False,
    }
    req = urllib.request.Request(
        APIFY_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=240) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data[0] if data else None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:200]
        print(f"   HTTP {exc.code} for node {node_id}: {body}", file=sys.stderr)
        return None
    except Exception as exc:
        print(f"   error for node {node_id}: {exc}", file=sys.stderr)
        return None


def process(row: sqlite3.Row) -> dict:
    node = row["node_id"]
    rec = {
        "id": row["id"],
        "name": row["name"],
        "node_id": node,
        "ok": False,
    }
    item = fetch_top1(node)
    if not item:
        rec["error"] = "no_item_returned"
        return rec
    asin = item.get("asin")
    title = item.get("title")
    overall_bsr = extract_overall_bsr(item)
    pages = _to_int(item.get("numberOfPages") or item.get("pageCount") or item.get("pages"))
    price_obj = item.get("price") or item.get("listPrice")
    price = _to_float(price_obj.get("value")) if isinstance(price_obj, dict) else _to_float(price_obj)
    rating = _to_float(item.get("stars") or item.get("rating"))
    reviews = _to_int(item.get("reviewsCount") or item.get("reviews"))
    publish = item.get("publicationDate") or item.get("publishDate")

    notes_parts = ["verified_via_salesrank_search"]
    if not pages:
        pages_for_math = DEFAULT_PAGE_COUNT
        notes_parts.append(f"pages_default={pages_for_math}")
    else:
        pages_for_math = pages
    if not price or price < 5.99:
        price_for_math = DEFAULT_PRICE_USD
        notes_parts.append(f"price_default=${price_for_math}")
    else:
        price_for_math = price

    daily_mid = royalty_mid = None
    weakness = "UNKNOWN"
    if overall_bsr:
        sales = bsr_to_daily_sales(overall_bsr)
        daily_mid = sales["mid"]
        royalty = estimate_monthly_royalty(overall_bsr, price_for_math, pages_for_math, color=False)
        royalty_mid = royalty["monthly_mid_usd"]
        weakness = _weakness(royalty_mid)

    rec.update({
        "ok": True,
        "asin": asin,
        "title": title,
        "bsr": overall_bsr,
        "price": price,
        "pages": pages,
        "rating": rating,
        "reviews": reviews,
        "publish": publish,
        "daily_mid": daily_mid,
        "royalty_mid": royalty_mid,
        "weakness": weakness,
        "notes": "; ".join(notes_parts),
    })
    return rec


def main():
    conn = sqlite3.connect(DB_PATH, timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")

    rows = conn.execute("""
        SELECT id, name, node_id FROM categories
        WHERE seed_book_type='sudoku' AND node_id IS NOT NULL
        ORDER BY id
    """).fetchall()
    print(f"Verifying {len(rows)} sudoku categories...")

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(process, r): r for r in rows}
        for fut in as_completed(futures):
            r = fut.result()
            results.append(r)
            tag = "OK " if r["ok"] else "FAIL"
            extra = (
                f"BSR={r.get('bsr'):>10,} weak={r.get('weakness')}"
                if r["ok"] and r.get("bsr") else r.get("error", "")
            )
            print(f"  {tag} id={r['id']:<3} node={r['node_id']:<14} {(r['name'] or '')[:34]:<35} {extra}")

    # Persist
    updated = 0
    for r in results:
        if not r["ok"]:
            continue
        conn.execute(
            """UPDATE categories SET
                top_asin=?, top_title=?, top_bsr=?, top_price_usd=?, top_pages=?,
                top_rating_avg=?, top_reviews_count=?, top_publish_date=?,
                top_daily_sales_mid=?, top_monthly_royalty_usd=?,
                weakness_label=?, notes=?, scanned_at=CURRENT_TIMESTAMP,
                bestseller_url=?
              WHERE id=?""",
            (
                r["asin"], r["title"], r["bsr"], r["price"], r["pages"],
                r["rating"], r["reviews"], r["publish"],
                r["daily_mid"], r["royalty_mid"],
                r["weakness"], r["notes"],
                f"https://www.amazon.com/s?i=stripbooks&rh=n%3A{r['node_id']}&s=salesrank",
                r["id"],
            ),
        )
        updated += 1
    print(f"\n✅ Updated {updated} rows in DB")


if __name__ == "__main__":
    main()
