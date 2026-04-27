"""Global KDP constants — single place to tweak.

Cover math, page math, and royalty constants used across agents.

NOTE (Phase 1 refactor, 2026-04-27): Niche scoring constants — WEIGHTS,
THRESHOLDS, OPPORTUNITY tiers, BSR_TIERS, SEASONS, LIMITS, hard-elim params —
are now loaded from data/criteria/niche_criteria_v*.json via niche_criteria.py.
The values below are kept as fallback only; if the JSON is missing they still
work. Edit the JSON to change criteria, NOT this file.
"""

from __future__ import annotations

try:
    from niche_criteria import (
        WEIGHTS as _CRIT_WEIGHTS,
        THRESHOLDS as _CRIT_THRESHOLDS,
        OPPORTUNITY_TIERS as _CRIT_OPP_TIERS,
        BSR_TIERS_TUPLES as _CRIT_BSR_TIERS,
        SEASONS as _CRIT_SEASONS,
        LIMITS as _CRIT_LIMITS,
        VERSION as CRITERIA_VERSION,
        SOURCE_PATH as CRITERIA_SOURCE,
        hard_elim_param as _hard_elim_param,
    )
    _CRITERIA_LOADED = True
except Exception:  # pragma: no cover — defensive: never break kdp_config consumers
    _CRITERIA_LOADED = False
    CRITERIA_VERSION = "fallback-hardcoded"
    CRITERIA_SOURCE = ""
    _CRIT_WEIGHTS = _CRIT_THRESHOLDS = _CRIT_OPP_TIERS = None
    _CRIT_BSR_TIERS = _CRIT_SEASONS = _CRIT_LIMITS = None
    def _hard_elim_param(rule_id, key, default=None):  # type: ignore
        return default

# ────────────────────────────────────────────────────────
# Cover math (KDP paperback, white paper, US marketplace)
# ────────────────────────────────────────────────────────

# spine_width (inches) = page_count × SPINE_PER_PAGE_WHITE
SPINE_PER_PAGE_WHITE = 0.002252
SPINE_PER_PAGE_CREAM = 0.0025

BLEED_IN = 0.125
LIVE_AREA_MARGIN_IN = 0.25   # keep text 0.25" from trim
BARCODE_SIZE_IN = (1.5, 1.5) # W × H on back cover bottom-right
BARCODE_MARGIN_IN = 0.25
MIN_SPINE_FOR_TEXT_IN = 0.125 # KDP: below this, spine cannot carry text


TRIM_SIZES = {
    "8.5x11":  (8.5, 11.0),
    "8.5x8.5": (8.5, 8.5),
    "6x9":     (6.0, 9.0),
    "7x10":    (7.0, 10.0),
    "8x10":    (8.0, 10.0),
}


def spine_width_inches(page_count: int, paper: str = "white") -> float:
    rate = SPINE_PER_PAGE_WHITE if paper == "white" else SPINE_PER_PAGE_CREAM
    return round(page_count * rate + 1e-9, 4)


def full_cover_dims(page_size: str, page_count: int, paper: str = "white") -> dict:
    """Return full cover dimensions (width, height, spine) in inches for KDP upload."""
    if page_size not in TRIM_SIZES:
        raise ValueError(f"unknown page_size {page_size}; supported: {list(TRIM_SIZES)}")
    trim_w, trim_h = TRIM_SIZES[page_size]
    spine = spine_width_inches(page_count, paper)
    full_w = round(trim_w + spine + trim_w + 2 * BLEED_IN, 4)
    full_h = round(trim_h + 2 * BLEED_IN, 4)
    return {
        "trim_size": page_size,
        "trim_width_in": trim_w,
        "trim_height_in": trim_h,
        "spine_width_in": spine,
        "full_width_in": full_w,
        "full_height_in": full_h,
        "bleed_in": BLEED_IN,
        "live_margin_in": LIVE_AREA_MARGIN_IN,
        "spine_can_have_text": spine >= MIN_SPINE_FOR_TEXT_IN,
    }


# ────────────────────────────────────────────────────────
# Royalty math (KDP paperback, 60% royalty rate, US marketplace)
# ────────────────────────────────────────────────────────

PRINTING_FIXED_USD = 0.85
PRINTING_PER_PAGE_BW = 0.012             # black-and-white interior
PRINTING_PER_PAGE_COLOR_PREMIUM = 0.07   # premium color interior
PRINTING_PER_PAGE_COLOR_STANDARD = 0.0255  # standard color (US, since 2025-06-10)
PRINTING_PER_PAGE_COLOR = PRINTING_PER_PAGE_COLOR_PREMIUM  # legacy alias

# KDP paperback royalty (US marketplace).
# Tiered structure since 2025-06-10:
#   list_price ≥ $9.99 → 60%
#   list_price <  $9.99 → 50%
# Below the threshold there is also a regional cutoff at $9.98 inclusive.
ROYALTY_RATE_PAPERBACK_HIGH = 0.60
ROYALTY_RATE_PAPERBACK_LOW = 0.50
ROYALTY_TIER_THRESHOLD_USD = 9.99
ROYALTY_RATE_PAPERBACK = ROYALTY_RATE_PAPERBACK_HIGH  # legacy alias — assumes high-tier

KENP_RATE_USD = 0.0045  # approximate US KDP Select KENP read rate


def paperback_royalty_rate(list_price: float) -> float:
    """KDP paperback royalty rate (US marketplace, post-2025-06-10)."""
    if list_price >= ROYALTY_TIER_THRESHOLD_USD:
        return ROYALTY_RATE_PAPERBACK_HIGH
    return ROYALTY_RATE_PAPERBACK_LOW


def printing_cost_usd(page_count: int, color: bool = False) -> float:
    per_page = PRINTING_PER_PAGE_COLOR if color else PRINTING_PER_PAGE_BW
    return round(PRINTING_FIXED_USD + page_count * per_page, 3)


def royalty_per_sale_usd(list_price: float, page_count: int, color: bool = False) -> float:
    rate = paperback_royalty_rate(list_price)
    return round((list_price - printing_cost_usd(page_count, color)) * rate, 3)


def break_even_acos_pct(list_price: float, page_count: int, color: bool = False) -> float:
    royalty = royalty_per_sale_usd(list_price, page_count, color)
    if list_price <= 0:
        return 0.0
    return round(100 * royalty / list_price, 2)


def max_cpc_usd(
    list_price: float,
    page_count: int,
    target_acos_pct: float = 40,
    conversion_rate_pct: float = 8,
    color: bool = False,
) -> float:
    royalty = royalty_per_sale_usd(list_price, page_count, color)
    return round(royalty * (target_acos_pct / 100.0) * (conversion_rate_pct / 100.0), 3)


# ────────────────────────────────────────────────────────
# BSR → Sales/day conversion (US paperback, approximate)
#
# Piecewise estimates compiled from Publisher Rocket, KDSPY, Book Bolt
# community data 2023-2025. Each tier returns (low, mid, high) estimates.
# These are ESTIMATES — real sales vary by category and season. Use the
# MID value for point estimates, the RANGE for confidence intervals.
# ────────────────────────────────────────────────────────

# Override with criteria-loaded values when available, fallback to hardcoded.
BSR_TIERS = _CRIT_BSR_TIERS if _CRITERIA_LOADED and _CRIT_BSR_TIERS else [
    # (min_bsr, max_bsr, low_sales, mid_sales, high_sales)
    (1,        10,        2000,  3500,  5000),
    (11,       100,       300,   900,   2000),
    (101,      1_000,     80,    160,   300),
    (1_001,    5_000,     25,    45,    80),
    (5_001,    10_000,    10,    17,    25),
    (10_001,   25_000,    6,     9,     13),
    (25_001,   50_000,    3,     5,     8),
    (50_001,   100_000,   1.5,   2.5,   4),
    (100_001,  200_000,   0.7,   1.2,   2),
    (200_001,  500_000,   0.2,   0.4,   0.8),
    (500_001,  1_000_000, 0.05,  0.12,  0.25),
    (1_000_001, 99_999_999, 0.01, 0.03, 0.07),
]


def bsr_to_daily_sales(bsr: int) -> dict:
    """Return estimated daily sales range for a given BSR.

    Returns dict with low/mid/high daily sales estimates + tier description.
    """
    if bsr is None or bsr <= 0:
        return {"low": 0, "mid": 0, "high": 0, "tier": "invalid"}
    for lo, hi, l, m, h in BSR_TIERS:
        if lo <= bsr <= hi:
            return {"low": l, "mid": m, "high": h, "tier": f"BSR {lo:,}–{hi:,}"}
    return {"low": 0, "mid": 0, "high": 0, "tier": "out_of_range"}


def estimate_monthly_royalty(
    bsr: int, list_price: float, page_count: int, color: bool = False
) -> dict:
    """End-to-end monthly royalty estimate for a book at a given BSR."""
    sales = bsr_to_daily_sales(bsr)
    royalty = royalty_per_sale_usd(list_price, page_count, color)
    return {
        "bsr": bsr,
        "daily_sales_low": sales["low"],
        "daily_sales_mid": sales["mid"],
        "daily_sales_high": sales["high"],
        "royalty_per_sale_usd": royalty,
        "monthly_low_usd": round(sales["low"] * 30 * royalty, 2),
        "monthly_mid_usd": round(sales["mid"] * 30 * royalty, 2),
        "monthly_high_usd": round(sales["high"] * 30 * royalty, 2),
    }


# ────────────────────────────────────────────────────────
# Niche scoring — Blue Ocean framework
# ────────────────────────────────────────────────────────

def opportunity_score(
    avg_monthly_sales_top10: float, avg_review_count_top10: float
) -> dict:
    """Industry-standard Opportunity Score (thresholds from criteria JSON).

    Opportunity = monthly_sales / reviews.
    High score = lots of sales but few reviews = break-in easy (new market).
    Low score = many reviews = saturated, hard for new books to rank.
    """
    tiers = _CRIT_OPP_TIERS or {"BLUE_OCEAN": 5.0, "MODERATE": 2.0, "COMPETITIVE": 0.5}
    if avg_review_count_top10 <= 0:
        # Division by zero — treat as infinite opportunity (brand new niche)
        opp = 999
        tier = "BLUE_OCEAN"
    else:
        opp = round(avg_monthly_sales_top10 / avg_review_count_top10, 3)
        if opp >= tiers["BLUE_OCEAN"]:
            tier = "BLUE_OCEAN"
        elif opp >= tiers["MODERATE"]:
            tier = "MODERATE"
        elif opp >= tiers["COMPETITIVE"]:
            tier = "COMPETITIVE"
        else:
            tier = "SATURATED"
    return {"opportunity": opp, "tier": tier}


def competition_strength(
    avg_review_count_top10: float,
    avg_age_days_top10: float,
    avg_rating_top10: float = 4.3,
) -> dict:
    """Composite competition score (lower = easier to break in)."""
    # Normalize each signal to 0-10
    review_score = min(10, avg_review_count_top10 / 50)           # 50 reviews ≈ 1 point
    age_score = min(10, avg_age_days_top10 / 180)                 # 1800 days ≈ 10
    rating_score = max(0, (avg_rating_top10 - 3.0) * 5)           # 3.0 → 0, 5.0 → 10
    composite = round((review_score + age_score + rating_score) / 3, 2)
    return {
        "composite_0_to_10": composite,
        "review_score": round(review_score, 2),
        "age_score": round(age_score, 2),
        "rating_score": round(rating_score, 2),
    }


# Hard-elimination rules — applied BEFORE scoring
HARD_ELIMINATION_RULES = {
    "dead_market": {
        "condition": "top3_bsr_all > 300_000",
        "reason": "All top-3 books selling < 1 copy/day — no real demand",
    },
    "over_saturated": {
        "condition": "top10_reviews_all > 500 AND all_4_star_plus",
        "reason": "Big established players — new books can't rank without huge ad budget",
    },
    "race_to_bottom": {
        "condition": "top10_price_all <= 6.99 AND top10_pages_all <= 50",
        "reason": "Generic low-quality books at rock-bottom prices — no margin",
    },
    "single_publisher_lock": {
        "condition": "top10_same_publisher_count >= 6",
        "reason": "One publisher dominates — likely has amz internal promotion",
    },
    "seasonal_missed_window": {
        "condition": "seasonal AND days_to_peak < 75",
        "reason": "KDP review (72h) + SEO warmup (30-60 days) = launch too late",
    },
    "ip_trap": {
        "condition": "niche_contains_trademark",
        "reason": "Character/brand name in keyword — auto-reject pipeline",
    },
}


def apply_hard_elimination(niche_data: dict) -> list[str]:
    """Return list of violated rules. Empty list = niche passes hard filter.

    Thresholds loaded from data/criteria/niche_criteria_v*.json via niche_criteria.py.
    Edit the JSON to tune (don't hardcode here).
    """
    violations = []
    top3 = niche_data.get("top3_bsr", [])
    top10_reviews = niche_data.get("top10_reviews", [])
    top10_prices = niche_data.get("top10_prices", [])
    top10_pages = niche_data.get("top10_pages", [])
    top10_publishers = niche_data.get("top10_publishers", [])

    dead_thr     = _hard_elim_param("dead_market", "top3_bsr_min_threshold", 300_000)
    sat_thr      = _hard_elim_param("over_saturated", "top10_reviews_min_threshold", 500)
    rb_price     = _hard_elim_param("race_to_bottom", "max_price", 6.99)
    rb_pages     = _hard_elim_param("race_to_bottom", "max_pages", 50)
    pub_max      = _hard_elim_param("single_publisher_lock", "max_same_publisher", 6)
    indie_list   = _hard_elim_param("single_publisher_lock", "indie_aliases",
                                    ["independently published", "?", "", "unknown"])
    season_min   = _hard_elim_param("seasonal_missed_window", "min_days_to_peak", 75)

    if top3 and len(top3) >= 3:
        best3 = sorted(top3)[:3]
        if all(b > dead_thr for b in best3):
            violations.append("dead_market")

    if (
        top10_reviews
        and len(top10_reviews) >= 10
        and all(r > sat_thr for r in top10_reviews[:10])
    ):
        violations.append("over_saturated")

    if (
        top10_prices
        and top10_pages
        and len(top10_prices) >= 10
        and len(top10_pages) >= 10
        and all(p <= rb_price for p in top10_prices[:10])
        and all(pg <= rb_pages for pg in top10_pages[:10])
    ):
        violations.append("race_to_bottom")

    if top10_publishers and len(top10_publishers) >= 10:
        from collections import Counter
        _INDIE_ALIASES = {str(a).strip().lower() for a in indie_list}
        filtered = [p for p in top10_publishers[:10] if str(p).strip().lower() not in _INDIE_ALIASES]
        if filtered:
            c = Counter(filtered)
            if max(c.values()) >= pub_max:
                violations.append("single_publisher_lock")

    if niche_data.get("is_seasonal") and niche_data.get("days_to_peak", 999) < season_min:
        violations.append("seasonal_missed_window")

    if niche_data.get("has_trademark_risk"):
        violations.append("ip_trap")

    # commodity_trap — qualitative_edge.unique_hook.pass=false
    qe = niche_data.get("qualitative_edge") or {}
    uh = qe.get("unique_hook") or {}
    if uh and uh.get("pass") is False:
        violations.append("commodity_trap")

    return violations


def niche_score(
    demand_0_10: float,
    competition_strength_0_10: float,
    margin_0_10: float,
    content_scale_0_10: float,
    longevity_0_10: float,
    opportunity_0_10: float,
) -> dict:
    """Weighted niche score (weights + thresholds from criteria JSON)."""
    competition_ease = 10 - competition_strength_0_10

    weights = _CRIT_WEIGHTS or {
        "demand": 0.20, "opportunity": 0.25, "competition": 0.15,
        "margin": 0.15, "content": 0.10, "longevity": 0.15,
    }
    thresholds = _CRIT_THRESHOLDS or {"HOT": 7.5, "WARM": 6.0, "COLD": 4.5}

    overall = (
        weights["demand"] * demand_0_10
        + weights["opportunity"] * opportunity_0_10
        + weights["competition"] * competition_ease
        + weights["margin"] * margin_0_10
        + weights["content"] * content_scale_0_10
        + weights["longevity"] * longevity_0_10
    )
    overall = round(overall, 2)

    if overall >= thresholds["HOT"]:
        rating = "HOT"
    elif overall >= thresholds["WARM"]:
        rating = "WARM"
    elif overall >= thresholds["COLD"]:
        rating = "COLD"
    else:
        rating = "SKIP"

    return {
        "overall": overall,
        "rating": rating,
        "weights": weights,
        "thresholds": thresholds,
        "criteria_version": CRITERIA_VERSION,
    }


# ────────────────────────────────────────────────────────
# KDP content limits — loaded from criteria JSON, fallback below
# ────────────────────────────────────────────────────────

LIMITS = _CRIT_LIMITS or {
    "title_plus_subtitle_chars": 200,
    "subtitle_chars": 150,
    "description_chars": 4000,
    "keyword_chars": 50,
    "keywords_count": 7,
    "category_count_initial": 2,
    "category_count_extra_request": 10,
    "min_line_weight_pt": 0.75,
    "min_dpi": 300,
    "max_pdf_mb": 650,
}


# ────────────────────────────────────────────────────────
# Seasonal ramp calendar — loaded from criteria JSON, fallback below
# ────────────────────────────────────────────────────────

SEASONS = _CRIT_SEASONS or [
    {"event": "valentines", "peak": "02-14", "ramp_days": 85},
    {"event": "mothers_day", "peak": "05-11", "ramp_days": 70},
    {"event": "fathers_day", "peak": "06-15", "ramp_days": 70},
    {"event": "back_to_school", "peak": "08-20", "ramp_days": 80},
    {"event": "halloween", "peak": "10-31", "ramp_days": 90},
    {"event": "christmas", "peak": "12-25", "ramp_days": 130},
    {"event": "new_year", "peak": "01-01", "ramp_days": 80},
]


if __name__ == "__main__":
    import json

    sample = {
        "cover_52_8.5x11": full_cover_dims("8.5x11", 52),
        "cover_100_8.5x8.5": full_cover_dims("8.5x8.5", 100),
        "royalty_rate_8.99": paperback_royalty_rate(8.99),
        "royalty_rate_9.99": paperback_royalty_rate(9.99),
        "royalty_8.99_52p_LOW_TIER": royalty_per_sale_usd(8.99, 52),
        "royalty_9.99_52p_HIGH_TIER": royalty_per_sale_usd(9.99, 52),
        "break_even_acos_9.99_52p": break_even_acos_pct(9.99, 52),
        "max_cpc_9.99_52p_40acos_8cvr": max_cpc_usd(9.99, 52, 40, 8),
        "bsr_28k_daily_sales": bsr_to_daily_sales(28_000),
        "bsr_28k_monthly_royalty_9.99_52p": estimate_monthly_royalty(28_000, 9.99, 52),
        "opportunity_300sales_180reviews": opportunity_score(300, 180),
        "opportunity_450sales_40reviews": opportunity_score(450, 40),
        "niche_score_sample_hot": niche_score(8, 4, 8, 9, 9, 7),
        "niche_score_sample_saturated": niche_score(9, 8, 6, 7, 8, 1),
    }
    print(json.dumps(sample, indent=2))
