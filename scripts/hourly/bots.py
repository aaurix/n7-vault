#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Bot sender_id filtering.

We prefer sender_id allow/deny decisions over text heuristics.
The denylist is stored in memory/bot_senders.json (user-maintained).
"""

from __future__ import annotations

import json
import os
from typing import Set


DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "memory", "bot_senders.json")


def load_bot_sender_ids(path: str = DEFAULT_PATH) -> Set[int]:
    try:
        if os.path.exists(path):
            data = json.loads(open(path, "r", encoding="utf-8").read())
            out: Set[int] = set()
            for _k, arr in (data.get("senderIds") or {}).items():
                for x in (arr or []):
                    try:
                        out.add(int(x))
                    except Exception:
                        pass
            return out
    except Exception:
        pass
    return set()
