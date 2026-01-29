#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Send PushDeer notifications to multiple pushkeys.

Reads keys from:
- env PUSHDEER_KEYS (comma-separated), or
- a file (one line comma-separated) passed via --keys-file.

Usage:
  python3 scripts/pushdeer_send.py --title "..." --desp "..." --type markdown

API:
  POST https://api2.pushdeer.com/message/push
Docs: https://www.pushdeer.com/official.html
"""

import argparse
import os
import json
from urllib.request import Request, urlopen
from urllib.parse import urlencode

API = "https://api2.pushdeer.com/message/push"


def load_keys(env_keys: str | None, keys_file: str | None) -> list[str]:
    keys = []
    if keys_file and os.path.exists(keys_file):
        raw = open(keys_file, "r", encoding="utf-8").read().strip()
        if raw:
            keys.extend([k.strip() for k in raw.split(",") if k.strip()])
    if env_keys:
        keys.extend([k.strip() for k in env_keys.split(",") if k.strip()])
    # dedup
    out = []
    seen = set()
    for k in keys:
        if k in seen:
            continue
        seen.add(k)
        out.append(k)
    return out


def post(pushkey: str, text: str, desp: str = "", type_: str = "text") -> dict:
    data = {
        "pushkey": pushkey,
        "text": text,
        "desp": desp,
        "type": type_,
    }
    body = urlencode(data).encode("utf-8")
    req = Request(
        API,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "clawdbot-pushdeer/1.0",
        },
        method="POST",
    )
    with urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", required=True, help="PushDeer text/title")
    ap.add_argument("--desp", default="", help="Markdown/body")
    ap.add_argument("--desp-file", default="", help="Read desp from a UTF-8 file (overrides --desp)")
    ap.add_argument("--type", default="markdown", choices=["text", "markdown", "image"])
    ap.add_argument("--keys-file", default="", help="file containing comma-separated pushkeys")
    args = ap.parse_args()

    desp = args.desp
    if args.desp_file:
        if not os.path.exists(args.desp_file):
            raise SystemExit(f"desp file not found: {args.desp_file}")
        desp = open(args.desp_file, "r", encoding="utf-8").read()

    keys = load_keys(os.environ.get("PUSHDEER_KEYS"), args.keys_file or None)
    if not keys:
        raise SystemExit("No PushDeer keys found (env PUSHDEER_KEYS or --keys-file)")

    ok = 0
    for k in keys:
        try:
            res = post(k, args.title, desp, args.type)
            # PushDeer returns {'code':0,...} on success
            if isinstance(res, dict) and res.get("code") == 0:
                ok += 1
        except Exception:
            pass

    print(f"pushdeer_sent={ok}/{len(keys)}")


if __name__ == "__main__":
    main()
