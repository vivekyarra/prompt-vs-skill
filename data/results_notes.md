
## Notes on how to read these results

These notes are written by hand and appended verbatim by `analysis/analyze.py`. Every number in them comes from the tables above, `data/*.jsonl`, `docs/failure-labels.md` or `docs/blind-audit.md`.

### Headline

Flagsmith's own experiment results (read from the Production experiment "Handoff: Prompt vs Skill") and our own log agree exactly: the official prompt reached `integration_verified` in 108 of 108 trials, the Agent Skill (v1) in 96 of 112 (85.7%). Flagsmith reports a lift of -14.3% for the skill, a credible interval of [-0.208, -0.078] on the absolute difference, and a skill chance to win of about 0.0009%. The pre-registered decision rule (win probability at least 95%, interval excludes zero, guardrail not worse) is met by the prompt arm.

### Stage structure

| Stage | Trials | What it is |
|---|---|---|
| `primary` | 220 | The pre-registered experiment, one Flagsmith experiment, frozen configuration. The decision uses this stage alone. |
| `replication` | 220 | A second run with the identical frozen configuration, in its own Flagsmith experiment, reported next to the primary result and never pooled into the decision. Completed; see the replication notes below. |
| `followup` | 110 (declared in `EXPERIMENT.md`) | An exploratory comparison of skill v2 against the official prompt. Status: not run; the spending cap was reached after the replication. Skill v2 is published for a future follow-up. |

This file analyses the `primary` stage (`--stage primary`, the default). Other stages are analysed with `--stage replication` and `--stage followup`.

### Two configuration tuples

Section 4 lists two configurations among the 220 records. The first 40 trials ran on repository commit `c74e23729987` with grader `3858b6bb4182`; the remaining 180 ran on `55184be6702b` with grader `746ccd2c5e86`. The agent, model, turn and token limits, skill, official prompt and task brief are identical in both (same hashes). The only change between them is a grader fix documented in `EXPERIMENT.md` (the "grader test-environment bug"): the app's own test (C1) now gets the placeholder credential variables when it fails without them. The fix is one-directional, so no earlier pass can change. Three of the first 40 verdicts were corrected after replaying each trial three times with the final grader (`data/corrections.jsonl`; two skill, one prompt). The "Post-freeze corrections" section above reports both views, as originally graded and as corrected. The pre-registration also asks for the results with and without the first 40 trials (verdicts as corrected):

| Subset | prompt passed/n | skill passed/n |
|---|---|---|
| first 40 trials (earlier grader) | 20/20 | 17/20 |
| remaining 180 trials (final grader) | 88/88 | 79/92 |
| all 220 | 108/108 | 96/112 |

The difference has the same direction and a similar size in both subsets.

### Trials that enabled local evaluation

Four skill-arm Node trials (`data/flagged.jsonl`) enabled the SDK's local evaluation, keyed on the `ser.` prefix of the grader's placeholder server key. Local evaluation reads an environment document that the grader's local emulator does not serve, so these trials could not record an exposure under the grader. They are kept as failures in every primary number, which is the pre-registered rule. The sensitivity section above shows the skill arm at 96/108 with those four excluded; the prompt arm is 108/108 either way. Whether a real environment document would have carried the experiment enrolment is not established, so counting them as passes would be a guess.

### Blind audit of passing diffs

To check that the grader's passes are real, 24 passing diffs (12 per arm, drawn at random from the 220) were shuffled, given random ids and reviewed against C2-C6 without knowing which arm produced them. 24 of 24 were real passes and none was a false pass (`docs/blind-audit.md`).

### Failure labels

All 18 graded failures were root-caused from each trial's diff and grader result (`docs/failure-labels.md`). One further skill trial ended in a runner error and has no grader result.

| Cause | Skill | Prompt |
|---|---|---|
| Browser SDK entry or unbound `fetch` loses events (React) | 10 | 0 |
| Local evaluation against the grader emulator (Node) | 4 | 0 |
| Test needed credentials at import (graded C1 fail, corrected to pass) | 2 | 1 |
| Reload served from an in-process cache the agent added (Node) | 1 | 0 |

The 15 skill failures that remain after corrections plus the runner-error trial make up the 16 non-passing skill exposures (96 of 112). In the React failures the page and button were right and only event delivery was lost. Every one of those agents had verified its work with a Node script, which cannot show a browser-only problem. The prompt arm sends the agent to the Flagsmith docs page, which shows the correct browser import. Skill v2 encodes the resulting fixes (`docs/fairness.md`, "Skill v2").

### Replication notes

All 220 replication trials ran on repository commit `fa46bf2` with the identical frozen configuration: the same skill (`eb5aa00e5679`), grader (`746ccd2c5e86`), official prompt, task brief, turn and token limits as the primary's final 180 trials. There were no runner errors. Flagsmith's counts match our log exactly in both arms (prompt 108 exposures and 106 conversions, skill 112 and 105).

| Run | prompt passed/n | skill passed/n | Flagsmith lift | Flagsmith credible interval (absolute difference) | skill chance to win |
|---|---|---|---|---|---|
| primary (the decision) | 108/108 (100%) | 96/112 (85.7%) | -14.3% | [-0.208, -0.078] | about 0.0009% |
| replication | 106/108 (98.1%) | 105/112 (93.8%) | -4.5% | [-0.097, +0.007] | about 4.6% |

The replication points the same way with a smaller gap. Its interval includes zero, so by the same rule the replication alone is inconclusive. The pre-registered decision rests on the primary alone. Pooled, secondary and not the decision: prompt 214/216, skill 201/223 (our own-log denominators, which exclude the one primary runner error). Guardrail `over_budget` was 0 in both replication arms (1 in each arm in the primary).

Treatment fidelity in the replication: the skill was loaded through the agent's skill tool in 112 of 112 skill trials and in 0 of 108 prompt trials. The primary records do not carry the field.

Cost and effort per trial (means over analysed trials; tokens are input plus output):

| Run | Arm | Mean turns | Mean tokens | Mean cost (USD) |
|---|---|---|---|---|
| primary | prompt | 84.9 | 4503172 | 0.101 |
| primary | skill | 64.8 | 2789320 | 0.082 |
| replication | prompt | 86.6 | 4604639 | 0.104 |
| replication | skill | 62.8 | 2752289 | 0.078 |

In both runs the skill arm used fewer turns, tokens and dollars per trial than the prompt arm.

Local-evaluation trials in the replication: four skill-arm Node trials (`trial-45967755797-40`, `trial-45967764018-22`, `trial-45967764018-35`, `trial-45967764018-55`, listed in `data/flagged.jsonl`) enabled the SDK's local evaluation and could not record an exposure under the grader's local emulator. They are counted as failures in every number above, as pre-registered. Excluding them, the replication is prompt 106/108 and skill 105/108 (97.2%); without these four, the skill's remaining replication failures are two React trials and one Python trial. As in the primary, whether a real environment document would have carried the experiment enrolment is not established.

### Skill v2 and the follow-up

Skill v2 was not run as an experiment arm. The Nebius spend budget was used up by the primary and the replication, so the declared 110-trial follow-up was not started. Skill v2 encodes the fixes from the failure analysis and is published for a future follow-up; it is not measured.

### Round 04: shipping the winner through the same flag

On 2026-11-27 at about 11:05Z the replication experiment was completed in Flagsmith with rollout decision `control`, which is the official prompt and the primary's winner. A check of 5 fresh identities all returned `prompt`. Five confirmation trials were dispatched in rollout mode (stage `rollout`, no events sent, excluded from every analysis above).

### Corrections footnote

**Three primary verdicts were corrected after a grader bug fix.** The trials are `trial-45914099371-14` (skill, python), `trial-45914099371-7` (skill, python) and `trial-45914099371-30` (prompt, node), all originally C1 failures: the app's existing test ran without the placeholder credential variables. The fix is one-directional (clean run first, retry with placeholders only if it failed), so no earlier pass could change. Each trial was replayed 3 of 3. All three flips are fail to pass (two skill, one prompt); none went from pass to fail. The three `integration_verified` events were sent to Flagsmith afterwards with `ops/backfill_events.py` (late events were verified to be counted), so Flagsmith's counts include them. As originally graded: prompt 107/108, skill 94/112. As corrected, which equals Flagsmith's counts: prompt 108/108, skill 96/112. The per-arm rates of the first 40 trials were already visible when the correction was decided (as graded: prompt 19/20, skill 15/20).
