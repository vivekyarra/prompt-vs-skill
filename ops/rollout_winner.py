"""Ship the winner: end the CURRENT running experiment with the matching rollout decision, then verify.

usage: rollout_winner.py <Development|Production> <prompt|skill> [--flag=<flag name>]
If an experiment on the flag is still running it is completed (prompt -> rollout_decision `control`;
skill -> `variant` + rollout_variant, the accepted form per rolllib.SKILL_ROLLOUT_VARIANT_FORM, forms are tried
in turn while unknown: a 400 mutates nothing). Then 5 fresh identities must all get the winner value from
get_identity_flags (retried for up to ~3 minutes for propagation). Prints PASS/FAIL.
Mutating: never run against Production before the replication ends.
"""

import json
import os
import sys
import time
import uuid

from fslib import out, register_secret
from rolllib import FLAG, WINNERS, connect, decision_bodies, find_flag, pick_running, split_args

pos, flag_arg = split_args(sys.argv[1:])
if len(pos) != 2 or pos[1] not in WINNERS:
    sys.exit("usage: rollout_winner.py <Development|Production> <prompt|skill> [--flag=<name>]")
env_name, winner = pos
flag_name = flag_arg or FLAG
api, E, pid, ek = connect(env_name)
flag = find_flag(api, pid, flag_name)
if not flag:
    out("flag not found:", flag_name)
    sys.exit(1)

running = pick_running(api.results(f"{E}/experiments/"), flag["id"])
if len(running) > 1:
    out("more than one running experiment on the flag; refusing:", [(x["id"], x["name"]) for x in running])
    sys.exit(1)
if running:
    x = running[0]
    out(f"ending running experiment {x['id']} '{x['name']}' for winner {winner}")
    opts = api.results(f"projects/{pid}/features/{flag['id']}/mv-options/")
    option = next((o for o in opts if o.get("string_value") == "skill"), None)
    done = False
    for body in decision_bodies(winner, option):
        code, d = api.call("POST", f"{E}/experiments/{x['id']}/complete/", body)
        if code < 300:
            keys = ("status", "ended_at", "rollout_decision", "rollout_variant")
            out(f"ACCEPTED {body}:", json.dumps({k: (d or {}).get(k) for k in keys}, default=str))
            done = True
            break
    if not done:
        out("FAIL: no rollout decision accepted (see the validation messages above)")
        sys.exit(1)
else:
    out("no running experiment on the flag; skipping completion")

from flagsmith import Flagsmith  # noqa: E402

skey = os.environ.get("FS_EXPERIMENT_SERVER_KEY")
if not skey:
    sys.exit("FS_EXPERIMENT_SERVER_KEY not set")
register_secret(skey)
fs = Flagsmith(environment_key=skey)
ok, vals = False, []
for attempt in range(1, 10):  # a flag change can take a little while to reach identity evaluation
    vals = []
    for _ in range(5):
        ident = f"rollout-verify-{uuid.uuid4().hex[:10]}"
        vals.append(fs.get_identity_flags(ident, traits={"stack": "react"}).get_flag(flag_name).value)
    ok = all(v == winner for v in vals)
    out(f"verify attempt {attempt}: values={vals}")
    if ok:
        break
    time.sleep(20)
out(f"ROLLOUT VERIFY ({winner}):", "PASS" if ok else "FAIL", vals)
sys.exit(0 if ok else 1)
