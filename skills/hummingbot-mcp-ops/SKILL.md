---
name: hummingbot-mcp-ops
description: "Operate Hummingbot API + Gateway via the local hummingbot-api MCP (stdio). Use for adding LP (CLMM), managing tokens/pools/allowances, deploying controllers/scripts, starting/stopping bots, and plan-first execution using deploy_v2_workflow_plan."
---

# hummingbot-mcp-ops

This skill is the runbook for the **local Hummingbot API MCP** adapter at:
- Repo: `/Users/massis/Documents/Code/hummingbot-api/mcp`
- API (host): `http://127.0.0.1:18000`
- Gateway container port: `15888` (usually reached via API tools)

## Golden rules

- **Plan-first**: always call `deploy_v2_workflow_plan` first; execute actions step-by-step.
- **No ambiguity**: prefer `pool_address` + token addresses. Avoid relying on token order.
- **No blind deploy**: if planner returns `blockers`, fix them before deploying.
- **After token/pool add**: restart gateway (`gateway_restart`), then re-run the planner.

## MCP registration (mcporter)

This MCP should be registered under `hummingbot-api` in:
- `/Users/massis/clawd/config/mcporter.json`

If tools time out, verify:
- command points to a Python with `httpx` installed
- args include `mcp/server.py`
- `PYTHONPATH` points to `/Users/massis/Documents/Code/hummingbot-api`

## Quick sanity checks

1) List tools:
- `mcporter list hummingbot-api --schema`

2) Basic connectivity:
- `mcporter call hummingbot-api.gateway_status`
- `mcporter call hummingbot-api.gateway_networks`
- `mcporter call hummingbot-api.gateway_connectors`

## Common workflows

### A) Add LP (CLMM) (safe default)

Inputs to ask user for:
- `network_id` (e.g. `solana-mainnet-beta`, `ethereum-mainnet`, `base-mainnet`)
- `connector_name` (e.g. `meteora/clmm`, `uniswap/clmm`)
- `pool_address` (preferred)
- token addresses + decimals (or fetch via `metadata_token`)
- `wallet_address` (if needed)
- deploy mode: `deployment_type` + `instance_name` + `credentials_profile`

Steps:
1) `metadata_token` for each token if missing metadata
2) **Approvals (per Deploy V2 UI):**
   - Tokens = base+quote from `trading_pair`.
   - Spenders = `connector_name` (if gateway) + `router_connector` (if `auto_swap_enabled` and gateway).
   - Call `gateway_allowances` with `{network_id, address: wallet_address, tokens, spender}`.
   - Treat allowance >= 1e10 as "unlimited"; if not, call `gateway_approve` for each missing token+spender.
3) `deploy_v2_workflow_plan` (read-only)
4) Execute returned actions in order:
   - `gateway_token_add` / `gateway_pool_add`
   - `gateway_restart` when instructed
5) Re-run `deploy_v2_workflow_plan` to confirm `blockers=[]`
6) Deploy:
   - `bot_deploy_v2_controllers` or `bot_deploy_v2_script`
7) Start bot: `bot_start`

### B) Run an existing strategy instance
1) `bot_instances` (confirm it exists)
2) `bot_start` (start)
3) `bot_status` (observe)

## References
- MCP tool list and notes: `/Users/massis/Documents/Code/hummingbot-api/mcp/README.md`
