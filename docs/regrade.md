# Offline regrade of the 440 saved agent diffs with the final grader

Method and counting rule were committed first (commit c29010b), before any regrade verdict was read; results below. Offline sensitivity analysis only: nothing is sent to Flagsmith, no event is created or altered, no `data/*.jsonl` record is edited, the pre-registered decision (primary 220 trials alone) and `RESULTS.md` are untouched.

## Method

- Inputs: `diff.patch`, `trial_record.json`, `grader_result.json` of the 440 artifacts (primary runs 45912277670, 45914099371, 45925699686, 45947367007, 45947370678; replication runs 45967764018, 45967760241, 45967755797).
- `scripts/regrade_diffs.py` copies `apps/<stack>`, applies the diff, runs the final grader as the runner did (`--mode proxy --reclaim-port`, the trial's flag, default 13 s waits). `.github/workflows/regrade.yml` fans out over 20 `ubuntu-latest` shards on a push to `regrade/run1`; an aggregate job merges `regrade_results.jsonl`. Reported run: 46004484352, commit e5d0af5, grader tree `814c52706be0da66043cf4617c3355bcd47fd1f9` (`git rev-parse HEAD:grader`); all 439 regrades report that one version. `scripts/regrade_summary.py` writes `data/regrade_summary.json` (it refuses an incomplete regrade).
- The agent's untracked `.env` / `.env.local` are not in the diffs (`git add -A` honours the agent's `.gitignore`). For every env name that added code reads and the grader does not supply, a placeholder goes into `.env` and `.env.local`: key-like names get a placeholder key (`ser.` for node/python, client key for react), flag-like names the trial's flag name; URLs, `DEBUG`, `DISABLED` are not supplied. The replay is therefore not identical to the original run, whose untracked file held whatever the agent wrote.
- A trial whose regrade verdict differs from the original is regraded twice more (3 runs).

## Counting rule (fixed in advance)

A trial's ORIGINAL verdict stands unless ALL of these hold: (1) the regrade verdict differs, (2) the cause is one of the two named grader changes: the C1 test-environment fix, or the environment-document emulator, and (3) the difference reproduces in 3 of 3 runs. Every other disagreement is LISTED and explained but not counted. Pass-to-fail flips are reported as prominently as fail-to-pass flips.

- Cause C1 fix: the original failed C1 and the regrade passes C1 (only the 40 trials graded before that fix, grader tree `3858b6b`, can have it).
- Cause environment document: the regrade result has the `local_evaluation` block (the app downloaded the environment document).
- Agreement is computed FIRST, on the trials NOT flagged as local evaluation (`data/flagged.jsonl`), as the share whose regrade verdict equals the original. Poor means below 95% (the 3 documented C1 corrections in `data/corrections.jsonl` are expected to differ and are left out of that rate; they are still listed). If it is poor, the offline replay is not faithful for those trials and the sensitivity table is NOT built from it; what can be reported is reported.

## What happened before this result (disclosure)

- A first fan-out (run 45999100805) failed every trial on a relative-path bug in the script (`git apply` could not open the patch); I read its log, which has apply errors and no verdict. Fixed, rerun.
- The second fan-out (45999409003, 439 rows) was read before the reported one. It showed the local-evaluation trials still failing C5/C6 for a grader reason (the exposure of the grader's own health-check request is flushed by the SDK timer inside the `load` phase and was taken for V1's identity), so `grader/` got a second post-freeze change (`docs/grader.md`, "Identity of a visitor under local evaluation"; only applies when the environment document was requested) and the self-tests were rerun. The script was also changed to tolerate an artifact without `diff.patch`/`grader_result.json`, to record `diff_bytes`, and to find `import.meta.env?.X`. None of this alters the counting rule. One shard of the reported run failed in `playwright install` (apt) and was rerun as is.
- The `?.` scanner fix is NOT in the reported run (found afterwards, see trial 45967760241-53 below); its single local rerun is reported as such.

## Results

Rows: 440. Regraded: 439. Trial 45947367007-33 (skill, react, runner error) has no `diff.patch`: not regradable, original verdict kept. 14 more diffs are 0 bytes (see 3 below).

**Agreement, non-flagged trials (computed first):** 413 of 431 give the original verdict (95.8%); without the 3 documented C1 corrections 413/428 (96.5%, above the 95% bar: not poor). Of the 428, 14 have an empty diff and cannot be replayed: on the 414 replayable ones 413 agree (99.8%).

**Counted by the rule: 11 verdict changes, all fail to pass (3 C1 fix + 8 environment document), 0 pass to fail.** All 26 differences:

1. 3 fail to pass, cause C1 fix, 3/3 runs, counted: 45914099371-7, -14 (skill, python), 45914099371-30 (prompt, node). These are the 3 documented corrections.
2. 8 fail to pass, cause environment document, 3/3 runs, counted: the 8 flagged skill-arm Node trials (4 primary, 4 replication). All pass C1-C7 now: 45914099371-12, 45925699686-4, 45947367007-3, 45947367007-49, 45967755797-40, 45967764018-22, -35, -55. Each downloaded the environment document and evaluated locally. Before the identity fix above they failed C5 (and C6) for a grader reason, not the app's.
3. 14 pass to fail, NOT counted: the artifact's `diff.patch` is 0 bytes (`capture_diff` runs `git diff --cached HEAD`, so an agent that committed its work leaves nothing). The replay has no code, no traffic, C2-C6 fail. 12 of 14 are the prompt arm. They are replay losses, not grader changes (no named cause): 45912277670-8 (in the first 40), 45947367007-24, -39, -54, -77, 45947370678-2, -28, -30, -75, 45967755797-57, -62, -66, 45967760241-49, 45967764018-12.
4. 1 pass to fail, NOT counted: 45967760241-53 (prompt, react). The diff reads `import.meta.env?.VITE_FLAGSMITH_ENVIRONMENT_ID`; my scanner missed the optional chaining, so no placeholder was written and the app never initialised Flagsmith. After the scanner fix a single local regrade passes (all checks), i.e. it agrees with the original.

Same verdict, different failed checks: 45967755797-1 (prompt, react, fails before and after). It reads `VITE_FLAGSMITH_ENVIRONMENT_KEY`; the original run saw no traffic (C2-C6 failed), which I infer means no key for that name existed then, the replay supplies a placeholder, the SDK initialises and the app's own test crashes (`i.init is not a function`, C1) and C6 fails. A consequence of the placeholder, not of the grader.

No difference is unexplained. Pass-to-fail changes (15) are all replay artifacts of my tooling; none reproduces a grader verdict.

## Sensitivity table

Denominator = every trial record of the arm (a runner error counts as not verified), as in Flagsmith. "As graded (log)" is `data/*.jsonl` as recorded; Flagsmith received 3 backfilled C1 corrections on top (108/108 and 96/112 = 107/108 and 94/112 + 1 prompt + 2 skill). "Regraded, counted" = as graded with the 11 counted changes; "raw" = every regrade verdict at face value on replayable trials (empty-diff and no-diff trials keep their original verdict).

| stage | source | prompt | skill | rates | difference (skill-prompt), 95% CI |
|---|---|---|---|---|---|
| primary | Flagsmith as sent | 108/108 | 96/112 | 100.0% / 85.7% | -0.140 [-0.212, -0.077] |
| primary | as graded (log) | 107/108 | 94/112 | 99.1% / 83.9% | -0.148 [-0.225, -0.080] |
| primary | regraded, counted rule | 108/108 | 100/112 | 100.0% / 89.3% | -0.105 [-0.171, -0.049] |
| primary | regraded, raw | 108/108 | 100/112 | 100.0% / 89.3% | -0.105 [-0.171, -0.049] |
| replication | Flagsmith as sent | 106/108 | 105/112 | 98.1% / 93.8% | -0.043 [-0.102, +0.011] |
| replication | as graded (log) | 106/108 | 105/112 | 98.1% / 93.8% | -0.043 [-0.102, +0.011] |
| replication | regraded, counted rule | 106/108 | 109/112 | 98.1% / 97.3% | -0.008 [-0.055, +0.038] |
| replication | regraded, raw | 105/108 | 109/112 | 97.2% / 97.3% | +0.001 [-0.048, +0.051] |

Beta(1,1) Beta-Binomial from `analysis/analyze.py` (`beta_binomial_diff`, seed 20261129). The raw replication row differs from the counted one only through trial 45967760241-53 (item 4). The skill arm gains 6 passes in the primary and 4 in the replication, the prompt arm 1; the sign of the primary difference is unchanged and its interval still excludes 0, the replication difference stays inside zero. This is a sensitivity analysis: the decision and `RESULTS.md` use the grader as it was.

## The 8 local-evaluation trials

All 8 pass C1-C7 in 3 of 3 regrades (list in item 2). Real Flagsmith counts Node local-evaluation exposures (`ops/rehearsal_node_localeval.py`, run 45998239172: 8 exposure identities for 6 Node-local plus 2 remote controls), so these are not an emulator-only pass.

## First 40 primary trials (graded by the pre-fix grader 3858b6b)

The 40 records with `grader_sha` starting `3858b6b` (runs 45912277670 = `a`, 45914099371 = `b`; arm p/s, stack n/r/p; P pass, F(failed checks); `*` = changed):

```
a1 p/n P>P; a2 s/r P>P; a3 s/r P>P; a4 p/r P>P; a5 p/p P>P; a6 s/r P>P; a7 p/n P>P; a8 p/n P>F(2,3,4,5,6)*
a9 s/n P>P; a10 s/r P>P; b1 p/p P>P; b2 p/n P>P; b3 s/r P>P; b4 p/r P>P; b5 p/r P>P; b6 s/r P>P
b7 s/p F(1)>P*; b8 p/p P>P; b9 p/r P>P; b10 p/n P>P; b11 s/r F(2,3,4)>F(2,3,4); b12 s/n F(2,4,5,6)>P*
b13 s/p P>P; b14 s/p F(1)>P*; b15 s/r P>P; b16 p/r P>P; b17 p/n P>P; b18 s/n P>P; b19 p/p P>P
b20 s/r F(2,3,4)>F(2,3,4); b21 p/n P>P; b22 p/n P>P; b23 s/r P>P; b24 s/r P>P; b25 s/n P>P; b26 s/n P>P
b27 p/r P>P; b28 p/r P>P; b29 s/r P>P; b30 p/n F(1)>P*
```

Yes, verdicts changed: 5 of 40. Three are the documented C1 corrections (b7, b14, b30). One is a local-evaluation trial (b12, flagged, environment document). One, a8, is a pass-to-fail replay artifact (0-byte diff, item 3), not a grader result. So beyond the 3 expected corrections the first 40 contain one already-flagged trial that now passes and one tooling artifact, nothing else.
