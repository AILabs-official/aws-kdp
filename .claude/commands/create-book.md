---
description: Launch pipeline — tạo 1 cuốn sách KDP end-to-end (từ concept/idea → interior + cover + listing + QA, sẵn sàng upload)
argument-hint: [concept description | niche_id=N | idea_file=ideas/xxx.md]
allowed-tools: Agent, AskUserQuestion
---

# Create KDP Book — Launch Pipeline

Spawn the **master-orchestrator** agent (CEO) với pipeline=launch. CEO sẽ điều phối:

1. **manuscript-generator** ∥ **listing-copywriter** (parallel) — prompts + images + interior.pdf + SEO
2. **cover-designer** — cover.pdf (spine math từ page_count)
3. **quality-reviewer** — GO/NO-GO audit
4. [User uploads to KDP, provides ASIN]
5. **ads-manager** — launch 3 Sponsored Products campaigns

Use Agent tool with `subagent_type: "master-orchestrator"`:

```
Run pipeline=launch. Args (if any): $ARGUMENTS

If no idea_file or niche_id provided, use AskUserQuestion to gather:
1. Concept (e.g., "cozy cats in a cafe")
2. Audience (adults / kids 6-12)
3. Page size (8.5x11 portrait / 8.5x8.5 square)
4. Page count (25-30 recommended)
5. Theme key (snake_case)
6. Author name

Then create a minimal idea_file on the fly in ideas/ (or skip directly to plan wave) and run the full launch pipeline end-to-end.
```
