"""Shared helpers for ops scripts. Never prints secrets: all output goes through scrub()."""

from __future__ import annotations

import json
import os
import re
import sys

import requests

BASE = "https://api.flagsmith.com"
_SECRETS: set[str] = set()
_KEYLIKE = re.compile(r"\b(?=[A-Za-z0-9_.\-]*\d)[A-Za-z0-9_.\-]{20,}\b")


def register_secret(s: str | None) -> None:
    if s and len(s) >= 8:
        _SECRETS.add(s)


for _n in ("FS_EXPERIMENT_SERVER_KEY", "FS_SANDBOX_CLIENT_KEY", "FS_SANDBOX_SERVER_KEY", "FS_SANDBOX_ADMIN_KEY"):
    register_secret(os.environ.get(_n))


def scrub(text) -> str:
    t = text if isinstance(text, str) else json.dumps(text, default=str)
    for s in sorted(_SECRETS, key=len, reverse=True):
        t = t.replace(s, "<redacted>")
    return _KEYLIKE.sub("<redacted?>", t)


def scrub_exact(text) -> str:
    """Like scrub() but only masks registered secret values (keeps timestamps/ids in JSON intact)."""
    t = text if isinstance(text, str) else json.dumps(text, default=str)
    for s in sorted(_SECRETS, key=len, reverse=True):
        t = t.replace(s, "<redacted>")
    return t


def out(*a) -> None:
    print(scrub(" ".join(str(x) for x in a)), flush=True)


class Api:
    def __init__(self, key: str | None = None):
        key = key or os.environ.get("FS_SANDBOX_ADMIN_KEY", "")
        if not key:
            out("FS_SANDBOX_ADMIN_KEY not set")
            sys.exit(2)
        self.h = {"Authorization": f"Api-Key {key}", "Accept": "application/json"}

    def call(self, method: str, path: str, body=None, quiet=False):
        url = path if path.startswith("http") else f"{BASE}/api/v1/{path.lstrip('/')}"
        try:
            r = requests.request(method, url, headers=self.h, json=body, timeout=60)
        except Exception as e:  # noqa: BLE001
            out(f"{method} {path} -> EXC {type(e).__name__}")
            return -1, None
        try:
            data = r.json() if r.content else None
        except ValueError:
            data = r.text[:500]
        if not quiet:
            shown = data if r.status_code >= 400 else ""
            out(f"{method} {path} -> {r.status_code} {str(shown)[:800]}")
        return r.status_code, data

    def results(self, path: str):
        """GET a list endpoint (follows `next`); returns list."""
        code, data = self.call("GET", path, quiet=True)
        items = []
        while True:
            if code != 200:
                out(f"GET {path} -> {code} {str(data)[:300]}")
                return items
            if isinstance(data, dict) and "results" in data:
                items += data["results"]
                nxt = data.get("next")
                if not nxt:
                    return items
                code, data = self.call("GET", nxt, quiet=True)
            else:
                return data if isinstance(data, list) else [data]
