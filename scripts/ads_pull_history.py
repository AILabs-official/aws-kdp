#!/usr/bin/env python3
"""Backfill Amazon Ads Sponsored Products history into ad_performance table.

Amazon SP reports cap at 95 days lookback. This script loops day-by-day
(start==end per request) so each ad_performance row carries the actual
date — required for analyst time-series. Skips days already in DB.

Usage:
    python3 scripts/ads_pull_history.py            # backfill last 95 days
    python3 scripts/ads_pull_history.py --days 30  # only last 30 days
    python3 scripts/ads_pull_history.py --start 2026-01-25 --end 2026-04-28
"""
from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DB_PATH = REPO / "data" / "kdp.db"
MAX_LOOKBACK_DAYS = 95


def days_already_pulled() -> set[str]:
    """Return set of YYYY-MM-DD strings already in ad_performance."""
    if not DB_PATH.exists():
        return set()
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute("SELECT DISTINCT date FROM ad_performance").fetchall()
        return {r[0] for r in rows if r[0]}
    finally:
        conn.close()


def pull_one_day(d: str) -> tuple[bool, str]:
    """Run amazon_ads_api.py report for a single day. Returns (ok, msg)."""
    cmd = [
        sys.executable,
        str(HERE / "amazon_ads_api.py"),
        "report",
        "--start-date", d,
        "--end-date", d,
        "--write-db",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if result.returncode == 0:
            tail = result.stdout.strip().splitlines()[-1] if result.stdout else ""
            return True, tail
        return False, (result.stderr or result.stdout)[-300:]
    except subprocess.TimeoutExpired:
        return False, "timeout after 15min"
    except Exception as e:
        return False, str(e)


def main() -> int:
    p = argparse.ArgumentParser(description="Backfill Amazon Ads history into ad_performance.")
    p.add_argument("--days", type=int, default=MAX_LOOKBACK_DAYS,
                   help=f"backfill last N days (max {MAX_LOOKBACK_DAYS}, Amazon limit)")
    p.add_argument("--start", help="YYYY-MM-DD (overrides --days)")
    p.add_argument("--end", help="YYYY-MM-DD (default: yesterday)")
    p.add_argument("--force", action="store_true", help="re-pull days already in DB")
    p.add_argument("--sleep", type=float, default=2.0,
                   help="sleep seconds between requests (avoid 429)")
    args = p.parse_args()

    today = date.today()
    end = date.fromisoformat(args.end) if args.end else today - timedelta(days=1)
    if args.start:
        start = date.fromisoformat(args.start)
    else:
        start = end - timedelta(days=min(args.days, MAX_LOOKBACK_DAYS) - 1)

    earliest = today - timedelta(days=MAX_LOOKBACK_DAYS)
    if start < earliest:
        print(f"⚠ start={start} older than {MAX_LOOKBACK_DAYS}d limit; clamping to {earliest}", file=sys.stderr)
        start = earliest

    existing = set() if args.force else days_already_pulled()

    all_days = []
    cursor = start
    while cursor <= end:
        all_days.append(cursor.isoformat())
        cursor += timedelta(days=1)

    todo = [d for d in all_days if d not in existing]
    skipped = len(all_days) - len(todo)

    print(f"Backfill window: {start} → {end} ({len(all_days)} days)")
    print(f"  already in DB: {skipped}")
    print(f"  to pull:       {len(todo)}")
    if not todo:
        print("✓ nothing to do.")
        return 0

    ok_count = 0
    fail_count = 0
    failed_days: list[str] = []
    for i, d in enumerate(todo, 1):
        print(f"\n[{i}/{len(todo)}] {d} ...", flush=True)
        ok, msg = pull_one_day(d)
        if ok:
            ok_count += 1
            print(f"  ✓ {msg}")
        else:
            fail_count += 1
            failed_days.append(d)
            print(f"  ✗ {msg[:200]}", file=sys.stderr)
        if i < len(todo) and args.sleep > 0:
            time.sleep(args.sleep)

    print(f"\n==== summary ====")
    print(f"  ok:     {ok_count}")
    print(f"  failed: {fail_count}")
    if failed_days:
        print(f"  failed days: {', '.join(failed_days[:20])}{' ...' if len(failed_days) > 20 else ''}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
