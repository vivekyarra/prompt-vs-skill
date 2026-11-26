# Blockers (human-only checkpoints, see docs/BUILD_SPEC.md section 5)

| ID | Task | Status |
|---|---|---|
| H1 | Flagsmith Cloud account + org, managed warehouse for Experimentation | DONE (verified live: Flagsmith-managed warehouse connection exists and received events in Development) |
| H2 | Create projects `handoff-experiment`, `handoff-sandbox` (+ Production/Development envs) | DONE (verified live 2026-11-26: `handoff-experiment` id 56666 in org "Yarra's Org"; `handoff-sandbox` id 56668 in org "Handoff Sandbox" 42328) |
| H3 | Create API credentials (experiment server key, sandbox keys/admin key) | DONE (experiment server keys, experiment admin key, sandbox keys all verified live) |
| H4 | Model API key with spend limit: Anthropic key (default agent) OR Nebius Token Factory key (`HANDOFF_AGENT=opencode`, secret `NEBIUS_API_KEY`) | PENDING |
| H5 | Add keys as GitHub Actions secrets (names in `.env.example`) | PENDING |
| H6 | Approve pilot cost and final sample target | PENDING (after pilot) |
| H7 | Start experiment in dashboard if CLI/API cannot | NOT NEEDED: `POST .../experiments/<id>/start/` works via API (verified live; both experiments running) |
| H8 | Record and upload demo video | PENDING |
| H9 | Post the issue/PR on Flagsmith's GitHub | PENDING |
| H10 | Register, star Flagsmith, submit form | PENDING |

## Resolved: admin credential for the experiment project

`FS_EXPERIMENT_ADMIN_KEY` (Master key, "Yarra's Org") was added; discovery and setup ran live (details in `docs/verified-facts.md` section 10). The warehouse is a Flagsmith-managed connection per environment and accepts events; no paid plan action was needed.

## Build status (what is done without credentials)

Done and merged to `main` with green CI: scaffold, sample apps (3 baselines, references, generated broken set),
grader (C1-C7, mock and mitmproxy modes, self-tests on reference and broken apps), Agent Skill, task brief,
verbatim official prompt, trial runner (unit tested, `--dry-run`), analysis scripts, workflows, doc drafts.

Not done, and cannot be done by the builder: everything that needs a live Flagsmith account or Anthropic key
(H1-H5), so Phases 7, 9, 10, 11 (real data), 12, and the video, contribution post and submission (H8-H10).
No results exist yet and none have been invented; `RESULTS.md` is not committed until real data exists.

## Running on Nebius (open-weight model) instead of Anthropic

The runner has a second backend, OpenCode, for any OpenAI-compatible endpoint (details and what is verified: `docs/verified-facts.md` section 9). **The live path has never been run against Nebius**; do step 1-2 before spending on the pilot.

1. Pick the model from your own account (model ids and prices are NOT verified in the repo):
   ```
   curl -s https://api.tokenfactory.nebius.com/v1/models?verbose=true -H "Authorization: Bearer $NEBIUS_API_KEY" \
     | python3 -c "import sys,json; [print(m['id'], m.get('context_length'), m.get('supported_features'), m.get('pricing')) for m in json.load(sys.stdin)['data']]"
   ```
   Choose a coding model that lists tool/function calling. Pricing strings are per token: multiply by 1,000,000 for `HANDOFF_PRICE_IN_PER_M` / `HANDOFF_PRICE_OUT_PER_M`.
2. Live smoke run (one real trial; needs the Nebius key AND the Flagsmith credentials H1-H3, because the runner records a real exposure). With the dry-run/fake flags no model is called, so they prove nothing about Nebius:
   ```
   npm i -g opencode-ai@1.19.6
   export HANDOFF_AGENT=opencode HANDOFF_MODEL='<id from step 1>' NEBIUS_API_KEY=... \
          HANDOFF_PRICE_IN_PER_M=<x> HANDOFF_PRICE_OUT_PER_M=<y> HANDOFF_MAX_TURNS=60 HANDOFF_MAX_TOKENS=5000000
   export FS_EXPERIMENT_SERVER_KEY=... FS_SANDBOX_CLIENT_KEY=... FS_SANDBOX_SERVER_KEY=... FS_SANDBOX_ADMIN_KEY=... FS_SANDBOX_PROJECT_ID=...
   python -m runner --trial-id trial-smoke-1 --out-dir out-smoke
   ```
   Check `out-smoke/trial_record.json`: `agent` is `opencode`, `turns` and `input_tokens`/`output_tokens` are non-zero (zero tokens means the endpoint did not return `usage`, so the token limit would never trigger: stop and fix), `cost_usd` is plausible, and `out-smoke/agent_output.jsonl` shows tool calls. Run it for a `skill` trial too (try other ids until the variant is `skill`) and confirm a `skill` tool call with the skill name appears.
3. In GitHub: secret `NEBIUS_API_KEY`; variables `HANDOFF_AGENT=opencode`, `HANDOFF_MODEL`, `HANDOFF_PRICE_IN_PER_M`, `HANDOFF_PRICE_OUT_PER_M`, optional `NEBIUS_BASE_URL`, `HANDOFF_CONTEXT_LIMIT`, `HANDOFF_OUTPUT_LIMIT`. Leave `ANTHROPIC_API_KEY` unset.
4. Budget: with ~$50, size the pilot from the smoke run's `cost_usd` before choosing the sample target; `HANDOFF_MAX_TOKENS` caps a single trial.

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

Setup notes for the credentialed phases:
- Create GitHub **environments** `development` and `production`; each stores its own `FS_EXPERIMENT_SERVER_KEY`
  (the same secret name), plus the shared secrets/variables from `.env.example`. Also set the variable `HANDOFF_MODEL`.
- The repository default branch must be `main` (Settings > Branches) or `trials.yml` cannot be dispatched and
  `collect.yml` will not trigger.
