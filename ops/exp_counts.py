"""Read an experiment's exposure/conversion counts from Flagsmith (refreshes results; sends no events).

usage: python ops/exp_counts.py <Development|Production> "<experiment name>"
"""

import json
import os
import sys

from fslib import Api, out, register_secret

env_name = sys.argv[1] if len(sys.argv) > 1 else "Development"
exp_name = sys.argv[2] if len(sys.argv) > 2 else "Handoff pilot"
key = os.environ["FS_EXPERIMENT_ADMIN_KEY"]
register_secret(key)
admin = Api(key)
pid = os.environ.get("FS_EXPERIMENT_PROJECT_ID") or "56666"
envs = {e["name"]: e for e in admin.results(f"environments/?project={pid}")}
k = envs[env_name]["api_key"]
register_secret(k)
E = f"environments/{k}"
for w in admin.results(f"{E}/warehouse-connections/"):
    out(f"warehouse: status={w.get('status')} total_events={w.get('total_events_received')} "
        f"unique={w.get('unique_events_count')}")  # fmt: skip
for x in admin.results(f"{E}/experiments/"):
    if x["name"] != exp_name:
        continue
    eid = x["id"]
    admin.call("POST", f"{E}/experiments/{eid}/results/refresh/")
    code, r = admin.call("GET", f"{E}/experiments/{eid}/results/", quiet=True)
    out(f"experiment {eid} '{exp_name}' status={x.get('status')} results -> {code}")
    out(json.dumps(r, default=str)[:4000])
