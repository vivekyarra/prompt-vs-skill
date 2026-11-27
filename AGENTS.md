# AGENTS.md

Handoff is a pre-registered Flagsmith experiment: does Flagsmith's official setup prompt or an Agent Skill get coding agents to a correctly wired A/B test more often? This repo holds the runner, the grader, both handoffs, the analysis and the results.

## Layout

| Path | What it is |
|---|---|
| `runner/` | Orchestrates one trial: assign variant via Flagsmith, run the agent, grade, report |
| `grader/` | Playwright + mitmproxy judge with a local Flagsmith emulator (`grader/mock.py`) |
| `skill/` | Variant B Agent Skill: `flagsmith-ab-test/` (v1, frozen) and `flagsmith-ab-test-v2/` |
| `prompt/` | Variant A, Flagsmith's official prompt, unmodified |
| `brief/` | The task brief both variants receive |
| `apps/` | Sample apps, reference solutions and broken fixtures for grader self-tests |
| `analysis/` | Trial-log analysis, Flagsmith cross-check, figures |
| `ops/` | Flagsmith setup, snapshot, rollover and rollout scripts (run through `ops.yml`) |
| `data/` | Collected trial records and Flagsmith results snapshot |
| `docs/` | Architecture, grader, fairness, failure labels, setup, contribution draft |

## Commands

```bash
ruff check .
pytest runner/tests tests analysis -q            # unit tests, no credentials
pytest grader -m grader -q                       # grader self-tests (Node 22, Chromium, mitmproxy)
python scripts/secret_scan.py                    # must pass before every commit
python -m runner --dry-run --scripted-agent-apply-reference --trial-id trial-readme-1 --out-dir out
python analysis/analyze.py --trials data/trials.jsonl --flagsmith-json data/flagsmith_primary_results.json --out RESULTS.md
```

Setup details: `docs/setup.md`.

## Rules

- **No secrets.** Never commit keys, tokens or `.env` files. `.env.example` lists names only. Run `python scripts/secret_scan.py`.
- **Frozen paths.** Do not change `grader/`, `skill/flagsmith-ab-test/`, `prompt/` or `brief/`. They were frozen before the production run, and any change would invalidate the comparison. A grader bug is fixed only in a way that cannot change a pass condition, and is documented in `EXPERIMENT.md`.
- **Pre-registration.** `EXPERIMENT.md` is append-only: add entries, never rewrite or delete them.
- **Numbers.** Every number in prose comes from `RESULTS.md`, `data/`, or `EXPERIMENT.md`. Do not edit raw `data/*.jsonl`. Regenerate `RESULTS.md` and the figures with `analysis/analyze.py`.
- **Wording.** Use "stub", "scripted", "placeholder" and "local emulator" for test doubles.
- **Pushes.** Work on a branch. Never push to `main` directly.
