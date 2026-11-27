"""Ship the winner: end the CURRENT running experiment with the matching rollout decision, then verify.

usage: rollout_winner.py <Development|Production> <prompt|skill> [--flag=<flag name>]
If an experiment on the flag is still running it is completed with rollout_decision for the winner
(prompt -> `control`; skill -> the accepted value from DECISION_BY_WINNER in rolllib.py, or, while that is
unknown, candidate values are tried in turn: a 400 mutates nothing). Then 5 fresh identities must all get the
winner value from get_identity_flags. Prints PASS/FAIL. Mutating: never run against Production before the
replication ends.
"""

import json
import os
import sys
import uuid

from fslib import out, register_secret
from rolllib import (
    DECISION_BY_WINNER,
    FLAG,
    connect,
    decision_candidates,
    find_flag,
    pick_running,
    split_args,
)

pos, flag_arg = split_args(sys.argv[1:])
if len(pos) != 2 or pos[1] not in DECISION_BY_WINNER:
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
    done = False
    for cand in decision_candidates(winner):
        code, d = api.call("POST", f"{E}/experiments/{x['id']}/complete/", {"rollout_decision": cand})
        if code < 300:
            out(f"ACCEPTED rollout_decision={cand!r}:", json.dumps({k: (d or {}).get(k) for k in (
                "status", "ended_at", "rollout_decision", "rollout_variant")}, default=str))
            done = True
            break
    if not done:
        out("FAIL: no rollout_decision accepted")
        sys.exit(1)
else:
    out("no running experiment on the flag; skipping completion")

from flagsmith import Flagsmith  # noqa: E402

skey = os.environ.get("FS_EXPERIMENT_SERVER_KEY")
if not skey:
    sys.exit("FS_EXPERIMENT_SERVER_KEY not set")
register_secret(skey)
fs = Flagsmith(environment_key=skey)
vals = []
for i in range(5):
    ident = f"rollout-verify-{uuid.uuid4().hex[:10]}"
    f = fs.get_identity_flags(ident, traits={"stack": "react"}).get_flag(flag_name)
    vals.append(f.value)
    out(f"identity {ident}: value={f.value!r} enabled={f.enabled}")
ok = all(v == winner for v in vals)
out(f"ROLLOUT VERIFY ({winner}):", "PASS" if ok else "FAIL", vals)
sys.exit(0 if ok else 1)
