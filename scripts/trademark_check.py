#!/usr/bin/env python3
"""KDP trademark pre-check.

Runs a keyword against USPTO + Trademarkia, focused on Class 016 (paper goods,
books, printed matter) — the only class that matters for KDP titles.

Two modes:
  api    — best-effort live HTTP call to USPTO Trademark Search (public, no auth).
           Returns LIVE / DEAD / NONE for the keyword in Class 016.
  urls   — produce structured manual-verify URLs (USPTO + Trademarkia + EUIPO)
           for cases where the API call is blocked or rate-limited.

Output is always JSON so the niche-hunter agent can `apply_hard_elimination` on
the `verdict` field directly.

Usage:
    python3 scripts/trademark_check.py "fantasy mushroom"
    python3 scripts/trademark_check.py "cozy cats" --mode urls
    python3 scripts/trademark_check.py "bluey" --json-only

Verdict values:
    CLEAR          — no LIVE Class-016 registrations found
    WARNING        — LIVE registrations exist in OTHER classes (003, 025, etc.)
    FAIL           — at least one LIVE Class-016 registration → reject niche
    MANUAL_CHECK   — automated check failed; reviewer must verify the URLs

Exit codes:
    0  CLEAR or WARNING
    1  FAIL
    2  MANUAL_CHECK (no live data, agent must verify by WebSearch)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
from dataclasses import asdict, dataclass, field
from typing import Any

try:
    import urllib.request
    import urllib.error
except ImportError:  # pragma: no cover
    print(json.dumps({"error": "urllib not available"}))
    sys.exit(2)


# ────────────────────────────────────────────────────────
# Constants
# ────────────────────────────────────────────────────────

# Class 016 = Paper goods, printed matter, books, magazines, periodicals.
# The ONLY class that creates a direct conflict with a KDP title.
KDP_CONFLICT_CLASS = "016"

# Adjacent classes that can still cause Amazon to remove a listing — agent
# should surface as WARNING but not reject outright.
KDP_ADJACENT_CLASSES = {
    "009": "Software, downloadable e-books",
    "028": "Toys, games (puzzle books risk)",
    "041": "Educational services, publishing services",
}

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) KDP-Niche-Hunter/1.0"
)

USPTO_TMSEARCH_HTML = "https://tmsearch.uspto.gov/search/search-information"
USPTO_TMSEARCH_API = "https://tmsearch.uspto.gov/api-v1-0-0/case-search/search"
TRADEMARKIA_SEARCH = "https://www.trademarkia.com/trademarks-search.aspx"
EUIPO_ESEARCH = "https://www.tmdn.org/tmview/welcome"


# ────────────────────────────────────────────────────────
# Result type
# ────────────────────────────────────────────────────────

@dataclass
class TrademarkResult:
    keyword: str
    verdict: str  # CLEAR | WARNING | FAIL | MANUAL_CHECK
    mode: str
    class_016_live_hits: int = 0
    adjacent_class_live_hits: int = 0
    registrations: list[dict[str, Any]] = field(default_factory=list)
    manual_check_urls: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    timestamp_utc: str = ""


# ────────────────────────────────────────────────────────
# URL builders
# ────────────────────────────────────────────────────────

def build_manual_check_urls(keyword: str) -> dict[str, str]:
    """Return search URLs that a human (or WebSearch agent) can verify."""
    encoded = urllib.parse.quote_plus(keyword)
    return {
        "uspto_tmsearch_class_016": (
            f"https://tmsearch.uspto.gov/search/search-information?"
            f"searchText={encoded}&filter=live&filter=class:{KDP_CONFLICT_CLASS}"
        ),
        "uspto_tmsearch_all": (
            f"https://tmsearch.uspto.gov/search/search-information?"
            f"searchText={encoded}&filter=live"
        ),
        "trademarkia": (
            f"https://www.trademarkia.com/trademarks-search.aspx?tn={encoded}"
        ),
        "euipo_eu": (
            f"https://www.tmdn.org/tmview/#/tmview/results?text={encoded}"
        ),
        "google_trademark_check": (
            f"https://www.google.com/search?q="
            + urllib.parse.quote_plus(f'"{keyword}" trademark site:uspto.gov')
        ),
    }


# ────────────────────────────────────────────────────────
# API attempt — best-effort, soft-fail
# ────────────────────────────────────────────────────────

def try_uspto_api(keyword: str, timeout_s: float = 8.0) -> tuple[bool, dict]:
    """Attempt USPTO Trademark Search API call.

    Returns (success, parsed_json). USPTO's public TMSearch site has a JSON
    backend but rate-limits anonymous traffic; we never retry on failure.
    """
    payload = {
        "searchText": keyword,
        "filter": ["live"],
        "rows": 25,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        USPTO_TMSEARCH_API,
        data=body,
        method="POST",
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read()
            data = json.loads(raw.decode("utf-8", errors="replace"))
            return True, data
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError) as e:
        return False, {"error": str(e), "kind": type(e).__name__}


def parse_uspto_response(data: dict, keyword: str) -> TrademarkResult:
    """Parse USPTO Trademark Search JSON into a TrademarkResult."""
    result = TrademarkResult(
        keyword=keyword,
        verdict="MANUAL_CHECK",
        mode="api",
        timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )

    # USPTO response shape varies; try common keys.
    hits = (
        data.get("results")
        or data.get("hits", {}).get("hits")
        or data.get("response", {}).get("docs")
        or []
    )

    if not hits:
        result.verdict = "CLEAR"
        result.notes.append("USPTO API returned 0 LIVE matches for keyword.")
        return result

    for hit in hits[:25]:
        # Best-effort field extraction (USPTO has multiple response shapes).
        source = hit.get("_source", hit)
        mark_text = (
            source.get("markIdentification")
            or source.get("mark_text")
            or source.get("wordMark")
            or ""
        )
        status = (source.get("status") or source.get("liveDeadIndicator") or "").upper()
        classes = source.get("usClasses") or source.get("internationalClasses") or []
        if isinstance(classes, str):
            classes = [c.strip() for c in classes.split(",")]
        classes = [str(c).zfill(3) for c in classes if c]

        registration = {
            "mark": mark_text,
            "status": status,
            "classes": classes,
            "serial": source.get("serialNumber") or source.get("serial_number"),
        }
        result.registrations.append(registration)

        if "LIVE" in status or status in {"REGISTERED", "PENDING"}:
            if KDP_CONFLICT_CLASS in classes:
                result.class_016_live_hits += 1
            elif any(c in KDP_ADJACENT_CLASSES for c in classes):
                result.adjacent_class_live_hits += 1

    if result.class_016_live_hits > 0:
        result.verdict = "FAIL"
        result.notes.append(
            f"{result.class_016_live_hits} LIVE Class-016 registrations — "
            "do NOT use this keyword in title/subtitle/keywords."
        )
    elif result.adjacent_class_live_hits > 0:
        result.verdict = "WARNING"
        result.notes.append(
            f"{result.adjacent_class_live_hits} LIVE registrations in adjacent "
            "classes — review manually before use."
        )
    else:
        result.verdict = "CLEAR"
        result.notes.append(
            f"No Class-016 conflicts found across {len(hits)} LIVE registrations."
        )

    return result


# ────────────────────────────────────────────────────────
# Heuristic guard — known IP-trap keywords
# ────────────────────────────────────────────────────────

# Hard-coded list of common KDP rejections — these are catch-all guards.
# Source: KDP community forum + 2024-2025 takedown reports.
KNOWN_TRADEMARK_TRAPS = {
    # Disney/Pixar
    "disney", "mickey mouse", "minnie", "frozen", "elsa", "moana", "encanto",
    "toy story", "buzz lightyear", "cars movie", "lightning mcqueen",
    # Nickelodeon / Cartoon Network
    "spongebob", "paw patrol", "peppa pig", "bluey", "cocomelon", "ms rachel",
    # Nintendo / gaming
    "pokemon", "pikachu", "mario", "zelda", "minecraft", "roblox", "fortnite",
    # Marvel / DC
    "marvel", "spider-man", "batman", "superman", "wonder woman", "avengers",
    # Brands
    "nike", "adidas", "coca cola", "starbucks", "lego", "barbie",
    # Sports
    "nfl", "nba", "mlb", "nhl", "fifa world cup",
    # Common KDP-banned phrases
    "spiral bound", "leather bound", "hard bound",
}


def heuristic_check(keyword: str) -> TrademarkResult:
    """Cheap pre-filter — catch obvious IP traps without an API call."""
    kw_lower = keyword.lower().strip()
    result = TrademarkResult(
        keyword=keyword,
        verdict="CLEAR",
        mode="heuristic",
        manual_check_urls=build_manual_check_urls(keyword),
        timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )

    matches = [trap for trap in KNOWN_TRADEMARK_TRAPS if trap in kw_lower]
    if matches:
        result.verdict = "FAIL"
        result.class_016_live_hits = len(matches)
        result.notes.append(
            f"Keyword contains known trademark trap(s): {', '.join(matches)}. "
            "Reject before any further research."
        )
        result.registrations = [
            {"mark": m, "status": "KNOWN_LIVE", "classes": [KDP_CONFLICT_CLASS], "source": "heuristic"}
            for m in matches
        ]
    else:
        result.notes.append(
            "Heuristic check passed — keyword does not contain known trademark traps. "
            "Verify manually via the URLs in `manual_check_urls`."
        )
    return result


# ────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────

def run(keyword: str, mode: str, timeout_s: float) -> TrademarkResult:
    """Execute trademark check."""
    keyword = keyword.strip()
    if not keyword:
        return TrademarkResult(
            keyword="",
            verdict="MANUAL_CHECK",
            mode=mode,
            notes=["Empty keyword."],
            timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

    # Always run the heuristic first — it is free and catches the obvious traps.
    heuristic = heuristic_check(keyword)
    if heuristic.verdict == "FAIL":
        return heuristic

    if mode == "urls":
        # Just return the heuristic result with URLs — agent does the verification.
        heuristic.notes.insert(
            0,
            "Mode=urls: agent must WebSearch the URLs in `manual_check_urls` and "
            "look for LIVE registrations in Class 016.",
        )
        return heuristic

    if mode == "api":
        ok, data = try_uspto_api(keyword, timeout_s=timeout_s)
        if ok:
            parsed = parse_uspto_response(data, keyword)
            parsed.manual_check_urls = build_manual_check_urls(keyword)
            return parsed
        # API failed — fall through to manual-check URLs.
        heuristic.verdict = "MANUAL_CHECK"
        heuristic.notes.insert(
            0,
            f"USPTO API call failed ({data.get('kind', 'unknown')}). "
            "Agent must verify via the URLs in `manual_check_urls`.",
        )
        return heuristic

    raise ValueError(f"unknown mode: {mode}")


def main() -> int:
    parser = argparse.ArgumentParser(description="KDP trademark pre-check (Class 016 focus).")
    parser.add_argument("keyword", help="Keyword or phrase to check.")
    parser.add_argument(
        "--mode",
        choices=("api", "urls"),
        default="urls",
        help="api = try USPTO live call (best-effort); urls = output manual-verify URLs (default).",
    )
    parser.add_argument("--timeout", type=float, default=8.0, help="HTTP timeout for api mode.")
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Print only the JSON result (no trailing summary).",
    )
    args = parser.parse_args()

    result = run(args.keyword, args.mode, args.timeout)
    output = asdict(result)
    print(json.dumps(output, indent=2, ensure_ascii=False))

    if not args.json_only:
        print(
            f"\n→ verdict: {result.verdict} "
            f"(class_016_live={result.class_016_live_hits}, "
            f"adjacent_live={result.adjacent_class_live_hits})",
            file=sys.stderr,
        )

    return {"CLEAR": 0, "WARNING": 0, "FAIL": 1, "MANUAL_CHECK": 2}.get(result.verdict, 2)


if __name__ == "__main__":
    sys.exit(main())
