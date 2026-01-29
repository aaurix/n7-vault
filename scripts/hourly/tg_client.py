#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Telegram local service client (HawkFi TG Service HTTP API)."""

from __future__ import annotations

import json
import random
import time
import urllib.request as urlreq
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class TgClient:
    base_url: str = "http://127.0.0.1:8000"
    user_agent: str = "clawdbot-hourly-summary/1.0"

    def _retry(
        self,
        fn,
        *,
        tries: int = 3,
        base_delay: float = 0.5,
        max_delay: float = 4.0,
        retry_on: Tuple[type, ...] = (Exception,),
    ):
        last = None
        for i in range(tries):
            try:
                return fn()
            except retry_on as e:
                last = e
                if i == tries - 1:
                    break
                d = min(max_delay, base_delay * (2**i))
                d = d * (0.8 + 0.4 * random.random())
                time.sleep(d)
        raise last  # type: ignore[misc]

    def request_json(self, method: str, path: str, payload: Optional[dict] = None, timeout: int = 10) -> Any:
        def _do():
            url = self.base_url + path
            data = None
            headers = {
                "User-Agent": self.user_agent,
                "Content-Type": "application/json",
            }
            if payload is not None:
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = urlreq.Request(url, data=data, headers=headers, method=method)
            with urlreq.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {}

        return self._retry(_do)

    def health_ok(self) -> bool:
        try:
            h = self.request_json("GET", "/health", timeout=6)
            if isinstance(h, dict):
                return bool(h.get("ok")) or (str(h.get("status") or "").lower() == "ok")
            return False
        except Exception:
            return False

    def replay(self, channel_id: int, *, limit: int, since: str, until: str) -> Dict[str, Any]:
        return self.request_json(
            "POST",
            "/replay",
            {"channel": int(channel_id), "limit": int(limit), "since": since, "until": until},
            timeout=15,
        )

    def fetch_messages(self, channel_id: int, *, limit: int, since: str, until: str) -> List[Dict[str, Any]]:
        path = (
            f"/channels/{urlreq.quote(str(channel_id))}/messages"
            f"?limit={int(limit)}&since={urlreq.quote(since)}&until={urlreq.quote(until)}"
        )
        rows = self.request_json("GET", path, timeout=12)
        if isinstance(rows, dict):
            return rows.get("messages") or []
        return rows or []

    def search(self, chat_id: int, q: str, *, limit: int = 20) -> List[Dict[str, Any]]:
        path = f"/search?q={urlreq.quote(q)}&limit={int(limit)}&chat_id={int(chat_id)}"
        rows = self.request_json("GET", path, timeout=12)
        # search endpoint returns a list
        return rows or []


def msg_text(m: Dict[str, Any]) -> str:
    return (m.get("raw_text") or m.get("text") or m.get("message") or m.get("content") or "").strip()


def sender_id(m: Dict[str, Any]) -> int | None:
    try:
        sid = m.get("sender_id")
        return int(sid) if sid is not None else None
    except Exception:
        return None
