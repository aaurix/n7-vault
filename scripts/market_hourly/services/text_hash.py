#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Text hashing helpers for summary fingerprints."""

from __future__ import annotations

import hashlib


def sha1_text(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()
