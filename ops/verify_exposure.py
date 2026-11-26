"""Verify exposure + event end to end in the Development environment (setup-check-* identities only).

Uses FS_EXPERIMENT_SERVER_KEY with the python SDK (enable_events=True), then reads the experiment's
warehouse/results counters via the admin API. Prints no keys.
"""

import json
import os
import sys
import time

from flagsmith import Flagsmith
from fslib import Api, out, register_secret

IDENT = sys.argv[1] if len(sys.argv) > 1 else "setup-check-1"
sk = os.environ["FS_EXPERIMENT_SERVER_KEY"]
register_secret(sk)

fs = Flagsmith(environment_key=sk, enable_events=True)
flag = fs.get_experiment_flag("onboarding_method", identifier=IDENT, traits={"stack": "react"})
exp = getattr(flag, "experiment", None)
out(
    "flag type:", type(flag).__name__, "| enabled:", getattr(flag, "enabled", None),
    "| value:", repr(getattr(flag, "value", None)), "| variant:", repr(getattr(flag, "variant", None)),
    "| in_experiment:", getattr(exp, "in_experiment", None),
)
fs.track_event("integration_verified", identifier=IDENT, traits={"stack": "react"})
fs.flush_events()
fs.close()
out("flushed (flush_events returned without raising)")

admin = Api(os.environ["FS_EXPERIMENT_ADMIN_KEY"])
register_secret(os.environ["FS_EXPERIMENT_ADMIN_KEY"])
pid = os.environ.get("FS_EXPERIMENT_PROJECT_ID") or "56666"
envs = {e["name"]: e for e in admin.results(f"environments/?project={pid}")}
ek = envs["Development"]["api_key"]
register_secret(ek)
E = f"environments/{ek}"
exps = [x for x in admin.results(f"{E}/experiments/") if x["name"] == "Handoff pilot"]
eid = exps[0]["id"]
out("pilot experiment", eid, "status", exps[0].get("status"))

for i in range(8):
    time.sleep(30)
    code, wh = admin.call("GET", f"{E}/warehouse-connections/", quiet=True)
    if code == 200 and wh:
        w = wh[0]
        out(f"warehouse: status={w.get('status')} total_events={w.get('total_events_received')} "
            f"unique={w.get('unique_events_count')} last={w.get('last_event_received_at')}")
        if (w.get("total_events_received") or 0) > 0:
            break

code, r = admin.call("POST", f"{E}/experiments/{eid}/results/refresh/")
out("refresh ->", code, json.dumps(r, default=str)[:500])
time.sleep(60)
code, r = admin.call("GET", f"{E}/experiments/{eid}/results/", quiet=True)
out("results ->", code, json.dumps(r, default=str)[:2500])
