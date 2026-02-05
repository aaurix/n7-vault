from .schema import wrap_result
from .services.context_builder import build_context
from .pipeline.hourly import run_hourly
from .services.summary_render import render
from .services.symbol_analysis import analyze_symbol
from .services.ca_analysis import analyze_ca


def analyze_hourly(total_budget_s: float = 240.0, *, fresh: bool = False, cache_ttl: str = "") -> dict:
    ctx = build_context(total_budget_s=total_budget_s, fresh=fresh, cache_ttl=cache_ttl)
    run_hourly(ctx)
    summary = render(ctx)
    return wrap_result(mode="hourly", data={"prepared": summary}, summary=summary, errors=ctx.errors, use_llm=ctx.use_llm)


def analyze_symbol_facade(symbol: str, template: str = "dashboard", allow_llm: bool = True) -> dict:
    out = analyze_symbol(symbol, template=template, allow_llm=allow_llm)
    return wrap_result(mode="symbol", data=out.get("data", {}), summary=out.get("summary"), errors=out.get("errors", []), use_llm=out.get("use_llm", False))


def analyze_ca_facade(addr: str, allow_llm: bool = True) -> dict:
    out = analyze_ca(addr, allow_llm=allow_llm)
    return wrap_result(mode="ca", data=out.get("data", {}), summary=out.get("summary"), errors=out.get("errors", []), use_llm=out.get("use_llm", False))
