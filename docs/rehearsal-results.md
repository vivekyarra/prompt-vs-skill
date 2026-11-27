# Rehearsal results (2026-11-27)

All live calls ran through `.github/workflows/ops.yml` with the **development** environment (Production was not touched; the one production run only scanned artifacts for secret values and printed counts). Scripts: `ops/rehearsal_exp2.py`, `ops/rehearsal_localeval.py`, `ops/scan_secrets.py`, `ops/flag_creation_check.py`. `ops.yml` on this branch also gets `GITHUB_TOKEN` and `permissions: contents/actions: read` (needed by the scan); that change is only on `feat/ops-rehearsals`.

## 1. Second-experiment rehearsal: PASS

**Stopping an experiment (was UNVERIFIED, now verified).** `POST environments/<env key>/experiments/<id>/complete/` ends it. Discovered by `OPTIONS` on candidate paths (`stop/`, `end/`, `finish/`, `archive/` -> 404; `complete/` and `pause/` exist). `complete/` with an empty body returns `400 {"rollout_decision": ["This field is required."]}`; `OPTIONS` lists the field as a `choice` but does not enumerate the choices; the error for a wrong value does not list them either. A candidate list was tried (400s mutate nothing): `no_decision, none, no_winner, inconclusive, keep_control` were all rejected, **`rollout_decision=control` was accepted** (200). Result: experiment 727 `status: completed`, `ended_at` 2026-11-27T07:16:20Z, `rollout_decision: control`, `rollout_variant: null`. Other valid values were not probed (the first valid one ended the experiment); the pattern suggests the variant key (`skill`) plus `rollout_variant` is the ship-variant form (UNVERIFIED).

**Create + start #2.** Same body as the official prompt, same flag (306199) and same Development metrics (744 `integration_verified`, 745 `over_budget`), name "Handoff pilot 2": `POST .../experiments/` -> 201 (id **1058**), `POST .../1058/start/` -> 200 `status: running`. The flag was not locked by the ended experiment, and existing metrics are reusable.

**Exposures.** `get_experiment_flag` for `rehearsal-1..20` (traits `stack=react`, events enabled, then `flush_events`): all 20 returned `in_experiment=True` with `experiment.id == 1058`. Values: **13 `prompt` (variant `control`), 7 `skill` (variant `skill`)**: both variants occur. The warehouse total was 61 before the local-evaluation test in section 2.

**Counts.**

| Read | Experiment 1058 (new) | Experiment 727 (old) |
|---|---|---|
| Before any exposure (refresh, as_of 07:17:38Z, new experiment seconds old; old identities `setup-check-*` and 24 old exposures existed in the environment) | 0 / 0 (no identities, no metric rows) | n/a |
| After the 20 exposures (as_of 07:23:36Z) | **control 13, skill 7**, metrics 744/745: n=13/7, sum 0 | frozen: control 11, skill 13, metric 744 sum 8/9, as_of = ended time 07:16:20Z |

**No leakage in either direction:** the new experiment started at zero (old exposures and the 17 old conversions do not appear), counted exactly the 20 new identities (13+7), and the old experiment's results are final and unchanged (its as_of stays at its end time, and refresh on an ended experiment returns 400). Not tested: re-exposing an old identity (`setup-check-1`) in the new experiment (it would very likely count as new because exposures are per experiment). Refresh throttle confirmed: a second refresh within 5 minutes returns `429`; the next one 5+ minutes later returns 202 and updates `as_of`.

**What the runner sees when NO experiment is running** (experiment 727 completed, nothing running; identities `rehearsal-norun-1..4`): `get_experiment_flag` returns `Flag(enabled=True, value='prompt', variant='control', experiment.in_experiment=False)` for every identity; no exposure event is emitted. So the runner's existing check (`in_experiment` false -> "identity not enrolled in a running experiment") rejects it; for a rollout mode the variant must come from `value` (all `prompt` here because the skill option has 0% allocation outside an experiment; after `complete` with decision `control` the flag serves control to everyone). Note `variant` is `control` and `experiment` metadata is present but `in_experiment` is `False`.

## 2. Local evaluation live check: YES, exposures are recorded

SDK source (flagsmith 6.7.0): `get_experiment_flag` -> `get_identity_flags(identifier, traits)` and emits `$flag_exposure` (value = `flag.variant`, `metadata={"experiment_id": ...}`) iff the flag is a `Flag`, enabled, `flag.experiment.in_experiment` and `flag.variant` set. `local_evaluation.py` strips experiment metadata only for **environment-level** flags (`dataclasses.replace(..., experiment=None)`, docstring: "only an identity is enrolled in one"); the **identity** path `_get_identity_flags_from_document` keeps `metadata.experiment` from the environment document, so identity evaluations carry `in_experiment`.

Live (Development server key, `enable_local_evaluation=True, enable_events=True`, experiment 1058 running): `rehearsal-le-1..6` -> `experiment=(1058, True)`, values prompt/skill/prompt/skill/prompt/skill. Warehouse events rose 61 -> 68 (+6 from `get_experiment_flag`, +1 from one manual `track_exposure_event`). After refresh (as_of 07:30:46Z) experiment 1058 showed **control 16, skill 11 = 27 identities = 20 + 6 + 1**: every local-evaluation exposure was counted by Flagsmith.

Answer: **yes** for correct local-evaluation integrations that use `get_experiment_flag` (identity path) with events enabled. (Caveat: environment-level reads such as `get_environment_flags()` carry no experiment and emit nothing. Only the Python SDK was tested live; Node's local-evaluation path was not.) So a grader flag (trial 12, node, local evaluation) is **not inherently** an artefact of real Flagsmith: real Flagsmith would have recorded the exposure; the failure there is the grader mock not implementing the environment-document endpoint.

## 3. Secret scan: PASS (no secret values found)

Run in development and again in production (production secrets). Scanned the artifacts of the last 5 completed `trials.yml` runs (45925699686, 45914099371, 45912277670, 45907896688, 45904063529: 80 trials, 4 files each, 320 text files) plus `data/trials.jsonl` on the `data` branch (210,651 bytes, 138 lines). `data/pilot.jsonl` does not exist on the `data` branch (404; the branch holds only `data/trials.jsonl`). Artifact contents are exactly `agent_output.jsonl, diff.patch, grader_result.json, trial_record.json`.

| Check | Count |
|---|---|
| Files containing the value of FS_EXPERIMENT_SERVER_KEY, FS_SANDBOX_CLIENT_KEY, FS_SANDBOX_SERVER_KEY, FS_SANDBOX_ADMIN_KEY, FS_EXPERIMENT_ADMIN_KEY or NEBIUS_API_KEY (dev values; prod values in the production run) | **0 of 321** |
| Files matching `sk-[A-Za-z0-9]{20,}` | 0 |
| Files matching `ser\.[A-Za-z0-9]{20,}` | 1: `trial-45907896688-1/agent_output.jsonl` (2 matches, 1 distinct string, length 24). Real server keys here are 26 characters and the string equals none of the environment's secrets, so it is almost certainly the grader's fake `ser.` key echoed by the agent; not a leak of a real key (not provable beyond that, since only values in the environment can be compared) |
| `diff.patch` files that touch a `.env*` path | 22 of 80 (tracked `.env*` files exist in the apps or were added); none contains a secret value (sandbox client key included) |

Conclusion: agent-written `.env.local` containing the real sandbox client key did not reach any scanned artifact (untracked files are excluded from `diff.patch`; tracked `.env*` diffs held no secret). Limits: only the 5 most recent completed runs were scanned; scanning cannot detect a secret that has been transformed (base64, split); runs still in progress at scan time were excluded.

## 4. Flag creation check: `deleted` proves a flag existed, not who created it

Code: `AdminApiCleaner.delete_flag` (runner/flags.py) lists `GET projects/{id}/features/?search=<name>`, filters for an **exact name** match, returns `not_found` if none, otherwise issues `DELETE` per match and returns `deleted` (HTTP errors give `error: ...`). It runs in the `finally` block of every trial, for every flag name derived from the trial id (`join_button_<trial_suffix>`), including trials that crashed. So `deleted` means: at cleanup a sandbox feature with exactly this trial-unique name existed and the DELETE succeeded. It cannot be `deleted` if no such flag existed. The agent is the only actor with the sandbox admin key that creates features (runner and grader do not create it; names are trial-unique), so `deleted` is strong evidence that the agent created the flag **by that name**, but it does not prove: the flag was correct (type, variation), that it was created during this trial rather than leftover from a retry of the same trial id (rerun jobs reuse ids), or that it was in use by the app. `not_found` does not prove the agent never created it: the agent can delete its own flag, or use a different name.

Live read-only list of the sandbox project (56668): 8 features (a leftover `show_demo_button` from 2026-11-26 18:04, and 7 trial-style flags created 07:11-07:23 by trials running concurrently, i.e. cleanup had not yet happened). The cleaner-style search for an absent name returned 0 results (-> `not_found`), for an existing name returned exactly that name. List response is a single page (`count`, `next`, `results`), so the exact-name filter is sound.

Data (`data/trials.jsonl`, 138 trials): `cleanup_status=deleted` 119 (83 passed, 36 failed), `not_found` 19 (all failed). Failed-but-`deleted` trials show the flag was created even when the integration failed, so `deleted` is not the same as success.

**Recommendation for an honest `flag_created` field (describe only, runner code not changed):** record it before cleanup, separately from `cleanup_status`: in `finally`, before deleting, call the same list endpoint and set `flag_exists_at_cleanup = bool(exact-name match)` (plus the feature's `type`, `created_date` and, if wanted, its variation count). Use `created_date >= trial start time` to rule out a leftover from an earlier attempt with the same id (or delete any pre-existing flag of that name in the pre-agent step and record that). Optionally also scan the agent's API traffic (grader proxy, or the agent transcript) for a `POST .../features/` with that name as independent confirmation. Report `flag_created` as `true` (exists and created after trial start), `false` (not found), or `unknown` (list/delete error), and keep `cleanup_status` as a pure cleanup outcome.
