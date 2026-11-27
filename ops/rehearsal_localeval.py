"""Local-evaluation live check, DEVELOPMENT ONLY. Requires 'Handoff pilot 2' to be running.

usage: python ops/rehearsal_localeval.py
Calls get_experiment_flag with enable_local_evaluation=True for rehearsal-le-1..6, then a manual
track_exposure_event for rehearsal-le-m1; compare warehouse event totals and read the experiment counts
afterwards with `rehearsal_exp2.py counts`.
"""

import os
import sys
import time

from flagsmith import Flagsmith
from fslib import Api, out, register_secret

key = os.environ["FS_EXPERIMENT_SERVER_KEY"]
register_secret(key)
akey = os.environ["FS_EXPERIMENT_ADMIN_KEY"]
register_secret(akey)
api = Api(akey)
pid = os.environ.get("FS_EXPERIMENT_PROJECT_ID") or "56666"
dev = {e["name"]: e for e in api.results(f"environments/?project={pid}")}["Development"]
if int(dev["id"]) != 121204:
    sys.exit("not Development; abort")
E = f"environments/{dev['api_key']}"


def wh():
    for w in api.results(f"{E}/warehouse-connections/"):
        return w.get("total_events_received")


out("warehouse events before:", wh())
fs = Flagsmith(environment_key=key, enable_local_evaluation=True, enable_events=True)
for i in range(1, 7):
    ident = f"rehearsal-le-{i}"
    f = fs.get_experiment_flag("onboarding_method", identifier=ident, traits={"stack": "react"})
    e = getattr(f, "experiment", None)
    out(ident, "value", f.value, "variant", getattr(f, "variant", None), "enabled", f.enabled,
        "experiment", None if e is None else (e.id, e.in_experiment))  # fmt: skip
fs.flush_events()
f = fs.get_identity_flags("rehearsal-le-m1", {"stack": "react"}).get_flag("onboarding_method")
out("manual: value", f.value, "variant", getattr(f, "variant", None))
fs.track_exposure_event("onboarding_method", identifier="rehearsal-le-m1",
                        value=getattr(f, "variant", None) or ("skill" if f.value == "skill" else "control"),
                        traits={"stack": "react"})  # fmt: skip
fs.flush_events()
fs.close()
time.sleep(40)
out("warehouse events after:", wh(), "(+6 = all get_experiment_flag calls emitted; +1 = only the manual one; +0 = none)")
