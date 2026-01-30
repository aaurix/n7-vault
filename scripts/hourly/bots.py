#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Bot sender_id filtering.

We prefer sender_id allow/deny decisions over text heuristics.
The denylist is stored in memory/bot_senders.json (user-maintained).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Set

from repo_paths import memory_path


DEFAULT_PATH: Path = memory_path("bot_senders.json")


def load_bot_sender_ids(path: Path = DEFAULT_PATH) -> Set[int]:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
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
