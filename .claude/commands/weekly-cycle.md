---
description: Weekly cycle — performance-analyst chạy classification → top-N actions → user confirm → CEO dispatch tới ads-manager/quality-reviewer/niche-hunter.
argument-hint: (no args)
allowed-tools: Agent, AskUserQuestion
---

# KDP Weekly Cycle

Spawn **master-orchestrator** pipeline=weekly. CEO sẽ:

1. Gọi **performance-analyst** period=weekly → classify sách (Winner/Promising/Stuck/Dead/New) → ghi `actions` queue
2. Đọc top 20 actions sorted by `expected_impact_usd DESC`
3. AskUserQuestion: execute top-N HIGH priority tự động?
4. Dispatch (group by action_type):
   - SCALE_ADS / ITERATE_ADS → `ads-manager` (≤5 parallel)
   - FIX_LISTING / FIX_COVER / FIX_INTERIOR → `quality-reviewer` re-audit
   - KILL → pause ad_campaigns
   - EXPAND_SERIES → `niche-hunter` adjacent seeds
5. Mark actions DONE, final report delta.

```
Run pipeline=weekly.
```
