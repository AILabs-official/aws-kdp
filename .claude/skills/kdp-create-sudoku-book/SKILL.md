---
name: kdp-create-sudoku-book
description: End-to-end pipeline tạo 1 cuốn sudoku book KDP từ concept → interior PDF + cover + listing SEO + QA, sẵn sàng upload Amazon. Tận dụng song song hóa tối đa (Wave 1 chạy puzzle generation ∥ listing copywriting cùng lúc qua sub-agents). Ngắn hơn coloring pipeline (~5-10 phút vs ~20-30 phút) vì sudoku là procedural — không cần AI image generation. USE WHEN user nói 'tao sach sudoku', 'create sudoku book', 'sudoku book end to end', 'build sudoku book', 'kdp sudoku launch', 'lam sach sudoku', 'tao sudoku tron goi', hoặc đưa concept sudoku và muốn ra file ready-to-upload. Không dùng cho coloring/crossword/word-search (mỗi loại có pipeline riêng).
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Agent, AskUserQuestion, Skill, TodoWrite
---

# KDP Create Sudoku Book — Launch Pipeline (sudoku-only)

End-to-end orchestrator cho **1 cuốn sudoku book**: concept → interior + cover + listing + QA → ready to upload KDP. Đây là biến thể sudoku-specific của `/create-book`, được tinh chỉnh để khai thác parallelism tối đa và bỏ hẳn AI-image pipeline (sudoku là procedural).

## Execution Protocol — READ FIRST

- Chạy **TẤT CẢ** phase tuần tự **KHÔNG dừng** giữa chừng.
- **KHÔNG** hỏi "ready to continue?" / "proceed?" / "shall I move on?". Skill được invoke = green light.
- Sau mỗi tool call (Bash/Agent/Skill), **lập tức** sang step kế tiếp trong cùng turn.
- Giữa các step chỉ emit ≤ 1 câu progress ngắn rồi tiếp tục.
- **Delegate heavy work** sang sub-agents (Agent tool) — để chúng chạy autonomously trong 200K context riêng.
- Dừng CHỈ KHI: (a) tất cả phase done, (b) blocking error không thể tiếp, (c) gặp **(pause for user)** explicit, (d) QA verdict NO_GO.

## Khi nào dùng

- User cung cấp concept sudoku và muốn pipeline hoàn chỉnh ("tao sach sudoku Large print cho người già")
- `/kdp-create-sudoku-book` slash command được gọi
- User đã có `niche_id` HOẶC `idea_file` từ niche-hunter và muốn launch
- `book_type` đã xác định là sudoku (KHÔNG dispatch sang đây nếu là coloring/activity-art)

**KHÔNG dùng** cho: coloring book → dùng `kdp-book-creator` hoặc `/create-book`. Crossword/word-search/maze → chưa có pipeline (phase 2).

## Phân tích parallelism (quan trọng — ảnh hưởng cách spawn agent)

| Phase | Mode | Lý do |
|---|---|---|
| 0. Intake (plan.json + DB row) | Sequential | Mọi thứ phụ thuộc plan.json |
| 1a. Puzzle gen + interior.pdf | **PARALLEL với 1b** | Đọc plan.json, ghi `actual_page_count` + `interior.pdf` |
| 1b. Listing SEO (title/keywords/description) | **PARALLEL với 1a** | Đọc plan.json, ghi metadata fields disjoint |
| 2. Cover (front + spine + back) | Sequential sau Phase 1 | Cần `actual_page_count` từ 1a để tính spine width |
| 3. QA (pdf_qc + metadata consistency) | Sequential sau Phase 2 | Cần đủ interior + cover + listing |
| 4. Publish gate | User-blocked | Chỉ user có ASIN sau khi upload KDP |

**Phase 1 spawn 2 sub-agents trong 1 message** (không tuần tự). DB đã enable WAL mode (`busy_timeout=30s`) nên concurrent writes an toàn. ETA tổng: 5-10 phút (sudoku) vs 20-30 phút (coloring).

## Prerequisites

- Repo có sẵn: `scripts/generate_sudoku.py`, `scripts/build_sudoku_book.py`, `scripts/generate_cover.py`, `scripts/pdf_qc.py`, `scripts/db.py`
- Sub-agents khả dụng: `manuscript-generator`, `listing-copywriter`, `cover-designer`, `quality-reviewer`
- Skills: `kdp-sudoku-generator`, `kdp-book-detail`, `kdp-cover-creator`, `kdp-cover-checker`, `quality-reviewer`
- Python 3.9+ với `reportlab` + `pypdf`
- `data/kdp.db` đã initialize (WAL mode tự bật)

## Inputs (xử lý linh hoạt)

Skill có thể được invoke với 1 trong 4 dạng input:

1. **Concept string** — `"large print sudoku for seniors, 200 puzzles easy-medium"`
2. **idea_file path** — `idea_file=ideas/sudoku_seniors.md` (frontmatter YAML)
3. **niche_id** — `niche_id=42` (đọc từ `niches` table)
4. **Empty** — không có gì → AskUserQuestion để gather

Required output từ intake:
- `concept` (string)
- `theme_key` (snake_case, e.g. `large_print_sudoku_seniors_v3`)
- `audience` (`adults` | `kids_6_12` | `seniors`)
- `difficulty_distribution` ({"easy": N, "medium": N, "hard": N, "expert": N})
- `author` (default từ `.env` AUTHOR_FIRST_NAME + AUTHOR_LAST_NAME)
- `page_size` (default `8.5x11` — sudoku v1 chỉ support trim này)

---

## Phase 0 — Intake (sequential)

### Step 0.1 — Parse args + gather missing fields

Pseudo-flow:

```
IF args chứa idea_file:
  Read frontmatter từ ideas/{file}.md → extract concept, audience, difficulty
ELIF args chứa niche_id:
  Bash: python3 scripts/db.py niches get $NICHE_ID → extract concept, scoring metadata
ELIF args là concept string:
  concept = string đó
ELSE:
  AskUserQuestion để gather (xem dưới)
```

Khi cần AskUserQuestion (chỉ hỏi field còn thiếu — đừng spam câu hỏi):

```
Q1. Concept ngắn gọn (e.g. "large print sudoku for seniors easy-medium")
Q2. Audience (options: adults, kids_6_12, seniors)
Q3. Tổng số puzzle (75 / 100 / 150 / 200 / 240 — recommend 150-200 cho perceived value)
Q4. Difficulty mix (options: "all_easy", "easy_medium", "balanced_4_levels", "hard_only", "custom")
Q5. Theme key (snake_case, validate regex ^[a-z][a-z0-9_]*$). Nếu user không gõ → suggest từ concept
Q6. Author name (default = .env AUTHOR_FIRST + AUTHOR_LAST nếu có)
```

Convert difficulty mix → distribution dict:
- `all_easy` → `{"easy": N}`
- `easy_medium` → `{"easy": N*0.6, "medium": N*0.4}`
- `balanced_4_levels` → `{"easy": N*0.3, "medium": N*0.4, "hard": N*0.2, "expert": N*0.1}`
- `hard_only` → `{"hard": N*0.7, "expert": N*0.3}`
- `custom` → ask user breakdown explicitly

### Step 0.2 — Tạo plan.json + books DB row

```bash
mkdir -p output/{theme_key}

# Build plan.json (book_type=sudoku quan trọng → routing đúng)
cat > output/{theme_key}/plan.json <<JSON
{
  "theme_key": "{theme_key}",
  "title": "",
  "subtitle": "",
  "author": "{author}",
  "audience": "{audience}",
  "page_size": "8.5x11",
  "book_type": "sudoku",
  "content_method": "sudoku",
  "difficulty_distribution": {distribution_dict_json},
  "target_page_count": 0,
  "concept": "{concept}",
  "description": "",
  "keywords": [],
  "categories": [],
  "cover_prompt": "",
  "page_prompts": [],
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
JSON

# Tạo books row (status=DRAFT, sẽ update INTERIOR_READY sau Phase 1)
BOOK_ID=$(python3 scripts/db.py books create '{
  "theme_key": "{theme_key}",
  "book_type": "activity",
  "page_size": "8.5x11",
  "author": "{author}",
  "audience": "{audience}",
  "status": "DRAFT"
}' | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

echo "BOOK_ID=$BOOK_ID"
```

Note: DB schema CHECK constraint chỉ cho phép `book_type IN (coloring, low_content, activity)` → sudoku phải lưu `"activity"`. plan.json giữ `"sudoku"` cho routing đúng.

### Step 0.3 — Tạo pipelines row (audit trail)

```bash
PIPELINE_ID=$(python3 scripts/db.py pipelines create '{
  "pipeline_type": "launch_sudoku",
  "status": "RUNNING",
  "book_id": '$BOOK_ID',
  "current_step": 1,
  "step_log": []
}' | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

python3 scripts/db.py pipelines append-log --id $PIPELINE_ID --step "intake" --status OK --note "theme={theme_key}, puzzles={total}, audience={audience}"
```

**→ proceed to Phase 1 ngay, không pause.**

---

## Phase 1 — PARALLEL: Puzzle generation ∥ Listing SEO

**Spawn 2 sub-agents trong CÙNG 1 message (1 turn, multiple Agent tool calls).** Đây là điểm quan trọng nhất của parallelism — đừng tuần tự.

### Sub-agent A: manuscript-generator (puzzle + interior PDF)

Prompt cho `manuscript-generator`:

```
theme_key={theme_key}
book_id={BOOK_ID}

Plan.json đã tồn tại tại output/{theme_key}/plan.json với book_type=sudoku.
Dispatch theo book_type → invoke skill kdp-sudoku-generator.

Yêu cầu:
1. Generate puzzles theo difficulty_distribution trong plan.json
2. Build interior.pdf (8.5x11, even page count, with how-to-play + solutions section)
3. Run pdf_qc.py để self-verify
4. Update plan.json.actual_page_count
5. Tạo manuscripts row trong DB (status=READY, file_path=interior.pdf)
6. Update books row → status=INTERIOR_READY

Return summary với: puzzle counts per difficulty, actual_page_count, qc verdict.
KHÔNG quay lại hỏi gì — invoked = đã có đầy đủ input.
```

### Sub-agent B: listing-copywriter (SEO metadata)

Prompt cho `listing-copywriter`:

```
theme_key={theme_key}
book_id={BOOK_ID}

Plan.json đã tồn tại tại output/{theme_key}/plan.json với:
- concept: "{concept}"
- audience: "{audience}"
- book_type: "sudoku"
- difficulty_distribution: ...

Yêu cầu (wraps skill kdp-book-detail):
1. Viết title + subtitle SEO-optimized cho Amazon (≤ 200 chars title, đặt keyword chính lên đầu)
2. Viết description HTML (350-450 từ, hook + features + CTA)
3. 7 backend keywords (mỗi cái ≤ 50 chars, không trùng title)
4. 2 BISAC categories ưu tiên cho Activity & Game Books / Puzzles
5. Reading age phù hợp (audience=seniors → 60+ adult; kids_6_12 → 6-12)
6. Update plan.json (chỉ ghi: title, subtitle, description, keywords, categories, reading_age)
7. Tạo listings row trong DB (status=READY)

KHÔNG đụng vào: actual_page_count, page_count, page_prompts, sudoku_puzzles, interior_pdf — đó là phòng manuscript.
KHÔNG quay lại hỏi gì.
Return summary với title + 7 keywords.
```

### Cách spawn (TRONG 1 MESSAGE):

```
Agent(subagent_type="manuscript-generator", prompt="<sub-agent A prompt>")
Agent(subagent_type="listing-copywriter", prompt="<sub-agent B prompt>")
```

Cả 2 chạy concurrent. Đợi cả 2 return rồi:

```bash
python3 scripts/db.py pipelines append-log --id $PIPELINE_ID --step "wave1_parallel" --status OK --note "puzzles+listing done"
```

**Conflict guard**: nếu cả 2 agent ghi cùng key trong plan.json → dùng read-modify-write pattern (load JSON, update sub-dict, save). Listing-copywriter agent đã được brief field-disjoint → khả năng conflict thấp, nhưng nếu xảy ra, manuscript thắng cho `actual_page_count`, listing thắng cho metadata.

**Failure mode**: nếu **một** sub-agent fail mà cái kia ok → append-log FAIL cho phần fail, pipeline status=PAUSED, report user blocker, **dừng** (không tự re-spawn). Nếu **cả 2** ok → tiếp Phase 2.

**→ proceed to Phase 2.**

---

## Phase 2 — Cover (sequential, depends on page_count)

```bash
PAGES=$(python3 -c "from pypdf import PdfReader; print(len(PdfReader('output/{theme_key}/interior.pdf').pages))")
echo "Page count for spine math: $PAGES"
```

Spawn `cover-designer` agent:

```
Agent(subagent_type="cover-designer", prompt="
theme_key={theme_key}
book_id={BOOK_ID}
page_count={PAGES}
trim_size=8.5x11
author={author}

Yêu cầu:
1. Đọc title/subtitle từ output/{theme_key}/plan.json (đã được listing-copywriter điền)
2. Generate full-wrap cover (front + spine + back)
   - Spine width = page_count × 0.002252\" (white paper)
   - Bleed 0.125\" mọi cạnh
   - Spine text chỉ in khi page_count >= 79
3. Lưu cover.png (raster) + cover.pdf (KDP upload format)
4. Run kdp-cover-checker để validate dimensions vs KDP spec
5. Tạo covers row trong DB (status=READY)
6. Update books → status=COVER_READY

Style hint cho front art (sudoku book):
- Audience seniors → calm, large readable text, soft pastels
- Audience kids → bright, playful, cartoon-like
- Audience adults → modern minimalist, geometric grid pattern
KHÔNG hỏi lại — đầy đủ input.
")
```

```bash
python3 scripts/db.py pipelines append-log --id $PIPELINE_ID --step "cover" --status OK --note "page_count=$PAGES, spine=" 
```

**→ proceed to Phase 3.**

---

## Phase 3 — QA (sequential, gates publish)

```
Agent(subagent_type="quality-reviewer", prompt="
theme_key={theme_key}
book_id={BOOK_ID}
section=all

Yêu cầu pre-publish audit:
1. Interior PDF: trim 8.5x11, even page count, 300 DPI, no encryption, not > 650 MB
2. Cover PDF: full-wrap dims đúng, bleed 0.125\", spine width khớp page_count
3. Metadata consistency: title/author trên title page === copyright === cover === spine === plan.json
4. Listing: title ≤ 200 chars, 7 keywords mỗi cái ≤ 50 chars, không banned terms (spiral bound, leather bound, hard bound, calendar)
5. Trademark check chạy scripts/trademark_check.py trên title + keywords
6. Ghi qa_reports row với verdict GO | NO_GO + critical issues list
7. Nếu NO_GO → tạo actions rows cho remediation (FIX_INTERIOR / FIX_COVER / FIX_LISTING) priority=3
")
```

Sau khi quality-reviewer return:

```bash
VERDICT=$(python3 scripts/db.py qa_reports list --book_id $BOOK_ID --order-by "id:DESC" --limit 1 \
  | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['verdict'])")

if [ "$VERDICT" = "NO_GO" ]; then
  python3 scripts/db.py pipelines append-log --id $PIPELINE_ID --step "qa" --status FAIL --note "verdict=NO_GO, see qa_reports"
  python3 scripts/db.py pipelines update $PIPELINE_ID '{"status": "PAUSED"}'
  # STOP — surface blockers to user
  exit 0
fi

python3 scripts/db.py pipelines append-log --id $PIPELINE_ID --step "qa" --status OK --note "verdict=GO"
python3 scripts/db.py books update $BOOK_ID '{"status": "READY_TO_PUBLISH"}'
```

**→ proceed to Phase 4.**

---

## Phase 4 — Publish gate **(pause for user)**

Đây là pause point duy nhất trong skill. KDP upload là user decision (không bao giờ auto-upload).

Report ra user:

```
✅ READY TO PUBLISH

theme_key={theme_key}
book_id={BOOK_ID}
pipeline_id={PIPELINE_ID}

📚 Interior:  output/{theme_key}/interior.pdf  ({PAGES} pages, GO)
🎨 Cover:     output/{theme_key}/cover.pdf      (full-wrap, GO)
📝 Listing:   title={title}
              keywords={keywords[0..2]}...
              categories={categories}

Next steps:
1. Upload interior.pdf + cover.pdf lên https://kdp.amazon.com
2. Paste title/subtitle/description/keywords từ plan.json vào form
3. Submit để Amazon review (~24-72h)
4. Khi có ASIN, paste lại đây hoặc chạy:
   python3 scripts/db.py books update {BOOK_ID} '{"asin": "B0XXXXXX", "status": "LIVE"}'
5. Sau khi LIVE → invoke ads-manager để launch Sponsored Products campaigns

Pipeline {PIPELINE_ID} status=READY_TO_PUBLISH (chờ ASIN).
```

Append-log final:

```bash
python3 scripts/db.py pipelines append-log --id $PIPELINE_ID --step "publish_gate" --status INFO --note "awaiting_asin"
```

**→ END of skill execution. Do NOT loop / wait / retry.**

---

## Outputs (full inventory)

```
output/{theme_key}/
  plan.json              — concept + book_type=sudoku + difficulty_distribution + SEO metadata (title/sub/desc/keywords/categories) + actual_page_count
  sudoku_puzzles.json    — N puzzles với verified unique solutions
  interior.pdf           — KDP upload-ready interior, 8.5x11, even page count
  front_artwork.png      — saved cover front art (reused on cover rebuild)
  cover.png              — full-wrap raster preview
  cover.pdf              — KDP upload-ready cover

DB rows created:
  books        — id={BOOK_ID}, status=READY_TO_PUBLISH
  manuscripts  — file_path=interior.pdf, status=READY
  covers       — file_path=cover.pdf, status=READY
  listings     — title/keywords/categories, status=READY
  qa_reports   — verdict=GO
  pipelines    — id={PIPELINE_ID}, type=launch_sudoku, status=PAUSED (awaiting_asin)
```

## Return summary template

```
✅ kdp-create-sudoku-book DONE — book_id={BOOK_ID}, pipeline_id={PIPELINE_ID}

🧩 Puzzles:    {total}  ({easy} easy / {medium} med / {hard} hard / {expert} exp)
📄 Interior:   {pages} pages  ({size_mb} MB)
🎨 Cover:      front+spine+back ({trim} wrap)
📝 Listing:    "{title}"
               keywords: {kw[:3]}...
               categories: {cat}
🛡️ QA verdict: GO

Time elapsed: ~{minutes} min  (Wave 1 parallel saved ~{savings_min} min vs sequential)
Next: upload to KDP → paste ASIN → invoke ads-manager.
```

---

## Error handling

| Error | Action |
|---|---|
| Concept ambiguous / theme_key trùng folder cũ | AskUserQuestion confirm overwrite hoặc đổi key (suffix `_v2`, `_v3`...) |
| `difficulty_distribution` total < 50 puzzles | Cảnh báo user "perceived value thấp", confirm trước khi tiếp |
| Sub-agent A fail (manuscript) | append-log FAIL, pipeline=PAUSED, report critical issues, **dừng** — không tự re-spawn (sub-agent biết retry trong skill của nó rồi) |
| Sub-agent B fail (listing) | tương tự A — pipeline=PAUSED |
| Cả 2 sub-agent ghi conflict trong plan.json | re-read plan.json, log conflict, manuscript thắng `actual_page_count`, listing thắng metadata fields |
| Cover dims sai (kdp-cover-checker NO_GO) | Re-run cover-designer 1 lần với `--regenerate=false` (reuse front_artwork). Vẫn fail → pipeline=PAUSED |
| QA verdict=NO_GO | append-log FAIL, pipeline=PAUSED, **NO** auto-fix, surface blockers + remediation actions cho user |
| `data/kdp.db` busy > 30s | Abort pipeline (data integrity > progress) |
| User cancel giữa chừng | Pipeline=PAUSED với last successful step, có thể resume bằng cách invoke manual sub-agent |

---

## Rules (critical — không vi phạm)

1. **KHÔNG auto-upload KDP** — Phase 4 luôn pause cho user decision (luật của master-orchestrator, áp dụng tại đây)
2. **KHÔNG spawn manuscript ∥ listing tuần tự** — phải song song trong cùng 1 message để tận dụng parallelism (mất ~50% Wave 1 time nếu sequential)
3. **KHÔNG bỏ qua QA** — verdict=NO_GO phải pause, không silently continue
4. **KHÔNG trộn book_type** — skill này CHỈ cho sudoku. Coloring concept → reject với message "use /create-book or kdp-book-creator instead"
5. **KHÔNG override DB schema** — `book_type` trong DB phải là `"activity"` (CHECK constraint), plan.json giữ `"sudoku"` cho routing
6. **LUÔN write pipelines.step_log** sau mỗi phase — audit trail không thể thiếu (mất pipeline đang ở step nào nếu crash giữa chừng)
7. **LUÔN read plan.json từ disk** giữa các phase (không cache stale value) — vì sub-agents Wave 1 đã thay đổi file
8. **LUÔN respect KDP weekly publishing limit** (10 titles/format/week) — nếu user đang batch nhiều sách, cảnh báo nếu đã đạt limit (đọc `books` table count by created_at)
9. **Spine text** chỉ enable khi `page_count >= 79` — `full_cover_dims()` trong `kdp_config.py` return `spine_can_have_text` flag, cover-designer phải respect
10. **Banned terms** trong title/subtitle/keywords: "spiral bound", "leather bound", "hard bound", "calendar" — quality-reviewer enforce, nhưng listing-copywriter cũng phải tránh tạo

---

## So sánh với /create-book (skill cũ generic)

| Aspect | `/create-book` (generic) | `/kdp-create-sudoku-book` (skill này) |
|---|---|---|
| Book types | All (coloring/sudoku/activity) | Sudoku only |
| Routing layer | master-orchestrator (CEO) → dispatch | Direct (bỏ qua CEO, gọi 4 agents trực tiếp) |
| Image generation | Có (cho coloring) | KHÔNG (procedural) |
| ETA | 20-30 min (coloring), 5-10 min (sudoku) | 5-10 min |
| Parallelism | manuscript ∥ listing trong CEO Wave 1 | manuscript ∥ listing — same pattern, không cần CEO indirection |
| User input | AskUserQuestion 6 câu (concept/audience/size/pages/key/author) | AskUserQuestion 6 câu sudoku-specific (concept/audience/puzzle_count/difficulty_mix/key/author) |
| Output dir | `output/{theme_key}/` | `output/{theme_key}/` (giống) |
| DB row `book_type` | Theo plan.json | Hardcoded `"activity"` (sudoku) |

Lý do tách skill riêng: sudoku có decision tree khác (difficulty mix thay vì page art style), không cần image renderer config (.env IMAGE_RENDERER bỏ qua), interior generation deterministic (seed-able). Lumping với coloring làm `/create-book` phức tạp hơn cần thiết.
