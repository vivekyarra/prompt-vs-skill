# Blockers (human-only checkpoints, see docs/BUILD_SPEC.md section 5)

| ID | Task | Status |
|---|---|---|
| H1 | Flagsmith Cloud account + org, managed warehouse for Experimentation | PENDING |
| H2 | Create projects `handoff-experiment`, `handoff-sandbox` (+ Production/Development envs) | PENDING |
| H3 | Create API credentials (experiment server key, sandbox keys/admin key) | PENDING |
| H4 | Anthropic API key with spend limit | PENDING |
| H5 | Add keys as GitHub Actions secrets (names in `.env.example`) | PENDING |
| H6 | Approve pilot cost and final sample target | PENDING (after pilot) |
| H7 | Start experiment in dashboard if CLI/API cannot | PENDING, probably not needed: official docs start it via `POST ./experiments/<id>/start/` through `flagsmith api` (UNVERIFIED live, needs H1-H3; see docs/verified-facts.md section 5) |
| H8 | Record and upload demo video | PENDING |
| H9 | Post the issue/PR on Flagsmith's GitHub | PENDING |
| H10 | Register, star Flagsmith, submit form | PENDING |

## Build status (what is done without credentials)

Done and merged to `main` with green CI: scaffold, sample apps (3 baselines, references, generated broken set),
grader (C1-C7, mock and mitmproxy modes, self-tests on reference and broken apps), Agent Skill, task brief,
verbatim official prompt, trial runner (unit tested, `--dry-run`), analysis scripts, workflows, doc drafts.

Not done, and cannot be done by the builder: everything that needs a live Flagsmith account or Anthropic key
(H1-H5), so Phases 7, 9, 10, 11 (real data), 12, and the video, contribution post and submission (H8-H10).
No results exist yet and none have been invented; `RESULTS.md` is not committed until real data exists.

## Runbook once H1-H5 are done

1. Verify the UNVERIFIED items in `docs/verified-facts.md` against the live service (CLI auth, metric and
   experiment request bodies, experiment start, real identities response shape).
2. Create the experiment per `docs/BUILD_SPEC.md` Phase 7; record IDs in `EXPERIMENT.md`.
3. Run the pilot: Actions > `trials` with count=10, environment=development; then `collect`.
4. Freeze model, `HANDOFF_MAX_TURNS`, `HANDOFF_MAX_TOKENS`, sample target, max-parallel in `EXPERIMENT.md`
   and commit before the full run (H6).
5. Full run in batches of 50 with environment=production; run `analysis/crosscheck.py` per batch.
6. `python analysis/analyze.py --trials data/trials.jsonl --out RESULTS.md`, then fill the README result paragraph.

Known pitfall found in Phase 0: the official prompt's Python advice (`max_buffer_items=1`) can drop the
exposure when `get_experiment_flag` is immediately followed by `track_event` (flagsmith 6.7.0, 6 of 6 runs in
`spike/py_buffer_race.sh`). Expect Variant A failures on C2 for Python; report it as a finding.
