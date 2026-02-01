#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prepare hourly market data (no LLM summarization).

Goal:
- Run deterministic collection + enrichment.
- Output a JSON object to stdout that an agent can summarize.

This avoids OpenAI chat/completions calls. Embeddings may still be used elsewhere,
but this script does not call hourly.llm_openai.chat_json.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from hourly.config import DEFAULT_TOTAL_BUDGET_S
from hourly.models import PipelineContext
from hourly.services.context_builder import build_context
from hourly.services.meme_radar import (
    merge_tg_addr_candidates_into_radar,
    spawn_meme_radar,
    wait_meme_radar,
)
from hourly.services.oi_service import build_oi, build_oi_plans_step
from hourly.services.telegram_service import build_human_texts, build_viewpoint_threads, fetch_tg_messages
from hourly.services.tg_topics import build_tg_topics
from hourly.services.social_cards import build_social_cards
from hourly.services.twitter_following import build_twitter_following_summary
from hourly.perp_dashboard import build_perp_dash_inputs
from hourly.tg_topics_fallback import tg_topics_fallback


_TRUTHY = {"1", "true", "True", "yes", "YES", "on", "ON"}

_STEP_ORDER = [
    "health_check",
    "meme_spawn",
    "tg_fetch",
    "human_texts",
    "oi_items",
    "oi_plans",
    "viewpoint_threads",
    "tg_topics",
    "tg_topics_fallback",
    "twitter_following",
    "meme_wait",
    "tg_addr_merge",
    "social_cards",
    "perp_dash_inputs",
]

_STEP_GROUPS: Dict[str, Set[str]] = {
    "tg": {
        "health_check",
        "tg_fetch",
        "human_texts",
        "viewpoint_threads",
        "tg_topics",
        "tg_topics_fallback",
        "tg_addr_merge",
        "social_cards",
    },
    "oi": {"oi_items", "oi_plans"},
    "meme": {"meme_spawn", "meme_wait", "tg_addr_merge"},
    "twitter": {"twitter_following"},
}


class StepTimeout(RuntimeError):
    pass


def _truthy_env(name: str) -> bool:
    return os.environ.get(name) in _TRUTHY


def _parse_step_tokens(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    parts = []
    for chunk in str(raw).replace(",", " ").split():
        part = chunk.strip()
        if part:
            parts.append(part)
    return parts


def _expand_step_tokens(tokens: Iterable[str]) -> Tuple[Set[str], List[str]]:
    known = set(_STEP_ORDER)
    out: Set[str] = set()
    unknown: List[str] = []
    for tok in tokens:
        t = str(tok or "").strip()
        if not t:
            continue
        if t in _STEP_GROUPS:
            out.update(_STEP_GROUPS[t])
            continue
        if t in known:
            out.add(t)
            continue
        unknown.append(t)
    return out, unknown


def _log(msg: str, *, enabled: bool) -> None:
    if not enabled:
        return
    print(msg, file=sys.stderr, flush=True)


def _call_with_timeout(timeout_s: float, fn: Callable[[], Any]) -> Any:
    if timeout_s <= 0:
        return fn()

    def _handler(signum, frame):  # type: ignore[no-untyped-def]
        raise StepTimeout(f"timeout>{timeout_s:.1f}s")

    prev = signal.signal(signal.SIGALRM, _handler)
    try:
        signal.setitimer(signal.ITIMER_REAL, timeout_s)
        return fn()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, prev)


class StepRunner:
    def __init__(
        self,
        ctx: PipelineContext,
        *,
        skip_steps: Set[str],
        only_steps: Set[str],
        log_steps: bool,
        timeout_s: float,
        continue_on_error: bool,
    ) -> None:
        self.ctx = ctx
        self.skip_steps = skip_steps
        self.only_steps = only_steps
        self.log_steps = log_steps
        self.timeout_s = timeout_s
        self.continue_on_error = continue_on_error

    def _should_run(self, name: str) -> bool:
        if self.only_steps and name not in self.only_steps:
            return False
        if name in self.skip_steps:
            return False
        return True

    def run(self, name: str, fn: Callable[[], Any], *, enabled: bool = True) -> Any:
        if not enabled or not self._should_run(name):
            if self.log_steps:
                reason = "disabled" if not enabled else "filtered"
                _log(f"[hourly_prepare] SKIP {name} ({reason})", enabled=self.log_steps)
            self.ctx.perf[f"prepare_{name}"] = 0.0
            self.ctx.perf[f"prepare_{name}_skipped"] = 1.0
            return None

        _log(f"[hourly_prepare] START {name}", enabled=self.log_steps)
        t0 = time.perf_counter()
        try:
            if self.timeout_s > 0:
                return _call_with_timeout(self.timeout_s, fn)
            return fn()
        except Exception as e:
            self.ctx.errors.append(f"step_failed:{name}:{type(e).__name__}:{e}")
            _log(f"[hourly_prepare] FAIL {name} {type(e).__name__}:{e}", enabled=self.log_steps)
            if not self.continue_on_error:
                raise
            return None
        finally:
            dt = time.perf_counter() - t0
            self.ctx.perf[f"prepare_{name}"] = round(dt, 3)
            _log(f"[hourly_prepare] END {name} {dt:.3f}s", enabled=self.log_steps)


def _resolve_steps(
    *,
    skip_tokens: Iterable[str],
    only_tokens: Iterable[str],
) -> Tuple[Set[str], Set[str], List[str], List[str]]:
    skip_steps, skip_unknown = _expand_step_tokens(skip_tokens)
    only_steps, only_unknown = _expand_step_tokens(only_tokens)
    return skip_steps, only_steps, skip_unknown, only_unknown


def _assert_tg_health(ctx: PipelineContext) -> None:
    if not ctx.client.health_ok():
        raise RuntimeError("TG service not healthy")


def run_prepare(
    total_budget_s: float = DEFAULT_TOTAL_BUDGET_S,
    *,
    skip_steps: Optional[Iterable[str]] = None,
    only_steps: Optional[Iterable[str]] = None,
    log_steps: Optional[bool] = None,
    step_timeout_s: Optional[float] = None,
    continue_on_error: Optional[bool] = None,
) -> Dict[str, Any]:
    t_total = time.perf_counter()
    ctx: PipelineContext = build_context(total_budget_s=total_budget_s)

    # LLM availability is decided by configuration (API key).

    log_steps = _truthy_env("HOURLY_PREP_LOG_STEPS") if log_steps is None else log_steps
    step_timeout_s = float(os.environ.get("HOURLY_PREP_STEP_TIMEOUT_S") or 0.0) if step_timeout_s is None else float(step_timeout_s)
    continue_on_error = _truthy_env("HOURLY_PREP_CONTINUE_ON_ERROR") if continue_on_error is None else bool(continue_on_error)

    skip_tokens: List[str] = list(skip_steps or [])
    only_tokens: List[str] = list(only_steps or [])

    if _truthy_env("HOURLY_PREP_SKIP_TG"):
        skip_tokens.append("tg")
    if _truthy_env("HOURLY_PREP_SKIP_MEME"):
        skip_tokens.append("meme")
    if _truthy_env("HOURLY_PREP_SKIP_OI"):
        skip_tokens.append("oi")

    skip_tokens += _parse_step_tokens(os.environ.get("HOURLY_PREP_SKIP_STEPS"))
    only_tokens += _parse_step_tokens(os.environ.get("HOURLY_PREP_ONLY_STEPS"))

    skip_set, only_set, skip_unknown, only_unknown = _resolve_steps(skip_tokens=skip_tokens, only_tokens=only_tokens)

    runner = StepRunner(
        ctx,
        skip_steps=skip_set,
        only_steps=only_set,
        log_steps=log_steps,
        timeout_s=step_timeout_s,
        continue_on_error=continue_on_error,
    )

    if skip_unknown:
        _log(f"[hourly_prepare] WARN unknown skip tokens: {', '.join(skip_unknown)}", enabled=log_steps)
    if only_unknown:
        _log(f"[hourly_prepare] WARN unknown only tokens: {', '.join(only_unknown)}", enabled=log_steps)

    runner.run("health_check", lambda: _assert_tg_health(ctx))

    meme_proc = runner.run("meme_spawn", lambda: spawn_meme_radar(ctx))

    runner.run("tg_fetch", lambda: fetch_tg_messages(ctx))
    runner.run("human_texts", lambda: build_human_texts(ctx))

    runner.run("oi_items", lambda: build_oi(ctx))

    # LLM-based OI plans (optional, budgeted)
    runner.run("oi_plans", lambda: build_oi_plans_step(ctx), enabled=bool(ctx.use_llm))

    runner.run("viewpoint_threads", lambda: build_viewpoint_threads(ctx))
    runner.run("tg_topics", lambda: build_tg_topics(ctx))

    # Deterministic fallback (only if tg_topics didn't already attempt one).
    if not ctx.narratives and not ctx.perf.get("tg_topics_fallback_used"):
        runner.run("tg_topics_fallback", lambda: setattr(ctx, "narratives", tg_topics_fallback(ctx.human_texts, limit=5)))

    runner.run("twitter_following", lambda: build_twitter_following_summary(ctx, allow_llm=False))

    # meme radar join
    runner.run("meme_wait", lambda: wait_meme_radar(ctx, meme_proc), enabled=meme_proc is not None)
    runner.run("tg_addr_merge", lambda: merge_tg_addr_candidates_into_radar(ctx), enabled=meme_proc is not None)

    # Unified social cards (TG + Twitter)
    runner.run("social_cards", lambda: build_social_cards(ctx))

    # Build twitter evidence packs for the agent (one token per pack)
    ca_inputs = []
    seen = set()
    for it in (ctx.radar_items or [])[:25]:
        dex = (it.get("dex") or {})
        sym = str(dex.get("baseSymbol") or "").upper().strip()
        ca = str(it.get("addr") or "").strip()
        ev = it.get("twitter_evidence") or {}
        snippets = (ev.get("snippets") or [])[:6]
        if not sym or not snippets:
            continue
        key = f"{sym}|{ca[:12]}" if ca else f"{sym}|-"
        if key in seen:
            continue
        seen.add(key)
        pack = {"sym": sym, "evidence": {"snippets": snippets}}
        if ca:
            pack["ca"] = ca
        ca_inputs.append(pack)
        if len(ca_inputs) >= 8:
            break

    def _build_perp_dash() -> List[Dict[str, Any]]:
        try:
            # Top perps are already enriched inside ctx.oi_items (kline_1h/4h + price/OI changes).
            return build_perp_dash_inputs(oi_items=ctx.oi_items, max_n=3)
        except Exception as e:
            ctx.errors.append(f"perp_dash_inputs_failed:{type(e).__name__}:{e}")
            return []

    perp_dash_inputs: List[Dict[str, Any]] = runner.run("perp_dash_inputs", _build_perp_dash) or []

    debug = {
        "human_texts": len(ctx.human_texts or []),
        "messages_by_chat": {k: len(v or []) for k, v in (ctx.messages_by_chat or {}).items()},
        "tg_topics_inferred": any(bool(it.get("_inferred")) for it in (ctx.narratives or []) if isinstance(it, dict)),
        "tg_topics_fallback_used": bool(ctx.perf.get("tg_topics_fallback_used")),
        "tg_topics_fallback_reason": ctx.tg_topics_fallback_reason or "",
    }

    ctx.perf["prepare_total"] = round(time.perf_counter() - t_total, 3)
    _log(f"[hourly_prepare] TOTAL {ctx.perf['prepare_total']:.3f}s", enabled=log_steps)

    return {
        "since": ctx.since,
        "until": ctx.until,
        "hourKey": ctx.hour_key,
        "use_llm": bool(ctx.use_llm),
        "perf": ctx.perf,
        "errors": ctx.errors,
        "prepared": {
            "oi_lines": ctx.oi_lines,
            "oi_items": ctx.oi_items,
            "perp_dash_inputs": perp_dash_inputs,
            "oi_plans": ctx.oi_plans,
            "tg_topics": ctx.narratives,
            "threads_strong": ctx.strong_threads,
            "threads_weak": ctx.weak_threads,
            "twitter_following": ctx.twitter_following,
            "twitter_following_summary": ctx.twitter_following_summary,
            "radar_items": ctx.radar_items[:15],
            "twitter_ca_inputs": ca_inputs,
            "social_cards": ctx.social_cards[:6],
            "debug": debug,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Hourly prepare (diagnostic-friendly)")
    ap.add_argument("--skip", help="comma/space separated step names or groups (tg, oi, meme)")
    ap.add_argument("--only", help="comma/space separated step names or groups (tg, oi, meme)")
    ap.add_argument("--log-steps", action="store_true", help="log step timing to stderr")
    ap.add_argument("--step-timeout", type=float, help="timeout (seconds) per step")
    ap.add_argument("--continue-on-error", action="store_true", help="continue after step failures")
    args = ap.parse_args()

    skip_steps = _parse_step_tokens(args.skip)
    only_steps = _parse_step_tokens(args.only)

    budget = float(os.environ.get("HOURLY_MARKET_SUMMARY_BUDGET_S") or DEFAULT_TOTAL_BUDGET_S)
    out = run_prepare(
        total_budget_s=budget,
        skip_steps=skip_steps,
        only_steps=only_steps,
        log_steps=True if args.log_steps else None,
        step_timeout_s=args.step_timeout,
        continue_on_error=True if args.continue_on_error else None,
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
