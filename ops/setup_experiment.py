"""Idempotent setup of the experiment flag, metrics and experiment in handoff-experiment.

usage: setup_experiment.py <Development|Production> [--start]
Looks up every object by name before creating; deletes nothing. Prints ids/status/error bodies only.
"""

import json
import os
import sys

from fslib import Api, out, register_secret

ENV_NAME = sys.argv[1] if len(sys.argv) > 1 else "Development"
START = "--start" in sys.argv
EXP_NAME = {"Production": "Handoff: Prompt vs Skill", "Development": "Handoff pilot"}[ENV_NAME]
FLAG, CONTROL, VARIANT = "onboarding_method", "prompt", "skill"
HYPOTHESIS = (
    "Agents given the Agent Skill pass the grader more often than agents given the official prompt, "
    "without exceeding the budget more often."
)

key = os.environ["FS_EXPERIMENT_ADMIN_KEY"]
register_secret(key)
pid = os.environ.get("FS_EXPERIMENT_PROJECT_ID") or "56666"
api = Api(key)

envs = {e["name"]: e for e in api.results(f"environments/?project={pid}")}
ek = envs[ENV_NAME]["api_key"]
register_secret(ek)
E = f"environments/{ek}"

# --- flag (project level; shared by both environments)
feats = [f for f in api.results(f"projects/{pid}/features/?search={FLAG}") if f["name"] == FLAG]
if feats:
    flag = feats[0]
    out("flag exists id", flag["id"])
else:
    code, flag = api.call(
        "POST",
        f"projects/{pid}/features/",
        {"name": FLAG, "type": "MULTIVARIATE", "initial_value": CONTROL, "default_enabled": True},
    )
    if code >= 300:
        sys.exit(1)
    out("flag created id", flag["id"])
fid = flag["id"]

opts = api.results(f"projects/{pid}/features/{fid}/mv-options/")
out("existing mv options:", [(o.get("id"), o.get("string_value"), o.get("key"), o.get("default_percentage_allocation")) for o in opts])
opt = next((o for o in opts if o.get("string_value") == VARIANT), None)
if not opt:
    code, opt = api.call(
        "POST",
        f"projects/{pid}/features/{fid}/mv-options/",
        {"type": "unicode", "string_value": VARIANT, "key": VARIANT, "default_percentage_allocation": 0, "feature": fid},
    )
    if code >= 300:
        sys.exit(1)
    out("mv option created id", opt["id"])
if opt.get("key") != VARIANT:
    out("WARNING: variation has no key (exposures would not be recorded):", opt.get("key"))
oid = opt["id"]

# --- schema discovery (DRF OPTIONS), best effort
for path in ("experiment-metrics/", "experiments/"):
    code, data = api.call("OPTIONS", f"{E}/{path}", quiet=True)
    post = (data or {}).get("actions", {}).get("POST") if isinstance(data, dict) else None
    out(f"OPTIONS {path} -> {code}", json.dumps(post, default=str)[:1800] if post else "no POST schema")

# --- metrics
METRICS = [("integration_verified", "up"), ("over_budget", "down")]
metric_ids = {}
existing = {m["name"]: m for m in api.results(f"{E}/experiment-metrics/")}
for name, direction in METRICS:
    if name in existing:
        metric_ids[name] = existing[name]["id"]
        out("metric exists", name, existing[name]["id"])
        continue
    code, m = api.call(
        "POST",
        f"{E}/experiment-metrics/",
        {"name": name, "aggregation": "occurrence", "direction": direction, "definition": {"version": 1, "event": name}},
    )
    if code < 300:
        metric_ids[name] = m["id"]
        out("metric created", name, m["id"], json.dumps(m, default=str)[:400])
out("metric ids:", metric_ids)
if len(metric_ids) < 2:
    sys.exit(1)

# --- experiment
exps = [x for x in api.results(f"{E}/experiments/") if x.get("name") == EXP_NAME]
if exps:
    exp = exps[0]
    out("experiment exists id", exp["id"], "status", exp.get("status"))
else:
    body = {
        "feature": fid,
        "name": EXP_NAME,
        "hypothesis": HYPOTHESIS,
        "metrics": [
            {"metric": metric_ids["integration_verified"], "expected_direction": "increase"},
            {"metric": metric_ids["over_budget"], "expected_direction": "decrease"},
        ],
        "experiment_rollout": {
            "enabled": True,
            "rollout_percentage": 100,
            "feature_state_value": {"type": "string", "value": CONTROL},
            "multivariate_feature_state_values": [
                {"multivariate_feature_option": oid, "percentage_allocation": 50}
            ],
        },
    }
    code, exp = api.call("POST", f"{E}/experiments/", body)
    if code >= 300:
        sys.exit(1)
    out("experiment created:", json.dumps(exp, default=str)[:1500])
eid = exp["id"]

if START:
    code, r = api.call("POST", f"{E}/experiments/{eid}/start/")
    out("start ->", code, json.dumps(r, default=str)[:600])
code, r = api.call("GET", f"{E}/experiments/{eid}/", quiet=True)
out("experiment", eid, "status:", (r or {}).get("status"))
out("experiment detail:", json.dumps(r, default=str)[:2500])
