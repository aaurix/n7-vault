# WhatsApp delivery + idempotency

## WhatsApp constraints
- Keep each message chunk <= ~950 chars to avoid truncation/failure.
- Split by section boundaries and newlines.

## Idempotency
- State file: `/Users/massis/clawd/memory/hourly_summary_delivery.json`
- Keyed by `hourKey + summaryHash`.
- Track `whatsappSent` boolean.

## Cron notes
- Cron exec: avoid heredocs.
- If WhatsApp gateway disconnects (428/499), treat as transient; next run should recover.
