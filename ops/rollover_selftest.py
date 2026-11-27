"""DEVELOPMENT-ONLY self-test of the rollover tooling on a throwaway flag `rollout_probe_<n>`.

usage: rollover_selftest.py <probe|full> [prompt|skill]
probe: throwaway flag + experiment, then try `rollout_decision` candidates to learn which value ships `skill`.
full:  old experiment -> rollover_experiment.py (twice: idempotency) -> rollout_winner.py <winner> -> verify.
Both clean up what they created (experiments, then the flag) and refuse to run unless the admin key resolves
the Development environment (121204).
"""

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from fslib import out, register_secret
from rolllib import SKILL_DECISION_CANDIDATES, connect, find_flag

PHASE = sys.argv[1] if len(sys.argv) > 1 else "probe"
WINNER = sys.argv[2] if len(sys.argv) > 2 else "skill"
api, E, pid, ek = connect("Development")
envs = {e["name"]: e for e in api.results(f"environments/?project={pid}")}
if int(envs["Development"]["id"]) != 121204:
    sys.exit("not the expected Development environment; abort")

N = int(time.time())
FLAG = f"rollout_probe_{N}"
OLD, NEW = f"rollover-test-old-{N}", f"rollover-test-new-{N}"
HERE = Path(__file__).resolve().parent
created_exps: list[int] = []
ok = True


def setup_flag():
    code, flag = api.call("POST", f"projects/{pid}/features/", {
        "name": FLAG, "type": "MULTIVARIATE", "initial_value": "prompt", "default_enabled": True})  # fmt: skip
    if code >= 300:
        sys.exit(1)
    code, opt = api.call("POST", f"projects/{pid}/features/{flag['id']}/mv-options/", {
        "type": "unicode", "string_value": "skill", "key": "skill",
        "default_percentage_allocation": 0, "feature": flag["id"]})  # fmt: skip
    if code >= 300:
        sys.exit(1)
    return flag, opt


def metric_ids():
    ms = {m["name"]: m["id"] for m in api.results(f"{E}/experiment-metrics/")}
    return ms["integration_verified"], ms["over_budget"]


def make_experiment(flag, opt, name):
    a, b = metric_ids()
    code, x = api.call("POST", f"{E}/experiments/", {
        "feature": flag["id"], "name": name, "hypothesis": "rollover self-test (throwaway)",
        "metrics": [{"metric": a, "expected_direction": "increase"}, {"metric": b, "expected_direction": "decrease"}],
        "experiment_rollout": {"enabled": True, "rollout_percentage": 100,
                               "feature_state_value": {"type": "string", "value": "prompt"},
                               "multivariate_feature_state_values": [
                                   {"multivariate_feature_option": opt["id"], "percentage_allocation": 50}]},
    })  # fmt: skip
    if code >= 300:
        sys.exit(1)
    created_exps.append(x["id"])
    code, _ = api.call("POST", f"{E}/experiments/{x['id']}/start/")
    if code >= 300:
        sys.exit(1)
    return x


def run(script, *args):
    out(f"--- running {script} {' '.join(args)}")
    p = subprocess.run([sys.executable, str(HERE / script), *args], capture_output=True, text=True, env=os.environ)
    out(p.stdout[-6000:], p.stderr[-1500:])
    out(f"--- {script} exit code {p.returncode}")
    return p.returncode


def identity_values(n=5):
    from flagsmith import Flagsmith

    skey = os.environ["FS_EXPERIMENT_SERVER_KEY"]
    register_secret(skey)
    fs = Flagsmith(environment_key=skey)
    return [fs.get_identity_flags(f"rollover-test-{uuid.uuid4().hex[:8]}").get_flag(FLAG).value for _ in range(n)]


def cleanup(flag):
    for eid in created_exps:
        code, _ = api.call("DELETE", f"{E}/experiments/{eid}/", quiet=True)
        out(f"cleanup: DELETE experiment {eid} -> {code}")
    code, d = api.call("DELETE", f"projects/{pid}/features/{flag['id']}/", quiet=True)
    out(f"cleanup: DELETE flag {FLAG} -> {code} {str(d)[:200] if code >= 300 else ''}")
    out("flag still present:", bool(find_flag(api, pid, FLAG)))


flag, opt = setup_flag()
out("throwaway flag", FLAG, flag["id"], "option", opt["id"])
try:
    if PHASE == "probe":
        x = make_experiment(flag, opt, OLD)
        code, d = api.call("OPTIONS", f"{E}/experiments/{x['id']}/complete/", quiet=True)
        out("OPTIONS complete/:", code, json.dumps(d, default=str)[:1200])
        for cand in SKILL_DECISION_CANDIDATES + ["control"]:
            code, d = api.call("POST", f"{E}/experiments/{x['id']}/complete/", {"rollout_decision": cand}, quiet=True)
            out(f"candidate {cand!r} -> {code} {json.dumps(d, default=str)[:300]}")
            if code < 300:
                out("ACCEPTED:", cand)
                break
        code, d = api.call("GET", f"{E}/experiments/{x['id']}/", quiet=True)
        out("after:", json.dumps({k: d.get(k) for k in ("status", "rollout_decision", "rollout_variant")}))
        vals = identity_values(10)
        out("identity values after completion (10):", vals)
    else:
        x = make_experiment(flag, opt, OLD)
        a = (f"--flag={FLAG}",)
        ok &= run("rollover_experiment.py", "Development", OLD, NEW, *a) == 0
        ok &= run("rollover_experiment.py", "Development", OLD, NEW, *a) == 0  # idempotent second call
        exps = [e for e in api.results(f"{E}/experiments/") if e.get("name") in (OLD, NEW)]
        out("experiments:", [(e["id"], e["name"], e["status"]) for e in exps])
        created_exps.extend(e["id"] for e in exps if e["id"] not in created_exps)
        ok &= sum(1 for e in exps if e["name"] == NEW) == 1
        ok &= run("rollout_winner.py", "Development", WINNER, *a) == 0
        ok &= run("rollout_winner.py", "Development", WINNER, *a) == 0  # nothing running: verify only
    out("SELFTEST", PHASE, "PASS" if ok else "FAIL")
finally:
    cleanup(flag)
sys.exit(0 if ok else 1)
