#!/usr/bin/env python3
"""KDP OS — Niche storage v2 CLI (Phase 2 companion to db.py).

Handles the new tables added in Phase 2:
  - niche_research_runs (1 row per /niche-hunter call)
  - niche_scores (long-format scoring per dimension)
  - niche_flags (Blue Ocean flags per run)
  - niche_top10 (competitor snapshot)
  - niche_eliminations (KILL LIST — never research same dead keyword twice)
  - niche_decisions (LAUNCH/REJECT/DEFER tracking)

Auto-tags every save with criteria_version from niche_criteria.py.
Auto-writes raw JSON packet to data/niches/raw/YYYY-MM-DD_<slug>.json.

Usage:
  python3 scripts/niches_v2.py save <packet.json>
  python3 scripts/niches_v2.py runs [--niche_id N] [--rating HOT]
  python3 scripts/niches_v2.py top10 <niche_id_or_slug>
  python3 scripts/niches_v2.py kill <keyword> --reason <r> [--notes "..."]
  python3 scripts/niches_v2.py is-killed <keyword>
  python3 scripts/niches_v2.py kill-list [--reason ip_trap]
  python3 scripts/niches_v2.py decide <niche_id> --decision LAUNCH --reason "..."
  python3 scripts/niches_v2.py decisions [--niche_id N]
  python3 scripts/niches_v2.py status
"""
from __future__ import annotations
import argparse
import json
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
DB_PATH = HERE.parent / "data" / "kdp.db"
RAW_DIR = HERE.parent / "data" / "niches" / "raw"

try:
    from niche_criteria import current_version
except Exception:
    def current_version() -> str:
        return "unknown"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def slugify(s: str) -> str:
    return (re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_") or "unknown")[:80]


# ──────────────────────────────────────────────────────────────────────
# CORE: save_research — the function niche-hunter agent calls
# ──────────────────────────────────────────────────────────────────────

def save_research(packet: dict, *, raw_path_override: str | None = None) -> dict:
    """Persist a niche-hunter research packet.

    Side-effects:
      1. Writes raw JSON → data/niches/raw/YYYY-MM-DD_<slug>.json
      2. Upserts row in niches (slug = unique key)
      3. Creates niche_research_runs row (criteria_version auto-tagged)
      4. Persists per-dimension scores → niche_scores
      5. Persists flags → niche_flags
      6. Persists top10 competitor snapshot → niche_top10
      7. If eliminated → also adds to niche_eliminations (kill list)
      8. Updates niches.latest_run_id + raw_json_path

    Returns: {"niche_id": ..., "run_id": ..., "raw_path": ..., "rating": ...}
    """
    name = packet.get("niche_name") or packet.get("primary_keyword")
    if not name:
        raise ValueError("packet missing niche_name / primary_keyword")
    slug = packet.get("slug") or slugify(name)
    book_type = packet.get("book_type", "coloring")
    crit_ver = packet.get("criteria_version") or current_version()

    # 1. Write raw packet
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if raw_path_override:
        raw_path = Path(raw_path_override)
    else:
        raw_path = RAW_DIR / f"{date.today().isoformat()}_{slug}.json"
        # if file exists, append a counter
        n = 1
        while raw_path.exists():
            raw_path = RAW_DIR / f"{date.today().isoformat()}_{slug}_{n}.json"
            n += 1
    packet_with_meta = {**packet, "criteria_version": crit_ver, "slug": slug}
    raw_path.write_text(json.dumps(packet_with_meta, indent=2, ensure_ascii=False))

    conn = get_conn()

    # 2. Upsert niche row (by slug)
    existing = conn.execute("SELECT id FROM niches WHERE slug = ?", (slug,)).fetchone()
    if existing:
        niche_id = existing["id"]
        conn.execute(
            "UPDATE niches SET niche_name = ?, book_type = ?, criteria_version = ?, raw_json_path = ?, primary_keyword = ?, audience = ?, page_size = ?, target_page_count = ?, recommended_list_price_usd = ?, ip_risk_notes = ? WHERE id = ?",
            (name, book_type, crit_ver, str(raw_path),
             packet.get("primary_keyword"), packet.get("audience"),
             packet.get("page_size", "8.5x11"), packet.get("target_page_count", 50),
             packet.get("recommended_list_price_usd"),
             packet.get("ip_risk_notes"), niche_id),
        )
    else:
        cur = conn.execute(
            """INSERT INTO niches (niche_name, book_type, slug, criteria_version, raw_json_path,
                                   primary_keyword, audience, page_size, target_page_count,
                                   recommended_list_price_usd, ip_risk_notes, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, book_type, slug, crit_ver, str(raw_path),
             packet.get("primary_keyword"), packet.get("audience"),
             packet.get("page_size", "8.5x11"), packet.get("target_page_count", 50),
             packet.get("recommended_list_price_usd"),
             packet.get("ip_risk_notes"), packet.get("status", "PENDING_IP_CHECK")),
        )
        niche_id = cur.lastrowid

    # 3. Create research run
    score_obj = packet.get("score", {})
    rating = score_obj.get("rating") or packet.get("rating")
    overall = score_obj.get("overall") if isinstance(score_obj, dict) else packet.get("overall_score")
    elims = packet.get("eliminations") or []
    eliminated = bool(elims)

    cur = conn.execute(
        """INSERT INTO niche_research_runs
           (niche_id, criteria_version, raw_json_path, overall_score, rating,
            eliminated, elimination_reasons, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (niche_id, crit_ver, str(raw_path), overall, rating,
         int(eliminated), json.dumps(elims) if elims else None,
         packet.get("notes")),
    )
    run_id = cur.lastrowid

    # 4. Persist per-dimension scores
    dims = packet.get("dimension_scores") or {}
    for dim, val in dims.items():
        try:
            conn.execute(
                "INSERT INTO niche_scores (run_id, dimension, value) VALUES (?, ?, ?)",
                (run_id, dim, float(val)),
            )
        except (TypeError, ValueError):
            pass

    # 5. Persist flags
    for f in packet.get("flags", []):
        try:
            conn.execute(
                "INSERT OR IGNORE INTO niche_flags (run_id, flag_name) VALUES (?, ?)",
                (run_id, f),
            )
        except sqlite3.Error:
            pass

    # 6. Persist top10 snapshot
    bsr = packet.get("top10_bsr", []) or []
    rev = packet.get("top10_reviews", []) or []
    rat = packet.get("top10_rating", []) or []
    pri = packet.get("top10_prices", []) or []
    pgs = packet.get("top10_pages", []) or []
    pub = packet.get("top10_publishers", []) or []
    age = packet.get("top10_age_days", []) or []
    asn = packet.get("top10_asins", []) or []
    n_max = max(len(bsr), len(rev), len(asn))
    for i in range(min(n_max, 20)):
        def _pick(lst, i, cast=lambda x: x):
            try: return cast(lst[i]) if i < len(lst) and lst[i] is not None else None
            except (TypeError, ValueError): return None
        conn.execute(
            """INSERT INTO niche_top10
               (run_id, rank, asin, bsr, reviews, rating, price, pages, publisher, age_days)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, i + 1,
             _pick(asn, i, str),
             _pick(bsr, i, int),
             _pick(rev, i, int),
             _pick(rat, i, float),
             _pick(pri, i, float),
             _pick(pgs, i, int),
             _pick(pub, i, str),
             _pick(age, i, int)),
        )

    # 7. If eliminated → kill list
    primary_kw = packet.get("primary_keyword") or name
    for reason in elims:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO niche_eliminations (keyword, reason, notes) VALUES (?, ?, ?)",
                (primary_kw, reason, f"From research run {run_id} (niche {niche_id})"),
            )
        except sqlite3.Error:
            pass

    # 8. Update latest_run_id pointer
    conn.execute("UPDATE niches SET latest_run_id = ? WHERE id = ?", (run_id, niche_id))

    conn.commit()
    return {"niche_id": niche_id, "run_id": run_id, "raw_path": str(raw_path),
            "rating": rating, "criteria_version": crit_ver, "slug": slug}


# ──────────────────────────────────────────────────────────────────────
# Kill list helpers
# ──────────────────────────────────────────────────────────────────────

def record_elimination(keyword: str, reason: str, notes: str = "") -> int:
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO niche_eliminations (keyword, reason, notes) VALUES (?, ?, ?)",
            (keyword.strip(), reason, notes),
        )
        conn.commit()
        return cur.lastrowid or 0
    except sqlite3.Error as e:
        print(f"❌ failed: {e}", file=sys.stderr)
        return 0


def is_killed(keyword: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, reason, notes, eliminated_at FROM niche_eliminations WHERE keyword = ? ORDER BY eliminated_at DESC",
        (keyword.strip(),),
    ).fetchall()
    return [dict(r) for r in rows]


def list_kills(reason_filter: str | None = None) -> list[dict]:
    conn = get_conn()
    sql = "SELECT id, keyword, reason, notes, eliminated_at FROM niche_eliminations"
    args: tuple = ()
    if reason_filter:
        sql += " WHERE reason = ?"; args = (reason_filter,)
    sql += " ORDER BY eliminated_at DESC"
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


# ──────────────────────────────────────────────────────────────────────
# Decisions
# ──────────────────────────────────────────────────────────────────────

def record_decision(niche_id: int, decision: str, reason: str = "", book_id: int | None = None) -> int:
    if decision not in ("LAUNCH", "REJECT", "DEFER", "DEAD"):
        raise ValueError(f"decision must be LAUNCH|REJECT|DEFER|DEAD, got {decision}")
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO niche_decisions (niche_id, decision, reason, book_id) VALUES (?, ?, ?, ?)",
        (niche_id, decision, reason, book_id),
    )
    conn.commit()
    return cur.lastrowid


def list_decisions(niche_id: int | None = None) -> list[dict]:
    conn = get_conn()
    sql = """SELECT d.id, d.niche_id, n.slug, n.niche_name, d.decision, d.reason, d.book_id, d.decided_at
             FROM niche_decisions d JOIN niches n ON n.id = d.niche_id"""
    args: tuple = ()
    if niche_id:
        sql += " WHERE d.niche_id = ?"; args = (niche_id,)
    sql += " ORDER BY d.decided_at DESC"
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


# ──────────────────────────────────────────────────────────────────────
# Queries
# ──────────────────────────────────────────────────────────────────────

def list_runs(niche_id: int | None = None, rating: str | None = None) -> list[dict]:
    conn = get_conn()
    where = []; args = []
    if niche_id: where.append("r.niche_id = ?"); args.append(niche_id)
    if rating: where.append("r.rating = ?"); args.append(rating)
    sql = """SELECT r.id, r.niche_id, n.slug, n.niche_name, r.criteria_version,
                    r.overall_score, r.rating, r.eliminated, r.elimination_reasons,
                    r.raw_json_path, r.created_at
             FROM niche_research_runs r JOIN niches n ON n.id = r.niche_id"""
    if where: sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY r.created_at DESC LIMIT 200"
    return [dict(r) for r in conn.execute(sql, tuple(args)).fetchall()]


def get_top10(niche_id_or_slug: str) -> list[dict]:
    conn = get_conn()
    if niche_id_or_slug.isdigit():
        niche_id = int(niche_id_or_slug)
    else:
        row = conn.execute("SELECT id FROM niches WHERE slug = ?", (niche_id_or_slug,)).fetchone()
        if not row: return []
        niche_id = row["id"]
    run = conn.execute(
        "SELECT id FROM niche_research_runs WHERE niche_id = ? ORDER BY created_at DESC LIMIT 1",
        (niche_id,),
    ).fetchone()
    if not run: return []
    rows = conn.execute(
        "SELECT rank, asin, bsr, reviews, rating, price, pages, publisher, age_days "
        "FROM niche_top10 WHERE run_id = ? ORDER BY rank", (run["id"],)
    ).fetchall()
    return [dict(r) for r in rows]


def status_summary() -> dict:
    conn = get_conn()
    out = {}
    out["niches_total"]    = conn.execute("SELECT COUNT(*) c FROM niches").fetchone()["c"]
    out["runs_total"]      = conn.execute("SELECT COUNT(*) c FROM niche_research_runs").fetchone()["c"]
    out["kills_total"]     = conn.execute("SELECT COUNT(*) c FROM niche_eliminations").fetchone()["c"]
    out["decisions_total"] = conn.execute("SELECT COUNT(*) c FROM niche_decisions").fetchone()["c"]
    out["top10_rows"]      = conn.execute("SELECT COUNT(*) c FROM niche_top10").fetchone()["c"]
    out["criteria_version_active"] = current_version()
    out["by_rating"] = {r["rating"] or "?": r["c"] for r in conn.execute(
        "SELECT rating, COUNT(*) c FROM niche_research_runs GROUP BY rating").fetchall()}
    out["by_criteria_version"] = {r["criteria_version"]: r["c"] for r in conn.execute(
        "SELECT criteria_version, COUNT(*) c FROM niche_research_runs GROUP BY criteria_version").fetchall()}
    return out


# ──────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────

def cli() -> None:
    p = argparse.ArgumentParser(prog="niches_v2")
    sub = p.add_subparsers(dest="cmd", required=True)

    save_p = sub.add_parser("save", help="Save a niche research packet (JSON file)")
    save_p.add_argument("packet_path")

    runs_p = sub.add_parser("runs", help="List research runs")
    runs_p.add_argument("--niche_id", type=int)
    runs_p.add_argument("--rating")

    t10_p = sub.add_parser("top10", help="Top-10 competitor snapshot for latest run")
    t10_p.add_argument("niche_id_or_slug")

    kill_p = sub.add_parser("kill", help="Add keyword to kill list")
    kill_p.add_argument("keyword")
    kill_p.add_argument("--reason", required=True,
                        choices=["dead_market","over_saturated","race_to_bottom",
                                 "single_publisher_lock","seasonal_missed_window",
                                 "ip_trap","commodity_trap","manual_reject"])
    kill_p.add_argument("--notes", default="")

    isk_p = sub.add_parser("is-killed", help="Check if a keyword is killed")
    isk_p.add_argument("keyword")

    kl_p = sub.add_parser("kill-list", help="List all killed keywords")
    kl_p.add_argument("--reason")

    dec_p = sub.add_parser("decide", help="Record a decision on a niche")
    dec_p.add_argument("niche_id", type=int)
    dec_p.add_argument("--decision", required=True, choices=["LAUNCH","REJECT","DEFER","DEAD"])
    dec_p.add_argument("--reason", default="")
    dec_p.add_argument("--book_id", type=int)

    decs_p = sub.add_parser("decisions", help="List decisions")
    decs_p.add_argument("--niche_id", type=int)

    sub.add_parser("status", help="System summary")

    args = p.parse_args()

    if args.cmd == "save":
        packet = json.loads(Path(args.packet_path).read_text())
        out = save_research(packet)
        print(json.dumps(out, indent=2, default=str))
    elif args.cmd == "runs":
        print(json.dumps(list_runs(args.niche_id, args.rating), indent=2, default=str))
    elif args.cmd == "top10":
        print(json.dumps(get_top10(args.niche_id_or_slug), indent=2, default=str))
    elif args.cmd == "kill":
        new_id = record_elimination(args.keyword, args.reason, args.notes)
        print(json.dumps({"ok": True, "id": new_id, "keyword": args.keyword, "reason": args.reason,
                          "already_existed": new_id == 0}, indent=2))
    elif args.cmd == "is-killed":
        kills = is_killed(args.keyword)
        print(json.dumps({"keyword": args.keyword, "killed": bool(kills), "reasons": kills}, indent=2, default=str))
    elif args.cmd == "kill-list":
        print(json.dumps(list_kills(args.reason), indent=2, default=str))
    elif args.cmd == "decide":
        new_id = record_decision(args.niche_id, args.decision, args.reason, args.book_id)
        print(json.dumps({"ok": True, "id": new_id}, indent=2))
    elif args.cmd == "decisions":
        print(json.dumps(list_decisions(args.niche_id), indent=2, default=str))
    elif args.cmd == "status":
        print(json.dumps(status_summary(), indent=2, default=str))


if __name__ == "__main__":
    cli()
