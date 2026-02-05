# Unified Report Outputs Design

**Goal**  
统一对外输出模型，保证同一份内容同时输出 Markdown 与富文本，不增加 LLM 调用次数，不做内容删减。

**Non-Goals**  
- 不改动 LLM 提示词与推理流程  
- 不引入新渠道（仅 Markdown + 富文本）  
- 不改变数据采集链路  

**Problems Observed**  
- 输出模板分散在 `features/*/service.py` 与 `output/*` 中  
- symbol/ca/hourly 格式风格不一致  
- WhatsApp 输出存在预算裁剪，存在“内容可能被截断”的风险  

**Architecture**  
新增一个“统一报告模型 + 双渲染器”层：  
1. `ReportSection` 作为统一内容容器  
2. `render_markdown(sections)` 与 `render_richtext(sections)` 作为格式层  
3. 业务层只构建 `sections`，渲染层只负责格式，不删减内容  

**Data Flow**  
- `cli.py → facade.py → service.py` 不变  
- `run_prepare()` 与 `LLM/规则` 仍产出结构化数据与观点  
- `build_*_sections()` 把结构化数据与观点映射为统一段落  
- 渲染器输出 Markdown + 富文本  
- 输出对象对外暴露 `markdown` 与 `richtext`，并可生成 `richtext_chunks` 用于消息分片  

**Report Structure (Symbol Example)**  
固定顺序，不做取舍：  
1. 标题区（标题 + 时间 + 数据源）  
2. 行情概览  
3. 结构与关键位  
4. 评分与解释  
5. 结论与观点  
6. 信号词与要点  
7. 操作与风险  
8. 数据附录  

**File Layout**  
- `market_ops/output/report_sections.py`  
  - `ReportSection`  
  - `render_markdown`  
  - `render_richtext`  
- `market_ops/output/symbol_report.py`  
  - `build_symbol_sections(prepared, dash, template)`  
- `market_ops/output/ca_report.py`  
  - `build_ca_sections(report)`  
- `market_ops/output/summary.py`  
  - 生成 `summary_richtext` 与 `summary_markdown`  
  - 禁用预算裁剪，保持与 Markdown 内容一致  

**Output Contract**  
- `markdown` 与 `richtext` 内容一致，仅格式不同  
- 禁止裁剪段落或删除条目  
- `summary` 可指向 `richtext` 以保持 CLI 输出  

**Testing Strategy**  
- 渲染器单测：所有段落行必须同时存在于 Markdown 与富文本  
- Symbol/CA 构建单测：必须包含关键标题段落  
- Summary 渲染单测：`apply_budget=False` 时输出长度可超过上限，且不截断  

**Migration Plan**  
1. 新增渲染器与 ReportSection  
2. 抽离 symbol/ca 报告构建并替换旧 `_render_*`  
3. Summary 输出使用新逻辑，双输出一致  
4. 删除冗余模板函数，保持结构单一  
