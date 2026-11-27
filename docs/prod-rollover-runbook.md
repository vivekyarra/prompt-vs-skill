# Production rollover runbook

Order of operations after the primary experiment (728 `Handoff: Prompt vs Skill`) has reached its target or the
stop line. Every step runs through `ops.yml` (workflow dispatch on `main`) or `trials.yml`. Run the steps strictly
in order and wait for each to finish. Do not run any of this while the primary is still running trials.

`ops.yml` splits `args` on spaces and has no quoting, so **underscores in an experiment name stand for spaces**
(`Handoff:_Prompt_vs_Skill` = `Handoff: Prompt vs Skill`). Scripts: `ops/snapshot_results.py`,
`ops/rollover_experiment.py`, `ops/rollout_winner.py` (helpers in `ops/rolllib.py`). All of them are on
`feat/prod-rollover` until merged; use `ref=main` once merged, else `ref=feat/prod-rollover`.

Common `ops.yml` inputs: `environment=production`, `ref=main`.

## 1. Snapshot the primary (last read of the primary; it contains the inference block)

- `script=ops/snapshot_results.py`, `args=Production`  (default experiment: `Handoff: Prompt vs Skill`)
- Refreshes results (waits through the 5-minute throttle, up to 15 min), prints `SNAPSHOT_JSON: {...}` with the
  full payload including `inference`, `as_of`, experiment id/name/status and a UTC timestamp, plus the warehouse
  counters. Check `"fresh":true`. Save the JSON line from the job log (`gh api repos/vivekyarra/prompt-vs-skill/actions/jobs/<id>/logs`)
  into the repo/data record before continuing: after step 2 the primary is frozen.
- Stopping rule: take this snapshot only when the primary is finished (target 220 reached or stop line passed).

## 2. Roll over to the replication experiment (MUTATING)

- `script=ops/rollover_experiment.py`, `args=Production Handoff:_Prompt_vs_Skill Handoff:_Replication`
  (the new name is free to choose; it must differ from the old one; use the same string in steps 4 and 5).
- What it does: prints the old experiment's `as_of`; completes it with `{"rollout_decision": "control"}`;
  creates the new experiment on flag `onboarding_method` (metrics `integration_verified` then `over_budget`,
  100% enrolment, skill 50%); starts it; verifies the served weights are 50/50 `prompt`/`skill` and that the
  experiment is `running`; prints `NEW EXPERIMENT ID: <id>`. Exit code 0 means PASS.
- Idempotent: re-running with the new experiment already running changes nothing and only re-verifies. A new
  experiment stuck in `created` (partial failure) is started.
- Between steps 2 and 3 the flag has exactly one running experiment; nothing else needs touching.
- Record the new experiment id in `EXPERIMENT.md`.

## 3. Dispatch the replication trials

`trials.yml` (workflow dispatch on `main`): `environment=production`, `assign=flagsmith`, `stage=replication`,
`count=<batch size>`, other inputs (model, max_turns, max_tokens, prices) at the frozen defaults. Repeat in
batches until 220 replication trials have completed (or the stop line, 28 Nov 2026 12:00 IST). Records land with
`stage: "replication"`.

## 4. Snapshot the replication

- `script=ops/snapshot_results.py`, `args=Production Handoff:_Replication`
- Same output and checks as step 1. Save the `SNAPSHOT_JSON` line.

## 5. Roll out the winner (MUTATING)

The DECISION uses the primary alone (EXPERIMENT.md); the winner is the variant that decision names.

- `script=ops/rollout_winner.py`, `args=Production prompt`  or  `args=Production skill`
- Completes the running experiment on `onboarding_method`: `prompt` -> `{"rollout_decision":"control"}`;
  `skill` -> `{"rollout_decision":"variant","rollout_variant":<skill option id>}`. Then evaluates
  `get_identity_flags` for 5 fresh identities (`rollout-verify-*`), retrying for ~3 minutes because a change takes
  a few seconds to propagate (the first attempt after completion often still shows the old mix). Prints
  `ROLLOUT VERIFY (<winner>): PASS` or `FAIL`; exit code 0 = PASS. Re-running with nothing running only verifies.

## 6. Five confirmation trials

`trials.yml`: `environment=production`, `assign=rollout`, `stage=rollout`, `count=5`. These send no Flagsmith
events and are excluded from both analyses.

## Verified in Development (2026-11-27, throwaway flags `rollout_probe_<n>`, experiments `rollover-test-*`)

- `complete/` accepts `{"rollout_decision":"control"}`; `skill` is **not** a valid `rollout_decision` choice.
  Shipping a variation is `{"rollout_decision":"variant","rollout_variant":<integer option id>}`
  (`rollout_variant` as the key string `skill` is rejected: "A valid integer is required").
- After `variant`, 10/10 identities got `skill`; after `control`, all got `prompt`, each after a short delay.
- Rollover (complete -> create -> start -> 50/50) and its idempotent rerun, both rollout directions, and the
  snapshot (timestamps intact, inference block present) all passed (`ops/rollover_selftest.py probe|full`).
  Throwaway experiments and flags were deleted afterwards (`DELETE` on experiments and features returns 204).

## Not verified / caveats

- Nothing here has been run against Production. In Production the old experiment's `complete/` with `control`
  is the same call as in the Development rehearsal; the Production option id is looked up at run time.
- 50/50 is checked from the experiment's `experiment_rollout` (what the experiment serves), not by sampling.
  The project features API only shows the option's default allocation (0 outside an experiment), and the
  environment feature state shows 0 for `skill` while the experiment runs, so those two are informational.
- Whether the metrics' list order makes `integration_verified` the dashboard's primary metric is unknown (the
  API has no primary field); the new experiment uses the same order as the primary.
- Batch size for step 3 is not fixed here; use whatever the primary used. UNRESOLVED: none.
