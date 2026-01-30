# Telegram 热点提炼（事件卡片）

## Why
Generic “聊天总结”没有交易价值。热点必须可定位、可验证。

## Target output
Each topic is an **event card**:
- `one_liner`: 1 sentence, Chinese, **must include an anchor**
- `sentiment`: 偏多/偏空/分歧/中性
- `triggers`: 3-6 short phrases
- `related_assets`: token/chain/platform/person (only if explicitly present)

## Algorithm (1→2→3)

### 1) Deterministic prefilter (high information density only)
Only keep TG messages that match at least one:
- Contains CA (0x… / solana base58)
- Contains `$TICKER`
- Contains ticker-like token name + event words (上线/上所/解锁/黑客/清算/回购/治理/空投/迁移…)
- Contains numeric scale + event word (e.g. “解锁500万”, “买入200k”)

Drop:
- Pure emotion / chatter
- Vague statements
- Copy-paste promo

### 2) LLM summarizer
Hard constraints:
- Never start with: 某个/某些/一些/有人/用户/群友/大家/投资者/市场参与者
- `one_liner` must include an anchor (token/CA/chain/platform/event word/number)
- If you can’t satisfy anchor: **omit the item** (OK to output <5 items)

### 3) Postfilter (strict)
Even if LLM returns 5 items:
- If `one_liner` does not contain an anchor → drop
- If it contains vague pronouns/泛指 → drop

Result can be 0-3 topics; that is preferred over low quality.

## Anchors (examples)
- Token: BONK / $BONK / 中文名
- CA: 0x… / 4T7X…
- Chain/platform: SOL/Base/BSC, Binance Alpha, OKX, GMGN, DexScreener
- Event words: 上线/上所/解锁/黑客/清算/回购/增发/治理/迁移/空投
- Numeric: 300k, 500w, 2M, 30% APR
