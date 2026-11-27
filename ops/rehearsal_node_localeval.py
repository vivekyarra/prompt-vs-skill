"""Live check, DEVELOPMENT ONLY: does real Flagsmith count an exposure sent by @flagsmith/nodejs under local evaluation?

The grader's emulator now serves the environment document (grader/mock.py). Before trusting it for Node, this script
confirms with the real service what the Node SDK does with `enableLocalEvaluation: true` and a server key:

 1. start a throw-away experiment on the Development flag `onboarding_method` (ops/rollover_experiment.py). That
    COMPLETES the experiment already running there ("Handoff pilot 2", id 1058, which cannot be restarted) and
    creates a new one; the script then waits until identity evaluation reports `in_experiment`;
 2. a Node process (@flagsmith/nodejs 9.5.0, installed in a temp dir) with local evaluation calls
    `getExperimentFlag` for rehearsal-node-1..6, tracks `integration_verified` for 1..3, flushes;
    two control identities (rehearsal-node-ctl-1..2) go through the Python SDK with remote evaluation;
 3. read the experiment's exposure counts: node + control counted -> 8, only the controls -> 2;
 4. complete the throw-away experiment again (rollout_winner.py prompt) so Development serves `prompt` as before.

usage: rehearsal_node_localeval.py        (needs FS_EXPERIMENT_SERVER_KEY and FS_EXPERIMENT_ADMIN_KEY)
Only Development (environment id 121204) and only identities rehearsal-node-*. Prints no secrets.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from flagsmith import Flagsmith
from fslib import out, register_secret
from rolllib import FLAG, connect, refresh_fresh

HERE = Path(__file__).resolve().parent
NEW_NAME = "Handoff_node_localeval_rehearsal"
FLAG_NAME = FLAG
NODE_JS = r"""
import { Flagsmith } from '@flagsmith/nodejs'
const fs = new Flagsmith({
  environmentKey: process.env.FS_EXPERIMENT_SERVER_KEY,
  enableLocalEvaluation: true,
  enableEvents: true,
})
for (let i = 1; i <= 6; i++) {
  const id = `rehearsal-node-${i}`
  const f = await fs.getExperimentFlag('onboarding_method', id, { stack: 'node' })
  const e = f.experiment
  console.log(JSON.stringify({ id, value: f.value, variant: f.variant ?? null, enabled: f.enabled, isDefault: !!f.isDefault,
    experiment: e ? { id: e.id, name: e.name, inExperiment: e.inExperiment } : null }))
  if (i <= 3) fs.trackEvent('integration_verified', { identifier: id })
}
await fs.flushEvents()
await fs.close(10000)
"""


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    for line in (r.stdout + r.stderr).splitlines():
        out(" |", line)
    return r.returncode


skey = os.environ["FS_EXPERIMENT_SERVER_KEY"]
register_secret(skey)
api, E, pid, ek = connect("Development")
code, env = api.call("GET", f"environments/{ek}/", quiet=True)
if code != 200 or int(env.get("id", 0)) != 121204:
    sys.exit("not the Development environment (121204); abort")

# 1. throw-away experiment
rc = run([sys.executable, str(HERE / "rollover_experiment.py"), "Development", "Handoff_pilot_2", NEW_NAME])
if rc != 0:
    sys.exit("could not start the rehearsal experiment")
exps = [x for x in api.results(f"{E}/experiments/") if x.get("name") == NEW_NAME.replace("_", " ")]
eid = exps[0]["id"]
out("rehearsal experiment", eid, exps[0].get("status"))

py = Flagsmith(environment_key=skey, enable_events=True)
for attempt in range(1, 13):
    f = py.get_identity_flags("rehearsal-node-probe", {"stack": "node"}).get_flag(FLAG_NAME)
    exp = getattr(f, "experiment", None)
    out(f"propagation probe {attempt}: in_experiment={bool(exp and exp.in_experiment)}")
    if exp and exp.in_experiment:
        break
    time.sleep(20)

# 2. Node local evaluation
with tempfile.TemporaryDirectory() as tmp:
    (Path(tmp) / "package.json").write_text('{"name":"rehearsal","private":true,"type":"module"}')
    (Path(tmp) / "run.mjs").write_text(NODE_JS)
    out("node", subprocess.run(["node", "-v"], capture_output=True, text=True).stdout.strip())
    if run(["npm", "install", "--no-audit", "--no-fund", "@flagsmith/nodejs@9.5.0"], cwd=tmp) != 0:
        sys.exit("npm install failed")
    rc = run(["node", "run.mjs"], cwd=tmp, env=dict(os.environ))
    out("node exit code", rc)

for i in (1, 2):
    f = py.get_experiment_flag(FLAG_NAME, identifier=f"rehearsal-node-ctl-{i}", traits={"stack": "node"})
    exp = getattr(f, "experiment", None)
    out(f"control rehearsal-node-ctl-{i}: value={f.value} variant={getattr(f, 'variant', None)} "
        f"in_experiment={bool(exp and exp.in_experiment)}")  # fmt: skip
py.flush_events()
py.close()


# 3. counts (refresh is throttled to once per 5 minutes; events take a while to land in the warehouse)
def exposure_total(r) -> int:
    p = (((r or {}).get("results") or {}).get("payload")) or {}
    tot = 0
    for pt in (p.get("exposures_timeseries") or {}).get("points", []):
        tot += sum((pt.get("new_identities") or {}).values())
    return tot


total = 0
for attempt in range(1, 5):
    time.sleep(60)
    r, fresh = refresh_fresh(api, E, eid, out, max_wait_s=420)
    total = exposure_total(r)
    p = (((r or {}).get("results") or {}).get("payload")) or {}
    out(f"counts attempt {attempt}: fresh={fresh} exposure identities={total}")
    for m in p.get("metrics", []):
        out("  metric", m.get("metric_id"), json.dumps(m.get("variants"), default=str)[:300])
    if total >= 8:
        break
out("RESULT: exposure identities counted by Flagsmith =", total,
    "(8 = Node local evaluation counted 6 + 2 controls; 2 = only the Python remote controls)")  # fmt: skip

# 4. restore: complete the throw-away experiment with the control decision
run([sys.executable, str(HERE / "rollout_winner.py"), "Development", "prompt"])
sys.exit(0)
