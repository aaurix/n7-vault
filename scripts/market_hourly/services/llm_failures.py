#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LLM failure logging for the hourly pipeline."""

from __future__ import annotations

from typing import Optional

from ..models import PipelineContext
from .text_hash import sha1_text


def _log_llm_failure(ctx: PipelineContext, tag: str, *, raw: str = "", exc: Optional[BaseException] = None) -> None:
    ctx.errors.append(tag)
    detail = tag
    if exc is not None:
        detail += f":{type(exc).__name__}:{exc}"
    if raw:
        detail += f":raw_len={len(raw)}:raw_sha1={sha1_text(raw)[:10]}"
    ctx.llm_failures.append(detail)
