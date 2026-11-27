"""Second-experiment rehearsal, DEVELOPMENT ONLY (experiment 727 'Handoff pilot' and its successor).

usage: python ops/rehearsal_exp2.py <phase> [extra]
phases: probe | stop [action ...] | noexp | create | expose | counts
Refuses to run unless the admin key resolves the Development environment (121204) and never touches Production.
"""

import json
import os
import sys
import time

from fslib import Api, out, register_secret

PHASE = sys.argv[1] if len(sys.argv) > 1 else "probe"
OLD_ID, NEW_NAME = 727, "Handoff pilot 2"
FLAG = "onboarding_method"
METRICS = (744, 745)  # Development integration_verified, over_budget
OPT_ID = 37439

akey = os.environ["FS_EXPERIMENT_ADMIN_KEY"]
register_secret(akey)
api = Api(akey)
pid = os.environ.get("FS_EXPERIMENT_PROJECT_ID") or "56666"
envs = {e["name"]: e for e in api.results(f"environments/?project={pid}")}
dev = envs["Development"]
if int(dev["id"]) != 121204:
    sys.exit("not the expected Development environment; abort")
ek = dev["api_key"]
register_secret(ek)
E = f"environments/{ek}"


def sdk():
    from flagsmith import Flagsmith

    skey = os.environ["FS_EXPERIMENT_SERVER_KEY"]
    register_secret(skey)
    return Flagsmith(environment_key=skey, enable_events=True)


def all_exps():
    return api.results(f"{E}/experiments/")


def new_exp():
    xs = [x for x in all_exps() if x.get("name") == NEW_NAME]
    return xs[0] if xs else None


def flag_info(f):
    e = getattr(f, "experiment", None)
    return {
        "value": f.value, "variant": getattr(f, "variant", None), "enabled": f.enabled,
        "in_exp": bool(e and e.in_experiment), "exp_id": getattr(e, "id", None), "exp_name": getattr(e, "name", None),
    }  # fmt: skip


def results(eid):
    code, r = api.call("GET", f"{E}/experiments/{eid}/results/", quiet=True)
    p = ((r or {}).get("results") or {}).get("payload") or {}
    pts = (p.get("exposures_timeseries") or {}).get("points", [])
    tot = {}
    for pt in pts:
        for k, v in (pt.get("new_identities") or {}).items():
            tot[k] = tot.get(k, 0) + v
    out(f"results {eid}: code={code} as_of={((r or {}).get('results') or {}).get('as_of')} new_identities_by_variant={tot}")
    for m in p.get("metrics", []):
        out("  metric", m.get("metric_id"), json.dumps(m.get("variants")))
    return tot


if PHASE == "probe":
    out("experiments:", [(x["id"], x["name"], x.get("status")) for x in all_exps()])
    code, d = api.call("GET", f"{E}/experiments/{OLD_ID}/")
    out("old detail keys:", sorted(d) if isinstance(d, dict) else d)
    out("old status/started/ended:", d.get("status"), d.get("started_at"), d.get("ended_at"))
    code, d = api.call("OPTIONS", f"{E}/experiments/{OLD_ID}/")
    out("OPTIONS detail:", code, json.dumps(d, default=str)[:1500])
    for p in ("stop", "end", "finish", "complete", "pause", "archive"):
        code, d = api.call("OPTIONS", f"{E}/experiments/{OLD_ID}/{p}/", quiet=True)
        out(f"OPTIONS {p}/ -> {code} {str(d)[:200]}")
    code, d = api.call("OPTIONS", f"{E}/experiments/", quiet=True)
    out("OPTIONS list -> ", code, str(d)[:300])

elif PHASE == "stop":
    acts = [a for a in sys.argv[2:] if "=" not in a] or ["stop"]
    body = dict(a.split("=", 1) for a in sys.argv[2:] if "=" in a) or None
    # a body value with commas is a list of candidates tried in order (a 400 mutates nothing)
    cands = [dict(body, **{k: c}) for k, v in (body or {}).items() if "," in v for c in v.split(",")] or [body]
    done = False
    for p in acts:
        code, d = api.call("OPTIONS", f"{E}/experiments/{OLD_ID}/{p}/", quiet=True)
        post = ((d or {}).get("actions") or {}).get("POST") if isinstance(d, dict) else None
        out(f"OPTIONS {p}/ schema keys:", sorted(post or {}))
        for bd in cands:
            code, d = api.call("POST", f"{E}/experiments/{OLD_ID}/{p}/", bd, quiet=True)
            out(f"POST {p}/ body={bd} ->", code, json.dumps(d, default=str)[:300])
            if code < 300:
                done = True
                break
        if done:
            break
    code, d = api.call("GET", f"{E}/experiments/{OLD_ID}/", quiet=True)
    out("old status now:", d.get("status"), "ended_at", d.get("ended_at"), "rollout_decision", d.get("rollout_decision"), d.get("rollout_variant"))

elif PHASE == "noexp":
    fs = sdk()
    for ident in ("rehearsal-norun-1", "rehearsal-norun-2", "rehearsal-norun-3", "rehearsal-norun-4"):
        f = fs.get_experiment_flag(FLAG, identifier=ident, traits={"stack": "react"})
        out(ident, flag_info(f))
    fs.flush_events()
    fs.close()
    out("experiments:", [(x["id"], x["name"], x.get("status")) for x in all_exps()])

elif PHASE == "create":
    if new_exp():
        out("new experiment exists", new_exp()["id"], new_exp().get("status"))
    else:
        body = {
            "feature": api.results(f"projects/{pid}/features/?search={FLAG}")[0]["id"],
            "name": NEW_NAME,
            "hypothesis": "Second experiment on the same flag after the first ended (rehearsal).",
            "metrics": [
                {"metric": METRICS[0], "expected_direction": "increase"},
                {"metric": METRICS[1], "expected_direction": "decrease"},
            ],
            "experiment_rollout": {
                "enabled": True, "rollout_percentage": 100,
                "feature_state_value": {"type": "string", "value": "prompt"},
                "multivariate_feature_state_values": [{"multivariate_feature_option": OPT_ID, "percentage_allocation": 50}],
            },
        }  # fmt: skip
        code, x = api.call("POST", f"{E}/experiments/", body)
        out("create ->", code, json.dumps(x, default=str)[:600])
    x = new_exp()
    if x:
        code, r = api.call("POST", f"{E}/experiments/{x['id']}/start/")
        out("start ->", code, json.dumps(r, default=str)[:500])
        out("new:", x["id"], (api.call("GET", f"{E}/experiments/{x['id']}/", quiet=True)[1] or {}).get("status"))

elif PHASE == "expose":
    x = new_exp()
    eid = x["id"]
    out("new experiment", eid, "status", x.get("status"))
    api.call("POST", f"{E}/experiments/{eid}/results/refresh/")
    time.sleep(30)
    out("BEFORE any exposure (leak check):")
    results(eid)
    fs = sdk()
    seen = {}
    for ident in [f"rehearsal-{i}" for i in range(1, 21)]:
        seen[ident] = flag_info(fs.get_experiment_flag(FLAG, identifier=ident, traits={"stack": "react"}))
    out("values:", {k: (v["value"], v["variant"], v["in_exp"], v["exp_id"]) for k, v in seen.items()})
    out("value counts:", {v: sum(1 for s in seen.values() if s["value"] == v) for v in {s["value"] for s in seen.values()}})
    out("variant counts:", {v: sum(1 for s in seen.values() if s["variant"] == v) for v in {s["variant"] for s in seen.values()}})
    out("all in new experiment:", all(s["exp_id"] == eid for s in seen.values()))
    fs.flush_events()
    fs.close()
    out("flushed; expected new-experiment identities: 20")

elif PHASE == "counts":
    x = new_exp()
    eid = x["id"]
    for w in api.results(f"{E}/warehouse-connections/"):
        out("warehouse total_events", w.get("total_events_received"), "unique", w.get("unique_events_count"))
    for attempt in range(4):  # refresh is throttled to once per 5 minutes (429): wait and retry
        code, _ = api.call("POST", f"{E}/experiments/{eid}/results/refresh/", quiet=True)
        out("refresh ->", code)
        if code < 300:
            time.sleep(60)
            results(eid)
            break
        time.sleep(150)
    else:
        results(eid)
    out("OLD experiment", OLD_ID)
    code, _ = api.call("POST", f"{E}/experiments/{OLD_ID}/results/refresh/", quiet=True)
    out("old refresh ->", code)
    time.sleep(30)
    results(OLD_ID)
