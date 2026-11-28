"""Read an experiment's exposure/conversion counts from Flagsmith (refreshes results; sends no events).

usage: python ops/exp_counts.py <Development|Production> "<experiment name>"
Through ops.yml (which splits args on spaces) write underscores for the spaces of the name: Handoff:_Skill_v2
"""

import json
import os
import sys

from fslib import Api, out, register_secret

env_name = sys.argv[1] if len(sys.argv) > 1 else "Development"
# Default experiment per environment (ops.yml splits args on spaces, so names are not passed in).
exp_name = sys.argv[2] if len(sys.argv) > 2 else (
    "Handoff: Prompt vs Skill" if env_name == "Production" else "Handoff pilot")
key = os.environ["FS_EXPERIMENT_ADMIN_KEY"]
register_secret(key)
admin = Api(key)
pid = os.environ.get("FS_EXPERIMENT_PROJECT_ID") or "56666"
envs = {e["name"]: e for e in admin.results(f"environments/?project={pid}")}
k = envs[env_name]["api_key"]
register_secret(k)
E = f"environments/{k}"
# ops.yml cannot pass a name with spaces: the name is tried as given first, then with underscores read as spaces.
all_exps = admin.results(f"{E}/experiments/")
if not any(x["name"] == exp_name for x in all_exps):
    exp_name = exp_name.replace("_", " ").strip()
if not any(x["name"] == exp_name for x in all_exps):
    out(f"experiment {exp_name!r} not found in {env_name}; names here: {sorted(x['name'] for x in all_exps)}")
    sys.exit(1)
for w in admin.results(f"{E}/warehouse-connections/"):
    out(f"warehouse: status={w.get('status')} total_events={w.get('total_events_received')} "
        f"unique={w.get('unique_events_count')}")  # fmt: skip
for x in all_exps:
    if x["name"] != exp_name:
        continue
    eid = x["id"]
    admin.call("POST", f"{E}/experiments/{eid}/results/refresh/")
    code, r = admin.call("GET", f"{E}/experiments/{eid}/results/", quiet=True)
    out(f"experiment {eid} '{exp_name}' status={x.get('status')} results -> {code}")
    # Counts only: the stopping rule forbids reading win probability mid-run, so drop inference blocks.
    for m in ((r or {}).get("results", {}).get("payload", {}).get("metrics", [])):
        m.pop("inference", None)
    out(json.dumps(r, default=str)[:4000])
