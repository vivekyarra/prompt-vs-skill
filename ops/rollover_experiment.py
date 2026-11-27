"""End the old experiment and start a second one on the same flag (the pre-registered replication).

usage: rollover_experiment.py <Development|Production> <old_name> <new_name> [--flag=<flag name>]
Underscores in names stand for spaces (ops.yml splits args on spaces): Handoff:_Prompt_vs_Skill
Take the results snapshot (snapshot_results.py) BEFORE this: completing freezes the old experiment.
Steps: print old as_of -> complete old (rollout_decision=control) -> create new (same metrics, 100% enrolment,
skill=50) -> start -> verify 50/50. Idempotent: if the new experiment exists it is not created again (a new one
stuck in `created` is started). Mutating: never run against Production while the primary is running.
"""

import json
import sys

from fslib import out
from rolllib import (
    CONTROL,
    FLAG,
    VARIANT,
    connect,
    feature_id,
    find_flag,
    is_5050,
    resolve_name,
    results_as_of,
    rollout_weights,
    split_args,
)

pos, flag_arg = split_args(sys.argv[1:])
if len(pos) != 3:
    sys.exit("usage: rollover_experiment.py <Development|Production> <old_name> <new_name> [--flag=<name>]")
env_name, old_name, new_name = pos[0], resolve_name(pos[1]), resolve_name(pos[2])
if old_name == new_name:
    sys.exit("old and new experiment names must differ")
flag_name = flag_arg or FLAG
HYPOTHESIS = (
    "Replication (same frozen configuration as the primary): agents given the Agent Skill pass the grader more "
    "often than agents given the official prompt, without exceeding the budget more often."
)
api, E, pid, ek = connect(env_name)
out(f"rollover in {env_name}: '{old_name}' -> '{new_name}' on flag {flag_name}")

flag = find_flag(api, pid, flag_name)
if not flag:
    out("flag not found:", flag_name)
    sys.exit(1)
fid = flag["id"]
exps = api.results(f"{E}/experiments/")
old = next((x for x in exps if x.get("name") == old_name), None)
new = next((x for x in exps if x.get("name") == new_name), None)
if not old and not new:
    out(f"old experiment {old_name!r} not found; refusing")
    sys.exit(1)

# (a) old experiment's results as_of (no inference printed)
if old:
    code, r = api.call("GET", f"{E}/experiments/{old['id']}/results/", quiet=True)
    out(f"old experiment {old['id']} status={old.get('status')} results as_of={results_as_of(r)} (GET -> {code})")


def verify(exp_id) -> bool:
    opts = api.results(f"projects/{pid}/features/{fid}/mv-options/")
    keys = {o["id"]: (o.get("key") or o.get("string_value")) for o in opts}
    out("project features API mv-options (default allocation):",
        [(o.get("string_value"), o.get("key"), o.get("default_percentage_allocation")) for o in opts])  # fmt: skip
    code, detail = api.call("GET", f"{E}/experiments/{exp_id}/", quiet=True)
    w = rollout_weights(detail or {}, keys)
    out(f"experiment {exp_id} status={(detail or {}).get('status')} served weights: {w}")
    states = api.results(f"{E}/featurestates/?feature={fid}")
    for s in states:
        out("env feature state:", json.dumps({k: s.get(k) for k in ("enabled", "feature_state_value")}, default=str)[:200],
            [(keys.get(m.get("multivariate_feature_option")), m.get("percentage_allocation"))
             for m in s.get("multivariate_feature_state_values") or []])  # fmt: skip
    ok = is_5050(w) and (detail or {}).get("status") == "running"
    out(f"VERIFY 50/50 {CONTROL}/{VARIANT} and running:", "PASS" if ok else "FAIL")
    return ok


if new and new.get("status") != "created":
    out(f"new experiment {new['id']} already exists (status={new.get('status')}); nothing to do")
    sys.exit(0 if verify(new["id"]) else 1)

# (b) complete the old experiment
if old and old.get("status") == "running":
    code, d = api.call("POST", f"{E}/experiments/{old['id']}/complete/", {"rollout_decision": "control"})
    if code >= 300:
        out("complete failed; the response above lists any accepted choices. Nothing was created.")
        sys.exit(1)
    out("old experiment completed:", (d or {}).get("status"), "ended_at", (d or {}).get("ended_at"),
        "rollout_decision", (d or {}).get("rollout_decision"))  # fmt: skip
elif old:
    out(f"old experiment already {old.get('status')}; not completing again")

# (c) create the new experiment with the same metrics and 100% enrolment
if not new:
    metrics = {m["name"]: m["id"] for m in api.results(f"{E}/experiment-metrics/")}
    missing = [n for n in ("integration_verified", "over_budget") if n not in metrics]
    if missing:
        out("metrics missing in this environment:", missing)
        sys.exit(1)
    opts = api.results(f"projects/{pid}/features/{fid}/mv-options/")
    opt = next((o for o in opts if o.get("string_value") == VARIANT), None)
    if not opt:
        out(f"variation {VARIANT!r} missing on flag")
        sys.exit(1)
    body = {
        "feature": fid,
        "name": new_name,
        "hypothesis": HYPOTHESIS,
        "metrics": [
            {"metric": metrics["integration_verified"], "expected_direction": "increase"},
            {"metric": metrics["over_budget"], "expected_direction": "decrease"},
        ],
        "experiment_rollout": {
            "enabled": True,
            "rollout_percentage": 100,
            "feature_state_value": {"type": "string", "value": CONTROL},
            "multivariate_feature_state_values": [
                {"multivariate_feature_option": opt["id"], "percentage_allocation": 50}
            ],
        },
    }
    code, new = api.call("POST", f"{E}/experiments/", body)
    if code >= 300:
        sys.exit(1)
    out("new experiment created id", new["id"], "feature", feature_id(new))

code, r = api.call("POST", f"{E}/experiments/{new['id']}/start/")
if code >= 300:
    sys.exit(1)
ok = verify(new["id"])
out(f"NEW EXPERIMENT ID: {new['id']} name={new_name!r}")
sys.exit(0 if ok else 1)
