# Chat sources strategy

## Problem
One set of chat_ids cannot serve both:
- Hot topic/event detection (broad, noisy)
- Viewpoint/tradability extraction (narrow, high-signal)

## Recommended split
- HOT_CHAT_IDS: broader set (channels + groups) used only for topic/event cards.
- VIEWPOINT_CHAT_IDS: curated groups/channels used for tradability and ticker/CA candidates.

## Operational rule
Expanding allowlist in hawkfi-telegram-service only affects **ingestion**.
You must also expand HOT_CHAT_IDS / VIEWPOINT_CHAT_IDS in the hourly script to affect summarization.
