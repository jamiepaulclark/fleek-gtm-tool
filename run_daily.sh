#!/bin/bash
# run_daily.sh — Schedule this to run every morning at 7am
#
# To set up as a cron job:
#   crontab -e
#   Add this line: 0 7 * * * /path/to/fleek-gtm-tool/run_daily.sh
#
# Or with GitHub Actions: see .github/workflows/daily_run.yml

cd "$(dirname "$0")"

DATE=$(date +%Y-%m-%d)
LOG_FILE="output/logs/run_${DATE}.log"
mkdir -p output/logs

echo "[$(date)] Starting daily pipeline run..." | tee -a "$LOG_FILE"

# Run the pipeline
python3 run_pipeline.py --no-ai 2>&1 | tee -a "$LOG_FILE"

echo "[$(date)] Done." | tee -a "$LOG_FILE"

# To merge a new batch when one arrives, run:
# python3 run_pipeline.py --no-ai --new-batch data/new_leads.xlsx --new-sheet Sheet1
