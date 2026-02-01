#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""State access for the hourly pipeline."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from repo_paths import state_path


def _iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class HourlyStateManager:
    def meme_radar_output_path(self) -> Path:
        return state_path("meme", "last_candidates.json")

    def load_meme_radar_output(self, errors: Optional[List[str]] = None) -> Dict[str, Any]:
        path = self.meme_radar_output_path()
        try:
            if not path.exists():
                if errors is not None:
                    errors.append("meme_radar_empty:no_output_file")
                return {}
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            if errors is not None:
                errors.append(f"meme_radar_read_failed:{e}")
            return {}

    def hourly_prepare_state_path(self) -> Path:
        return state_path("hourly_prepare_state.json")

    def update_hourly_prepare_state(self, update_fn: Callable[[Dict[str, Any]], None]) -> None:
        path = self.hourly_prepare_state_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data: Dict[str, Any] = {}
            if path.exists():
                try:
                    loaded = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        data = loaded
                except Exception:
                    data = {}
            update_fn(data)
            data["updated_at"] = _iso_now()
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            return
