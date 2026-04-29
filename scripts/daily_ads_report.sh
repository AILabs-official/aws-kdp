#!/usr/bin/env bash
# Daily Amazon Ads SP campaigns report puller.
# Pulls yesterday → today (1-day window) and writes rows into ad_performance DB.
# Cron: 0 9 * * * /Users/tonytrieu/Downloads/AIOS/aws-kdp/scripts/daily_ads_report.sh
set -euo pipefail

REPO="/Users/tonytrieu/Downloads/AIOS/aws-kdp"
LOG_DIR="$REPO/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/daily_ads_$(date +%Y%m%d).log"

cd "$REPO"

YESTERDAY=$(date -v-1d +%Y-%m-%d)
TODAY=$(date +%Y-%m-%d)

{
  echo "==== $(date '+%Y-%m-%d %H:%M:%S') ===="
  /usr/bin/env python3 scripts/amazon_ads_api.py report \
    --start-date "$YESTERDAY" \
    --end-date "$TODAY" \
    --write-db
  echo ""
} >> "$LOG" 2>&1
