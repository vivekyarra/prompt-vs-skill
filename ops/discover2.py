"""Discovery 2: organisations reachable, and what the experiment server key can see."""

import os

import requests

from fslib import Api, out

api = Api()
orgs = api.results("organisations/")
out("ORGS:", [(o.get("id"), o.get("name")) for o in orgs])
for o in orgs:
    ps = api.results(f"projects/?organisation={o['id']}")
    out(f"org {o['id']} projects:", [(p["id"], p["name"]) for p in ps])
    code, data = api.call("GET", f"organisations/{o['id']}/", quiet=True)
    if code == 200 and isinstance(data, dict):
        out("  org fields:", sorted(data.keys()))

key = os.environ.get("FS_EXPERIMENT_SERVER_KEY", "")
out("experiment key set:", bool(key), "length:", len(key), "prefix-ser:", key.startswith("ser."))
if key:
    for host in ("https://edge.api.flagsmith.com/api/v1/flags/", "https://api.flagsmith.com/api/v1/flags/"):
        r = requests.get(host, headers={"X-Environment-Key": key}, timeout=30)
        names = []
        if r.status_code == 200:
            names = [f["feature"]["name"] for f in r.json()]
        out(host.split("/")[2], "flags ->", r.status_code, names)
    # Does the admin key reach an environment addressed by the experiment key (works only if it is a client key)?
    code, data = api.call("GET", f"environments/{key}/", quiet=True)
    out("admin GET environments/<experiment key>/ ->", code, str(data)[:200] if code >= 400 else "ok")
    r = requests.get(
        "https://edge.api.flagsmith.com/api/v1/environment-document/", headers={"X-Environment-Key": key}, timeout=30
    )
    if r.status_code == 200:
        d = r.json()
        out("environment-document: project", d.get("project", {}).get("name"), "env id", d.get("id"), "keys", sorted(d.keys())[:12])
    else:
        out("environment-document ->", r.status_code)
