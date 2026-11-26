# Handoff: Prompt vs Skill

A pre-registered Flagsmith experiment that asks which handoff gets coding agents to a correctly wired Flagsmith A/B test more often: Flagsmith's official setup prompt or an Agent Skill.

## 1. The question and why it matters

Every devtool now onboards AI agents, either with a prompt to paste or with a skill to install. Nobody has measured which works. For Flagsmith, and for any devtool, this is a live product decision. Handoff answers it with a real Flagsmith experiment and a ground-truth grader instead of opinion.

## 2. The result

**Pending.** No trials have been analysed yet. This paragraph is filled from [`RESULTS.md`](RESULTS.md) once it contains real data, and will report an inconclusive outcome as inconclusive.

## 3. How it works

```
GitHub Actions (matrix: N trials in parallel, max-parallel limited)
 └── one job = one trial
      1. Runner picks a sample app at random (seeded by trial ID) → stack trait
      2. Runner asks Flagsmith (experiment project) for onboarding_method
         with identity = trial ID  → exposure recorded
      3. Runner prepares a clean workspace:
           - copies the sample app
           - Variant A: writes official prompt + task brief as the agent's instruction
           - Variant B: installs the Agent Skill into the agent's skill folder,
                        writes a short trigger instruction + the same task brief
      4. Runner starts the coding agent headlessly with fixed limits
         (sandbox Flagsmith credentials only)
      5. Agent finishes or hits a limit → runner records turns, tokens, duration
      6. Grader runs the agent's app behind an intercepting proxy,
         simulates visitors, checks C1–C6 from recorded traffic
      7. Runner sends events to Flagsmith (experiment project), identity = trial ID:
           - integration_verified if all of C1–C6 pass
           - over_budget if a limit was hit
         and flushes events before exit
      8. Runner writes the trial record (JSON) as an artifact
      9. Cleanup: delete the trial's flag from the sandbox project
```

More detail: [`docs/architecture.md`](docs/architecture.md).

## 4. How Flagsmith is used

- **Flag:** `onboarding_method`, multivariate. Control `prompt`, variation `skill`. 100% of trials enrolled, 50/50.
- **Exposure:** recorded when the runner asks for the flag with the trial ID as identity, before the agent starts (`runner/`).
- **Metrics:** `integration_verified` (primary, sent only when checks C1-C6 pass) and `over_budget` (guardrail).
- **Experiment:** Flagsmith computes exposures, rates, credible interval and win probability. Our own analysis in `analysis/` is only a labelled cross-check.
- **Rollout:** if the pre-registered decision rule picks a winner, the same flag is set to 100% for it. If inconclusive, the flag stays 50/50.

## 5. The grader and its checks

The grader runs the agent's modified app behind an intercepting proxy, simulates visitors with Playwright, and checks C1-C6 from recorded Flagsmith traffic. C7 is a diagnostic (server key exposed in client code) and does not affect the primary metric. Check definitions live with the grader (`grader/`, `docs/grader.md`).

## 6. Reproduce a trial

Prerequisites: Python 3.12, Node 20, Playwright Chromium, mitmproxy, the Flagsmith CLI, Claude Code (`npm i -g @anthropic-ai/claude-code`), and two Flagsmith projects (experiment and sandbox).

Environment variables (names only, see `.env.example`): `FS_EXPERIMENT_SERVER_KEY`, `FS_SANDBOX_CLIENT_KEY`, `FS_SANDBOX_SERVER_KEY`, `FS_SANDBOX_ADMIN_KEY`, `FS_SANDBOX_PROJECT_ID`, `ANTHROPIC_API_KEY`, `HANDOFF_MAX_TURNS`, `HANDOFF_MAX_TOKENS`; optional alternative agent (OpenCode + Nebius): `HANDOFF_AGENT`, `HANDOFF_MODEL`, `NEBIUS_API_KEY`, `NEBIUS_BASE_URL`, `HANDOFF_PRICE_IN_PER_M`, `HANDOFF_PRICE_OUT_PER_M` (see `docs/BLOCKERS.md`).

```bash
pip install playwright mitmproxy requests flagsmith
python -m playwright install chromium
python -m runner --trial-id trial-local-1 --out-dir out      # one full trial
python -m grader --help                                      # grade a workspace on its own
python analysis/analyze.py --trials data/trials.jsonl --out RESULTS.md
```

A successful run writes a trial record (JSON) and `diff.patch` into `out/`, and sends `integration_verified` and/or `over_budget` to the experiment project. Reproduction from a fresh clone is verified in CI: TBD (pending the first green fresh-clone run).

## 7. Run the full experiment yourself

1. Create the `development` and `production` GitHub environments with the secrets and variables above.
2. Actions tab, run **trials** with `count` and `environment` (start with 3 in `development`).
3. **collect** runs after each batch and appends new records (deduplicated by trial ID) to `data/trials.jsonl` on the `data` branch. It never pushes to `main`.
4. Run `python analysis/analyze.py` on the collected data and `python analysis/crosscheck.py --flagsmith-json flagsmith.json` to compare with the Flagsmith dashboard.

Follow the stopping rule in `EXPERIMENT.md`: do not stop because the result looks good.

## 8. Repository map

| Path | Purpose |
|---|---|
| `apps/` | Sample apps the agents modify (React, Node, Python) |
| `grader/` | Playwright + mitmproxy grader |
| `skill/` | Variant B Agent Skill |
| `prompt/` | Variant A official prompt, unmodified |
| `brief/` | Task brief shared by both variants |
| `runner/` | One-trial orchestrator |
| `analysis/` | `analyze.py`, `crosscheck.py`, `collect.py` and tests |
| `.github/workflows/` | `trials.yml`, `collect.yml`, `ci.yml` |
| `docs/` | Architecture, demo script, contribution draft, build spec |
| `EXPERIMENT.md`, `RESULTS.md` | Pre-registration and results |

## 9. Judging criteria map

| Criterion | How Handoff meets it | Evidence |
|---|---|---|
| Use of Flagsmith | Flagsmith assigns every trial's variant, records exposures, receives grader verdicts, computes the winner, and ships it with the same flag. | `runner/`, Flagsmith dashboard, `RESULTS.md` |
| Impact | Answers a live product question for Flagsmith and every devtool; specific fixes for Flagsmith's onboarding. | `docs/flagsmith-contribution.md` |
| Creativity | A head-to-head experiment of prompt vs skill for agent onboarding, with a ground-truth grader. | This README, video |
| Demo video | Problem, build, Flagsmith fit. | Video link (TBD) |
| Track 01: one experiment done well | One flag, one primary metric, one guardrail. | `EXPERIMENT.md` |
| Track 01: clear hypothesis | Pre-registered before the full run. | `EXPERIMENT.md` commit timestamp |
| Track 01: versions behind a flag | `onboarding_method`: `prompt` / `skill`. | Flagsmith dashboard |
| Track 01: metric from real events | `integration_verified` comes only from real grader verdicts on real agent runs. | `grader/`, `data/trials.jsonl` |
| Track 01: results you can explain | Credible interval, decision rule, sanity checks, failure breakdown, limitations. | `RESULTS.md` |

## 10. Limitations

One agent (Claude Code) and one model. Small sample apps rather than real codebases. The task brief replaces interactive answers a human would give. Results may differ for other agents, models and real-world codebases. Runner-error trials are reported separately and excluded from pass-rate denominators in our own cross-check.

## 11. Links

- Demo video: TBD
- Pre-registration: [`EXPERIMENT.md`](EXPERIMENT.md)
- Results: [`RESULTS.md`](RESULTS.md)
- Hackathon page: https://wemakedevs.org/hackathons/flagsmith
- Flagsmith issue/PR: TBD

## 12. Built for

Built for Toggle Wars: The Flagsmith Experimentation Hackathon (WeMakeDevs × Flagsmith), Track 01.
