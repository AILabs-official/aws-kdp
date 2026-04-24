---
name: kdp-book-creator
description: Create a KDP coloring book end-to-end by orchestrating sub-agents for planning, image generation & review, and book assembly. USE WHEN the user says 'tao sach', 'create coloring book', 'kdp create book', 'build coloring book end to end', 'make a coloring book', 'tao sach to mau', or otherwise asks to produce a complete KDP coloring book from a concept. Trigger even when the user only gives a concept (e.g. "a book about cozy cats") without explicitly naming the pipeline.
---

# KDP Book Creator — End-to-End Orchestrator

You are the **orchestrator**. You own the interview, plan review, and delivery. All heavy work is delegated to sub-agents (the 8-agent KDP company structure in `.claude/agents/`):

| Phase | Sub-agent(s) | Job |
|---|---|---|
| 2a | `listing-copywriter` | Write SEO metadata (title/subtitle/description/7 keywords/2 categories) → plan.json |
| 2b | prompt-writer sub-agent (general-purpose + kdp-prompt-writer skill) | Write page_prompts[] + cover_prompt → plan.json |
| 4  | `manuscript-generator` | Generate images, review, auto-regen, build interior.pdf (plan-exists mode) |
| 5a | `cover-designer` | Front artwork + composite full wrap + cover.pdf |
| 5b | `quality-reviewer` | Pre-publish GO/NO-GO audit + remediation actions if NO_GO |

---

## Execution Protocol — READ FIRST

- Run ALL phases **in sequence without stopping**, except Phase 1 (interview) and Phase 3 (plan review) which need user input.
- Do **NOT** ask confirmation between phases. The user invoked the skill — that's the green light.
- After a sub-agent returns, **immediately proceed** in the same turn. No "ready to continue?".
- Between phases, emit ONE short progress sentence, then continue.
- Delegate heavy work — sub-agents run autonomously in their own 200K context.
- Stop only when: (a) Phase 5 delivered, (b) blocking error, (c) Phase 1/3 needs user.

---

## Pipeline

```
Phase 1: Interview                       (you — pause for user)
Phase 2: Plan Writing (PARALLEL ×2)      (Agents: listing-copywriter ∥ prompt-writer)
Phase 3: Plan Review                     (you — pause for user)
Phase 4: Images + Interior PDF           (Agent: manuscript-generator, plan-exists mode)
Phase 5a: Cover Design                   (Agent: cover-designer)
Phase 5b: Quality Audit                  (Agent: quality-reviewer)
   + Deliver                             (you — present to user)
```

---

## Phase 1: Interview (pause for user)

**AskUserQuestion** to collect:

1. **Concept** — e.g. "cozy cats in a cafe". Skip if passed in invocation args.
2. **Audience** — Adults (cozy/cute) or Kids (6–12).
3. **Book size** — 8.5x11 (portrait, default) or 8.5x8.5 (square).
4. **Page count** — recommend 25–30.
5. **Theme key** — snake_case slug; suggest one based on concept.
6. **Author** — first + last name.

Sau khi user trả lời, write initial plan.json skeleton + register book trong DB:
```bash
mkdir -p output/{theme_key}
python3 -c "
import json
json.dump({
  'theme_key': '{theme_key}',
  'concept': '{concept}',
  'audience': '{audience}',
  'page_size': '{page_size}',
  'author': {'first_name': '{first}', 'last_name': '{last}'},
  'title': '', 'subtitle': '', 'description': '',
  'keywords': [], 'categories': [], 'reading_age': '',
  'cover_prompt': '', 'page_prompts': []
}, open('output/{theme_key}/plan.json','w'), indent=2, ensure_ascii=False)
"
BOOK_ID=$(python3 scripts/db.py books create '{"theme_key":"{theme_key}","book_type":"coloring","page_size":"{page_size}","target_page_count":{page_count},"status":"DRAFT"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "book_id=$BOOK_ID"
```

**→ IMMEDIATELY Phase 2.**

---

## Phase 2: Plan Writing (PARALLEL — 2 agents, 1 message)

Phòng Biên tập và Phòng Content Marketing chạy đồng thời. Cùng đọc plan.json nhưng ghi field **disjoint** (copywriter → title/desc/keywords, prompt-writer → cover_prompt/page_prompts) — KHÔNG conflict.

Launch BOTH trong 1 message:

**Call A — prompt writer:**
```
Agent(
  subagent_type: "general-purpose",
  description: "Write prompts for {theme_key}",
  prompt: "
Write page_prompts + cover_prompt for a KDP coloring book.

- theme_key: {theme_key}
- concept: {concept}
- audience: {audience}
- page_size: {page_size}
- page_count: {page_count}

Steps:
1. Read prompt guide based on audience:
   - Adults: .claude/skills/kdp-prompt-writer/references/adult-prompt-guide.md
   - Kids: .claude/skills/kdp-prompt-writer/references/kids-prompt-guide.md
2. Write cover_prompt (full-color, NO text in image)
3. Write {page_count} page_prompts. SIZE_TAG: 'SQUARE format (1:1)' cho 8.5x8.5, 'PORTRAIT orientation (3:4)' cho 8.5x11. Every prompt must include: NO borders, NO frames. Adults: cute cozy medium-detail, large shapes. Kids: bold thick outlines, single centered subject.
4. Update ONLY 'cover_prompt' and 'page_prompts' in output/{theme_key}/plan.json. page_prompts MUST be array of STRINGS. Leave title/keywords empty (listing-copywriter handles those).
5. Write output/{theme_key}/prompts.txt (one per line).

Return: cover_prompt + 3 sample page_prompts.
Claude writes ALL prompts — KHÔNG gọi external LLM.
  "
)
```

**Call B — listing-copywriter:**
```
Agent(
  subagent_type: "listing-copywriter",
  description: "Write SEO metadata for {theme_key}",
  prompt: "
Write Amazon listing SEO cho 1 sách.

- theme_key: {theme_key}
- audience: {audience}
- author_first_name: {first}
- author_last_name: {last}
- book_id: {BOOK_ID}

Follow your agent spec: read plan context, invoke kdp-book-detail skill, update plan.json title/subtitle/description/keywords/categories/reading_age, validate banned terms, write listings DB row.

Return: title, subtitle, 7 keywords, 2 categories, reading_age.
  "
)
```

**→ When BOTH agents return, Read plan.json, proceed to Phase 3.**

---

## Phase 3: Plan Review (pause for user)

Read `output/{theme_key}/plan.json` và present:
- **Title** + Subtitle
- **Description** (HTML raw)
- **7 Keywords**, 2 Categories, Reading Age
- **Cover prompt**
- 3–5 sample page prompts

Hỏi user: *"Duyệt để tiếp tục generate images (~10–15 phút, tốn API), hoặc cần sửa gì?"*

Nếu cần sửa: edit plan.json trực tiếp, re-present, loop cho đến khi approve.

**→ Approve rồi thì IMMEDIATELY Phase 4.**

---

## Phase 4: Images + Interior PDF (manuscript-generator, plan-exists mode)

Plan đã có prompts → manuscript-generator skip Step 1 (prompt writing), chạy Step 2-5 (images + review + regen + PDF).

```
Agent(
  subagent_type: "manuscript-generator",
  description: "Generate images + interior PDF for {theme_key}",
  prompt: "
Plan already exists at output/{theme_key}/plan.json with prompts filled. SKIP Step 1 (prompt writing).

Run:
- Step 2: python3 scripts/generate_images.py --plan output/{theme_key}/plan.json --count {page_count}
- Step 3: Review each page_XX.png by vision, auto-regen REDOs (max 2/page)
- Step 4: python3 scripts/build_pdf.py --theme {theme_key} --author '{first} {last}' (đọc title/subtitle từ plan.json)
- Step 5: DB writes (manuscripts row, book status→INTERIOR_READY)

- theme_key: {theme_key}
- audience: {audience}
- page_count: {page_count}
- author: {first} {last}
- book_id: {BOOK_ID}

Return: PASS/WARN/REDO-resolved/REDO-unresolved counts + interior.pdf path + size + pages.
  "
)
```

**→ Keep unresolved list, proceed to Phase 5.**
Nếu >30% REDO unresolved: pause, ask user ship / regen / abort.

---

## Phase 5a: Cover Design

```
Agent(
  subagent_type: "cover-designer",
  description: "Build cover PDF for {theme_key}",
  prompt: "
Interior PDF exists. Build full-wrap cover.

- theme_key: {theme_key}
- author_name: {first} {last}
- page_size: {page_size}
- book_id: {BOOK_ID}

Follow your agent spec: preconditions → kdp-cover-creator skill → kdp-cover-checker validate → auto-fix dimension → covers DB row → book status COVER_READY.

Return: cover.pdf path + dimension (WxH) + spine_width_in + verdict.
  "
)
```

## Phase 5b: Quality Audit

```
Agent(
  subagent_type: "quality-reviewer",
  description: "Pre-publish audit for {theme_key}",
  prompt: "
Final pre-publish audit.

- book_id: {BOOK_ID}
- theme_key: {theme_key}
- section: all

Follow your agent spec: load context, quality-reviewer skill domain checklist, pdf_qc.py mechanical preflight (both PDFs), metadata consistency across plan/interior/cover, content compliance (banned terms), verdict GO|NO_GO, write qa_reports + remediation actions nếu NO_GO.

Return: verdict + critical count + warning count + book status.
  "
)
```

**→ Auditor trả về rồi, deliver.**

---

## Delivery

```
📚 BOOK COMPLETE!

Interior PDF: output/{theme_key}/interior.pdf  ({size} MB, {pages} pages)
Cover:        output/{theme_key}/cover.pdf    ({dim})
Plan:         output/{theme_key}/plan.json
  - Title:    {title}
  - Keywords: {keywords}

KDP PRE-FLIGHT: {verdict}  —  {critical} critical, {warnings} warnings
{Unresolved pages from Phase 4, if any — "manual review recommended"}

NEXT STEPS
1. kdp.amazon.com → New Paperback
2. Upload interior.pdf + cover.pdf (KHÔNG upload PNG)
3. Trim: {page_size}, No bleed
4. Copy title / description / 7 keywords / 2 categories / reading age từ plan.json

LƯU Ý: KDP giới hạn 10 titles / format / week.
```

---

## Error Handling

| Failure | Recovery |
|---|---|
| Phase 2 prompt-writer fails | Retry once; nếu vẫn fail, Claude write inline từ guide |
| Phase 2 listing-copywriter fails | Agent có internal retry + Claude fallback; escalate chỉ khi full block |
| Phase 4 >30% REDO unresolved | Pause, ask user: ship / regen / abort |
| Phase 5a cover dimension sai | cover-designer auto-retry với fixed flag; escalate nếu vẫn fail |
| Phase 5b verdict=NO_GO | Show critical issues + queued remediation actions; user quyết fix hay accept |

Retries nằm trong từng agent. Chỉ surface blockers cần user.

---

## Rules

- **Never** gọi external LLM API cho writing — Claude viết hết.
- Sub-agent return → continue ngay trong same turn. KHÔNG chờ nudge.
- Chỉ 2 user pauses: Phase 1 (interview) và Phase 3 (plan review). Phase 4 >30% REDO là soft gate.
- Phase 2 PARALLEL (2 Agent calls trong 1 message) → tiết kiệm ~40% thời gian plan.
- 5 sub-agents dùng ở đây là specialists của 8-agent KDP company — reusable qua `master-orchestrator` cho batch pipelines.
