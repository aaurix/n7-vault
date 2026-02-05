#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/massis/.openclaw/workspace"
REPORT_DIR="$ROOT/reports"
mkdir -p "$REPORT_DIR"

scan_report="$REPORT_DIR/skills_scan_$(date +%F_%H%M%S).txt"
health_report="$REPORT_DIR/health_$(date +%F_%H%M%S).txt"
summary_report="$REPORT_DIR/auto_watchdog_$(date +%F_%H%M%S).txt"

# Update skills inventory
"$ROOT/scripts/update_skills_inventory.sh" >/dev/null

# Run scans
"$ROOT/scripts/scan_skills.sh" "$ROOT/skills" "$scan_report" >/dev/null
"$ROOT/scripts/monitor_health.sh" "$health_report" >/dev/null

# Determine if scan has hits
hits=$(grep -vE '^(Skill Scan Report|Root:|Time:|---|\[pattern\])' "$scan_report" | sed '/^\s*$/d' | wc -l | tr -d ' ')

{
  echo "Auto Watchdog Summary"
  echo "Time: $(date)"
  echo "Scan report: $scan_report"
  echo "Health report: $health_report"
  echo "Inventory: $ROOT/skills_inventory.md"
  echo "Scan hits: $hits"
} > "$summary_report"

# exit code indicates whether to alert
if [ "$hits" -gt 0 ]; then
  exit 2
fi

exit 0
