"""Audit the SANDBOX project for leftovers from trials (flags, metrics, experiments). Read-only."""

import os

from fslib import Api, out, register_secret

api = Api()
pid = os.environ.get("FS_SANDBOX_PROJECT_ID") or "56668"
feats = api.results(f"projects/{pid}/features/")
out(f"sandbox features: {len(feats)}", sorted(f.get("name") for f in feats)[:40])
for e in api.results(f"environments/?project={pid}"):
    register_secret(e.get("api_key"))
    k = e["api_key"]
    for path in ("experiment-metrics/", "experiments/"):
        code, data = api.call("GET", f"environments/{k}/{path}", quiet=True)
        items = data.get("results", data) if isinstance(data, dict) else data
        names = [(i.get("id"), i.get("name"), i.get("status")) for i in (items or [])] if isinstance(items, list) else items
        out(f"{e['name']} {path} -> {code} count={len(names) if isinstance(names, list) else '?'}", str(names)[:600])
