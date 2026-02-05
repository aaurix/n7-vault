# Market Ops Scripts Split Design (market_ops + market_data)

## Summary
- 目标：以 `scripts/` 为唯一真源包根，将可复用的数据访问模块拆分为 `scripts/market_data`，业务聚合与 pipeline 保留在 `scripts/market_ops`。
- Cron 执行路径统一为：`python3 -m scripts.market_ops hourly`。

## Goals
- 修复断链：`kline_fetcher` 与 `meme_radar` 不再依赖已删除的外部脚本路径。
- 去重收敛：`flow_label`、`fmt_*` 等重复逻辑集中到单一模块。
- 明确边界：`market_data` 仅做 IO/缓存/解析，`market_ops` 仅做业务逻辑与渲染。
- 符合 Python 包实践：`scripts/` 成为可导入包根，删除 `src/`。

## Non-goals
- 不引入新的外部依赖或复杂框架。
- 不改变现有业务输出语义（除非为修复断链）。
- 不新增 CLI 子命令（沿用 `hourly/symbol/ca`）。

## Target Structure
```
scripts/
  __init__.py
  market_ops/
    __init__.py
    __main__.py
    cli.py
    facade.py
    schema.py
    core/
    pipeline/
    services/
    rendering/
    utils/
  market_data/
    __init__.py
    exchange/   # ccxt / binance / kline
    social/     # bird / twitter evidence
    onchain/    # dexscreener / coingecko
```

## Boundary Rules
- `market_data` 不允许 import `market_ops`。
- `market_ops` 可以 import `market_data`。
- `pipeline` 只调用 `services`；`services` 可调用 `market_data`。
- `rendering` 只消费业务输出，不反向依赖业务逻辑。

## Migration Plan (Phased)
1) **断链修复**
   - `kline_fetcher` 改为直连 `market_data/exchange/*`。
   - `meme_radar` 改为调用内部实现或 `market_data/social/*`。
2) **去重收敛**
   - `flow_label` 统一到 `market_ops/core/indicators.py`。
   - `fmt_pct/fmt_usd` 统一到 `market_ops/core/formatting.py`。
   - 删除 `ports/` 或合并其能力到 `market_data`。
3) **目录迁移**
   - `src/market_ops` 全量迁入 `scripts/market_ops`。
   - 提取可复用 IO 模块到 `scripts/market_data`。
   - 删除 `src/`。

## Cron & CLI
- Cron：`python3 -m scripts.market_ops hourly`
- 兼容入口（如需）：`python3 scripts/market_ops/cli.py hourly`

## Risks
- 路径变更导致 cron/脚本失败：需同步更新相关文档与任务配置。
- 迁移过程中模块 import 路径易断：需要全量搜索替换 + tests 覆盖。

## Tests
- 现有 pytest 全量跑通。
- 新增：确保 `scripts` 包可被 `python3 -m` 调起。
