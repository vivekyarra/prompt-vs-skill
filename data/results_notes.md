
## Notes on how to read these results

These notes are written by hand and appended verbatim by `analysis/analyze.py`. Every number in them comes from the tables above, `data/*.jsonl`, `docs/failure-labels.md` or `docs/blind-audit.md`.

### Headline

Flagsmith's own experiment results (read from the Production experiment "Handoff: Prompt vs Skill") and our own log agree exactly: the official prompt reached `integration_verified` in 108 of 108 trials, the Agent Skill (v1) in 96 of 112 (85.7%). Flagsmith reports a lift of -14.3% for the skill, a credible interval of [-0.208, -0.078] on the absolute difference, and a skill chance to win of about 0.0009%. The pre-registered decision rule (win probability at least 95%, interval excludes zero, guardrail not worse) is met by the prompt arm.

### Stage structure

| Stage | Trials | What it is |
|---|---|---|
| `primary` | 220 | The pre-registered experiment, one Flagsmith experiment, frozen configuration. The decision uses this stage alone. |
| `replication` | 220 (declared in `EXPERIMENT.md`) | A second run with the identical frozen configuration, in its own Flagsmith experiment, reported next to the primary result and never pooled into the decision. |
| `followup` | 110 (declared in `EXPERIMENT.md`) | An exploratory comparison of skill v2 against the official prompt. Skill v2 was written after the primary results, so it is reported alongside and never pooled. |

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
