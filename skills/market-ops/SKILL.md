---
name: market-ops
description: Production ops for the hourly TG+Twitter market/meme summary: pipeline behavior, WhatsApp delivery, cron/idempotency, and debugging.
---

# market-ops

This skill is the **runbook** for the hourly summary pipeline in this repo.

## Use this skill when
- Changing the hourly summary content/format (Top3/Top5, sections, wording)
- Debugging hourly cron failures, missing deliveries, idempotency issues
- Tuning TG/Twitter topic extraction, filtering, or summary quality
- Adjusting meme radar merge behavior inside the hourly summary

## Quick start (most common)
- Run locally:
  - `python3 /Users/massis/clawd/scripts/hourly_market_summary.py`
- Cron rule of thumb:
  - **Do not use heredocs** like `python3 - <<'PY'` (cron exec may fail)
- Delivery rule of thumb:
  - WhatsApp message split: keep each chunk **<= ~950 chars**

## Reference docs (read as needed)
- Hourly pipeline overview: `references/pipeline-hourly.md`
- TG热点提炼（按“高信息密度预筛→LLM→事件卡片”）: `references/telegram-topics.md`
- WhatsApp delivery + idempotency: `references/delivery-whatsapp.md`
- Debugging checklist: `references/debugging.md`
- Chat source config strategy (HOT vs VIEWPOINT): `references/chat-sources.md`
