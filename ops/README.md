# ops/

Scripts run through `.github/workflows/ops.yml` with an environment's secrets. They print ids, statuses and counts, never secret values.

| Script | Purpose |
|---|---|
| `setup_experiment.py` | Create the flag, the two metrics and the experiment idempotently |
| `snapshot_results.py` | End-of-run snapshot of the experiment results, including Flagsmith's inference |
| `exp_counts.py` | Read exposure and conversion counts |
| `backfill_events.py` | Send late `integration_verified` events for corrected verdicts |
| `rollover_experiment.py` | End an experiment and start a second one on the same flag |
| `rollout_winner.py` | End the running experiment with a rollout decision and verify the winner is served |
| `sandbox_audit.py`, `scan_secrets.py` | Sandbox project audit and a secret-name scan of workflow logs |
| `fslib.py`, `rolllib.py`, `rollover_selftest.py` | Shared helpers and a self-test for the rollover forms |
