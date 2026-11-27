"""End-of-run snapshot of an experiment's results, INCLUDING the inference block (do not run mid-run).

usage: snapshot_results.py <Development|Production> [experiment_name]   (underscores in the name = spaces)
Refreshes (retrying through the 5-minute throttle), then prints ONE line `SNAPSHOT_JSON: {...}`.
Reads only (the refresh recomputes results; it changes no experiment state).
"""

import json
import sys
from datetime import datetime, timezone

from fslib import out, scrub_exact
from rolllib import DEFAULT_EXPERIMENT, build_snapshot, connect, refresh_fresh, resolve_name

args = sys.argv[1:]
if not args:
    sys.exit("usage: snapshot_results.py <Development|Production> [experiment_name]")
env_name = args[0]
exp_name = resolve_name(args[1]) if len(args) > 1 else DEFAULT_EXPERIMENT.get(env_name, "")
api, E, pid, ek = connect(env_name)

warehouses = api.results(f"{E}/warehouse-connections/")
for w in warehouses:
    out(f"warehouse: status={w.get('status')} total_events={w.get('total_events_received')} "
        f"unique={w.get('unique_events_count')}")  # fmt: skip
exps = [x for x in api.results(f"{E}/experiments/") if x.get("name") == exp_name]
if not exps:
    out(f"experiment {exp_name!r} not found in {env_name}")
    sys.exit(1)
exp = exps[0]
eid = exp["id"]
out(f"experiment {eid} '{exp_name}' status={exp.get('status')}")
r, fresh = refresh_fresh(api, E, eid, out)
if r is None:
    out("could not read results")
    sys.exit(1)
code, detail = api.call("GET", f"{E}/experiments/{eid}/", quiet=True)
snap = build_snapshot(env_name, detail if isinstance(detail, dict) else exp, r, warehouses,
                      datetime.now(timezone.utc), fresh)  # fmt: skip
print("SNAPSHOT_JSON: " + scrub_exact(json.dumps(snap, default=str, separators=(",", ":"))), flush=True)
out(f"snapshot done: as_of={snap['as_of']} fresh={fresh}")
