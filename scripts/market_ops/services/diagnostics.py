#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnostics helpers: timing, hashing, and LLM failure logging."""

from __future__ import annotations

import hashlib
import time
from typing import Callable, Dict, Optional

from ..models import PipelineContext


def measure(perf: Dict[str, float], name: str) -> Callable[[], None]:
    t0 = time.perf_counter()

    def done() -> None:
        perf[name] = round(time.perf_counter() - t0, 3)

    return done


def sha1_text(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def log_llm_failure(
    ctx: PipelineContext,
    tag: str,
    *,
    raw: str = "",
    exc: Optional[BaseException] = None,
) -> None:
    ctx.errors.append(tag)
    detail = tag
    if exc is not None:
        detail += f":{type(exc).__name__}:{exc}"
    if raw:
        detail += f":raw_len={len(raw)}:raw_sha1={sha1_text(raw)[:10]}"
    ctx.llm_failures.append(detail)
