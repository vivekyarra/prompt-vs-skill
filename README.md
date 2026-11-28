<div align="center">

# Handoff: Prompt vs Skill

### Does Flagsmith's setup prompt or an Agent Skill get a coding agent to a correctly wired A/B test more often? We ran the experiment in Flagsmith to find out.

[![CI](https://github.com/vivekyarra/prompt-vs-skill/actions/workflows/ci.yml/badge.svg)](https://github.com/vivekyarra/prompt-vs-skill/actions/workflows/ci.yml)
[![Grader](https://github.com/vivekyarra/prompt-vs-skill/actions/workflows/grader.yml/badge.svg)](https://github.com/vivekyarra/prompt-vs-skill/actions/workflows/grader.yml)
[![Python](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![Built on Flagsmith](https://img.shields.io/badge/built%20on-Flagsmith-7c6cf0)](https://flagsmith.com)
[![Toggle Wars](https://img.shields.io/badge/Toggle%20Wars%20·%20Track%2001-Test%20something%20real-f5a623)](https://wemakedevs.org/hackathons/flagsmith)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

<img src="assets/results.svg" alt="Pass rate per arm: official prompt 108 of 108, skill 96 of 112, with credible intervals" width="760">

</div>

```bash
python -m runner --dry-run --scripted-agent-apply-reference --trial-id trial-readme-1 --out-dir out   # one full trial, no credentials
```

<p align="center"><a href="RESULTS.md"><b>Results</b></a> · <a href="EXPERIMENT.md"><b>Pre-registration</b></a> · <a href="docs/replication-gap.md"><b>Replication gap</b></a> · <a href="docs/regrade.md"><b>Regrade</b></a> · <a href="docs/failure-labels.md"><b>Failure analysis</b></a> · <a href="docs/flagsmith-contribution.md"><b>Suggestions for Flagsmith</b></a></p>
<p align="center">Built for Toggle Wars, Track 01: Test something real</p>

## The question

When a developer asks a coding agent to add a Flagsmith A/B test, which handoff works better: Flagsmith's official setup prompt, or an Agent Skill? Each trial is assigned by Flagsmith itself (`onboarding_method`, 50/50), a grader checks the agent's finished app from its network traffic, and Flagsmith computes the result.

## The answer

**In our pre-registered run, the official prompt did better: 108 of 108 correctly wired trials against 96 of 112 for the skill** (Flagsmith lift -14.3%, credible interval [-0.208, -0.078], which excludes zero). **The replication shows a smaller gap and is inconclusive on its own**: 106 of 108 against 105 of 112, interval [-0.097, +0.007]. Pooled over all 440 trials the skill is about 9 points lower (-0.088, [-0.133, -0.049]), most of it in one place: React browser-SDK imports. The skill also costs less: fewer turns, tokens and dollars per trial ([cost and speed](#cost-and-speed)).

Offline sensitivity, after fixing a grader limitation and regrading all 440 saved diffs ([docs/regrade.md](docs/regrade.md)): primary 108/108 vs 100/112 (difference -0.105 [-0.171, -0.049]), replication 106/108 vs 109/112 (-0.008 [-0.055, +0.038]). The primary difference shrinks but keeps its sign; the replication difference is indistinguishable from zero. The pre-registered decision uses the grader as it was. We think the gap is real but modest for React and partly sampling variation ([why the gap shrank](docs/replication-gap.md)).

## Scope

One agent (OpenCode 1.19.6), one model (MiniMax-M3.1-Flash), one task on three stacks (React, Node, Python). Not tested: other agents (including Claude Code), other models, other tasks. Both arms were near the ceiling, so the test can only see a gap of several points. The brief pre-answers the interactive steps a person would face, so this measures how well a handoff gets an agent through the wiring, not the whole onboarding. Skill v1 was frozen before the production run; the proposed v2 is untested. Our Python stack runs a long-lived server; the Python SDK's lost-events-at-exit behaviour did not affect delivery (verified, exploratory: [docs/python-sdk-close.md](docs/python-sdk-close.md)). The full list is the Limitations block below.

## Proof

- **Flagsmith's own results pages**, experiments 728 (primary) and 1142 (replication): dated screenshots are slotted in the [Results](#results) section below, with the raw reads committed under `data/`.
- **Replication:** a second 220-trial run with the identical frozen setup, as its own Flagsmith experiment ([RESULTS.md](RESULTS.md)).
- **Our log matches Flagsmith's counts exactly** in both runs, 3 post-freeze corrections are disclosed with both views, and the pre-registration is [append-only, with a link to the freeze commit](EXPERIMENT.md).
- **Every failure is root-caused** (18 primary failures) and a blind review of 24 passing diffs found no false pass.
- **Mock vs real Flagsmith (exploratory):** regraded against the real service in a sandbox, 46 of 47 diffs get the same verdict as with the local emulator; the one difference is an emulator false fail ([docs/mock-vs-real.md](docs/mock-vs-real.md)).
- **Flagsmith GitHub issue:** <!-- FLAGSMITH_ISSUE --> link to be added here.

## Video

<!-- VIDEO --> Demo video: link to be added here.

---

## Details

### The problem

Every devtool now onboards AI agents, either with a prompt to paste or with a skill to install. Nobody had measured which one works. For Flagsmith, and for any devtool, that is a live product decision.

- Prompts and skills are judged on taste and anecdote today. A grader that watches real network traffic turns it into a number.
- A good answer needs the real thing: real agents, real apps, and a real Flagsmith experiment that assigns, records and decides.

Handoff runs that experiment. Flagsmith assigns each trial to the official prompt or to the skill, a ground-truth grader checks the agent's app, and Flagsmith computes the result.

### What it does

| | |
|---|---|
| **Runs a real experiment** | One flag, `onboarding_method`, assigns each trial 50/50. Flagsmith records the exposure and the grader's verdict, and computes the credible interval. |
| **Judges from network behaviour** | The grader runs the agent's app behind an intercepting proxy, drives it with Chromium and checks exposure, conversion, identity and UI from recorded traffic. |
| **Explains every failure** | All 18 graded failures are root-caused from their diffs. A blind review of 24 passing diffs found no false pass. |
| **Proposes skill v2 (untested)** | The failure analysis turns directly into proposed fixes, and skill v2 encodes them. It has not been run as an experiment arm. |
| **Checks your own app** | The same grader is a standalone 60-second wiring check for any web app. |

### See it work

Credential-free, real output: the grader on a correct reference app and on a copy that sends the conversion on page load (`python scripts/demo_grader.py`).

```text
=== reference node: PASS ===
  C1 App runs                               pass  app healthy, existing test passed, Join button clickable
  C2 Exposure sent                          pass  2 exposure event(s) for 'onboarding_demo' with V1 identity
  C3 Conversion on action                   pass  1 join_clicked event(s) in click phase, none on load
  C4 Identity match                         pass  exposure and conversion use the same identity
  C5 Identity stable                        pass  identity stable across reload; V2 differs
  C6 Flag drives the UI                     pass  button text equals the value Flagsmith returned (V1 and V2)
  C7 No server key in client (diagnostic)   pass  no server key in 2 browser-loaded assets

=== broken node/B3: FAIL ===
  C3 Conversion on action                   FAIL  join_clicked was sent during page load, before any click (1 event(s))
```

The quickstart command above runs a full trial end to end: a scripted agent applies the reference integration, the real grader passes it, and `trial_record.json` lists `integration_verified` as the only event.

### How it works

```mermaid
flowchart LR
  A[GitHub Actions<br/>one job = one trial] --> B[Runner]
  B -->|"get_experiment_flag(trial ID)"| F[(Flagsmith)]
  F -->|prompt or skill| B
  B --> C[Coding agent<br/>same brief, same limits]
  C -->|edits sample app| D[Grader<br/>proxy + Chromium]
  D -->|C1-C6 verdict| B
  B -->|integration_verified / over_budget| F
  F --> R[Results + inference]
  B --> L[(Trial log)] --> X[analysis/ + RESULTS.md]
```

1. **Assign.** The runner reads `onboarding_method` for the trial ID. The read records the exposure.
2. **Hand off.** Variant A gets the official prompt unedited. Variant B gets the Agent Skill installed in the agent's skill folder. Both get the same task brief.
3. **Run.** The agent (OpenCode with `MiniMaxAI/MiniMax-M3.1-Flash`) edits a randomly chosen React, Node or Python sample app, with fixed turn and token limits.
4. **Grade.** The grader checks C1 to C6 from recorded traffic: the app runs, an exposure is sent, the conversion fires on click, both use one identity, the identity is stable, and the flag value drives the UI.
5. **Report.** The runner sends `integration_verified` and `over_budget` to Flagsmith, then writes the trial record.
6. **Analyse.** Flagsmith's inference is the primary result. `analysis/` cross-checks it against our own log.

### Results

The official prompt currently gets agents to a correctly wired experiment more often than a skill written without it. Flagsmith's own inference reports it, our log matches Flagsmith's counts exactly, and the failure analysis shows how to close the gap.

| `integration_verified` (Flagsmith experiment) | Official prompt | Agent Skill (v1) | Flagsmith lift, credible interval |
|---|---|---|---|
| **Primary** (220 trials, experiment 728) | **108/108 (100%)** | 96/112 (85.7%) | -14.3%, [-0.208, -0.078] |
| **Replication** (220 trials, experiment 1142) | 106/108 (98.1%) | 105/112 (93.8%) | -4.5%, [-0.097, +0.007] |
| Guardrail `over_budget`, primary / replication | 1 / 0 | 1 / 0 | |

> **Correction footnote: three primary verdicts were corrected after a grader bug fix.** The trials are `trial-45914099371-14` (skill, python), `trial-45914099371-7` (skill, python) and `trial-45914099371-30` (prompt, node). All three were originally graded as C1 failures: the app's existing test ran without the placeholder credential variables the grader supplies at app start. The fix is one-directional (the test runs clean first and is retried with the placeholders only if it failed), so no earlier pass could change. Each trial was replayed 3 of 3 with the final grader. All three flips are fail to pass (two skill, one prompt); none went from pass to fail. The three `integration_verified` events were then sent to Flagsmith with `ops/backfill_events.py` (late events were verified to be counted), so Flagsmith's counts include them. Both views:
>
> | Primary view | Official prompt | Agent Skill (v1) |
> |---|---|---|
> | As originally graded | 107/108 (99.1%) | 94/112 (83.9%) |
> | As corrected (= Flagsmith's counts, the table above) | 108/108 (100%) | 96/112 (85.7%) |
>
> The per-arm rates for the first 40 trials were already visible when the correction was decided (as graded: prompt 19/20, skill 15/20). Details: [EXPERIMENT.md](EXPERIMENT.md) and the post-freeze corrections section of [RESULTS.md](RESULTS.md).

**Offline regrade (sensitivity, not the decision).** After the grader's local Flagsmith emulator was fixed to serve the environment document, all 440 saved diffs were regraded offline ([docs/regrade.md](docs/regrade.md); nothing was sent to Flagsmith):

| Skill minus prompt, 95% credible interval | Flagsmith as sent | Regraded with the final grader |
|---|---|---|
| Primary | -0.140 [-0.212, -0.077] (108/108 vs 96/112) | -0.105 [-0.171, -0.049] (108/108 vs 100/112) |
| Replication | -0.043 [-0.102, +0.011] (106/108 vs 105/112) | -0.008 [-0.055, +0.038] (106/108 vs 109/112) |

11 verdicts changed by the counting rule fixed in advance, all from fail to pass (3 C1 corrections and 8 local-evaluation trials). No pass-to-fail change survived the rule; the 15 that differ are replay artifacts of the offline tooling, listed in the doc. Pooled over both runs as corrected: -0.088 [-0.133, -0.049] ([RESULTS.md](RESULTS.md)).

**Flagsmith's own results pages.** Flagsmith results page, experiment 728 (primary): screenshot captured 2026-11-27T18:30:32Z; the corresponding raw results read is committed as `data/flagsmith_primary_results.json` (as_of 2026-11-27T08:38:18.776351Z). ![Flagsmith results page, experiment 728, captured 2026-11-27T18:30:32Z](assets/flagsmith-results-728.png)

Flagsmith results page, experiment 1142 (replication): screenshot captured 2026-11-27T18:30:32Z; the corresponding raw results read is committed as `data/flagsmith_replication_results.json` (as_of 2026-11-27T11:02:42.683924Z). ![Flagsmith results page, experiment 1142, captured 2026-11-27T18:30:32Z](assets/flagsmith-results-1142.png)

Primary: Flagsmith reports a lift of -14.3% for the skill, a credible interval of [-0.208, -0.078] on the absolute difference, and a skill chance to win of about 0.0009%. The decision rule fixed before the first trial (win probability at least 95%, interval excludes zero, guardrail not worse) is met by the prompt arm.

**Runner-error trial.** `trial-45947367007-33` (skill, react) ended in a `UnicodeDecodeError` in the runner after the agent step. Its exposure was recorded, and no verdict or event was sent, so Flagsmith counts it as an exposed non-conversion for the skill arm: Flagsmith's 96/112 includes it, while our own-log analysis excludes it from the denominator (96/111). The decode bug was fixed afterwards (`errors="replace"`) and did not recur in the 220 replication trials.

<!-- REPLICATION:START -->
We ran the whole experiment a second time, as its own Flagsmith experiment with the same frozen setup: the prompt reached 106 of 108 (98.1%) and the skill 105 of 112 (93.8%). Flagsmith reports a lift of -4.5% for the skill, a credible interval of [-0.097, +0.007] that includes zero, and a skill chance to win of about 4.6%. The replication points the same way with a smaller gap, and by the same rule it is inconclusive on its own, so the pre-registered decision rests on the primary alone. Flagsmith's counts match our log exactly in both runs, there were zero runner errors, and the skill was loaded in 112 of 112 skill trials and 0 of 108 prompt trials. Both runs are in [RESULTS.md](RESULTS.md).
<!-- REPLICATION:END -->

**Round 04: the winner ships through the same flag.** On 2026-11-27 the replication experiment was completed in Flagsmith with rollout decision `control` (the official prompt, the primary's winner), and a check of 5 fresh identities all returned `prompt`; 5 confirmation trials were dispatched in rollout mode and are excluded from the analysis. All 5 confirmation trials (stage `rollout`, no events sent) were served `prompt` and passed the wiring check.

What the 18 root-caused failures show:

| Cause | Skill | Prompt |
|---|---|---|
| Browser SDK entry or unbound `fetch` loses events (React) | 10 | 0 |
| Local evaluation against the grader emulator (Node) | 4 | 0 |
| Test needed credentials at import (graded C1 fail, corrected to pass) | 2 | 1 |
| Reload served from an in-process cache the agent added (Node) | 1 | 0 |

In the React failures the page and button were right and only event delivery was lost. The prompt sends the agent to a docs page that shows the correct browser import, and the skill had no import path. Skill v2 adds the exact import per runtime, one targeted docs read, and verification in the runtime that sends the events. Details: [RESULTS.md](RESULTS.md), [failure labels](docs/failure-labels.md), [blind audit](docs/blind-audit.md).

**Per stack** (exploratory, not part of the decision; passes/trials, runner-error trial excluded; the stack was drawn at random per trial, so cells are small):

| Stack | Primary prompt | Primary skill | Replication prompt | Replication skill |
|---|---|---|---|---|
| react | 36/36 | 27/37 | 32/34 | 25/27 |
| node | 39/39 | 36/41 | 30/30 | 35/39 |
| python | 33/33 | 33/33 | 44/44 | 45/46 |

The primary gap sits in React for the skill arm (27/37), and the replication's React cell for the skill arm is 25/27. Full table: [RESULTS.md](RESULTS.md).

### Cost and speed

Each cell is `mean / median / p90` per trial, computed from the trial logs ([RESULTS.md](RESULTS.md) has every statistic, including cost in dollars and duration for both runs). Tokens are input plus output, in millions.

| Run, arm (trials) | Turns | Tokens (M) | Cost (USD) | Duration (s) |
|---|---|---|---|---|
| Primary, prompt (108) | 84.9 / 80.0 / 116.2 | 4.50 / 4.13 / 7.10 | 0.101 / 0.090 / 0.156 | 499 / 500 / 764 |
| Primary, skill (111) | 64.8 / 58.0 / 89.0 | 2.79 / 2.02 / 5.02 | 0.082 / 0.052 / 0.163 | 358 / 207 / 720 |
| Replication, prompt (108) | 86.6 / 80.0 / 124.3 | 4.60 / 4.06 / 7.53 | 0.104 / 0.088 / 0.168 | 483 / 470 / 714 |
| Replication, skill (112) | 62.8 / 57.0 / 90.7 | 2.75 / 2.28 / 4.79 | 0.078 / 0.063 / 0.136 | 320 / 227 / 746 |
| *Passing trials only* | | | | |
| Primary, skill (96) | 62.0 / 55.5 / 85.0 | 2.56 / 1.86 / 4.85 | 0.071 / 0.049 / 0.133 | 308 / 177 / 617 |
| Replication, prompt (106) | 86.2 / 80.0 / 118.5 | 4.57 / 4.01 / 7.35 | 0.103 / 0.088 / 0.167 | 477 / 470 / 704 |
| Replication, skill (105) | 62.2 / 57.0 / 86.6 | 2.71 / 2.25 / 4.68 | 0.077 / 0.062 / 0.131 | 306 / 213 / 676 |

All 108 primary prompt trials passed, so its passing-only row equals its all-trials row.

What the data show:

- **The skill arm is cheaper and faster at the mean and the median, in both runs, but not twice as cheap.** Relative to the prompt arm, the primary means are turns -24%, tokens -38%, cost -19% and duration -28%; the replication means are -28%, -40%, -25% and -34%. At the median the differences are larger (primary cost -42%, replication cost -29%).
- **At the 90th percentile the cost and duration advantage mostly disappears.** Skill p90 cost is $0.163 against $0.156 in the primary (+5%) and $0.136 against $0.168 in the replication (-19%); p90 duration is 720 s against 764 s (-6%) and 746 s against 714 s (+4%).
- **Failing trials are not the cheap ones here.** The slow, expensive tail of the skill arm contains its failures: with failures removed, the skill's primary p90 cost falls from $0.163 to $0.133 and its p90 duration from 720 s to 617 s. The passing-only rows therefore show the skill at -15% (primary) and -22% (replication) p90 cost against the prompt arm.
- Cost and speed are descriptive. They do not enter the pre-registered decision, which is about `integration_verified`.

**Why the cost is small.** Most input tokens are cache reads, billed at $0.015 per million against $0.15 for fresh input, so about 4 million input tokens cost about $0.09.

**How the limits relate to the pilot rule.** The pre-registered rule is limit = 1.5 x the pilot's 90th percentile. The first pilot, at a 60-turn cap, hit the cap on every trial, so the plain rule was unusable. At a 200-turn cap the pilot trials ended on their own (59 to 161 turns, p90 about 146), which gives 220 turns, and 12 million tokens is 1.5 x the pilot p90 of about 7 million. A typical trial used 57 to 80 turns (the medians above), so the limits rarely bind: `over_budget` fired once per arm in the primary and not at all in the replication. The guardrail worked as a safety net, not as a metric that separates the arms.

### Proposed skill v2 (untested)

Skill v2 ([`skill/flagsmith-ab-test-v2/`](skill/flagsmith-ab-test-v2/SKILL.md)) is a proposal: fixes drawn from the failure analysis, written after the primary results. **All of v2 is untested.** It was never run as an experiment arm (the declared follow-up was not started because the spending cap was reached, see [EXPERIMENT.md](EXPERIMENT.md)), and its results and ship steps (read results, decision rule, approval gate, rollout, verify) were never run against live Flagsmith by an agent following the skill. What it proposes:

1. Create the multivariate flag with a keyed variation, the conversion metric and the experiment, then start it.
2. Wire the right SDK for the runtime, with the exact import per runtime, and identify the visitor once.
3. Verify in the real runtime that sends the events, not in a side script.
4. Read the results with `--json --jq`, apply the agreed decision rule, ask a human before any production change, then ship the winner through the same flag and verify it with fresh identities.

v1 is what was measured. Every result in this README is for v1 and the official prompt.

### How Handoff uses Flagsmith

| Flagsmith feature | What Handoff does with it |
|---|---|
| Multivariate flag with a keyed variation | `onboarding_method`: `prompt` / `skill`, 50/50 |
| Experiment-flag read that records the exposure | The runner reads the flag with the trial ID before the agent starts |
| `trackEvent` conversions | `integration_verified` and `over_budget` per trial, with the same identity |
| Two metrics | Primary `integration_verified`, guardrail `over_budget` |
| Experiment with results and inference | Credible interval and chance to win from Flagsmith, cross-checked against our log |
| Second experiment on the same flag | The replication runs as its own experiment |
| End an experiment and roll out the winner | The replication experiment was completed with rollout decision `control` (the prompt), and fresh identities return it from the same flag |
| CLI and skills | The skill drives the whole setup through the `flagsmith` CLI and the SDKs |

Flagsmith is the experiment engine here, not a logging side channel. Every feature and the file that uses it: [docs/how-handoff-uses-flagsmith.md](docs/how-handoff-uses-flagsmith.md).

### Check your own app in 60 seconds

The grader is a standalone tool. It answers "does my Flagsmith experiment wiring record exposures and conversions?" for any web app, with no Flagsmith credentials and no traffic to the real service.

```bash
pip install playwright==1.63.0 mitmproxy && python -m playwright install chromium
(cd path/to/your/app && npm ci)
python -m grader --app-dir path/to/your/app --stack custom --start-cmd "npm start" \
  --url http://127.0.0.1:3000/ --flag your_flag --event signup_clicked \
  --click-selector "#signup" --variant-values "Sign up,Create account" --out result.json --report
```

`--stack react|node|python` keeps the built-in install, test and start steps. `--variant-values` is "control,variation". Exit code 0 is a pass, 1 a fail, 2 a grader error. `--report` prints one fix hint per failed check.

| Check | Means |
|---|---|
| C1 | the app starts (and its tests pass, on the built-in stacks) and the button can be clicked |
| C2 | an exposure event is recorded for the flag |
| C3 | the conversion is sent from the click, not on page load |
| C4 | exposure and conversion use the same visitor identity |
| C5 | the identity survives a reload and differs for a new visitor |
| C6 | the button text is the flag value Flagsmith returned |
| C7 | (diagnostic) no server key reaches the browser |

The same check runs in GitHub Actions:

```yaml
name: flagsmith-wiring
on: [push, pull_request]
jobs:
  wiring:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/checkout@v4
        with: { repository: vivekyarra/prompt-vs-skill, path: .grader }
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - uses: actions/setup-node@v4
        with: { node-version: "22" }
      - run: pip install playwright==1.63.0 mitmproxy
      - run: python -m playwright install --with-deps chromium
      - run: npm ci
      - run: |
          PYTHONPATH=.grader python -m grader --app-dir . --stack custom --start-cmd "npm start" \
            --url http://127.0.0.1:3000/ --flag your_flag --event your_conversion_event \
            --click-selector "#your-button" --variant-values "Control text,Variation text" \
            --out result.json --report
```

The grader's local emulator reports your flag as enrolled in a running experiment, so it verifies your code and not your Flagsmith project setup. To reuse the method for your own devtool, see "Adapt it to your devtool" in [docs/grader.md](docs/grader.md).

### Quick start

```bash
pip install playwright==1.63.0 mitmproxy requests flagsmith flask pytest pyyaml ruff
python -m playwright install chromium          # also needs Node 22
python -m runner --dry-run --scripted-agent-apply-reference --trial-id trial-readme-1 --out-dir out
pytest runner/tests tests analysis -q          # unit tests
python analysis/analyze.py --trials data/trials.jsonl \
    --flagsmith-json data/flagsmith_primary_results.json --out RESULTS.md   # regenerate results and figures
```

To run the whole experiment from GitHub Actions (preflight, ops, trials, collect, analyze) and for the environment variable names, see [docs/setup.md](docs/setup.md).

### Engineering

- **Pre-registered.** Question, metrics, decision rule, sample size and stopping rule were committed before the first production trial, in the freeze commit [`c74e237`](https://github.com/vivekyarra/prompt-vs-skill/commit/c74e23729987dd8d5b27c8ab2969cac6e2849fcc) (merged 2026-11-26T23:39:33Z, 1 minute 19 seconds before the first production trial record at 23:40:52Z; a git tag could not be created from our environment, so the commit link is the pointer). Every deviation and correction is logged in [EXPERIMENT.md](EXPERIMENT.md), and its "Amendments after the freeze" index lists every later edit: none changed the hypothesis, the metrics or the decision rule.
- **One variable.** Same agent, model, limits, task brief, sample apps and grader for both arms. Only the handoff differs ([fairness](docs/fairness.md)).
- **A grader that is itself tested.** One reference app per stack passes every check, and one broken copy per check fails exactly that check, in two interception modes.
- **Two sources of truth that agree.** Flagsmith's counts and our own trial log match exactly, per arm.
- **Audited passes.** A blind review of 24 passing diffs, arm hidden, found 24 real passes and 0 false passes.
- **Isolated credentials.** The experiment project is touched only by the runner. Agents work in a separate sandbox project, and `scripts/secret_scan.py` runs in CI.
- **Reproducible.** One command runs a full trial without credentials. CI runs lint, unit tests, the grader self-tests and an end-to-end trial.

**Scope.** What is measured:

- one agent harness and model (OpenCode 1.19.6 with `MiniMaxAI/MiniMax-M3.1-Flash`);
- small sample apps in React, Node and Python;
- the grader checks wiring from network behaviour against a local Flagsmith emulator, so `integration_verified` means the agent's code is wired correctly and does not cover the Flagsmith-side setup;
- the sample is 220 trials, below the original per-variant target, because of a spending cap (a logged deviation).

**Limitations.** Read these before generalising the result:

- **One harness, one model, and a cheap open one.** OpenCode 1.19.6 with `MiniMaxAI/MiniMax-M3.1-Flash`. Other agents and models were not tested. In particular Claude Code, the usual harness for Flagsmith's prompt, was not tested, so the result may not carry over to it.
- **Ceiling effect.** The official-prompt arm is near 100% (108/108 in the primary, 106/108 in the replication), so the experiment can show how far the skill falls short but not how much better a handoff could be. The task is small, and the brief pre-answers the questions the official prompt expects a human to answer (what to test, what success is, which Flagsmith, approval). That makes it easier than real onboarding.
- **SDK versions were not pinned.** Both arms resolved the same versions, by timing, because the arms were interleaved in the same batches ([fairness](docs/fairness.md)). A rerun after a new SDK release could differ.
- **Sampling temperature and seed were not recorded.** Neither was set or logged for either arm.
- **`integration_verified` is a wiring check.** The grader judges the code from network behaviour against a local emulator, so the metric does not cover the Flagsmith-side setup (flag, metric, experiment).

### Tech stack

| Layer | Choice |
|---|---|
| Orchestration | Python 3.12, GitHub Actions matrix |
| Experiment engine | Flagsmith Cloud (flag, metrics, experiment, results), Flagsmith Python SDK, Flagsmith CLI |
| Agent | OpenCode 1.19.6, `MiniMaxAI/MiniMax-M3.1-Flash` on Nebius Token Factory |
| Grader | Playwright (Chromium), mitmproxy, a local Flagsmith emulator |
| Sample apps | React (Vite), Node (Express), Python (Flask) |
| Analysis | Python standard library, Beta-Binomial cross-check, SVG figures |

### Project structure

```text
runner/      one-trial orchestrator (assign, run agent, grade, report)
grader/      Playwright + mitmproxy judge and local Flagsmith emulator, with self-tests
skill/       Agent Skill: flagsmith-ab-test (v1, frozen) and flagsmith-ab-test-v2
prompt/      the official Flagsmith setup prompt, unmodified
brief/       task brief shared by both variants
apps/        sample apps, reference solutions, broken fixtures
analysis/    trial-log analysis, Flagsmith cross-check, figures
data/        trial records, Flagsmith results snapshot, result notes
ops/         Flagsmith setup, snapshot, rollover and rollout scripts
scripts/     demo grader, preflight, secret scan
assets/      results and failure figures, video cards
docs/        architecture, Flagsmith usage, setup, grader, fairness, audits
tests/       repo-level checks (workflows, skill, scaffold)
EXPERIMENT.md  pre-registration, freeze log, deviations      RESULTS.md  generated results
```

### Docs

- [Architecture](docs/architecture.md) and [How Handoff uses Flagsmith](docs/how-handoff-uses-flagsmith.md)
- [Setup](docs/setup.md), [Grader](docs/grader.md) and [Fairness](docs/fairness.md)
- [Failure labels](docs/failure-labels.md), [Blind audit](docs/blind-audit.md) and [SDK notes](docs/flagsmith-sdk-notes.md)
- [Suggestions for Flagsmith](docs/flagsmith-contribution.md) and [Video script](docs/video-script.md)

### Built by

[Vivek Yarra](https://github.com/vivekyarra) for **Toggle Wars: The Flagsmith Experimentation Hackathon** (WeMakeDevs × Flagsmith), Track 01: Test something real. MIT licensed.
