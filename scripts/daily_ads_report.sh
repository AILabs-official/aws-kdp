#!/usr/bin/env bash
# Daily Amazon Ads SP campaigns report puller.
# Pulls YESTERDAY (single day, fully settled) → ad_performance DB.
# Cron: 7 9 * * * /Users/tonytrieu/Downloads/AIOS/aws-kdp/scripts/daily_ads_report.sh
set -euo pipefail

REPO="/Users/tonytrieu/Downloads/AIOS/aws-kdp"
LOG_DIR="$REPO/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/daily_ads_$(date +%Y%m%d).log"

cd "$REPO"

# Yesterday is fully settled (Amazon data lag 12-48h, but D-1 is reliable by 9am).
YESTERDAY=$(date -v-1d +%Y-%m-%d)

{
  echo "==== $(date '+%Y-%m-%d %H:%M:%S') pulling $YESTERDAY ===="
  /usr/bin/env python3 scripts/amazon_ads_api.py report \
    --start-date "$YESTERDAY" \
    --end-date   "$YESTERDAY" \
    --write-db
  echo ""
} >> "$LOG" 2>&1
