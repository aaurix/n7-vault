#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/Users/massis/.openclaw/workspace/skills}"
OUT="${2:-/Users/massis/.openclaw/workspace/reports/skills_scan_$(date +%F_%H%M%S).txt}"

mkdir -p "$(dirname "$OUT")"

PATTERNS=(
  "Authorization: Bearer"
  "api_key"
  "MOLTBOOK_API_KEY"
  "OPENROUTER_API_KEY"
  "cat ~/.env"
  "find / -name \"*.env\""
  "curl .*http"
)

{
  echo "Skill Scan Report"
  echo "Root: $ROOT"
  echo "Time: $(date)"
  echo "---"
  for p in "${PATTERNS[@]}"; do
    echo ""
    echo "[pattern] $p"
    rg -n --no-heading --hidden -g 'SKILL.md' "$p" "$ROOT" || true
  done
} > "$OUT"

echo "Wrote: $OUT"
