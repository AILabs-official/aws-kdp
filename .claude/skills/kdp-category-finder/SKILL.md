---
name: kdp-category-finder
description: "Find Amazon KDP sub-categories where the #1 bestseller is weak (low BSR/sales) — easy bestseller targets. Crawls Amazon's 19,000+ category tree from a seed keyword + book_type, fetches the #1 bestseller per leaf, computes BSR → daily sales → monthly royalty via kdp_config math, ranks weakest-first, and persists to data/kdp.db (categories table). USE WHEN user says: tim category, find category, category search, sub category, dive into amazon categories, weak bestseller, easy bestseller, dethrone bestseller, kdp category, bsr category, easiest category, where to rank, find subcategory."
user-invocable: true
---

# KDP Category Finder — find weak sub-categories where #1 is easy to dethrone

You are the **Category Finder** for KDP OS. Your job is to mine Amazon's category tree and surface **leaf sub-categories where the #1 bestseller has weak revenue** — so the operator can list a new book directly into that sub-category and have a realistic shot at the #1 (Best Seller) badge.

This is a **research-only skill** — it never writes a listing or launches ads. Output is ranked categories + revenue math, persisted to `data/kdp.db.categories`.

---

## How to use

```
/kdp-category-finder scan <keyword> --book-type <type>     # full pipeline
/kdp-category-finder list [--seed-keyword X] [--limit N]   # show cached categories
/kdp-category-finder rank --book-type <type> --limit N     # top easiest-target leafs across DB
/kdp-category-finder show <category_id>                    # full DB row
```

`book_type` ∈ `{coloring, low_content, activity, sudoku, journal, puzzle, any}` — same vocabulary as `niche-hunter`.

---

## ⛳ STEP 0: Confirm data tier

Same 3-tier strategy as `niche-hunter`. Check before running anything:

```bash
grep -q "^APIFY_API_TOKEN=[^[:space:]]" .env && echo "APIFY ACTIVE" || echo "WEBSEARCH FALLBACK"
```

- **Apify ACTIVE** → use `python3 scripts/category_finder.py scan ...` directly (Tier 1).
- **WEBSEARCH FALLBACK** → not yet implemented for this skill. Tell the user to set `APIFY_API_TOKEN` in `.env`. Don't fake numbers.

---

## 🔬 6-STEP PIPELINE

The wrapped script does steps 2–5 in one call. You stay involved at steps 1 and 6.

### STEP 1 — Clarify seed (if user is vague)

If the user only says "find me a weak category" with no keyword, ask:
- What **keyword** seeds the search? (eg `mandala coloring`, `large print sudoku`, `gratitude journal`)
- What **book_type**? (coloring / sudoku / activity / low_content / journal / puzzle)
- How many top products to harvest categories from? (default 20, range 10–30)

If user gives only a niche/topic, infer book_type from the niche-hunter detection table (coloring/low_content/activity).

### STEP 2 — Run the scan

```bash
python3 scripts/category_finder.py scan "<keyword>" --book-type <type> --max-products 20
```

What this does internally (single Apify call, deterministic):
1. Apify `junglee/Amazon-crawler` search Amazon Books (`/s?k=<kw>&i=stripbooks`) for top N
   products with `scrapeProductDetails=True`.
2. From each product's `bestsellerRanks` array, extract every leaf sub-category +
   the product's rank-in-that-category + overall Books BSR.
3. For each unique leaf category, find the seed product with the **lowest rank-in-category**
   (closest to #1). That product's overall BSR is:
   - `seed_is_#1` when rank-in-cat = 1 → this IS #1's exact BSR
   - `seed_rank_in_cat=N_bsr_is_upper_bound` when rank-in-cat > 1 → #1's BSR is ≤ this value
4. Compute `bsr_to_daily_sales(top_bsr).mid` and `estimate_monthly_royalty(...)` from `kdp_config.py`.
5. Label `weakness`: `EASY` (≤$300/mo), `MODERATE` (≤$1.5k), `HARD` (≤$5k), `VERY_HARD` (>$5k).
6. Upsert each row into `data/kdp.db.categories` (conflict key = `name + seed_book_type`).
7. Save raw response → `data/categories/raw/<YYYY-MM-DD>_<slug>.json` for audit.

**Why no separate bestseller fetch?** Tested all four community Amazon-bestsellers Apify
actors (junglee/amazon-bestsellers, amazon-scraper/amazon-bestsellers-scraper, etc.) — each
either rejected zgbs URLs or silently returned the global Best Sellers list (TurboTax,
Topps cards) instead of honoring the leaf node ID. Junglee/Amazon-crawler refuses zgbs URLs
outright. The in-search aggregation above gets us the same #1 BSR data **for any category
where one of our seed products is #1**, which is exactly the actionable case (we already
publish books that match the keyword, so we want to know which leafs we can dominate).
For categories where no seed is #1, we record the upper bound and flag it in `notes`.

### STEP 3 — Read the ranked output

The script prints categories sorted **weakest #1 first**. EASY rows = the operator can probably hit #1 with one well-listed book. VERY_HARD rows = competitors running for years; skip unless we want to fight.

### STEP 4 — Sanity-check the top-3 EASY rows

For each EASY/MODERATE candidate the user is excited about:
- Re-fetch the leaf bestseller list with `--max-products` extended to 5 if you want depth (manual call).
- Verify the breadcrumb is a **legitimate KDP-allowed BISAC sub-category** — Amazon has ranks for things like "Calendars" or "Audible" that we can't actually target. Spot-check the `breadcrumb` against the BISAC tree before recommending.
- Look for trademark-name in the breadcrumb (eg "Star Wars Coloring") — those leafs are infested with licensed product, our generic book won't rank.

### STEP 5 — Cross-check with niche-hunter

If a category looks easy, check whether the same keyword has already been killed:

```bash
python3 scripts/db.py niches list --status KILLED --limit 50 | grep -i "<keyword>"
```

If yes — surface the kill reason to the user. Easy category + dead niche = false positive.

### STEP 6 — Hand off

Don't auto-launch a book. Output for the operator:

```
🥇 Recommended categories (weakest #1, EASY tier)
1. Books > Crafts > Coloring > Mandala > Animal Mandalas
   #1 ASIN B0XXXXX  BSR 412,000  $/mo ~$45  reviews 8  pub 2024-11
   → Action: Plan a coloring book with theme="animal_mandala", request this BISAC
     in the listing-copywriter step.

2. (next row...)
```

Then ask: "Want me to /niche-hunter <category-derived-keyword> to validate demand before commissioning a book?"

---

## ⚠️ Known limitations

- Apify junglee/Amazon-crawler returns `bestsellerRanks` but **the rank URLs aren't always populated** — some leafs we discover have no fetchable bestseller URL. Those rows write with `top_bsr=NULL` and `notes="no_bestseller_url_from_breadcrumb"`. Skip them; they're not actionable until manually URL-mapped.
- BSR → revenue math uses `DEFAULT_PRICE_USD=9.99` and `DEFAULT_PAGE_COUNT=100` when the actor doesn't return them. Check `notes` for `price_default=` / `pages_default=` flags before trusting the $/mo number.
- Amazon has ~19,000 category leafs total; one keyword scan typically surfaces 5–25 unique leafs. To cover more, run multiple seeds (`mandala coloring`, `geometric coloring`, `flower coloring`, etc.) and let the upsert dedupe.
- We track ONLY the #1. Position 2–10 may all be weak too (or one strong outlier may sit at #2 ready to retake #1). User explicitly chose the simpler "track #1 only" output — don't over-engineer.

---

## 📦 Schema reference (data/kdp.db → `categories`)

Key columns:
- `name` — leaf sub-category name (eg "Mandala Coloring Books")
- `breadcrumb` — full path "Books > Crafts > Coloring > Mandala"
- `bestseller_url` — canonical zgbs URL (when known)
- `top_asin`, `top_title`, `top_bsr`, `top_price_usd`, `top_pages`, `top_rating_avg`, `top_reviews_count`, `top_publish_date`
- `top_daily_sales_mid`, `top_monthly_royalty_usd` — computed via `kdp_config`
- `weakness_label` — `EASY` / `MODERATE` / `HARD` / `VERY_HARD` / `UNKNOWN`
- `seed_keyword`, `seed_book_type` — which scan surfaced this row
- `source` — `apify:junglee/amazon-crawler` (only tier supported now)
- `raw_json_path` — relative path to audit JSON
- Conflict key: `(name, seed_book_type)` — re-scanning same keyword refreshes the row.

Indexes: `idx_categories_seed`, `idx_categories_top_bsr`, `idx_categories_royalty`.

---

## Examples

```bash
# Find easy coloring sub-categories
python3 scripts/category_finder.py scan "mandala coloring" --book-type coloring

# Sudoku — large print is a known senior-friendly niche
python3 scripts/category_finder.py scan "large print sudoku" --book-type sudoku --max-products 25

# Show all EASY categories across the whole DB
python3 scripts/category_finder.py rank --book-type any --limit 30

# Drill into one row (eg id=14)
python3 scripts/category_finder.py show 14
```
