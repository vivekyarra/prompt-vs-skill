"""Pure helpers + connection helper shared by snapshot_results / rollover_experiment / rollout_winner.

No side effects at import time (the parsing helpers are unit-tested in tests/test_rolllib.py).
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone

FLAG = "onboarding_method"
CONTROL, VARIANT = "prompt", "skill"
DEFAULT_EXPERIMENT = {"Production": "Handoff: Prompt vs Skill", "Development": "Handoff pilot"}
# rollout_decision (verified live in Development): `control` ships the control value (prompt). Shipping a variation
# is `rollout_decision="variant"` plus a required `rollout_variant` (integer option id; found by
# `ops/rollover_selftest.py probe`). With the form unset, key/id/uuid are tried in turn.
SKILL_ROLLOUT_VARIANT_FORM: str | None = "id"  # verified live in Development: the option's integer id
WINNERS = ("prompt", "skill")


def resolve_name(s: str) -> str:
    """ops.yml splits args on spaces and has no quoting, so underscores in a name stand for spaces."""
    return s.replace("_", " ").strip()


def split_args(argv: list[str]) -> tuple[list[str], str | None]:
    """Separate `--flag=<name>` / `--flag <name>` from positional args."""
    pos, flag, i = [], None, 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--flag="):
            flag = a.split("=", 1)[1]
        elif a == "--flag" and i + 1 < len(argv):
            flag = argv[i + 1]
            i += 1
        else:
            pos.append(a)
        i += 1
    return pos, flag


# Hypothesis text stored on a new experiment (rollover_experiment.py --hypothesis=<key>). The default key keeps
# the text every earlier rollover used.
HYPOTHESES = {
    "replication": (
        "Replication (same frozen configuration as the primary): agents given the Agent Skill pass the grader more "
        "often than agents given the official prompt, without exceeding the budget more often."
    ),
    "followup": (
        "Exploratory follow-up (no decision rule): agents given skill v2 (skill/flagsmith-ab-test-v2) compared with "
        "agents given the official prompt; same agent, model, limits, prompt, brief, apps and grader. Never pooled "
        "with the primary or the replication."
    ),
}


def pop_option(argv: list[str], name: str) -> tuple[list[str], str | None]:
    """Remove `--<name>=<value>` from argv; return (remaining args, value or None). Other args are untouched."""
    rest, value = [], None
    for a in argv:
        if a.startswith(f"--{name}="):
            value = a.split("=", 1)[1]
        else:
            rest.append(a)
    return rest, value


def feature_id(exp: dict):
    f = exp.get("feature")
    return f.get("id") if isinstance(f, dict) else f


def pick_running(exps: list[dict], flag_id) -> list[dict]:
    return [x for x in exps if x.get("status") == "running" and feature_id(x) == flag_id]


def parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def is_fresh(as_of: str | None, since: datetime) -> bool:
    d = parse_ts(as_of)
    return bool(d and d >= since)


def results_as_of(r) -> str | None:
    return ((r or {}).get("results") or {}).get("as_of")


def rollout_weights(detail: dict, option_keys: dict) -> dict[str, float]:
    """Variation weights (percent) served by an experiment: the multivariate entries of its experiment_rollout
    (option id -> key via `option_keys`), with the control value taking the remainder."""
    rollout = (detail or {}).get("experiment_rollout") or {}
    w: dict[str, float] = {}
    for e in rollout.get("multivariate_feature_state_values") or []:
        opt = e.get("multivariate_feature_option")
        opt = opt.get("id") if isinstance(opt, dict) else opt
        w[option_keys.get(opt, f"option_{opt}")] = float(e.get("percentage_allocation") or 0)
    w[CONTROL] = round(100 - sum(w.values()), 6)
    return w


def is_5050(w: dict[str, float]) -> bool:
    return set(w) == {CONTROL, VARIANT} and abs(w[CONTROL] - 50) < 1e-6 and abs(w[VARIANT] - 50) < 1e-6


def build_snapshot(env_name: str, exp: dict, results, warehouses: list[dict], now: datetime, fresh: bool) -> dict:
    return {
        "snapshot_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "environment": env_name,
        "experiment": {k: exp.get(k) for k in ("id", "name", "status", "started_at", "ended_at", "rollout_decision")},
        "as_of": results_as_of(results),
        "fresh": fresh,
        "warehouse": [
            {"status": w.get("status"), "total_events_received": w.get("total_events_received"),
             "unique_events_count": w.get("unique_events_count")}
            for w in warehouses
        ],  # fmt: skip
        "results": results,  # full payload, inference included on purpose (end-of-run snapshot)
    }


def decision_bodies(winner: str, option: dict | None = None) -> list[dict]:
    """Request bodies to try (in order) for POST .../complete/ so the flag ships `winner` (400s mutate nothing)."""
    if winner not in WINNERS:
        raise ValueError(f"winner must be one of {list(WINNERS)}, got {winner!r}")
    if winner == CONTROL:
        return [{"rollout_decision": "control"}]
    option = option or {}
    forms = {"key": option.get("key") or VARIANT, "id": option.get("id"), "uuid": option.get("uuid")}
    order = [SKILL_ROLLOUT_VARIANT_FORM] if SKILL_ROLLOUT_VARIANT_FORM else ["key", "id", "uuid"]
    return [{"rollout_decision": "variant", "rollout_variant": forms[f]} for f in order if forms[f] is not None]


def connect(env_name: str):
    """Return (api, E, pid, env_key). Prints no secrets."""
    from fslib import Api, out, register_secret

    if env_name not in ("Development", "Production"):
        sys.exit(f"environment must be Development or Production, got {env_name!r}")
    key = os.environ.get("FS_EXPERIMENT_ADMIN_KEY")
    if not key:
        sys.exit("FS_EXPERIMENT_ADMIN_KEY not set")
    register_secret(key)
    api = Api(key)
    pid = os.environ.get("FS_EXPERIMENT_PROJECT_ID") or "56666"
    envs = {e["name"]: e for e in api.results(f"environments/?project={pid}")}
    if env_name not in envs:
        out("environment not found:", env_name)
        sys.exit(1)
    ek = envs[env_name]["api_key"]
    register_secret(ek)
    return api, f"environments/{ek}", pid, ek


def find_flag(api, pid, name: str):
    fs = [f for f in api.results(f"projects/{pid}/features/?search={name}") if f["name"] == name]
    return fs[0] if fs else None


def refresh_fresh(api, E, eid, out, max_wait_s: int = 900):
    """POST results/refresh/ (throttled to once per 5 min: retry on 429), then poll until as_of is fresh.
    Returns (results_response, fresh_bool). An ended experiment refuses refresh (400): its results are final."""
    since = datetime.now(timezone.utc)
    deadline = time.time() + max_wait_s
    accepted = False
    while True:
        code, d = api.call("POST", f"{E}/experiments/{eid}/results/refresh/", quiet=True)
        if code < 300:
            accepted = True
            break
        if code == 429 and time.time() < deadline:
            out("refresh throttled (429); waiting 60s")
            time.sleep(60)
            continue
        out(f"refresh -> {code} {str(d)[:200]}")
        break
    r = None
    for _ in range(12):
        _, r = api.call("GET", f"{E}/experiments/{eid}/results/", quiet=True)
        if not accepted or is_fresh(results_as_of(r), since):
            break
        time.sleep(20)
    if accepted:
        fresh = bool(r) and is_fresh(results_as_of(r), since)
    else:
        fresh = bool(r) and bool((r.get("results") or {}).get("is_final"))
    return r, fresh
