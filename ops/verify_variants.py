"""Find what a `skill`-bucket identity returns (value vs variant). Uses setup-check-N identities only (Development)."""

import os

from flagsmith import Flagsmith
from fslib import out, register_secret

sk = os.environ["FS_EXPERIMENT_SERVER_KEY"]
register_secret(sk)
fs = Flagsmith(environment_key=sk, enable_events=True)
seen = {}
for i in range(2, 12):
    flag = fs.get_experiment_flag("onboarding_method", identifier=f"setup-check-{i}", traits={"stack": "node"})
    v = (repr(flag.value), repr(flag.variant), flag.experiment.in_experiment if flag.experiment else None)
    out(f"setup-check-{i}:", v)
    seen[v[1]] = v
    if "'skill'" in seen:
        break
fs.flush_events()
fs.close()
out("flushed")
