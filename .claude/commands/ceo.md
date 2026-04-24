---
description: CEO full access — pick any of 7 pipelines (launch, daily, weekly, optimize, scale, kill, seasonal).
argument-hint: pipeline=<type> [book_id=N] [niche_id=N] [season=X] [target=N]
allowed-tools: Agent, AskUserQuestion
---

# KDP CEO — Master Orchestrator

Spawn **master-orchestrator** với pipeline = user's choice.

7 pipelines:
- **launch** — 1 niche/idea → sách live + ads (6 phòng ban)
- **daily** — morning brief, non-interactive
- **weekly** — analyst → dispatch top actions
- **optimize** — iterate 1 book (analyst scope 1 → ads/QC)
- **scale** — Winner: +30% budget + adjacent niches
- **kill** — pause ads, status=DORMANT (user confirm)
- **seasonal** — holiday ramp, auto-enqueue launch batch

```
Args: $ARGUMENTS

If pipeline= missing, AskUserQuestion with 4 common options (launch, weekly, optimize, seasonal).
Proceed with master-orchestrator agent, which handles pipelines row + step_log tracking.
```
