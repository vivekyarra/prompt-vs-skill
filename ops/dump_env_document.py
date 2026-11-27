"""Print the STRUCTURE of the live Flagsmith environment document (read-only GET, no state change).

The document is what SDK local evaluation downloads: `GET <api>/environment-document/` with the
server-side key in `X-Environment-Key`. Used once to model the grader emulator faithfully
(grader/mock.py). Prints key names and value types, plus the feature-state entry of one flag with its
values. Never prints a key: strings are shown as `<str>` (except inside the one flag entry, where
long token-like strings and uuids are masked), the environment api_key is a client key but still masked.

usage: dump_env_document.py [flag_name]     (default: onboarding_method)
env:   FS_EXPERIMENT_SERVER_KEY
"""

from __future__ import annotations

import json
import os
import re
import sys

import requests
from fslib import out, register_secret

API = "https://edge.api.flagsmith.com/api/v1/environment-document/"
SECRET_KEYS = {"api_key", "key", "client_api_key", "secret", "token"}
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
TOKENISH = re.compile(r"^(?=.*\d)[A-Za-z0-9_.\-]{20,}$")


def shape(v, depth=0):
    """Structure only: dict -> {key: shape}, list -> [len, shape of first item], scalars -> type name."""
    if isinstance(v, dict):
        return {k: shape(x, depth + 1) for k, x in v.items()}
    if isinstance(v, list):
        return [f"len={len(v)}"] + ([shape(v[0], depth + 1)] if v else [])
    if v is None:
        return "null"
    return type(v).__name__


def mask(v, key=""):
    """Values of the one flag entry; secrets and uuids masked."""
    if isinstance(v, dict):
        return {k: mask(x, k) for k, x in v.items()}
    if isinstance(v, list):
        return [mask(x, key) for x in v]
    if isinstance(v, str):
        if key in SECRET_KEYS or TOKENISH.match(v):
            return "<masked>"
        if UUID_RE.match(v):
            return "<uuid>"
    return v


def main() -> int:
    flag = sys.argv[1] if len(sys.argv) > 1 else "onboarding_method"
    key = os.environ.get("FS_EXPERIMENT_SERVER_KEY", "")
    if not key:
        out("FS_EXPERIMENT_SERVER_KEY not set")
        return 2
    register_secret(key)
    r = requests.get(API, headers={"X-Environment-Key": key, "Accept": "application/json"}, timeout=60)
    out("GET environment-document ->", r.status_code, "link header:", bool(r.headers.get("link")))
    if r.status_code != 200:
        return 1
    doc = r.json()
    print("DOC_STRUCTURE:", json.dumps(shape(doc), indent=1), flush=True)
    fss = doc.get("feature_states") or []
    out("feature_states:", len(fss), "names:", sorted(fs["feature"]["name"] for fs in fss))
    mine = [fs for fs in fss if fs["feature"]["name"] == flag]
    out(f"entries for {flag}:", len(mine))
    for fs in mine:
        print("FLAG_ENTRY:", json.dumps(mask(fs), indent=1), flush=True)
    for name in ("project", "organisation"):
        sub = doc.get(name)
        if isinstance(sub, dict):
            print(f"{name.upper()}_KEYS:", json.dumps(shape(sub)), flush=True)
    segs = (doc.get("project") or {}).get("segments") or []
    out("segments:", len(segs), "identity_overrides:", len(doc.get("identity_overrides") or []))
    out("top-level keys:", sorted(doc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
