#!/usr/bin/env python3
"""Niche schema migration v2 (Phase 2, 2026-04-27).

Idempotent: safe to run multiple times.

Adds:
  - niches columns: slug, criteria_version, latest_run_id, raw_json_path
  - tables: niche_research_runs, niche_scores, niche_flags, niche_top10,
            niche_eliminations (kill list), niche_decisions
  - Backfills existing niches with slug + criteria_version='legacy-pre-2026.04.27'
  - Special-cases niche #3 (Cozy Cat Cafe, score 82.0 — legacy schema drift)
"""
from __future__ import annotations
import re
import sys
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB_PATH = HERE.parent / "data" / "kdp.db"
LEGACY_VERSION = "legacy-pre-2026.04.27"


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s[:80] or "unknown"


NEW_COLUMNS = [
    ("slug",             "TEXT"),
    ("criteria_version", "TEXT"),
    ("latest_run_id",    "INTEGER"),
    ("raw_json_path",    "TEXT"),
]

NEW_TABLES = """
CREATE TABLE IF NOT EXISTS niche_research_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    niche_id INTEGER NOT NULL REFERENCES niches(id),
    criteria_version TEXT NOT NULL,
    raw_json_path TEXT,
    overall_score REAL,
    rating TEXT CHECK(rating IN ('HOT','WARM','COLD','SKIP','LEGACY_INVALID')),
    eliminated INTEGER DEFAULT 0,
    elimination_reasons TEXT,
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_runs_niche ON niche_research_runs(niche_id);
CREATE INDEX IF NOT EXISTS idx_runs_version ON niche_research_runs(criteria_version);

CREATE TABLE IF NOT EXISTS niche_scores (
    run_id INTEGER NOT NULL REFERENCES niche_research_runs(id),
    dimension TEXT NOT NULL,
    value REAL NOT NULL,
    PRIMARY KEY (run_id, dimension)
);

CREATE TABLE IF NOT EXISTS niche_flags (
    run_id INTEGER NOT NULL REFERENCES niche_research_runs(id),
    flag_name TEXT NOT NULL,
    PRIMARY KEY (run_id, flag_name)
);

CREATE TABLE IF NOT EXISTS niche_top10 (
    run_id INTEGER NOT NULL REFERENCES niche_research_runs(id),
    rank INTEGER NOT NULL,
    asin TEXT,
    bsr INTEGER,
    reviews INTEGER,
    rating REAL,
    price REAL,
    pages INTEGER,
    publisher TEXT,
    age_days INTEGER,
    PRIMARY KEY (run_id, rank)
);

CREATE TABLE IF NOT EXISTS niche_eliminations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,
    reason TEXT NOT NULL,
    notes TEXT,
    eliminated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_elim_kw_reason ON niche_eliminations(keyword, reason);
CREATE INDEX IF NOT EXISTS idx_elim_keyword ON niche_eliminations(keyword);

CREATE TABLE IF NOT EXISTS niche_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    niche_id INTEGER NOT NULL REFERENCES niches(id),
    decision TEXT CHECK(decision IN ('LAUNCH','REJECT','DEFER','DEAD')),
    reason TEXT,
    book_id INTEGER REFERENCES books(id),
    decided_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_decisions_niche ON niche_decisions(niche_id);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrate() -> dict:
    conn = get_conn()
    report = {"columns_added": [], "tables_created": [], "backfilled": 0, "legacy_flagged": 0}

    # 1. Add columns to niches (idempotent — catch duplicate)
    existing_cols = {r["name"] for r in conn.execute("PRAGMA table_info(niches)").fetchall()}
    for col, sql_type in NEW_COLUMNS:
        if col not in existing_cols:
            conn.execute(f"ALTER TABLE niches ADD COLUMN {col} {sql_type}")
            report["columns_added"].append(col)

    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_niches_slug ON niches(slug) WHERE slug IS NOT NULL")

    # 2. Create new tables
    pre_tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.executescript(NEW_TABLES)
    post_tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    report["tables_created"] = sorted(post_tables - pre_tables)

    # 3. Backfill existing niches: slug + criteria_version + 1 legacy research run
    for row in conn.execute("SELECT id, niche_name, overall_score, rating FROM niches WHERE slug IS NULL OR criteria_version IS NULL").fetchall():
        slug = slugify(row["niche_name"])
        # ensure slug uniqueness
        suffix = 0
        candidate = slug
        while conn.execute("SELECT 1 FROM niches WHERE slug = ? AND id != ?", (candidate, row["id"])).fetchone():
            suffix += 1
            candidate = f"{slug}_{suffix}"
        slug = candidate

        # Detect legacy drift — score outside 0-10 means old schema
        score = row["overall_score"]
        is_legacy_invalid = score is not None and (score < 0 or score > 10)
        legacy_rating = "LEGACY_INVALID" if is_legacy_invalid else (row["rating"] or "COLD")
        legacy_score = None if is_legacy_invalid else score
        notes = "Legacy schema drift — score outside 0-10. Re-research with /niche-hunter to refresh." if is_legacy_invalid else "Backfilled from pre-Phase-1 schema."
        if is_legacy_invalid:
            report["legacy_flagged"] += 1

        cur = conn.execute(
            """INSERT INTO niche_research_runs
               (niche_id, criteria_version, overall_score, rating, eliminated, notes)
               VALUES (?, ?, ?, ?, 0, ?)""",
            (row["id"], LEGACY_VERSION, legacy_score, legacy_rating, notes),
        )
        run_id = cur.lastrowid
        conn.execute(
            "UPDATE niches SET slug = ?, criteria_version = ?, latest_run_id = ? WHERE id = ?",
            (slug, LEGACY_VERSION, run_id, row["id"]),
        )
        report["backfilled"] += 1

    conn.commit()
    return report


if __name__ == "__main__":
    print(f"📦 Migrating niches schema → v2 ({DB_PATH})")
    r = migrate()
    print(f"  columns_added : {r['columns_added'] or '(none — already present)'}")
    print(f"  tables_created: {r['tables_created'] or '(none — already present)'}")
    print(f"  backfilled    : {r['backfilled']} niche(s) tagged with slug + {LEGACY_VERSION}")
    print(f"  legacy_flagged: {r['legacy_flagged']} niche(s) had invalid score → marked LEGACY_INVALID")
    print("✅ Migration complete (idempotent — safe to re-run)")
