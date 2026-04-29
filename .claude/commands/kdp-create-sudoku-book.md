---
description: Launch pipeline sudoku-only — tạo 1 cuốn sudoku book KDP end-to-end (concept → interior + cover + listing + QA), Wave 1 chạy parallel sub-agents (~5-10 phút).
argument-hint: [concept | niche_id=N | idea_file=ideas/xxx.md]
allowed-tools: Skill, Agent, AskUserQuestion, Bash, Read, Write, Edit
---

# KDP Create Sudoku Book

Invoke skill `kdp-create-sudoku-book` với args đã pass-through.

Skill sẽ:
1. **Phase 0** — Intake (parse args / AskUserQuestion nếu thiếu) → tạo plan.json + books DB row + pipelines audit row
2. **Phase 1** — Spawn 2 sub-agents PARALLEL trong cùng 1 message:
   - `manuscript-generator` (puzzles + interior.pdf via `kdp-sudoku-generator` skill)
   - `listing-copywriter` (title/keywords/description/categories via `kdp-book-detail` skill)
3. **Phase 2** — Sequential: spawn `cover-designer` (cần page_count cho spine math)
4. **Phase 3** — Sequential: spawn `quality-reviewer` (GO/NO-GO gate)
5. **Phase 4** — Pause cho user upload KDP + paste ASIN

Args: $ARGUMENTS

Skip nếu user chưa cung cấp concept — skill sẽ tự AskUserQuestion 6 fields (concept, audience, puzzle count, difficulty mix, theme_key, author).

Use Skill tool with `skill: "kdp-create-sudoku-book"` và `args: "$ARGUMENTS"`.
