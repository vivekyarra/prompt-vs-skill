"""Send `integration_verified` for trials whose verdict was corrected after the fact.

Only trial ids listed in data/corrections.jsonl with new_passed=true are accepted; anything else is refused.
Default is a dry run. `--send` actually sends (identity = trial id, trait stack, like the runner).
`--dev-test <identity>` sends ONE event for an arbitrary `setup-check-*` identity in the environment the
secrets belong to (use it only with the development environment) to prove late events are counted.

usage (ops.yml passes args split on spaces): python ops/backfill_events.py [--send] [--dev-test setup-check-2]
"""

import json
import os
import pathlib
import sys

from flagsmith import Flagsmith
from fslib import out, register_secret

args = sys.argv[1:]
send = "--send" in args
dev_test = args[args.index("--dev-test") + 1] if "--dev-test" in args else None
key = os.environ["FS_EXPERIMENT_SERVER_KEY"]
register_secret(key)

fs = Flagsmith(environment_key=key, enable_events=True)
targets: list[tuple[str, str]] = []
if dev_test:
    if not dev_test.startswith("setup-check-"):
        sys.exit("--dev-test only accepts setup-check-* identities")
    targets.append((dev_test, "react"))
else:
    path = pathlib.Path(__file__).resolve().parents[1] / "data" / "corrections.jsonl"
    for line in path.read_text().splitlines():
        r = json.loads(line)
        if r.get("new_passed") is True and r.get("replays_passed") == "3/3":
            targets.append((r["trial_id"], r["stack"]))
        else:
            out(f"skip {r['trial_id']}: not confirmed (replays_passed={r.get('replays_passed')})")
out(f"targets: {[t for t, _ in targets]} | send={send}")
for ident, stack in targets:
    if send or dev_test:
        fs.track_event("integration_verified", identifier=ident, traits={"stack": stack})
        out(f"sent integration_verified for {ident}")
    else:
        out(f"dry run: would send integration_verified for {ident}")
if send or dev_test:
    fs.flush_events()
    fs.close()
    out("flushed")
