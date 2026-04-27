"""Niche criteria loader — single source of truth for KDP niche scoring.

Reads `data/criteria/niche_criteria_v*.json` (latest by version field) and
exposes weights, thresholds, hard-elimination params, BSR table, seasons,
limits, and the WIN checklist.

Design:
  - Zero dependencies (json stdlib only).
  - Caching via lru_cache — read file once per process.
  - Fail-soft: if file missing or unparseable, return baked-in defaults
    matching the 2026-04-27 snapshot. This keeps `kdp_config.py` and all
    agents working even before the criteria file is deployed.
  - Versioned: every active criteria run is tagged with `current_version()`
    so research records can be re-scored under newer weights later (Phase 2).

Usage:
    from niche_criteria import (
        WEIGHTS, THRESHOLDS, OPPORTUNITY_TIERS, HARD_ELIM, FLAGS,
        BSR_TIERS, SEASONS, LIMITS, WIN_CHECKLIST,
        current_version, load,
    )

    # Or fetch the full dict:
    crit = load()
    print(crit["version"])
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

# Resolve `data/criteria/` relative to repo root (scripts/.. = repo root).
_REPO_ROOT = Path(__file__).resolve().parent.parent
_CRITERIA_DIR = _REPO_ROOT / "data" / "criteria"
_VERSION_PATTERN = re.compile(r"niche_criteria_v(\d{4}-\d{2}-\d{2})\.json$")


# ──────────────────────────────────────────────────────────────────────
# Baked-in defaults — mirror data/criteria/niche_criteria_v2026-04-27.json
# Used only when the file is missing/unreadable. Keep in sync if you bump
# the canonical JSON, or this becomes drift.
# ──────────────────────────────────────────────────────────────────────

_DEFAULTS: dict[str, Any] = {
    "version": "2026.04.27-baked-in",
    "schema_version": 2,
    "weights": {
        "demand": 0.20, "opportunity": 0.25, "competition": 0.15,
        "margin": 0.15, "content": 0.10, "longevity": 0.15,
    },
    "thresholds": {"HOT": 7.5, "WARM": 6.0, "COLD": 4.5},
    "opportunity_tiers": {"BLUE_OCEAN": 5.0, "MODERATE": 2.0, "COMPETITIVE": 0.5},
    "hard_elimination": {
        "rules": [
            {"id": "dead_market",            "params": {"top3_bsr_min_threshold": 300_000}},
            {"id": "over_saturated",         "params": {"top10_reviews_min_threshold": 500}},
            {"id": "race_to_bottom",         "params": {"max_price": 6.99, "max_pages": 50}},
            {"id": "single_publisher_lock",  "params": {"max_same_publisher": 6,
                                                         "indie_aliases": ["independently published", "?", "", "unknown"]}},
            {"id": "seasonal_missed_window", "params": {"min_days_to_peak": 75}},
            {"id": "ip_trap",                "params": {}},
            {"id": "commodity_trap",         "params": {}},
        ],
    },
    "flags": {
        "BLUE_OCEAN_OPPORTUNITY": {"threshold": 5.0},
        "LOW_REVIEW_BARRIER":     {"threshold": 50},
        "FRAGMENTED_MARKET":      {"threshold": 2},
        "EMERGING_MARKET":        {"threshold": 365},
        "GOLDMINE":               {"thresholds": {"royalty": 500, "reviews": 100}},
    },
    "book_type_minimums": {
        "coloring":    {"min_concepts": 30, "min_content_scale_score": 7},
        "low_content": {"min_concepts": 10, "requires_template": True},
        "activity":    {"min_concepts": 20, "requires_difficulty_ladder": True},
    },
    "bsr_to_sales_table": {
        "tiers": [
            {"bsr_min": 1,         "bsr_max": 10,        "low": 2000, "mid": 3500, "high": 5000},
            {"bsr_min": 11,        "bsr_max": 100,       "low": 300,  "mid": 900,  "high": 2000},
            {"bsr_min": 101,       "bsr_max": 1000,      "low": 80,   "mid": 160,  "high": 300},
            {"bsr_min": 1001,      "bsr_max": 5000,      "low": 25,   "mid": 45,   "high": 80},
            {"bsr_min": 5001,      "bsr_max": 10000,     "low": 10,   "mid": 17,   "high": 25},
            {"bsr_min": 10001,     "bsr_max": 25000,     "low": 6,    "mid": 9,    "high": 13},
            {"bsr_min": 25001,     "bsr_max": 50000,     "low": 3,    "mid": 5,    "high": 8},
            {"bsr_min": 50001,     "bsr_max": 100000,    "low": 1.5,  "mid": 2.5,  "high": 4},
            {"bsr_min": 100001,    "bsr_max": 200000,    "low": 0.7,  "mid": 1.2,  "high": 2},
            {"bsr_min": 200001,    "bsr_max": 500000,    "low": 0.2,  "mid": 0.4,  "high": 0.8},
            {"bsr_min": 500001,    "bsr_max": 1000000,   "low": 0.05, "mid": 0.12, "high": 0.25},
            {"bsr_min": 1000001,   "bsr_max": 99999999,  "low": 0.01, "mid": 0.03, "high": 0.07},
        ],
    },
    "seasons": [
        {"event": "valentines",     "peak": "02-14", "ramp_days": 85},
        {"event": "mothers_day",    "peak": "05-11", "ramp_days": 70},
        {"event": "fathers_day",    "peak": "06-15", "ramp_days": 70},
        {"event": "back_to_school", "peak": "08-20", "ramp_days": 80},
        {"event": "halloween",      "peak": "10-31", "ramp_days": 90},
        {"event": "christmas",      "peak": "12-25", "ramp_days": 130},
        {"event": "new_year",       "peak": "01-01", "ramp_days": 80},
    ],
    "limits": {
        "title_plus_subtitle_chars": 200, "subtitle_chars": 150,
        "description_chars": 4000, "keyword_chars": 50, "keywords_count": 7,
        "category_count_initial": 2, "category_count_extra_request": 10,
        "min_line_weight_pt": 0.75, "min_dpi": 300, "max_pdf_mb": 650,
    },
    "win_checklist": {"items": []},
}


def _list_criteria_files() -> list[Path]:
    if not _CRITERIA_DIR.is_dir():
        return []
    files = []
    for entry in _CRITERIA_DIR.iterdir():
        if entry.is_file() and _VERSION_PATTERN.search(entry.name):
            files.append(entry)
    files.sort(key=lambda p: _VERSION_PATTERN.search(p.name).group(1))  # type: ignore[union-attr]
    return files


@lru_cache(maxsize=1)
def load() -> dict[str, Any]:
    """Load the most recent criteria JSON file.

    Returns the parsed dict. If no file exists or all files fail to parse,
    returns the baked-in defaults (logged once via stderr).
    """
    # Allow override via env for testing / temporary pinning.
    override = os.environ.get("KDP_CRITERIA_FILE")
    candidates: list[Path]
    if override and Path(override).is_file():
        candidates = [Path(override)]
    else:
        candidates = list(reversed(_list_criteria_files()))  # newest first

    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict) or "version" not in data:
                continue
            data["_source_path"] = str(path)
            return data
        except (OSError, json.JSONDecodeError):
            continue

    # Fallback — defaults.
    fallback = dict(_DEFAULTS)
    fallback["_source_path"] = "<baked-in defaults — no criteria file found>"
    return fallback


def current_version() -> str:
    """Active criteria version (e.g. '2026.04.27'). Used to tag DB records."""
    return str(load().get("version", "unknown"))


def list_versions() -> list[str]:
    """Available criteria file versions on disk (sorted oldest → newest)."""
    return [_VERSION_PATTERN.search(p.name).group(1)  # type: ignore[union-attr]
            for p in _list_criteria_files()]


# ──────────────────────────────────────────────────────────────────────
# Module-level constants — convenience exports. These are the values
# kdp_config.py and the niche-hunter agent should use directly.
# ──────────────────────────────────────────────────────────────────────

def _strip_meta(d: dict) -> dict:
    """Drop underscore-prefixed metadata keys (e.g. _doc) so dicts stay numeric."""
    if not isinstance(d, dict):
        return d
    return {k: v for k, v in d.items() if not (isinstance(k, str) and k.startswith("_"))}


_LOADED = load()

VERSION              = _LOADED.get("version", "unknown")
SOURCE_PATH          = _LOADED.get("_source_path", "")
WEIGHTS              = _strip_meta(_LOADED.get("weights", _DEFAULTS["weights"]))
THRESHOLDS           = _strip_meta(_LOADED.get("thresholds", _DEFAULTS["thresholds"]))
OPPORTUNITY_TIERS    = _strip_meta(_LOADED.get("opportunity_tiers", _DEFAULTS["opportunity_tiers"]))
HARD_ELIM            = _LOADED.get("hard_elimination", _DEFAULTS["hard_elimination"])
FLAGS                = _strip_meta(_LOADED.get("flags", _DEFAULTS["flags"]))
QUALITATIVE_EDGE     = _LOADED.get("qualitative_edge", {})
BOOK_TYPE_MINIMUMS   = _strip_meta(_LOADED.get("book_type_minimums", _DEFAULTS["book_type_minimums"]))
BSR_TIERS_RAW        = _LOADED.get("bsr_to_sales_table", _DEFAULTS["bsr_to_sales_table"])["tiers"]
# Same shape as legacy kdp_config.BSR_TIERS — list of (lo, hi, low, mid, high) tuples.
BSR_TIERS_TUPLES     = [(t["bsr_min"], t["bsr_max"], t["low"], t["mid"], t["high"]) for t in BSR_TIERS_RAW]
SEASONS              = _LOADED.get("seasons", _DEFAULTS["seasons"])
LIMITS               = _strip_meta(_LOADED.get("limits", _DEFAULTS["limits"]))
WIN_CHECKLIST        = _LOADED.get("win_checklist", _DEFAULTS["win_checklist"])


def hard_elim_param(rule_id: str, key: str, default: Any = None) -> Any:
    """Get a parameter from a named hard-elim rule. Used by apply_hard_elimination."""
    for rule in HARD_ELIM.get("rules", []):
        if rule.get("id") == rule_id:
            return rule.get("params", {}).get(key, default)
    return default


def flag_threshold(flag_name: str, key: str | None = None, default: Any = None) -> Any:
    """Read a flag threshold (single value or nested key)."""
    flag = FLAGS.get(flag_name, {})
    if key is None:
        return flag.get("threshold", default)
    nested = flag.get("thresholds", {})
    return nested.get(key, default)


if __name__ == "__main__":
    # Self-check + summary
    print(f"=== Niche Criteria Loader ===")
    print(f"Active version : {VERSION}")
    print(f"Source         : {SOURCE_PATH}")
    print(f"Available      : {list_versions() or '(none)'}")
    print(f"Weights        : {WEIGHTS}  sum={round(sum(WEIGHTS.values()), 4)}")
    print(f"Thresholds     : {THRESHOLDS}")
    print(f"Opportunity    : {OPPORTUNITY_TIERS}")
    print(f"BSR tiers      : {len(BSR_TIERS_TUPLES)}")
    print(f"Seasons        : {len(SEASONS)}")
    print(f"Hard-elim rules: {[r['id'] for r in HARD_ELIM.get('rules', [])]}")
    print(f"Flags          : {list(FLAGS)}")
    print(f"WIN checklist  : {len(WIN_CHECKLIST.get('items', []))} items")
    # Sanity check — weights must sum to 1.0
    s = sum(WEIGHTS.values())
    assert abs(s - 1.0) < 1e-6, f"Weights sum to {s}, expected 1.0 — fix criteria file"
    print("OK weights sum to 1.0")
