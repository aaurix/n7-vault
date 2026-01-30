# Hourly AgentTurn: 二级山寨「决策仪表盘mini」渲染

> 目标：让小时报的“二级山寨”部分可直接拿来下单/设条件。
> 数据来自 `scripts/hourly_prepare.py` 输出的 `prepared.perp_dash_inputs`（确定性、无引用原话）。

## 输入字段（prepare stage）
- `prepared.perp_dash_inputs`: list（最多3个）
  - `symbol`
  - `price_chg.{1h_pct,4h_pct,24h_pct}`
  - `oi_chg.{1h_pct,4h_pct,24h_pct}`
  - `structure.1h`: `swing_hi/lo`, `ema20_slope_pct`, `rsi14`, `atr_pct`, `range_loc`, `vol_ratio`
  - `structure.4h`: `swing_hi/lo`, `ema20_slope_pct`, `rsi14`, `atr_pct`, `range_loc`
  - `key_levels.{resistance,support}`
  - `flow_label`（价/OI象限）
  - `bias_hint`（规则偏多/偏空/观望，可被LLM微调）
  - `action_notes`（规则动作提示，1~2条）

> fallback：当 `perp_dash_inputs` 为空时，使用旧字段 `prepared.oi_lines`。

## 建议的 AgentTurn Prompt（替换/新增“二级山寨”段落）

### 指令（中文）
- 只输出 WhatsApp 可直接发送的文本，不要 markdown 表格。
- 每个币种做一个「决策仪表盘mini」，最多 2~3 个币。
- 不要引用任何原话/推文/聊天原句（**no raw quotes**）。
- 不要报“现价/报价”，只用变化率与关键位（支撑/压力）即可。
- 结构必须覆盖：
  - 价变动 + OI变动
  - 1H/4H：swing hi/lo、EMA20斜率、RSI、ATR%
  - 关键位（支撑/压力）
  - flow_label
  - 1~2条“动作/条件单”提示
- 输出需要可拆分：单条消息 <=950 字；若超过，用清晰分段（例如 `---` 作为分割符）。

### 建议格式（示例骨架）
```
*二级山寨Top3（决策仪表盘mini）*
1) {SYM}（{bias}）价1h{+x}% 4h{+y}% | OI1h{+a}% 4h{+b}%
   - 1H: swing {hi}/{lo} | EMA20斜率{+s}% | RSI{r} | ATR{t}%
   - 4H: swing {hi}/{lo} | EMA20斜率{+s}% | RSI{r} | ATR{t}%
   - 关键位：压{res} / 撑{sup} | {flow_label}
   - 动作：{note1}；{note2}
2) ...
```

> 如果 LLM 需要更“交易员口吻”，允许在不引入新事实的前提下精简/换词。
