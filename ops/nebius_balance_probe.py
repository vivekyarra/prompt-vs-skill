"""Probe whether the Nebius Token Factory API exposes balance/usage (read-only GETs, prints statuses and key names)."""

import json
import os

import requests
from fslib import out, register_secret

key = os.environ.get("NEBIUS_API_KEY", "")
register_secret(key)
base = (os.environ.get("NEBIUS_BASE_URL") or "https://api.tokenfactory.nebius.com/v1/").rstrip("/")
root = base.rsplit("/v1", 1)[0]
h = {"Authorization": f"Bearer {key}"}
for url in (f"{base}/usage", f"{base}/credits", f"{base}/balance", f"{base}/billing", f"{base}/billing/balance",
            f"{root}/v0/usage", f"{root}/v1/usage", f"{root}/billing/balance", f"{base}/models?verbose=false"):
    try:
        r = requests.get(url, headers=h, timeout=20)
        body = r.text[:200].replace("\n", " ")
        try:
            body = "json keys: " + str(list(r.json().keys())[:8]) if isinstance(r.json(), dict) else body
        except ValueError:
            pass
        out(f"GET {url.replace(root, '<root>')} -> {r.status_code} {body}")
    except Exception as e:  # noqa: BLE001
        out(f"GET {url} -> EXC {type(e).__name__}")
