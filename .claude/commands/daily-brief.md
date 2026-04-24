---
description: Daily brief — doanh thu hôm qua, ad spend, alerts (bleed / spike / paused). Non-interactive, chạy nhanh.
argument-hint: (no args)
allowed-tools: Agent
---

# KDP Daily Brief

Spawn **master-orchestrator** pipeline=daily. CEO ingest fresh data + SQL anomaly detection:
- Ad spend > 3× median → bleed alert
- 0 impressions in 24h on active campaign → paused unexpected
- Sales > 2× 7d avg → spike (consider SCALE)

```
Run pipeline=daily. Non-interactive, no sub-agents. Ingest royalties + ads performance, detect anomalies, print brief.
```
