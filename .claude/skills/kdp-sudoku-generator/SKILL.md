---
name: kdp-sudoku-generator
description: Generate 9×9 Sudoku puzzles (backtracking + unique-solution verified) and assemble a KDP-ready interior PDF (title/copyright/how-to-play + puzzle pages + solutions section + thank-you, even page count enforced). Wraps scripts/generate_sudoku.py + scripts/build_sudoku_book.py. USE WHEN user says 'generate sudoku', 'create sudoku book', 'sudoku interior', 'build sudoku pdf', 'make sudoku puzzles', 'tao sudoku', 'tao sach sudoku', or when a book's plan.json has book_type='sudoku' or style='sudoku'.
---

# KDP Sudoku Generator

Produces the **interior** of a Sudoku book end-to-end: puzzles + PDF. Front matter, puzzle pages (1 per page), solutions (4 per page), and thank-you are all included in the output `interior.pdf`. Use this instead of the AI-image pipeline (`kdp-prompt-writer` + `kdp-image-generator` + `kdp-image-reviewer` + `kdp-book-builder`) whenever the book is procedurally-generated sudoku content.

---

## Execution Protocol — READ FIRST

- Run **ALL** steps in sequence **WITHOUT stopping** between them.
- Do **NOT** ask "ready to continue?" / "proceed?" / "shall I move on?" between steps. The skill was invoked — that's the green light.
- After a tool call returns (Bash/Read/Write/Agent), **immediately proceed** to the next step in the same turn.
- Between steps, emit at most ONE short progress sentence, then continue.
- Delegate heavy work to sub-agents (general-purpose Task) — let them run autonomously in their own 200K context.
- Stop ONLY when: (a) all steps complete, (b) blocking error makes next step impossible, (c) a step explicitly marked **(pause for user)** is reached.

---

## When to use

- User wants to build a Sudoku book interior
- A book's `plan.json` has `book_type: "sudoku"` OR `style: "sudoku"` OR `content_method: "sudoku"`
- `manuscript-generator` agent dispatches to this skill via book_type routing
- `/create-book` slash command is invoked with a sudoku concept

**Do NOT use** for: coloring books, crossword, word search, maze, journal, comic. Each has (or will have) its own generator skill.

---

## Prerequisites

1. `scripts/generate_sudoku.py` and `scripts/build_sudoku_book.py` exist
2. `output/{theme_key}/plan.json` exists with at least: `title`, `subtitle`, `author`, `difficulty_distribution` (or `puzzle_count`)
3. Python 3.9+ with `reportlab`, `pypdf` installed (covered by `requirements.txt`)

---

## Process

### Step 1 — Read the book spec

```bash
cat output/{theme_key}/plan.json
```

Required fields (skill fails loud if missing):
- `title` — string
- `author` — string (pen name or imprint accepted)
- `difficulty_distribution` — object like `{"easy": 60, "medium": 120, "hard": 60, "expert": 0}`

Optional fields (with defaults):
- `subtitle` — empty string if missing
- `seed` — integer RNG seed for reproducibility (omit for random)

**→ proceed directly to next step without pausing.**

### Step 2 — Generate puzzles

```bash
# Build difficulty spec string from plan.json
SPEC=$(python3 -c "
import json
p = json.load(open('output/{theme_key}/plan.json'))
d = p['difficulty_distribution']
print(','.join(f'{k}:{v}' for k,v in d.items() if v > 0))
")

SEED=$(python3 -c "
import json
p = json.load(open('output/{theme_key}/plan.json'))
print(p.get('seed', ''))
")

SEED_ARG=""
[ -n "$SEED" ] && SEED_ARG="--seed $SEED"

python3 scripts/generate_sudoku.py \
  --theme {theme_key} \
  --difficulty "$SPEC" \
  $SEED_ARG
```

Output: `output/{theme_key}/sudoku_puzzles.json` — every puzzle has a verified unique solution (backtracking solver, limit=2). Budget ~0.3s per puzzle (240 puzzles ≈ 60-90s).

**Verify**:
```bash
python3 -c "
import json
p = json.load(open('output/{theme_key}/sudoku_puzzles.json'))
want = json.load(open('output/{theme_key}/plan.json'))['difficulty_distribution']
got = {}
for puz in p:
    got[puz['difficulty']] = got.get(puz['difficulty'], 0) + 1
for k, v in want.items():
    if v > 0 and got.get(k, 0) != v:
        raise SystemExit(f'count mismatch {k}: want {v} got {got.get(k, 0)}')
print(f'OK — {len(p)} puzzles, distribution {got}')
"
```

**→ proceed directly to next step without pausing.**

### Step 3 — Build interior PDF

```bash
python3 scripts/build_sudoku_book.py --theme {theme_key}
```

Output: `output/{theme_key}/interior.pdf`. Layout is fixed at 8.5×11 in for v1 (large-print standard trim for sudoku). Even page count enforced by a trailing blank if necessary.

**Verify**:
```bash
python3 -c "
from pypdf import PdfReader
r = PdfReader('output/{theme_key}/interior.pdf')
n = len(r.pages)
assert n % 2 == 0, f'odd page count: {n}'
print(f'OK — {n} pages')
"
```

**→ proceed directly to next step without pausing.**

### Step 4 — QC

```bash
python3 scripts/pdf_qc.py \
  --pdf output/{theme_key}/interior.pdf \
  --trim 8.5x11 \
  --require-even-pages
```

Must exit 0 (`GO`). On `NO_GO`, surface the critical issues to the caller — do not silently continue.

**→ proceed directly to next step without pausing.**

### Step 5 — Update plan.json + DB

Persist the **actual** page count (differs from `target_page_count` because solution pages scale with puzzle count):

```bash
PAGES=$(python3 -c "from pypdf import PdfReader; print(len(PdfReader('output/{theme_key}/interior.pdf').pages))")

python3 -c "
import json
p = json.load(open('output/{theme_key}/plan.json'))
p['actual_page_count'] = $PAGES
json.dump(p, open('output/{theme_key}/plan.json', 'w'), indent=2)
"

# DB — create book row if missing, then manuscripts row
BOOK_ID=$(python3 scripts/db.py books get --theme_key {theme_key} 2>/dev/null \
  | python3 -c "import sys,json; r=json.load(sys.stdin); print(r['id'] if r else '')")

if [ -z "$BOOK_ID" ]; then
  BOOK_ID=$(python3 scripts/db.py books create '{
    "theme_key": "{theme_key}",
    "book_type": "activity",
    "page_size": "8.5x11",
    "target_page_count": '$PAGES',
    "actual_page_count": '$PAGES',
    "status": "INTERIOR_READY"
  }' | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
fi

python3 scripts/db.py manuscripts create '{
  "book_id": '$BOOK_ID',
  "plan_json_path": "output/{theme_key}/plan.json",
  "file_path": "output/{theme_key}/interior.pdf",
  "page_count": '$PAGES',
  "status": "READY"
}'

python3 scripts/db.py books update $BOOK_ID '{"actual_page_count": '$PAGES', "status": "INTERIOR_READY"}'
```

Note: `book_type` in DB uses `"activity"` (the schema CHECK allows coloring/low_content/activity). Sudoku books are classified as activity.

**→ END of skill execution. Report results to user.**

---

## Inputs

- `theme_key` (required) — snake_case folder name under `output/`
- `plan.json` (required) — must be pre-populated by niche-hunter or `kdp-book-detail` skill

## Outputs

- `output/{theme_key}/sudoku_puzzles.json` — 240+ puzzles with solutions
- `output/{theme_key}/interior.pdf` — KDP-upload-ready interior
- `plan.json.actual_page_count` — updated with real page count
- DB: `books` row + `manuscripts` row, status `INTERIOR_READY`

## Return

Summary to caller:
```
theme_key={theme_key}
puzzles={total}  ({easy} easy + {medium} medium + {hard} hard + {expert} expert)
interior_pages={N}  (even ✓)
interior_pdf={path}  size={size_mb} MB
qc_verdict=GO
book_id={id}
```

---

## Error handling

| Error | Action |
|---|---|
| `plan.json` missing `difficulty_distribution` | Fail loud — caller must fix plan. Do NOT assume defaults |
| `generate_sudoku.py` fails | Retry once. Unique-solution loop is deterministic per-seed; if failing repeatedly, escalate |
| A difficulty count comes back short (rare — uniqueness floor) | Re-run with higher RNG attempts; surface final counts in return |
| `build_sudoku_book.py` fails on missing plan fields | Report which field is missing; ask caller to pre-fill |
| `pdf_qc.py` NO_GO | Surface critical issues verbatim. Do not modify interior to bypass QC |
| `pypdf` not installed | `pip install pypdf` — listed in requirements.txt |

---

## Rules

- This skill handles **interior only**. Cover is `kdp-cover-creator`; listing is `kdp-book-detail`; QC is `quality-reviewer` agent
- Never override the unique-solution verification — shipping puzzles with multiple/no solutions is the #1 review killer for sudoku books
- Keep puzzle count ≥ 100 for perceived value; keep page count ≤ 500 (gutter requirements + KDP cost)
- Only 8.5×11 trim supported in v1. 6×9 commuter trim support is phase 2 — do NOT silently accept other trim keys
- If the book uses `book_type: "sudoku"` in plan.json, persist as `book_type: "activity"` in DB (schema constraint)
- Seed the RNG (`--seed` in plan.json) when you want reproducible builds for testing or cover-reprint scenarios
