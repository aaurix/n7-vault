# Unified Report Outputs Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Unify symbol/CA/hourly outputs to a single ReportSection model with Markdown + richtext renderers, no content truncation, no extra LLM calls.

**Architecture:** Add `ReportSection` + renderers in `market_ops/output`, refactor symbol/CA to build sections and render both formats, and update hourly summary to emit richtext + markdown with budget disabled.

**Tech Stack:** Python 3.14, pytest, existing market_ops modules.

---

### Task 1: Add ReportSection renderers + tests

**Files:**
- Create: `tests/market_ops/test_report_render.py`
- Create: `scripts/market_ops/output/report_sections.py`

**Step 1: Write the failing test**

```python
from scripts.market_ops.output.report_sections import ReportSection, render_markdown, render_richtext


def test_renderers_preserve_lines():
    sections = [
        ReportSection("标题区", ["时间: 00:00", "数据源: 市场/链上/社交"]),
        ReportSection("行情概览", ["现价: 1.23", "24h: +2%"]),
    ]
    md = render_markdown(sections)
    rt = render_richtext(sections)
    for line in ["时间: 00:00", "数据源: 市场/链上/社交", "现价: 1.23", "24h: +2%"]:
        assert line in md
        assert line in rt
    assert md.startswith("# ")
    assert rt.startswith("*")
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/market_ops/test_report_render.py::test_renderers_preserve_lines -v`  
Expected: FAIL (module not found)

**Step 3: Write minimal implementation**

```python
from dataclasses import dataclass
from typing import Iterable, List


@dataclass
class ReportSection:
    title: str
    lines: List[str]


def _render(sections: Iterable[ReportSection], *, heading_fmt: str) -> str:
    out: List[str] = []
    for idx, sec in enumerate(sections):
        title = sec.title.strip()
        if not title:
            continue
        if idx == 0:
            out.append(heading_fmt.format(level=1, title=title, rich=True))
        else:
            out.append(heading_fmt.format(level=2, title=title, rich=False))
        for line in sec.lines:
            if str(line).strip():
                out.append(f"- {line}")
        out.append("")
    return "\n".join(out).strip() + "\n"


def render_markdown(sections: Iterable[ReportSection]) -> str:
    return _render(sections, heading_fmt="{level} {title}".replace("{level}", "#"))


def render_richtext(sections: Iterable[ReportSection]) -> str:
    def fmt(level: int, title: str, rich: bool = False) -> str:
        return f"*{title}*"
    # inline formatter to reuse _render signature
    return _render(sections, heading_fmt="{level} {title}")
```

Adjust implementation to satisfy test expectations, keep it simple and deterministic.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/market_ops/test_report_render.py::test_renderers_preserve_lines -v`  
Expected: PASS

**Step 5: Commit**

```bash
git -C scripts add output/report_sections.py
git add tests/market_ops/test_report_render.py
git commit -m "feat: add report sections renderer"
```

---

### Task 2: Add symbol report sections builder + tests

**Files:**
- Create: `tests/market_ops/test_symbol_report_sections.py`
- Create: `scripts/market_ops/output/symbol_report.py`

**Step 1: Write the failing test**

```python
from scripts.market_ops.output.symbol_report import build_symbol_sections
from scripts.market_ops.output.report_sections import render_markdown, render_richtext


def test_build_symbol_sections_contains_core_titles():
    prepared = {
        "prepared": {
            "symbol": "TEST",
            "price": {"now": 1.2, "chg_24h_pct": 2.0, "chg_1h_pct": 0.5, "chg_4h_pct": 1.0},
            "oi": {"chg_1h_pct": 1.0, "chg_4h_pct": 2.0, "chg_24h_pct": 3.0, "oi_value_now": 1000},
            "market": {"market_cap": 1000000, "fdv": 2000000},
            "derived": {"scores": {"trend": 70, "oi": 65, "social": 50, "overall": 60}, "bias_hint": "偏多"},
        }
    }
    dash = {"verdict": "偏多", "bullets": ["要点1"], "risks": ["风险1"]}
    sections = build_symbol_sections(prepared, dash, template="dashboard")
    titles = [s.title for s in sections]
    assert "行情概览" in titles
    assert "评分与解释" in titles
    md = render_markdown(sections)
    rt = render_richtext(sections)
    assert "要点1" in md and "要点1" in rt
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/market_ops/test_symbol_report_sections.py::test_build_symbol_sections_contains_core_titles -v`  
Expected: FAIL (module not found)

**Step 3: Write minimal implementation**

Create `build_symbol_sections(prepared, dash, template)` and move the text assembly from `_render_dashboard_text` and `_render_plan_text` into section building.  
Ensure sections follow the agreed order and contain all lines previously emitted.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/market_ops/test_symbol_report_sections.py::test_build_symbol_sections_contains_core_titles -v`  
Expected: PASS

**Step 5: Commit**

```bash
git -C scripts add output/symbol_report.py
git add tests/market_ops/test_symbol_report_sections.py
git commit -m "feat: add symbol report sections builder"
```

---

### Task 3: Refactor symbol service to unified outputs

**Files:**
- Modify: `scripts/market_ops/features/symbol/service.py`
- Modify: `tests/market_ops/test_structure.py` (if needed)

**Step 1: Write the failing test**

Add to `tests/market_ops/test_symbol_report_sections.py`:
```python
from scripts.market_ops.output.symbol_report import render_symbol_report

def test_render_symbol_report_dual_output():
    prepared = {"prepared": {"symbol": "TEST"}}
    dash = {"verdict": "观望"}
    report = render_symbol_report(prepared, dash, template="dashboard")
    assert report["markdown"]
    assert report["richtext"]
    assert "TEST" in report["markdown"]
    assert "TEST" in report["richtext"]
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/market_ops/test_symbol_report_sections.py::test_render_symbol_report_dual_output -v`  
Expected: FAIL (function not found)

**Step 3: Implement minimal code**

1. Add `render_symbol_report()` to `output/symbol_report.py` to return:
   - `markdown`, `richtext`, `richtext_chunks`, `sections`, `template`
2. Replace `_render_dashboard_text` / `_render_plan_text` usage in `features/symbol/service.py` with `render_symbol_report()`
3. Remove old `_render_*` renderers to avoid divergence
4. Update returned `data` keys:
   - Remove `whatsapp` and `whatsapp_chunks`
   - Add `report` object and keep `summary` as `richtext`

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/market_ops/test_symbol_report_sections.py::test_render_symbol_report_dual_output -v`  
Expected: PASS

**Step 5: Commit**

```bash
git -C scripts add output/symbol_report.py features/symbol/service.py
git add tests/market_ops/test_symbol_report_sections.py
git commit -m "refactor: unify symbol output to report renderers"
```

---

### Task 4: Refactor CA output to unified sections

**Files:**
- Create: `tests/market_ops/test_ca_report_sections.py`
- Create: `scripts/market_ops/output/ca_report.py`
- Modify: `scripts/market_ops/features/ca/service.py`

**Step 1: Write the failing test**

```python
from scripts.market_ops.output.ca_report import build_ca_sections
from scripts.market_ops.output.report_sections import render_markdown, render_richtext


def test_build_ca_sections_contains_core_titles():
    report = {"address": "0xabc", "symbol": "TEST", "dex": {"chainId": "eth"}}
    sections = build_ca_sections(report)
    titles = [s.title for s in sections]
    assert "行情概览" not in titles
    assert "总结" in titles
    md = render_markdown(sections)
    rt = render_richtext(sections)
    assert "0xabc" in md and "0xabc" in rt
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/market_ops/test_ca_report_sections.py::test_build_ca_sections_contains_core_titles -v`  
Expected: FAIL

**Step 3: Implement minimal code**

1. Create `build_ca_sections(report)` in `output/ca_report.py`  
2. Update `features/ca/service.py` to use sections + renderers  
3. Return `report` object with `markdown`, `richtext`, `richtext_chunks`  
4. Remove `_render_text` old path

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/market_ops/test_ca_report_sections.py::test_build_ca_sections_contains_core_titles -v`  
Expected: PASS

**Step 5: Commit**

```bash
git -C scripts add output/ca_report.py features/ca/service.py
git add tests/market_ops/test_ca_report_sections.py
git commit -m "refactor: unify ca output to report renderers"
```

---

### Task 5: Summary output dual format without truncation

**Files:**
- Modify: `scripts/market_ops/output/whatsapp.py`
- Modify: `scripts/market_ops/output/summary.py`
- Create: `tests/market_ops/test_summary_richtext.py`

**Step 1: Write the failing test**

```python
from scripts.market_ops.output.whatsapp import build_summary, WHATSAPP_CHUNK_MAX


def test_build_summary_without_budget_keeps_length():
    oi_lines = ["- " + ("A" * 120)] * 20
    text = build_summary(title="T", oi_lines=oi_lines, whatsapp=True, apply_budget=False)
    assert len(text) > WHATSAPP_CHUNK_MAX
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/market_ops/test_summary_richtext.py::test_build_summary_without_budget_keeps_length -v`  
Expected: FAIL (apply_budget not supported)

**Step 3: Implement minimal code**

1. Add `apply_budget: bool = True` to `build_summary`  
2. When `apply_budget=False`, skip `_apply_whatsapp_budget` and skip truncation  
3. Update `output/summary.py` to emit:
   - `summary_richtext`  
   - `summary_richtext_chunks`  
   - `summary_markdown`  
   - `summary_markdown_path`  
   - Use `show_twitter_metrics=True` for both  
   - Use `apply_budget=False` for both  
4. Update `summary_hash` to combine `summary_richtext + summary_markdown`

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/market_ops/test_summary_richtext.py::test_build_summary_without_budget_keeps_length -v`  
Expected: PASS

**Step 5: Commit**

```bash
git -C scripts add output/whatsapp.py output/summary.py
git add tests/market_ops/test_summary_richtext.py
git commit -m "refactor: summary outputs richtext + markdown without truncation"
```

---

### Task 6: Full verification

**Step 1: Run full test suite**

Run: `PYTHONPATH=. /Users/massis/.openclaw/workspace/.venv/bin/pytest`  
Expected: PASS

**Step 2: Commit submodule pointer**

```bash
git add scripts
git commit -m "refactor: unify report outputs across symbol/ca/summary"
```
