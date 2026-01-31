#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Monitor @bankrbot replies and score mentioned accounts.

Output: JSON to stdout.

Design:
- Fetch recent tweets from @bankrbot using bird user-tweets --json-full.
- Keep only replies (heuristic: tweet text starts with '@' OR legacy.entities.user_mentions present and first token is @).
- Extract mentioned handles from entities.user_mentions.
- Score each mentioned handle using basic account stats from bird user-tweets <handle> -n 1 --json-full.
- Persist last_seen_tweet_id in a state file for de-dup.

This intentionally avoids complex NLP. It's a lightweight heuristic 'quality' gate.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

from repo_paths import state_path

STATE_PATH: Path = state_path("bankr_watch_state.json")

PROMO_KW = re.compile(r"(airdrop|giveaway|join\s+telegram|vip|signal|paid\s+group|link\s+in\s+bio|referral|邀请码)", re.IGNORECASE)


def _run(cmd: List[str], timeout_s: int = 25) -> str:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout_s)
    # bird writes status lines to stderr sometimes; ignore unless stdout empty
    return (p.stdout or "").strip()


def load_state() -> Dict[str, Any]:
    try:
        if STATE_PATH.exists():
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"last_seen_id": ""}


def save_state(state: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def bird_user_tweets(handle: str, n: int = 30) -> List[Dict[str, Any]]:
    raw = _run(["bird", "user-tweets", handle, "-n", str(n), "--json-full"], timeout_s=35)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _tweet_mentions(tweet_full: Dict[str, Any]) -> List[str]:
    try:
        legacy = (tweet_full.get("_raw") or {}).get("legacy") or {}
        ents = legacy.get("entities") or {}
        ums = ents.get("user_mentions") or []
        out = []
        for u in ums:
            sn = (u.get("screen_name") or "").strip()
            if sn:
                out.append(sn.lower())
        return out
    except Exception:
        return []


def _is_reply(tweet_full: Dict[str, Any]) -> bool:
    txt = (tweet_full.get("text") or "").strip()
    if txt.startswith("@"):
        return True
    # fallback: if user_mentions exist and text begins with @<first_mention>
    ms = _tweet_mentions(tweet_full)
    if ms and txt.lower().startswith("@" + ms[0]):
        return True
    # raw field if present
    try:
        legacy = (tweet_full.get("_raw") or {}).get("legacy") or {}
        if legacy.get("in_reply_to_status_id_str"):
            return True
    except Exception:
        pass
    return False


def _extract_user_legacy(tweet_full: Dict[str, Any]) -> Dict[str, Any]:
    """Extract author user legacy from a tweet json-full payload."""
    try:
        ur = ((tweet_full.get("_raw") or {}).get("core") or {}).get("user_results") or {}
        res = ur.get("result") or {}
        legacy = res.get("legacy") or {}
        return {
            "followers_count": legacy.get("followers_count"),
            "friends_count": legacy.get("friends_count"),
            "listed_count": legacy.get("listed_count"),
            "statuses_count": legacy.get("statuses_count"),
            "description": legacy.get("description") or "",
            "name": legacy.get("name") or "",
            "screen_name": legacy.get("screen_name") or "",
            "is_blue_verified": bool(res.get("is_blue_verified")),
            "protected": bool((res.get("privacy") or {}).get("protected")) if isinstance(res.get("privacy"), dict) else bool(res.get("protected")),
        }
    except Exception:
        return {}


def score_user(handle: str) -> Tuple[int, Dict[str, Any]]:
    """Return (score 0-100, meta)."""
    tweets = bird_user_tweets(handle, n=1)
    if not tweets:
        return 0, {"handle": handle, "reason": "no_data"}

    u = _extract_user_legacy(tweets[0])
    followers = int(u.get("followers_count") or 0)
    listed = int(u.get("listed_count") or 0)
    statuses = int(u.get("statuses_count") or 0)
    desc = (u.get("description") or "").strip()
    blue = bool(u.get("is_blue_verified"))
    prot = bool(u.get("protected"))

    score = 50
    reasons: List[str] = []

    # followers
    if followers >= 100_000:
        score += 20; reasons.append(">=100k followers")
    elif followers >= 20_000:
        score += 15; reasons.append(">=20k followers")
    elif followers >= 5_000:
        score += 10; reasons.append(">=5k followers")
    elif followers >= 1_000:
        score += 5; reasons.append(">=1k followers")
    else:
        score -= 10; reasons.append("<1k followers")

    # listed
    if listed >= 500:
        score += 10; reasons.append("listed>=500")
    elif listed >= 100:
        score += 5; reasons.append("listed>=100")

    # activity
    if statuses >= 10_000:
        score += 5; reasons.append("active (10k+ tweets)")
    elif statuses < 100:
        score -= 10; reasons.append("very new/low activity")

    if blue:
        score += 5; reasons.append("blue verified")

    if prot:
        score -= 20; reasons.append("protected")

    if desc and PROMO_KW.search(desc):
        score -= 20; reasons.append("promo keywords")

    score = max(0, min(100, score))
    meta = {
        "handle": handle,
        "score": score,
        "followers": followers,
        "listed": listed,
        "statuses": statuses,
        "blue": blue,
        "protected": prot,
        "reasons": reasons[:6],
    }
    return score, meta


def main() -> int:
    state = load_state()
    last_seen = str(state.get("last_seen_id") or "")

    bankr = bird_user_tweets("bankrbot", n=40)

    # sort oldest->newest by id as int
    def _id_int(x: str) -> int:
        try:
            return int(x)
        except Exception:
            return 0

    bankr.sort(key=lambda t: _id_int(str(t.get("id") or "0")))

    new_items = []
    newest_id = last_seen
    for tw in bankr:
        tid = str(tw.get("id") or "")
        if not tid:
            continue
        if _id_int(tid) <= _id_int(last_seen):
            continue
        newest_id = tid
        if not _is_reply(tw):
            continue
        new_items.append(tw)

    mentions: Dict[str, int] = {}
    tweet_refs: Dict[str, List[str]] = {}  # handle -> [tweet urls]

    for tw in new_items:
        tid = str(tw.get("id") or "")
        ms = _tweet_mentions(tw)
        for h in ms:
            if h == "bankrbot":
                continue
            mentions[h] = mentions.get(h, 0) + 1
            tweet_refs.setdefault(h, []).append(f"https://x.com/bankrbot/status/{tid}")

    # score
    scored: List[Dict[str, Any]] = []
    for h, cnt in sorted(mentions.items(), key=lambda kv: (-kv[1], kv[0])):
        s, meta = score_user(h)
        meta["mentions"] = cnt
        meta["refs"] = tweet_refs.get(h, [])[:3]
        scored.append(meta)

    # produce alerts: score > 50 (threshold controlled by cron message; keep code aligned)
    alerts = [x for x in scored if int(x.get("score") or 0) > 50]

    out = {
        "handle": "bankrbot",
        "window": "since_last_seen",
        "last_seen_id": last_seen,
        "newest_id": newest_id,
        "new_replies": len(new_items),
        "mentioned_accounts": len(scored),
        "alerts": alerts,
        "top": scored[:8],
    }

    # update state even if no alerts (so we don't reprocess)
    if newest_id and newest_id != last_seen:
        state["last_seen_id"] = newest_id
        save_state(state)

    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
