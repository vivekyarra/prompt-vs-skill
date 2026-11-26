# Handoff: Prompt vs Skill — Complete Build Specification

**Hackathon:** Toggle Wars: The Flagsmith Experimentation Hackathon (WeMakeDevs × Flagsmith)
**Track:** 01 — Test Something Real ($2,000)
**Dates:** Hacking 26 Nov 2026, 8 AM IST → submissions close 29 Nov 2026, 8 PM IST
**Hackathon page:** https://wemakedevs.org/hackathons/flagsmith

This document is the single source of truth for the project. It is written so that a human team or Claude Code working autonomously can build, run, and package the whole submission end to end. Read all of it before writing any code.

---

## Table of contents

1. Vision
2. The experiment (pre-registered)
3. What "done" means (submission-grade definition)
4. Rules for the builder (read before coding)
5. Human-only checkpoints
6. System architecture
7. Phase 0 — Verification spike (no guessing)
8. Phase 1 — Repository scaffold
9. Phase 2 — Sample apps
10. Phase 3 — The grader
11. Phase 4 — The Agent Skill (Variant B)
12. Phase 5 — The official prompt (Variant A) and the task brief
13. Phase 6 — The trial runner
14. Phase 7 — Flagsmith experiment setup
15. Phase 8 — GitHub Actions trial matrix
16. Phase 9 — Pilot run and budget freeze
17. Phase 10 — Full run and monitoring
18. Phase 11 — Analysis and results
19. Phase 12 — Rollout of the winner
20. Phase 13 — README, docs, and demo assets
21. Phase 14 — Contribution back to Flagsmith
22. Phase 15 — Submission
23. Judging criteria map
24. Risks and mitigations
25. Timeline
26. Final checklist

---

## 1. Vision

### The problem

Every developer tool company in 2026 has a new kind of user: the coding agent. When a developer says "add Flagsmith to my app," an agent such as Claude Code does the setup. How a tool hands that job to an agent decides whether the setup works.

There are two main ways to hand a job to an agent:

- **A setup prompt:** a block of instructions the developer pastes into the agent. Flagsmith publishes one: "Set up an Experiment with a Coding Agent" (https://docs.flagsmith.com/experimentation/set-up-with-a-coding-agent).
- **An Agent Skill:** a packaged folder of instructions (and optional scripts) that the agent loads for a specific job, following the open Agent Skills spec. Flagsmith is investing here too: Toggle Wars has a dedicated Track 04 whose winning skills get merged into the official Flagsmith skills repo.

Flagsmith ships both, and so does almost every devtool company. Nobody has measured which one actually gets agents to a correct setup. Wiring mistakes are real and silent: public scans of Toggle Wars repos have found teams reading experiment flags with `getValue`, which records no exposure, so none of their conversions count.

### What we build

**Handoff** is a real A/B test, run with Flagsmith Experimentation, where the subjects are coding agent runs. Each trial gives a fresh agent a small real app and the job "set up a Flagsmith A/B test in this app." Flagsmith decides whether the agent receives the official prompt or our Agent Skill. An independent grader then runs the agent's app and checks, from real network traffic, whether the experiment is wired correctly. The grader's verdict is sent back to Flagsmith as the success event. Flagsmith's Bayesian engine decides which handoff method wins, and we roll the winner out with the same flag.

### Why it matters

- **For Flagsmith:** a data-backed answer to a live product decision (prompt vs skill), plus concrete failure modes to fix in their onboarding.
- **For every devtool:** the first public head-to-head measurement of the two ways the industry onboards agents.
- **For the judges:** one experiment, done rigorously, on real events, with a result we can explain honestly, which is exactly what Track 01 asks for.

### One-line pitch

"Every devtool now onboards AI agents, either with a prompt or a skill. We ran a real Flagsmith experiment to find out which one actually works."

---

## 2. The experiment (pre-registered)

These values are fixed before any real trial runs. They are committed in `EXPERIMENT.md` with a timestamp before the full run starts. Only the values explicitly marked "set in pilot" may be filled in after the pilot, and they must be frozen and committed before the full run.

| Item | Value |
|---|---|
| Question | Does an Agent Skill get coding agents to a correctly wired Flagsmith experiment more often than Flagsmith's official setup prompt? |
| Hypothesis | Agents given the Agent Skill pass the grader more often than agents given the official prompt, without exceeding the budget more often. |
| Unit | One trial = one agent run on one sample app |
| Identity | The trial ID (`trial-<run_id>-<index>`), unique per trial, used for every Flagsmith call about that trial |
| Flag | `onboarding_method`, multivariate. Control value `prompt`, variation `skill` (with a key, so exposures are recorded) |
| Split | 100% of trials enrolled, 50/50 |
| Exposure | Recorded when the runner calls the experiment-flag method with the trial ID, before the agent starts |
| Primary metric | `integration_verified` (occurrence, higher is better). Sent only when the grader passes all primary checks (C1–C6) |
| Guardrail metric | `over_budget` (occurrence, lower is better). Sent when the agent hits the turn limit or token limit |
| Trait | `stack` = `react`, `node`, or `python` (for secondary breakdown only) |
| Sample target | 150–200 trials per variant (final number set in pilot, see Phase 9) |
| Decision rule | Ship the winning variant only if Flagsmith reports ≥95% win probability for it AND the credible interval on the difference excludes zero AND the guardrail is not significantly worse for it. Otherwise report the result as inconclusive and state roughly how many more trials would be needed. |
| Stopping rule | Do not stop when the result looks good. Stop only when the target sample is reached or the deadline buffer (29 Nov, 12:00 IST) is hit, whichever comes first. |
| Sanity check | Sample ratio check: exposures per variant must be within roughly 45/55. A larger imbalance means a bug; pause and fix before trusting any result. |
| Fairness | Same agent, same model, same tool permissions, same turn and token limits, same sample app pool, same task brief. The only difference between variants is the handoff method. |

### The task the agent is given (identical in both variants)

The agent must add a Flagsmith A/B test to the sample app:

- Test: the text on the app's "Join" button. Control `Join`, variation `Join free`.
- Flag name: `join_button_<trial_suffix>` (unique per trial to avoid collisions).
- Success: a visitor clicks the Join button. Event name: `join_clicked`.
- Use the existing visitor identity mechanism in the app.
- Flagsmith target: the sandbox project, credentials provided via environment variables.

---

## 3. What "done" means (submission-grade definition)

The project is complete only when every item below is true:

1. A public GitHub repo containing all code, docs, workflows, and results, with no secrets committed.
2. Three sample apps (React, Node/Express, Python/Flask), each with a broken-variant set that proves every grader check catches its failure.
3. A grader that passes its own test suite: every check is shown to pass on a correct reference integration and fail on its matching broken app.
4. An Agent Skill (Variant B) that follows the Agent Skills spec, uses the Flagsmith CLI, and passes the grader on all three stacks in at least one manual run each.
5. The official Flagsmith prompt (Variant A) stored with its source URL and retrieval date, unmodified.
6. A trial runner and GitHub Actions matrix that run trials end to end with no human input.
7. A live Flagsmith experiment with the flag, both metrics, real exposures, and real events from completed trials.
8. `EXPERIMENT.md` committed before the full run, with pilot-set values frozen before the full run.
9. A full run reaching the sample target, or as close as the deadline allows, with every trial logged.
10. `RESULTS.md` with Flagsmith's numbers (exposures, rates, lift, credible interval, win probability), the guardrail, the sample ratio check, the cross-check between our trial log and Flagsmith's counts, and per-check failure breakdowns.
11. The winner rolled out through the same flag (or a documented decision not to roll out if inconclusive).
12. README that a stranger can follow to reproduce a trial.
13. Demo video script, shot list, and all on-screen assets ready; video recorded and uploaded by a human (2–3 minutes).
14. Contribution to Flagsmith prepared (issue or PR with findings).
15. Submission form completed before 29 Nov, 8 PM IST (target: 29 Nov, 3 PM IST).

---

## 4. Rules for the builder (read before coding)

These rules apply to every phase, especially when Claude Code works autonomously.

1. **No API guesswork.** Every Flagsmith SDK method, CLI command, endpoint, and payload format must be verified against official docs or observed in a real run during Phase 0 before it is used. Record each verified fact in `docs/verified-facts.md` with its source. If docs and behavior disagree, trust observed behavior and note it.
2. **Never fabricate results.** No made-up numbers, screenshots, or trial outcomes anywhere: not in docs, not in the README, not in the video script. If data is missing, say so.
3. **Never commit secrets.** All keys live in environment variables locally and GitHub Actions secrets in CI. Add a pre-commit secret scan (for example `gitleaks`) and a `.gitignore` covering `.env*`.
4. **Two Flagsmith projects, never mixed:**
   - **Experiment project** (`handoff-experiment`): holds `onboarding_method`, the two metrics, and the experiment. Only the runner touches it.
   - **Sandbox project** (`handoff-sandbox`): where trial agents create their own flags. Agents never receive keys for the experiment project.
5. **Work phase by phase.** Finish each phase's acceptance criteria before starting the next. Commit at the end of each phase with a message naming the phase.
6. **Test first where possible.** The grader especially must be proven on broken apps before any trial result is trusted.
7. **Stop and report instead of improvising** when blocked by a human-only checkpoint (Section 5). Write what is needed in `docs/BLOCKERS.md`, continue with any other phase that is not blocked, and resume when unblocked.
8. **Keep it small.** One experiment done well. Do not add dashboards, extra variants, or features not in this spec.
9. **Log everything.** Every trial produces a JSON record (Section 13) saved as a workflow artifact and appended to `data/trials.jsonl`.
10. **Be honest in all writing.** Report inconclusive results as inconclusive. Report limitations.

---

## 5. Human-only checkpoints

Claude Code cannot do these. A human must do them, and the builder must list any that are pending in `docs/BLOCKERS.md`.

| ID | Task | Needed by |
|---|---|---|
| H1 | Create a Flagsmith Cloud account and organisation; enable the managed warehouse for Experimentation | Phase 0 |
| H2 | Create the two projects (`handoff-experiment`, `handoff-sandbox`) and their Production/Development environments | Phase 0 |
| H3 | Create API credentials: experiment project server-side environment key; sandbox Admin API key (or CLI credentials) scoped to the sandbox organisation if possible | Phase 0 |
| H4 | Create an Anthropic API key (or the key for whichever agent is chosen) with a spending limit set | Phase 0 |
| H5 | Create the public GitHub repo and add all keys as Actions secrets (names in Section 6.4) | Phase 1 |
| H6 | Approve the pilot cost and the final sample target after Phase 9 | Phase 9 |
| H7 | Start the Flagsmith experiment in the dashboard if starting via CLI/API is not available | Phase 7 |
| H8 | Record and upload the demo video | Phase 13 |
| H9 | Open the issue or PR on Flagsmith's GitHub (review the text first) | Phase 14 |
| H10 | Register for the hackathon (if not done), star Flagsmith on GitHub, and fill in the submission form | Phase 15 |

---

## 6. System architecture

### 6.1 Overview

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

### 6.2 Components

| Component | Language | Purpose |
|---|---|---|
| `apps/` | React (Vite), Node (Express), Python (Flask) | Sample apps the agents modify |
| `grader/` | Python (Playwright + mitmproxy) | Runs an app, records Flagsmith traffic, evaluates checks |
| `skill/` | Markdown + optional scripts | Variant B Agent Skill |
| `prompt/` | Markdown | Variant A official prompt, stored unmodified |
| `brief/` | Markdown | The task brief given identically to both variants |
| `runner/` | Python | Orchestrates one trial end to end |
| `analysis/` | Python | Aggregates trial logs, cross-checks Flagsmith counts, writes results |
| `.github/workflows/` | YAML | Trial matrix, grader tests, CI |

### 6.3 Agent choice

- Default agent: **Claude Code** in headless (non-interactive) mode, because it supports Agent Skills natively and runs in CI. Verify in Phase 0: the headless invocation flag, how to set a maximum number of turns, how to get structured JSON output including token usage, how to restrict tools, and where project-level skills are loaded from.
- One model for every trial in both variants. Pick it in Phase 9 based on pilot cost. Record the exact model ID in `EXPERIMENT.md`.
- Tool permissions identical in both variants: shell, file read/write/edit, web fetch (the official prompt tells the agent to read Flagsmith docs, so web access must be allowed for both variants equally).

### 6.4 Secrets and environment variables

| Name | Where | Used by |
|---|---|---|
| `FS_EXPERIMENT_SERVER_KEY` | Actions secret | Runner only (experiment project, server-side key) |
| `FS_SANDBOX_CLIENT_KEY` | Actions secret | Passed to the agent for the app's client-side SDK |
| `FS_SANDBOX_SERVER_KEY` | Actions secret | Passed to the agent for server-side SDKs |
| `FS_SANDBOX_ADMIN_KEY` | Actions secret | Passed to the agent for CLI/API flag creation; also used by cleanup |
| `FS_SANDBOX_PROJECT_ID` | Actions variable | Passed to the agent |
| `ANTHROPIC_API_KEY` | Actions secret | Agent |
| `HANDOFF_MAX_TURNS` | Actions variable | Runner (set in pilot) |
| `HANDOFF_MAX_TOKENS` | Actions variable | Runner (set in pilot) |

Verify the exact names the Flagsmith CLI expects for credentials in Phase 0 and map these variables accordingly.

---

## 7. Phase 0 — Verification spike (no guessing)

**Goal:** prove every external assumption before building on it. Work in a throwaway folder `spike/` (committed, so the evidence is visible).

### Tasks

1. **Flagsmith SDK experiment calls.** For each SDK we use (JS/React `@flagsmith/flagsmith` 12.4.0+, Node `@flagsmith/nodejs` 9.1.0+, Python `flagsmith` 6.3.0+), confirm from https://docs.flagsmith.com/experimentation and the SDK docs:
   - the method that reads an experiment flag and records an exposure (expected: `getExperimentFlag` in JS, `get_experiment_flag` in Python),
   - the method that sends a conversion event (expected: `trackEvent` / `track_event`),
   - the option that enables events (expected: `enableEvents: true` / `enable_events=True`),
   - how events are flushed before process exit (expected: `flushEvents` in JS),
   - the option for a custom API URL (needed only if interception requires it).
2. **What goes over the wire.** Write a tiny script per SDK that reads an experiment flag for identity `spike-1` and sends event `spike_event`. Capture the traffic (see task 3) and record in `docs/verified-facts.md`: hosts contacted, endpoint paths, how identity, exposure, and event names appear in the payloads, and whether events are batched.
3. **Interception approach.** The grader must see Flagsmith traffic from apps whose code the agent wrote, without relying on the agent cooperating. Choose and prove one approach that works for a browser app, a Node server, and a Python server:
   - Preferred: run `mitmproxy` as an HTTPS proxy; trust its CA via `NODE_EXTRA_CA_CERTS` (Node), `REQUESTS_CA_BUNDLE` and `SSL_CERT_FILE` (Python), and Playwright/Chromium proxy settings with the CA trusted or certificate errors ignored for the browser. For Node, confirm whether the SDK's HTTP client honors `HTTPS_PROXY` (on recent Node versions this may require `NODE_USE_ENV_PROXY=1` or a global proxy agent); if not, use a different capture method.
   - Fallback: DNS override of Flagsmith hosts to a local `mitmproxy` reverse proxy that forwards to the real hosts.
   - Acceptance: for all three stacks, the spike scripts' exposure and event requests appear in the capture with identity and event names readable.
4. **Flagsmith CLI.** Install the CLI v2 (`curl -fsSL https://get.flagsmith.com | sh`, or `npm install -g @flagsmith/cli` as fallback). Verify: login/auth in headless mode with an API key, creating a multivariate flag, adding a keyed variation, creating a metric, creating and starting an experiment, deleting a flag. Record exact commands. Note: variations need a key for exposures to be recorded.
5. **Experiment lifecycle via CLI/API.** Confirm whether experiments can be started from the CLI/API (the official agent guide notes the MCP server cannot start experiments). If not possible, mark H7 in `docs/BLOCKERS.md`.
6. **Headless agent.** Verify the exact Claude Code headless invocation, turn limit flag, JSON output with usage, tool restrictions, and project skill location. Run a trivial headless task and confirm usage numbers are captured.
7. **Official prompt.** Fetch https://docs.flagsmith.com/experimentation/set-up-with-a-coding-agent and confirm the prompt text can be extracted verbatim. Note every point where it expects interactive human answers (it asks what to test, what counts as success, which Flagsmith instance, and asks for approval before writing code; it may also offer to send test traffic). These will be answered by the task brief (Phase 5).
8. **Rate limits.** Check Flagsmith API rate limits and pick a safe `max-parallel` for the matrix (start at 5).

### Acceptance criteria

- `docs/verified-facts.md` lists every method, command, endpoint, payload field, and env var name used later, each with a source link or "observed in spike" note.
- Interception proven on all three stacks.
- One manual Flagsmith experiment created, started, and showing at least one exposure and one event from the spike.

---

## 8. Phase 1 — Repository scaffold

### Layout

```
handoff/
├── README.md
├── EXPERIMENT.md
├── RESULTS.md
├── LICENSE                     (MIT)
├── .gitignore
├── .env.example                (names only, no values)
├── docs/
│   ├── verified-facts.md
│   ├── BLOCKERS.md
│   ├── architecture.md
│   ├── grader.md
│   ├── fairness.md
│   ├── demo-script.md
│   └── flagsmith-contribution.md
├── apps/
│   ├── react/                  (correct baseline, no Flagsmith yet)
│   ├── node/
│   ├── python/
│   └── reference/              (correct Flagsmith integrations, one per stack, for grader tests)
│   └── broken/                 (one broken integration per check per stack)
├── grader/
│   ├── grader/                 (package)
│   ├── tests/
│   └── pyproject.toml
├── skill/
│   └── flagsmith-ab-test/
│       └── SKILL.md            (+ optional scripts/)
├── prompt/
│   └── OFFICIAL_PROMPT.md
├── brief/
│   └── TASK_BRIEF.md
├── runner/
│   ├── runner/
│   ├── tests/
│   └── pyproject.toml
├── analysis/
│   ├── analyze.py
│   └── crosscheck.py
├── data/
│   └── trials.jsonl            (appended by the collection workflow)
├── spike/
└── .github/workflows/
    ├── ci.yml                  (lint, unit tests, grader self-tests)
    ├── trials.yml              (trial matrix)
    └── collect.yml             (gathers trial artifacts into data/)
```

### Acceptance criteria

- Repo created, structure in place, `ci.yml` running lint and empty test suites green.
- Secret scanning active. `.env.example` lists every variable from Section 6.4 without values.

---

## 9. Phase 2 — Sample apps

**Goal:** three small, realistic apps that give the agent a fair, identical job in each stack.

### Requirements (all three apps)

- One page with a heading, a short paragraph, and a single "Join" button.
- Clicking Join triggers a visible success state ("Thanks for joining!") and, for server apps, a POST to `/join`.
- An existing, working **visitor identity mechanism** that the agent must find and reuse:
  - React: a visitor ID generated once and stored in `localStorage` (`visitor_id`).
  - Node/Express: a visitor ID in a long-lived cookie (`vid`), set by middleware.
  - Python/Flask: a visitor ID in a long-lived cookie (`vid`), set in `before_request`.
- A `README.md` describing how to install and run the app, and where identity lives (stated plainly, the same way in all three).
- A start command that serves on a known port (React: build + preview on 5173 or static serve; Node: 3000; Flask: 5000).
- A minimal existing test (for example, "page renders, Join button exists") that the grader runs to confirm the agent did not break the app.
- No Flagsmith code in the baseline apps.
- Pinned dependency versions and lockfiles.

### Reference integrations (`apps/reference/`)

For each stack, a correct Flagsmith integration that the grader must pass:
- Experiment flag read with the experiment method and the app's visitor identity.
- Button text taken from the flag value.
- `join_clicked` sent with the same identity only when Join is clicked.
- Events enabled and flushed correctly.
- Client-side key in the browser; server-side key only on the server.

### Broken integrations (`apps/broken/`)

For each stack, one broken copy per check (Section 10), each with exactly one mistake:
- B1: app fails to start (syntax error).
- B2: flag read with `getValue`/plain flag access instead of the experiment method (no exposure).
- B3: conversion sent on page load instead of on click.
- B4: conversion sent with a different identity than the exposure.
- B5: new random identity on every load (unstable identifier).
- B6: flag read but button text not driven by it.
- B7 (diagnostic only): server-side key embedded in the browser bundle.

### Acceptance criteria

- All three baselines run and pass their own tests.
- All reference integrations run against the sandbox project and send real exposures and events (confirmed via capture).

---

## 10. Phase 3 — The grader

**Goal:** an independent, deterministic judge of whether an app's Flagsmith experiment is correctly wired. This is the most important component. Its credibility is the project's credibility.

### Interface

```
python -m grader --app-dir <path> --stack <react|node|python> \
                 --flag <flag_name> --event join_clicked \
                 --variant-values "Join,Join free" --out <result.json>
```

### Procedure

1. Install dependencies and start the app with the interception proxy active (approach from Phase 0). Timeout: 120 s to become healthy.
2. Run the app's existing test. Record pass/fail.
3. **Visitor V1:** new browser context. Load page. Wait for network idle plus 3 s. Record requests (phase "load"). Click Join. Wait for network idle plus 5 s (allow event batching/flush). Record requests (phase "click").
4. **Visitor V1 again:** same browser context (same cookies and storage). Reload. Record identity used.
5. **Visitor V2:** fresh browser context. Load page. Record identity used.
6. For server-side stacks, identity and SDK calls happen in the server process; the proxy still captures them. Associate server requests with the browser visitor by timing and by identity value.
7. Stop the app and proxy. Evaluate checks.

### Checks

| ID | Check | Pass condition |
|---|---|---|
| C1 | App runs | App becomes healthy, existing test passes, Join button is clickable |
| C2 | Exposure sent | At least one exposure for the trial's flag is sent with V1's identity (as observed in the payload format verified in Phase 0) |
| C3 | Conversion on action | A `join_clicked` event is sent in the "click" phase and none is sent in the "load" phase |
| C4 | Identity match | The identity on V1's exposure equals the identity on V1's `join_clicked` event |
| C5 | Identity stable | V1's identity is the same after reload, and V2's identity differs from V1's |
| C6 | Flag drives the UI | The rendered Join button text equals one of the variant values, and matches the variant Flagsmith returned for that identity |
| C7 | No server key in client (diagnostic) | No server-side key string appears in any browser-loaded asset. Recorded, but not part of the pass decision |

**Pass = C1 AND C2 AND C3 AND C4 AND C5 AND C6.** This definition is pre-registered and must not change after the pilot.

### Output

`result.json` containing: each check's pass/fail, a one-line reason for each failure, the identities observed, counts of captured requests per phase, durations, and the grader version (git SHA).

### Self-tests (`grader/tests/`)

- Every reference integration passes all checks on all three stacks.
- Every broken integration fails exactly its matching check (and the failure reason names the problem).
- The grader is deterministic: running it 3 times on the same app gives the same verdict.
- These tests run in `ci.yml` on every push.

### Acceptance criteria

- All self-tests green in CI.
- `docs/grader.md` explains each check in plain language with the matching broken example.

---

## 11. Phase 4 — The Agent Skill (Variant B)

**Goal:** a skill that does the same job as the official prompt, packaged per the Agent Skills spec, using the Flagsmith CLI.

### Requirements

- Folder `skill/flagsmith-ab-test/` with `SKILL.md` containing the required front matter (name, description) per the Agent Skills spec (verify the spec in Phase 0).
- Scope identical to the official prompt's job: find how the app identifies users, create the multivariate flag with a keyed variation, create the metric, create (and start if possible) the experiment, wire the experiment-flag read and the conversion event into the code, then verify.
- Uses the Flagsmith CLI for all Flagsmith writes, with `--json` output where available, keeping output small to save tokens.
- Contains a **verification step** before finishing: run the app, trigger one visit and one click, and confirm locally that the exposure and event were sent with the same identity. This must use only general tools (the CLI, logs, a short script), not our grader.
- Contains a short "common mistakes" section, written from verified facts: plain flag reads record no exposure; conversion must fire on the action, not page load; same identity for exposure and conversion; stable identifiers; enable and flush events; keyed variations.
- Concise. Target under 1,500 words in `SKILL.md`. Token efficiency is part of what is being tested.
- Must not reference the grader, this experiment, or the hidden checks. It must be a genuine, reusable skill any developer could use.

### Acceptance criteria

- Manual headless run with the skill passes the grader on each of the three stacks at least once.
- The skill passes a manual review against the Agent Skills spec.

---

## 12. Phase 5 — The official prompt (Variant A) and the task brief

### Official prompt

- Store the prompt text from https://docs.flagsmith.com/experimentation/set-up-with-a-coding-agent verbatim in `prompt/OFFICIAL_PROMPT.md`, with the source URL, retrieval date and time, and a SHA-256 of the text.
- Do not edit it. If the docs license makes storing it unclear, fetch it at runtime instead and log the hash per trial; if the hash changes mid-run, pause and record it.

### Task brief (`brief/TASK_BRIEF.md`)

The official prompt expects a human to answer questions and approve changes. In headless trials no human is present, so both variants receive the same task brief, which pre-answers everything. The brief must be identical, word for word, in both variants. It states:

- What to test: the Join button text, control `Join`, variation `Join free`.
- Flag name: `join_button_<trial_suffix>`.
- What counts as success: a click on the Join button, event name `join_clicked`.
- Which Flagsmith: Flagsmith Cloud, sandbox project; credentials are in the environment (list the variable names).
- Approval: all code changes and Flagsmith changes are pre-approved; proceed without asking.
- Test traffic: do not send simulated traffic; it is not needed.
- Finish by stating "DONE" with a one-paragraph summary.

### How each variant is delivered

- **Variant A (prompt):** agent instruction = official prompt text, followed by the task brief.
- **Variant B (skill):** the skill is installed in the agent's project skill folder; agent instruction = one neutral line ("Set up a Flagsmith A/B test in this app using the flagsmith-ab-test skill."), followed by the same task brief.

Document this in `docs/fairness.md`, including why the brief is needed and that it is applied identically.

### Acceptance criteria

- One manual headless run of Variant A on each stack completes (pass or fail does not matter; it must run cleanly end to end).

---

## 13. Phase 6 — The trial runner

**Goal:** one command runs one complete trial with no human input.

### Interface

```
python -m runner --trial-id <id> --out-dir <path>
```

### Steps

1. Pick the stack deterministically from a hash of the trial ID (uniform over react, node, python).
2. Call Flagsmith (experiment project, server-side SDK, events enabled) for `onboarding_method` with identity = trial ID and trait `stack`. This records the exposure. Read the variant value.
3. Create a clean temp workspace with a copy of the stack's baseline app. Initialise git in it (to capture the agent's diff later).
4. Deliver the variant (Phase 5). Install the skill only for Variant B.
5. Start the agent headlessly with: the instruction, the fixed model, the fixed tool permissions, the turn limit, and only sandbox credentials in its environment. Capture full JSON output.
6. Enforce limits: stop the agent if turns exceed `HANDOFF_MAX_TURNS` or total tokens exceed `HANDOFF_MAX_TOKENS`, or wall time exceeds 30 minutes. Mark `over_budget = true` if any limit is hit.
7. Run the grader on the workspace.
8. Send events to Flagsmith (experiment project), identity = trial ID:
   - `integration_verified` if the grader passed,
   - `over_budget` if any limit was hit.
   Flush events and confirm the flush completed before exiting.
9. Write the trial record:

```json
{
  "trial_id": "trial-<run_id>-<index>",
  "timestamp_utc": "...",
  "variant": "prompt | skill",
  "stack": "react | node | python",
  "model": "<exact model id>",
  "agent_version": "...",
  "prompt_sha256": "...",
  "skill_sha": "<git sha of skill folder>",
  "grader_sha": "...",
  "turns": 0,
  "input_tokens": 0,
  "output_tokens": 0,
  "cost_usd": 0.0,
  "duration_s": 0,
  "over_budget": false,
  "limit_hit": "none | turns | tokens | time",
  "checks": {"C1": true, "C2": true, "C3": true, "C4": true, "C5": true, "C6": true, "C7": true},
  "failure_reasons": [],
  "passed": true,
  "events_sent": ["integration_verified"],
  "agent_diff_path": "diff.patch"
}
```

10. Save the agent's diff and the grader's result as artifacts.
11. Cleanup: delete the trial's flag from the sandbox project. Never touch the experiment project during cleanup.

### Failure handling

- If the runner itself crashes (not the agent), mark the trial `runner_error = true`, send no conversion event, and keep the record. Runner errors are reported separately in results and must stay below 5% of trials; if higher, pause and fix.
- Retries: never retry a trial that reached the agent step (that would bias results). Only retry infrastructure failures that happen before the exposure is recorded.

### Acceptance criteria

- Unit tests for stack selection, limit enforcement, record writing, and event sending (with Flagsmith calls mocked).
- Five local end-to-end trials complete with correct records and events visible in Flagsmith.

---

## 14. Phase 7 — Flagsmith experiment setup

Do this in the **experiment project**, Production environment, using verified CLI commands (or the dashboard if needed).

1. Create `onboarding_method`, multivariate. Control value `prompt`. Add variation `skill` with key `skill`. Weights 50/50.
2. Create metric `integration_verified`: occurrence, higher is better.
3. Create metric `over_budget`: occurrence, lower is better.
4. Create the experiment "Handoff: Prompt vs Skill" on `onboarding_method`, primary metric `integration_verified`, secondary/guardrail `over_budget`, 100% enrolment.
5. Start it (CLI/API if supported, else H7).
6. Record every ID (project, environment, flag, metrics, experiment) in `docs/verified-facts.md` and `EXPERIMENT.md`.

Also: run the pilot (Phase 9) in a **separate Development-environment experiment** so pilot trials never mix with the real experiment's data.

### Acceptance criteria

- Experiment shows as running; a test trial's exposure appears in the dashboard.

---

## 15. Phase 8 — GitHub Actions trial matrix

### `trials.yml`

- Trigger: `workflow_dispatch` with inputs `count` (trials in this batch) and `environment` (`development` for pilot, `production` for the real run).
- Matrix over `index` from 1 to `count`, `max-parallel` from Phase 0 (start at 5).
- Each job: checkout, set up Python and Node, install Playwright browsers, mitmproxy, the Flagsmith CLI, and the agent; run `python -m runner --trial-id trial-${{ github.run_id }}-${{ matrix.index }}`; upload artifacts.
- `fail-fast: false`, so one failing trial never cancels others.
- Job timeout 45 minutes.

### `collect.yml`

- Trigger: after `trials.yml` completes, and manually.
- Downloads all trial artifacts from completed runs, appends new records to `data/trials.jsonl` (no duplicates by trial ID), commits.

### Acceptance criteria

- A batch of 3 Development trials runs green end to end from the Actions tab, and `collect.yml` adds 3 records.

---

## 16. Phase 9 — Pilot run and budget freeze

1. Run 10 trials in the Development environment.
2. Measure: cost per trial, duration, turns and tokens used, pass rates per variant, runner error rate.
3. Set and freeze:
   - `HANDOFF_MAX_TURNS` = roughly 1.5× the 90th percentile of turns in the pilot (rounded), but never below what a successful pilot run needed.
   - `HANDOFF_MAX_TOKENS` set the same way.
   - Model ID.
   - Final sample target per variant (150–200), based on cost and time left (H6: human approves the total cost).
   - `max-parallel` based on rate limits and how long the full run must take.
4. Commit `EXPERIMENT.md` with these frozen values and the commit timestamp before the full run starts.
5. If the pilot shows a bug (for example, the grader fails a run that is clearly correct), fix it, rerun its self-tests, and rerun the pilot. Never change the pass definition.

### Acceptance criteria

- `EXPERIMENT.md` frozen and committed. Human approval of cost recorded in `docs/BLOCKERS.md` as resolved.

---

## 17. Phase 10 — Full run and monitoring

1. Launch batches in the Production environment until the target is reached (for example, batches of 50).
2. After the first batch and then every batch, check:
   - sample ratio (exposures per variant within roughly 45/55),
   - runner error rate under 5%,
   - our trial log counts match Flagsmith's exposure and event counts (`analysis/crosscheck.py`).
3. Do not read the win probability to decide whether to stop. Follow the stopping rule.
4. Stop at the target sample or at 29 Nov, 12:00 IST, whichever comes first.

### Acceptance criteria

- Target reached (or deadline reached), all records collected, cross-check matches within a small, explained difference (for example, events still flushing).

---

## 18. Phase 11 — Analysis and results

### `analysis/analyze.py` produces `RESULTS.md` with:

1. **Primary result (from Flagsmith):** exposures per variant, `integration_verified` rate per variant, lift, credible interval on the difference, win probability. Include a screenshot of the Flagsmith results page (taken by a human if needed) and the date and time it was read.
2. **Decision:** applied exactly as pre-registered (ship, or inconclusive with the number of extra trials that would likely be needed).
3. **Guardrail:** `over_budget` rate per variant, plus mean turns, tokens, cost, and duration per variant from our logs.
4. **Sanity checks:** sample ratio, runner error rate, our-log vs Flagsmith count cross-check.
5. **Where agents fail:** failure rate of each check (C1–C6) per variant. This shows which mistakes each handoff method prevents or causes. Include 2–3 anonymised example diffs of typical failures.
6. **Secondary breakdown by stack** (clearly labelled as exploratory, not part of the decision).
7. **C7 diagnostic:** how often agents exposed a server key in client code, per variant.
8. **Limitations:** one agent and one model; small sample apps; the task brief replaces interactive answers; results may differ for other agents, models, and real-world codebases.

### Acceptance criteria

- `RESULTS.md` complete, every number traceable to `data/trials.jsonl` or the Flagsmith dashboard, no invented values.

---

## 19. Phase 12 — Rollout of the winner

- **If there is a winner by the decision rule:** set `onboarding_method` to 100% for the winning value through Flagsmith (the same flag), end the experiment, and run 5 confirmation trials showing every trial now receives the winner. Record this in `RESULTS.md`.
- **If inconclusive:** do not roll out. Document the decision and keep the flag at 50/50 so the experiment can continue.

---

## 20. Phase 13 — README, docs, and demo assets

### README.md structure

1. Title and one-line pitch.
2. The question and why it matters (short).
3. The result in one paragraph (filled from `RESULTS.md`; written honestly).
4. How it works (diagram from Section 6.1).
5. How Flagsmith is used (flag, metrics, experiment, rollout) with links to code.
6. The grader and its checks.
7. Reproduce a trial: prerequisites, environment variables, exact commands, what a successful run looks like.
8. Run the full experiment yourself (Actions workflow).
9. Repository map.
10. Judging criteria map (Section 23).
11. Limitations.
12. Links: demo video, `EXPERIMENT.md`, `RESULTS.md`, hackathon page.
13. Built for Toggle Wars: The Flagsmith Experimentation Hackathon (WeMakeDevs × Flagsmith), Track 01.

### Demo video (`docs/demo-script.md`), 2–3 minutes

| Time | Shows | Says |
|---|---|---|
| 0:00–0:15 | Title card | "Every devtool now onboards AI agents, with a prompt or a skill. Which works? We ran a real Flagsmith experiment." |
| 0:15–0:40 | Flagsmith's setup prompt page and the Track 04 skills idea | Why this is a live decision for Flagsmith and every devtool |
| 0:40–1:10 | Actions run: a trial starting, Flagsmith assigning the variant, agent working | How a trial runs; identity = trial ID |
| 1:10–1:35 | Grader output on one pass and one fail (e.g. C3 conversion on page load) | What "correctly wired" means, checked from real traffic |
| 1:35–2:15 | Flagsmith results page | Exposures, rates, credible interval, win probability, guardrail, read honestly |
| 2:15–2:35 | Flipping the flag to the winner; confirmation trials | Shipping the winner with the same flag |
| 2:35–2:50 | The issue/PR to Flagsmith; repo link | What Flagsmith can do with this |

Prepare all assets for the video: the shot list, terminal commands to show, the final results screenshot, and title cards. A human records and uploads (H8). Recording must happen by 28 Nov evening or 29 Nov morning at the latest, with results filled in once final.

### Acceptance criteria

- README followed by a fresh clone on a clean machine successfully runs one trial (verified by running it in CI from scratch).

---

## 21. Phase 14 — Contribution back to Flagsmith

`docs/flagsmith-contribution.md` contains a ready-to-post issue (or PR description) for Flagsmith with:

- The question, method, sample size, and decision rule.
- The result, stated with its credible interval.
- The most common failure modes per variant (from Phase 11, item 5).
- Concrete, specific suggestions for the official prompt and/or skill, each tied to observed failures.
- If the skill won: an offer to contribute it to the official skills repo.
- Link to the repo and `RESULTS.md`.

A human reviews and posts it (H9). Its link goes into the README and the video.

---

## 22. Phase 15 — Submission

1. Confirm every item in Section 26.
2. Repo public; default branch contains final code, data, and docs.
3. Video uploaded (YouTube unlisted or as the form requires) and linked in README.
4. Human submits through the WeMakeDevs form (H10), selecting Track 01, with repo link, video link, and a short description taken from the README's first paragraph.
5. Target submission time: 29 Nov 2026, 3 PM IST. Hard deadline: 8 PM IST.

---

## 23. Judging criteria map

| Criterion (from the hackathon page) | How Handoff meets it | Evidence |
|---|---|---|
| Use of Flagsmith: core, flags/experiments do real work | Flagsmith assigns every trial's variant, records exposures, receives the grader's verdicts, computes the winner, and ships it with the same flag. The subject of the test is Flagsmith's own onboarding. Remove Flagsmith and nothing runs. | `runner/`, Flagsmith dashboard, `RESULTS.md` |
| Impact: real problem, a team would use it | Answers a live product question for Flagsmith and every devtool; delivers specific fixes to Flagsmith's onboarding | `docs/flagsmith-contribution.md`, posted issue/PR |
| Creativity: new idea or familiar idea somewhere new | First head-to-head experiment of prompt vs skill for onboarding agents, with a ground-truth grader | README, video |
| Demo video: problem, build, Flagsmith fit | Script in Section 20 | Video link |
| Track 01: one experiment done well | One flag, one primary metric, one guardrail | `EXPERIMENT.md` |
| Track 01: clear hypothesis | Pre-registered, committed before the full run | `EXPERIMENT.md` commit timestamp |
| Track 01: versions behind a flag | `onboarding_method`: `prompt` / `skill` | Flagsmith dashboard |
| Track 01: metric from real events | `integration_verified` sent only from real grader verdicts on real agent runs | `grader/`, `data/trials.jsonl` |
| Track 01: results you can explain | Credible interval, decision rule, sanity checks, failure breakdown, limitations | `RESULTS.md` |

### Organizers' warnings, and how each is handled

| Warning (from "How to Win Toggle Wars") | Handling |
|---|---|
| Unstable identifier | Identity = trial ID, generated once, used for every call |
| Exposures on one side only | Sample ratio check every batch |
| Conversions flat while exposures rise | Cross-check of our logs vs Flagsmith counts every batch |
| Boolean flag converted late | `onboarding_method` is multivariate from the start |
| Stopping when the number looks good | Fixed sample target and stopping rule |
| No guardrail | `over_budget` tracked |
| Keys in the repo | Secrets only in env/Actions secrets; secret scan in CI |
| README assumes your laptop | Reproduction verified from a fresh clone in CI |
| Video recorded in the last hour | Recording scheduled 28 Nov / early 29 Nov |

---

## 24. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Agent cost too high for the target sample | Pilot measures cost; pick model and target accordingly; same model for both variants |
| Grader wrongly passes or fails | Reference and broken-app self-tests in CI; determinism test; manual review of 10 random graded trials after the first batch |
| Interception fails for a stack | Proven in Phase 0 for all stacks before any building; fallback method documented |
| Official prompt changes mid-run | Hash logged per trial; pause and document if it changes |
| Flagsmith rate limits | Conservative `max-parallel`; backoff and retry on rate-limit responses only before the exposure |
| Sandbox clutter from trial flags | Per-trial cleanup; a manual cleanup script for leftovers |
| Experiment cannot be started via API | H7: human starts it in the dashboard |
| Inconclusive result | Report it honestly with the sample needed; still a strong submission because the method and failure analysis stand |
| Competitor with a similar concept (agents as subjects) | Our differentiators: the sponsor's real onboarding, prompt vs skill as the question, a ground-truth grader from real traffic, and a contribution back to Flagsmith. State these in the first 15 seconds of the video. |

---

## 25. Timeline

| When (IST) | Work |
|---|---|
| 26 Nov | Phase 0 spike, Phase 1 scaffold, Phase 2 sample apps (baselines + references) |
| 27 Nov morning | Broken apps, Phase 3 grader + self-tests green |
| 27 Nov afternoon | Phase 4 skill, Phase 5 prompt + brief, Phase 6 runner |
| 27 Nov evening | Phase 7 experiment setup, Phase 8 workflows, Phase 9 pilot, freeze `EXPERIMENT.md`, start full run |
| 28 Nov | Phase 10 full run with monitoring; README draft; demo assets; record video draft |
| 29 Nov until 12:00 | Run completes; Phase 11 analysis; Phase 12 rollout; final README; Phase 14 contribution text |
| 29 Nov 12:00–15:00 | Final video cut with real results; submission (target 15:00) |
| 29 Nov 20:00 | Hard deadline |

---

## 26. Final checklist

- [ ] `docs/verified-facts.md` complete; no unverified API use anywhere
- [ ] Sample apps: 3 baselines, 3 references, broken set per check per stack
- [ ] Grader self-tests green in CI; determinism confirmed
- [ ] Skill follows the Agent Skills spec; passes the grader on all stacks manually
- [ ] Official prompt stored verbatim with source, date, and hash
- [ ] Task brief identical in both variants; `docs/fairness.md` written
- [ ] Runner unit tests green; local end-to-end trials verified
- [ ] Flagsmith experiment project: flag, two metrics, running experiment; IDs recorded
- [ ] Pilot done in Development; `EXPERIMENT.md` frozen and committed before the full run
- [ ] Full run complete (or stopped at the deadline per the stopping rule)
- [ ] Sample ratio check, runner error rate, and log-vs-Flagsmith cross-check reported
- [ ] `RESULTS.md` complete and honest; screenshot of Flagsmith results included
- [ ] Winner rolled out via the same flag, or inconclusive decision documented
- [ ] README reproducible from a fresh clone
- [ ] No secrets in the repo; secret scan clean
- [ ] Contribution to Flagsmith posted; link in README
- [ ] Demo video recorded (2–3 minutes), uploaded, linked
- [ ] Flagsmith starred on GitHub
- [ ] Submitted on the WeMakeDevs form before 29 Nov 2026, 8 PM IST
