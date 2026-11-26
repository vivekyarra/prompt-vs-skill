# Architecture

One job in the GitHub Actions matrix is one trial. Flagsmith assigns the variant, the grader judges the result from real traffic, and Flagsmith receives the verdict.

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

## Data flow after the trials

```
trials.yml (artifacts: trial record + diff per trial)
   └── collect.yml → analysis/collect.py → data/trials.jsonl on the `data` branch
          └── analysis/analyze.py → RESULTS.md   (own-log cross-check, sanity checks, failure breakdown)
          └── analysis/crosscheck.py             (our counts vs Flagsmith exposure/event counts)
```

`collect.yml` pushes only to the `data` branch, never to `main`. Merge `data` into `main` by hand when the data should ship with the final repo.

## Components

| Component | Language | Purpose |
|---|---|---|
| `apps/` | React (Vite), Node (Express), Python (Flask) | Sample apps the agents modify |
| `grader/` | Python (Playwright + mitmproxy) | Runs an app, records Flagsmith traffic, evaluates checks |
| `skill/` | Markdown + optional scripts | Variant B Agent Skill |
| `prompt/` | Markdown | Variant A official prompt, stored unmodified |
| `brief/` | Markdown | The task brief given identically to both variants |
| `runner/` | Python | Orchestrates one trial end to end |
| `analysis/` | Python (stdlib only) | Aggregates trial logs, cross-checks Flagsmith counts, writes results |
| `.github/workflows/` | YAML | Trial matrix, collection, grader tests, CI |

## Two Flagsmith projects, never mixed

- `handoff-experiment`: holds `onboarding_method`, the two metrics, and the experiment. Only the runner touches it.
- `handoff-sandbox`: where trial agents create their own flags. Agents never receive keys for the experiment project.

## Secrets

| Name | Where | Used by |
|---|---|---|
| `FS_EXPERIMENT_SERVER_KEY` | Actions secret (per environment) | Runner only |
| `FS_SANDBOX_CLIENT_KEY` | Actions secret | Agent (client-side SDK) |
| `FS_SANDBOX_SERVER_KEY` | Actions secret | Agent (server-side SDKs) |
| `FS_SANDBOX_ADMIN_KEY` | Actions secret | Agent (CLI/API) and cleanup |
| `FS_SANDBOX_PROJECT_ID` | Actions variable | Agent |
| `ANTHROPIC_API_KEY` | Actions secret | Agent |
| `HANDOFF_MAX_TURNS`, `HANDOFF_MAX_TOKENS` | Actions variables | Runner |
