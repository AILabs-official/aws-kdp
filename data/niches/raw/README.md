# data/niches/raw/

**Immutable raw research packets** — 1 file per `/niche-hunter` run.

## Naming
```
YYYY-MM-DD_<slug>.json
```
Example: `2026-04-27_fantasy-mushroom-coloring.json`

## Schema
Full JSON packet from niche-hunter Step 8 (see [.claude/skills/niche-hunter/SKILL.md](../../../.claude/skills/niche-hunter/SKILL.md) → "Niche JSON Packet Schema"). Must include:
- `top10_bsr`, `top10_reviews`, `top10_prices`, `top10_pages`, `top10_publishers`, `top10_age_days`, `top10_rating`, `top10_asins`
- `qualitative_edge` (4 checks)
- `trademark_check` (verdict + class hits)
- `criteria_version` — version of `data/criteria/niche_criteria_v*.json` used
- `sources[]` — URLs of WebSearch / Apify queries

## Rules
1. **Append-only** — never overwrite. New research = new file.
2. **One slug, many files** — re-running `/niche-hunter cozy_cat_cafe` 3 months later creates `2026-07-12_cozy-cat-cafe.json`. Both kept.
3. **Re-scoring** — when `data/criteria/niche_criteria_v*.json` bumps version, raw files here can be re-evaluated under new weights without losing history.
4. **Linked from DB** — `niche_research_runs.raw_json_path` references the file (Phase 2 schema).

## Why
Without raw inputs, score drift is impossible to detect. Niche #3 in the DB has score `82.0` (composite is 0-10 scale!) — proof that DB without raw = lost truth.
