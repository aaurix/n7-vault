# Debugging checklist (hourly)

## Symptom: cron says ok but no WhatsApp message
- Check idempotency file: `/Users/massis/clawd/memory/hourly_summary_delivery.json`
- Confirm it didn’t mark whatsappSent=true already for that hourKey.

## Symptom: tg_viewpoint_msgs = 0
- Ingest may not have new messages for the new allowlist yet.
- Check hawkfi-telegram health:
  - `mcporter call hawkfi-telegram.health --json`
- Search dialogs to confirm the chat exists:
  - `mcporter call hawkfi-telegram.dialogs_search --json query="<name>"`
- Search messages:
  - `mcporter call hawkfi-telegram.search --json q="<ticker or keyword>" limit=20`

## Symptom: Telegram 热点输出泛化
- Ensure deterministic prefilter is enabled.
- Ensure postfilter drops non-anchor items.
- Prefer outputting 0-2 topics over 5 low-quality.
