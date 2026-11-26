"""Discovery 2: what the experiment server key identifies, and whether the admin key reaches it."""

import os

import requests

from fslib import Api, out, register_secret

api = Api()
orgs = api.results("organisations/")
out("ORGS reachable by admin key:", [(o.get("id"), o.get("name")) for o in orgs])

key = os.environ.get("FS_EXPERIMENT_SERVER_KEY", "")
out("experiment server key set:", bool(key), "length:", len(key))
r = requests.get(
    "https://edge.api.flagsmith.com/api/v1/environment-document/", headers={"X-Environment-Key": key}, timeout=30
)
out("environment-document ->", r.status_code)
if r.status_code == 200:
    d = r.json()
    register_secret(d.get("api_key"))
    proj = d.get("project", {})
    out("experiment env: id", d.get("id"), "name", d.get("name"), "| project id", proj.get("id"), "name", proj.get("name"),
        "org", (proj.get("organisation") or {}).get("name") if isinstance(proj.get("organisation"), dict) else proj.get("organisation"))
    out("feature states:", [(fs.get("feature", {}).get("name"), fs.get("enabled")) for fs in d.get("feature_states", [])])
    ck = d.get("api_key")
    for path in ("", "warehouse-connections/", "experiment-metrics/"):
        code, data = api.call("GET", f"environments/{ck}/{path}", quiet=True)
        out(f"admin GET environments/<experiment client key>/{path} ->", code, str(data)[:150] if code >= 400 else "ok")
    code, data = api.call("GET", f"projects/{proj.get('id')}/", quiet=True)
    out(f"admin GET projects/{proj.get('id')}/ ->", code, str(data)[:150] if code >= 400 else "ok")
