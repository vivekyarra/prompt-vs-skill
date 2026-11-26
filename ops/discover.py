"""Discovery: which projects/environments can the admin key reach; is a warehouse connected?

Prints names, ids, HTTP statuses only. Environment api_keys are used internally and never printed.
"""

import json

from fslib import Api, out, register_secret

api = Api()
projects = api.results("projects/")
out("PROJECTS:", [(p.get("id"), p.get("name"), p.get("organisation")) for p in projects])
for p in projects:
    envs = api.results(f"environments/?project={p['id']}")
    out(f"project {p['id']} {p['name']!r} environments:")
    for e in envs:
        register_secret(e.get("api_key"))
        out(f"  env id={e.get('id')} name={e.get('name')!r}")
    if "experiment" in p["name"].lower():
        for e in envs:
            k = e["api_key"]
            out(f"--- experiment project env {e['name']!r}")
            for path in ("warehouse-connections/", "experiment-metrics/", "experiments/"):
                code, data = api.call("GET", f"environments/{k}/{path}", quiet=True)
                if code >= 400:
                    summary = data
                else:
                    summary = {
                        "count": len(data["results"]) if isinstance(data, dict) and "results" in data else None,
                        "keys": sorted(data.keys()) if isinstance(data, dict) else type(data).__name__,
                    }
                out(f"GET environments/<key>/{path} -> {code} {json.dumps(summary, default=str)[:600]}")
                if code == 200 and path == "warehouse-connections/":
                    items = data["results"] if isinstance(data, dict) and "results" in data else data
                    out(
                        "  warehouse connections:",
                        [
                            {kk: v for kk, v in (it or {}).items() if kk in ("id", "type", "status", "name", "provider", "is_active")}
                            for it in (items or [])
                        ],
                    )
            fs = api.results(f"projects/{p['id']}/features/")
            out("  features:", [(f.get("id"), f.get("name"), f.get("type")) for f in fs])
