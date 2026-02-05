#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Compatibility shim for Twitter evidence helpers."""

from __future__ import annotations

from .services import twitter_evidence as _evidence

globals().update({k: v for k, v in _evidence.__dict__.items() if not k.startswith("__")})

__all__ = [k for k in globals().keys() if not k.startswith("__") and k != "_evidence"]
