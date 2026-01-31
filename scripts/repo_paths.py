#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Repo-root-relative path helpers.

Cron jobs often run with an unexpected CWD; using repo-root-relative paths prevents
reads/writes from drifting.

This module lives under scripts/ so that all scripts can import it without
installing a package.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def repo_root() -> Path:
    """Return the absolute repo root Path."""
    # scripts/repo_paths.py -> scripts/ -> repo root
    return Path(__file__).resolve().parents[1]


def repo_path(*parts: str) -> Path:
    return repo_root().joinpath(*parts)


def scripts_path(*parts: str) -> Path:
    return repo_path("scripts", *parts)


def memory_path(*parts: str) -> Path:
    return repo_path("memory", *parts)


def state_path(*parts: str) -> Path:
    return repo_path("state", *parts)
