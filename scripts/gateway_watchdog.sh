#!/bin/zsh
set -euo pipefail

LABEL="com.clawdbot.gateway"
DOMAIN="gui/$(id -u)"
DASHBOARD_URL="http://127.0.0.1:18789/"

# State file to avoid flapping
STATE_DIR="${HOME}/.clawdbot/watchdog"
STATE_FILE="${STATE_DIR}/gateway_failcount.txt"
MAX_FAILS=3

mkdir -p "$STATE_DIR"

failcount=0
if [[ -f "$STATE_FILE" ]]; then
  failcount=$(cat "$STATE_FILE" 2>/dev/null || echo 0)
fi

# Health check: dashboard reachable within 2s and returns any body
if curl -fsS --max-time 2 "$DASHBOARD_URL" >/dev/null 2>&1; then
  echo 0 >| "$STATE_FILE"
  exit 0
fi

failcount=$((failcount + 1))
echo "$failcount" >| "$STATE_FILE"

logger -t clawdbot-gateway-watchdog "Gateway healthcheck failed (${failcount}/${MAX_FAILS})."

if (( failcount >= MAX_FAILS )); then
  logger -t clawdbot-gateway-watchdog "Restarting ${LABEL} via launchctl kickstart."
  # -k: kill existing, then start
  launchctl kickstart -k "$DOMAIN/$LABEL" || true
  echo 0 >| "$STATE_FILE"
fi
