#!/usr/bin/env bash
set -euo pipefail

OUT="${1:-/Users/massis/.openclaw/workspace/reports/health_$(date +%F_%H%M%S).txt}"
mkdir -p "$(dirname "$OUT")"

{
  echo "OpenClaw Health Report"
  echo "Time: $(date)"
  echo "---"
  openclaw gateway status || true
  echo "---"
  echo "Disk usage"
  df -h /
  echo "---"
  echo "Top processes"
  ps -Ao pid,pcpu,pmem,comm | head -n 10 || true
} > "$OUT"

echo "Wrote: $OUT"
