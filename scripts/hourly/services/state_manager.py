#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""State access for the hourly pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from repo_paths import state_path


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
