"""Discovery 3: experiment admin key reach, environments, warehouse, existing metrics/experiments."""

import json
import os

from fslib import Api, out, register_secret

key = os.environ.get("FS_EXPERIMENT_ADMIN_KEY", "")
register_secret(key)
out("FS_EXPERIMENT_ADMIN_KEY set:", bool(key), "| project id var:", os.environ.get("FS_EXPERIMENT_PROJECT_ID"))
api = Api(key)
orgs = api.results("organisations/")
out("ORGS:", [(o.get("id"), o.get("name")) for o in orgs])
projects = api.results("projects/")
out("PROJECTS:", [(p.get("id"), p.get("name"), p.get("organisation")) for p in projects])
pid = os.environ.get("FS_EXPERIMENT_PROJECT_ID") or "56666"
envs = api.results(f"environments/?project={pid}")
for e in envs:
    register_secret(e.get("api_key"))
    out(f"env id={e.get('id')} name={e.get('name')!r}")
for e in envs:
    k = e["api_key"]
    out(f"--- {e['name']}")
    for path in ("warehouse-connections/", "experiment-metrics/", "experiments/"):
        code, data = api.call("GET", f"environments/{k}/{path}", quiet=True)
        out(f"GET environments/<key>/{path} -> {code} {json.dumps(data, default=str)[:700]}")
fs = api.results(f"projects/{pid}/features/")
out("features:", [(f.get("id"), f.get("name"), f.get("type")) for f in fs])
