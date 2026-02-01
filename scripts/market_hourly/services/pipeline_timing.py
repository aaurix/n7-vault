#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Timing helpers for pipeline perf tracking."""

from __future__ import annotations

import time
from typing import Callable, Dict


def measure(perf: Dict[str, float], name: str) -> Callable[[], None]:
    t0 = time.perf_counter()

    def done() -> None:
        perf[name] = round(time.perf_counter() - t0, 3)

    return done
