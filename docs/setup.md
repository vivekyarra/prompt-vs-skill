# Setup

Two ways in: reproduce one trial with no credentials, or run the whole experiment from GitHub Actions.

## Prerequisites

| Tool | Version | Used for |
|---|---|---|
| Python | 3.12 | runner, grader, analysis |
| Node | 22 (22.21 or newer for grading Node apps behind the proxy) | sample apps and the grader's app runs |
| Playwright Chromium | `playwright==1.63.0` | the grader's simulated visitors |
| mitmproxy | current | answers `*.flagsmith.com` from the local emulator |
| OpenCode | 1.19.6 (`npm i -g opencode-ai@1.19.6`) | the agent, real runs only |
| Flagsmith CLI | current | the agent and `ops/`, real runs only |

```bash
pip install playwright==1.63.0 mitmproxy requests flagsmith flask pytest pyyaml ruff
python -m playwright install chromium
```

Claude Code is also supported (`HANDOFF_AGENT=claude`, `npm i -g @anthropic-ai/claude-code`) but it is not the agent of this experiment.

## 1. Reproduce one trial without credentials

No model, no Flagsmith calls. A scripted agent copies the reference integration into a sample app, and the real grader grades it.

```bash
python -m runner --dry-run --scripted-agent-apply-reference --trial-id trial-readme-1 --out-dir out
python -m runner --dry-run --trial-id trial-readme-2 --out-dir out2     # untouched app: fails C2
```

The first command passes C1 to C6 and records `integration_verified` as the only event. The second leaves the app untouched, so it fails C2 (no exposure). Each run writes `trial_record.json` and `diff.patch` to its output directory. Without mitmproxy installed the grader reports `C1: mitmdump not found`.

Other credential-free checks:

```bash
python scripts/demo_grader.py                 # grader on a correct vs a broken app
pytest runner/tests tests analysis -q         # unit tests
pytest grader -m grader -q                    # grader self-tests (Node, Chromium, mitmproxy)
ruff check . && python scripts/secret_scan.py
```

## 2. Run the experiment from GitHub Actions

Create two Flagsmith projects (experiment and sandbox) and the `development` and `production` GitHub environments with the secrets and variables below. Then, from the Actions tab:

1. **preflight** (environment): checks that the credentials work and prints pricing. No secret is printed.
2. **ops** (environment, ref, script, args): runs one script from `ops/` with that environment's secrets. `ops/setup_experiment.py <Development|Production> --start` creates the flag, the two metrics and the experiment idempotently.
3. **trials** (`count`, `environment`, `stage`; defaults are the frozen model, limits and prices): one matrix job per trial, 5 in parallel. Start with a small count in `development`.
4. **collect** (optional `run_id`): appends new records, deduplicated by trial ID, to the trial log. It never pushes to `main`.
5. **analyze**, locally:

```bash
# the end-of-run Flagsmith snapshot is taken with ops/snapshot_results.py through the ops workflow
python analysis/analyze.py --trials data/trials.jsonl \
    --flagsmith-json data/flagsmith_primary_results.json --out RESULTS.md
python analysis/crosscheck.py --flagsmith-json data/flagsmith_primary_results.json
```

`analyze.py` also writes `assets/results.svg` and `assets/failures.svg` and appends `data/results_notes.md`. Use `--stage replication` or `--stage followup` for the other stages. Follow the stopping rule in `EXPERIMENT.md`: stop at the pre-registered count, and never because the result looks good.

## Environment variables

Names only (`.env.example`). Values are never committed.

| Name | Purpose |
|---|---|
| `FS_EXPERIMENT_SERVER_KEY` | Runner: server key of the experiment project |
| `FS_EXPERIMENT_ADMIN_KEY`, `FS_EXPERIMENT_PROJECT_ID` | `ops/` scripts: admin access to the experiment project |
| `FS_SANDBOX_CLIENT_KEY`, `FS_SANDBOX_SERVER_KEY`, `FS_SANDBOX_ADMIN_KEY`, `FS_SANDBOX_PROJECT_ID` | Sandbox project the agent works in |
| `HANDOFF_AGENT`, `HANDOFF_MODEL` | Agent (`opencode` or `claude`) and model id |
| `NEBIUS_API_KEY`, `NEBIUS_BASE_URL` | Model endpoint for OpenCode |
| `ANTHROPIC_API_KEY` | Only for the Claude agent |
| `HANDOFF_PRICE_IN_PER_M`, `HANDOFF_PRICE_OUT_PER_M` | Cost accounting |
| `HANDOFF_CONTEXT_LIMIT`, `HANDOFF_OUTPUT_LIMIT` | Model context and output limits |
| `HANDOFF_MAX_TURNS`, `HANDOFF_MAX_TOKENS` | Per-trial limits enforced by the runner |

The frozen values of the production run are in `EXPERIMENT.md`. A real trial records a real exposure in the experiment project, so use the Development environment unless you mean it. `--assign local` exists for pilots only and is refused when `HANDOFF_ENVIRONMENT=production`.
