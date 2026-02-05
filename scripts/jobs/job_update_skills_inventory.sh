#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/Users/massis/.openclaw/workspace/skills}"
OUT="${2:-/Users/massis/.openclaw/workspace/skills_inventory.md}"
TMP="${OUT}.tmp"

{
  echo "# Skills Inventory"
  echo ""
  echo "| Skill | Source | Author | Version | Permissions | Audit Status | Last Updated |"
  echo "|------|--------|--------|---------|-------------|--------------|--------------|"
  find "$ROOT" -name SKILL.md -print0 | while IFS= read -r -d '' f; do
    name=$(rg -m1 '^name:' "$f" | sed 's/name:\s*//') || true
    version=$(rg -m1 '^version:' "$f" | sed 's/version:\s*//') || true
    [ -z "$name" ] && name="(unknown)"
    [ -z "$version" ] && version="(unknown)"
    source="$f"
    author=$(rg -m1 '^author:' "$f" | sed 's/author:\s*//') || true
    [ -z "$author" ] && author="(unknown)"
    echo "| $name | $source | $author | $version | (tbd) | pending | $(date +%F) |"
  done
  echo ""
  echo "> Update this table whenever a new skill is added or upgraded."
} > "$TMP"

mv "$TMP" "$OUT"

# keep a snapshot for diff
cp "$OUT" /Users/massis/.openclaw/workspace/reports/skills_inventory_last.md

echo "Wrote: $OUT"