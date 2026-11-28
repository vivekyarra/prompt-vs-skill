# Runbook: skill v2 follow-up (110 trials, exploratory)

Written 2026-11-28. The follow-up declared in `EXPERIMENT.md` ("Follow-up experiment: skill v2 vs the official prompt") has not run. This is the ordered list of steps to run it once the owner raises the spend cap. Nothing in this file was run against Flagsmith, GitHub Actions or the model provider; what was checked locally, and how, is marked in "What was verified".

**Rules that hold for every step**

- The follow-up is **exploratory**. It has no decision rule, it changes nothing about the primary decision, and its trials are **never pooled** with the primary or the replication.
- N is **110 records in total**, runner errors included. No top-up batches. Do not stop early and do not extend because of how a result looks; the checks between batches print no pass rate on purpose.
- Every trial spends the owner's Nebius balance and records a real exposure in the Production experiment project. Do not dispatch on an assumption.
- `grader/`, `skill/flagsmith-ab-test/`, `prompt/` and `brief/` stay untouched. `EXPERIMENT.md` is append-only.

## 0. Preconditions (all must be true before step 2)

1. **The owner has said the cap is raised**, in writing, with a number in USD of recorded spend for this follow-up. Use it as `--cap-usd` below. See "Budget" for what to expect.
2. **The owner has appended an entry to `EXPERIMENT.md`** that allows the run. Two things in that file stand in the way today, and only an appended entry can settle them (draft text is in "Text to append to EXPERIMENT.md" at the end):
   - The "Stop line" section says all trials end by 28 Nov 2026 12:00 IST. It names the primary and the replication; the follow-up was declared after it. That time has passed.
   - The declaration says the follow-up uses the identical grader as the primary run. The grader tree changed afterwards (the environment-document amendment). The follow-up will be graded by tree `814c52706be0`, the primary was graded by `3858b6bb4182` and `746ccd2c5e86` (`grader_sha` in `data/trials.jsonl`).
3. **The branch with this runbook is merged to `main`.** The steps need the changes listed in "What changed in the code". Dispatch every workflow on `main`.
4. `ruff check .`, `pytest runner/tests tests analysis -q` and `python scripts/secret_scan.py` pass on that commit.
5. Dispatch **preflight** with `environment=production`. It only lists models and checks credentials; it costs nothing. All rows must be good.
6. The owner reads the Nebius balance and writes it down. It is read again after 40 trials (step 4).

## 1. Rehearse in Development (recommended; about 2 trials of spend)

This exercises the one path that has never run against live Flagsmith: creating a new experiment on a flag whose previous experiment is already completed.

| Workflow | Inputs |
|---|---|
| `ops` | `environment=development`, `ref=main`, `script=ops/rollover_experiment.py`, `args=Development Handoff_pilot_2 Handoff_skill_v2_rehearsal --hypothesis=followup` |
| `trials` | `count=2`, `environment=development`, `assign=flagsmith`, `stage=followup`, `skill_dir=skill/flagsmith-ab-test-v2`, everything else default |
| `ops` | `environment=development`, `ref=main`, `script=ops/rollout_winner.py`, `args=Development prompt` |

Check: the first `ops` log ends with `VERIFY 50/50 prompt/skill and running: PASS` and `NEW EXPERIMENT ID`. Both trial jobs finish without `runner_error`, and each record has `stage` `followup`, `skill_dir` `skill/flagsmith-ab-test-v2`, `environment` `development`. The last `ops` log ends with `ROLLOUT VERIFY (prompt): PASS`.

Do **not** collect these two records into `data/`: `analysis/collect.py` routes by stage, so Development follow-up records would land in `data/followup.jsonl` (the analysis ignores them, the file would still be wrong).

If the first step fails, stop. Read the Flagsmith error in the log; nothing was started in Production.

## 2. Start the Production experiment 'Handoff: Skill v2'

State today: experiment 1142 is completed with rollout decision `control`, so `onboarding_method` serves `prompt` to everyone. Its name in Flagsmith is `Handoff: Replication` (`data/flagsmith_replication_results.json`), not the label used in the object table of `EXPERIMENT.md`.

| Workflow | Inputs |
|---|---|
| `ops` | `environment=production`, `ref=main`, `script=ops/rollover_experiment.py`, `args=Production Handoff:_Replication Handoff:_Skill_v2 --hypothesis=followup` |

`ops.yml` splits `args` on spaces and has no quoting. Underscores in the two names stand for spaces; the colon is passed as it is. With the `gh` CLI the same dispatch is:

```bash
gh workflow run ops.yml --repo vivekyarra/prompt-vs-skill --ref main \
  -f environment=production -f ref=main -f script=ops/rollover_experiment.py \
  -f args='Production Handoff:_Replication Handoff:_Skill_v2 --hypothesis=followup'
```

What the script does on this path: it finds the old experiment, sees it is completed and leaves it alone, creates 'Handoff: Skill v2' on the same flag with the two existing metrics, 100% enrolment and `skill` at 50%, starts it and verifies the split. It is idempotent: a second run finds the new experiment and only verifies.

Check in the log:

- `old experiment 1142 status=completed` and `old experiment already completed; not completing again`.
- `new experiment created id <ID>`, then `VERIFY 50/50 prompt/skill and running: PASS`, then `NEW EXPERIMENT ID: <ID> name='Handoff: Skill v2'`. Write the id down.
- If it prints `old experiment 'Handoff: Replication' not found; refusing`, nothing was changed. Use `Handoff:_Prompt_vs_Skill` (experiment 728, also completed) as the old name.

**From this moment the Production flag serves 50/50 again, not the rollout winner.** Step 7 restores it. Do not leave the experiment running longer than the trials need.

## 3. Batch 1: 10 trials

| Workflow | Inputs |
|---|---|
| `trials` | `count=10`, `environment=production`, `assign=flagsmith`, `stage=followup`, `skill_dir=skill/flagsmith-ab-test-v2`. Leave `model`, `max_turns`, `max_tokens`, `price_in`, `price_out` at their defaults (the frozen values: `MiniMaxAI/MiniMax-M3.1-Flash`, 220, 12000000, 0.15, 0.6) |

```bash
gh workflow run trials.yml --repo vivekyarra/prompt-vs-skill --ref main \
  -f count=10 -f environment=production -f assign=flagsmith -f stage=followup \
  -f skill_dir=skill/flagsmith-ab-test-v2
```

The `prepare` job now refuses, before any trial job starts, `stage=followup` without the v2 folder, `stage=followup` with `assign=rollout`, and the v2 folder in production under any other stage. It cannot catch a dispatch that leaves **both** `stage` and `skill_dir` at their defaults: that would run skill v1 trials labelled `primary` inside the new experiment. Read the inputs twice.

The workflow runs 5 trial jobs in parallel (`max-parallel: 5`), one matrix job per trial, each with a 45-minute timeout.

After the run finishes, collect (step 5 commands, one run id) and check:

```bash
python scripts/check_followup_records.py data/followup.jsonl --expect 10 --cap-usd <CAP>
```

It must end with `FOLLOW-UP RECORDS: OK`. It checks, per record: `stage`, `skill_dir`, `environment`, `assignment`, agent, model, turn and token limits, that the prompt and brief hashes are the primary run's, one skill tree, one grader tree, no clash with earlier trial ids, runner errors, that the skill arm loaded the skill and the prompt arm did not, that every pass sent its event, and the projected spend at 110 trials. Expected trees on `main` today: skill `274b7bef8135`, grader `814c52706be0`.

Then cross-check the counts with Flagsmith (counts only, the inference block is removed by the script):

| Workflow | Inputs |
|---|---|
| `ops` | `environment=production`, `ref=main`, `script=ops/exp_counts.py`, `args=Production Handoff:_Skill_v2` |

Exposures per arm must equal the per-arm record counts printed by the check script. Flagsmith's warehouse can lag; if the counts are short, wait a few minutes and run it again before treating it as a mismatch.

## 4. Batches 2 and 3: 30, then 70

Same inputs as batch 1 with `count=30`, then `count=70`. This mirrors the primary's plan (10, then up to 40 in total, then a pause for the balance).

- After batch 2 (40 records): run the check script with `--expect 40`, and **the owner reads the Nebius balance again**. The recorded `cost_usd` uses cache-read pricing; the drop in the real balance is the number that counts. If the real drop per trial times 110 is over the cap, stop.
- After batch 3 (110 records): run the check script with `--expect 110`.

Batch 3 may be split into two runs dispatched together (`count=35` twice) to halve the wall time. The primary's records come from five runs of 10, 30, 20, 80 and 80 trials and the replication's from three runs of 74, 73 and 73 (counts per run id in `data/trials.jsonl` and `data/replication.jsonl`).

### Stop conditions

Stop dispatching and report to the owner if any of these happens. None of them depends on a pass rate.

| Condition | Where it shows |
|---|---|
| Any `FAIL` line from `scripts/check_followup_records.py` (wrong stage, wrong skill folder, wrong model or limits, more than one grader or skill tree, runner errors over 5%, prompt arm loaded the skill, no skill-arm trial loaded the skill, projected spend over the cap, more than 110 records) | check script |
| Sample ratio p below 0.001 at any point, or the skill share outside 45% to 55% at 110 records | check script |
| Flagsmith exposures per arm differ from the record counts after the warehouse has caught up | `ops/exp_counts.py` |
| Every trial of a run ends as a runner error naming "not enrolled in a running experiment" (the experiment is not running; no agent ran, nothing was spent) | job logs, check script |
| The real Nebius balance drop per trial, times 110, is over the cap | owner |
| 110 records reached | check script |

A run that was stopped is reported with the number it reached. Records already collected stay.

## 5. Collection

`collect.yml` fires after every `trials` run but **commits only `data/trials.jsonl`** to the `data` branch; it does not commit `data/followup.jsonl`. Collect by hand, per run id. Artifacts are kept for 30 days (`retention-days: 30`) and also hold `diff.patch`, which the failure labels need, so download them all.

```bash
mkdir -p /tmp/followup/artifacts /tmp/followup/collected
gh run download <RUN_ID> --repo vivekyarra/prompt-vs-skill --dir /tmp/followup/artifacts/<RUN_ID>   # once per run
python analysis/collect.py --artifacts-dir /tmp/followup/artifacts --out /tmp/followup/collected/trials.jsonl
ls /tmp/followup/collected            # must list followup.jsonl and nothing else
cp /tmp/followup/collected/followup.jsonl data/followup.jsonl
wc -l data/followup.jsonl
```

The scratch `--out` keeps `data/trials.jsonl` out of reach: `collect.py` writes primary-stage production records to its `--out` file, and a mislabelled record must never be appended to the primary log. If `/tmp/followup/collected` holds a `trials.jsonl`, a `pilot.jsonl` or a `rollout.jsonl`, a run was dispatched with the wrong inputs: stop. Re-running `collect.py` after each batch is safe, it skips trial ids it has already written.

Fallback when artifacts are gone but logs remain: `python scripts/fetch_trial_records.py <RUN_ID> /tmp/followup/artifacts/<RUN_ID>.jsonl`, one output file per run (the script overwrites its output file), then the same `collect.py` command.

Keep the artifact folders. Copy the saved diffs of every failed trial somewhere durable before the 30 days are over.

## 6. Flagsmith snapshot (once, at 110 records, before the experiment is ended)

| Workflow | Inputs |
|---|---|
| `ops` | `environment=production`, `ref=main`, `script=ops/snapshot_results.py`, `args=Production Handoff:_Skill_v2` |

This is the only step that reads Flagsmith's inference (lift, interval, win probability). Do not run it before the last trial has finished. The log must end with `snapshot done: as_of=... fresh=True`.

```bash
gh run view <OPS_RUN_ID> --repo vivekyarra/prompt-vs-skill --log \
  | grep -o 'SNAPSHOT_JSON: .*' | sed 's/^SNAPSHOT_JSON: //' > data/flagsmith_followup_results.json
python -c "import json; d=json.load(open('data/flagsmith_followup_results.json')); print(d['experiment'], d['as_of'], d['fresh'])"
```

The file name `data/flagsmith_followup_results.json` follows the two existing snapshots. Then check the counts before going on:

```bash
python analysis/analyze.py --trials data/trials.jsonl --flagsmith-json data/flagsmith_primary_results.json \
  --followup-trials data/followup.jsonl --followup-flagsmith-json data/flagsmith_followup_results.json \
  --out /tmp/followup/check.md --figures-dir /tmp/followup/figs
grep -A8 "Follow-up: cross-check" /tmp/followup/check.md
```

It must say `All counts match.` If it says `Counts differ`, the warehouse has not caught up or a trial lost an event: wait, take the snapshot again and repeat. Do not go to step 7 until the snapshot is the one you will report, because a completed experiment refuses a refresh.

## 7. End the experiment and put the winner back on the flag

| Workflow | Inputs |
|---|---|
| `ops` | `environment=production`, `ref=main`, `script=ops/rollout_winner.py`, `args=Production prompt` |

`prompt` here is not a verdict on the follow-up. The follow-up has no decision rule, so the flag goes back to what the pre-registered primary decision shipped. The log must end with `ROLLOUT VERIFY (prompt): PASS` (5 fresh identities all get `prompt`). Completion is final.

## 8. Analysis and where the result goes

Regenerate `RESULTS.md` with the follow-up section added after the replication:

```bash
python analysis/analyze.py --trials data/trials.jsonl \
  --flagsmith-json data/flagsmith_primary_results.json \
  --replication-trials data/replication.jsonl \
  --replication-flagsmith-json data/flagsmith_replication_results.json \
  --followup-trials data/followup.jsonl \
  --followup-flagsmith-json data/flagsmith_followup_results.json \
  --out RESULTS.md
```

The committed `RESULTS.md` had its two "Screenshot" rows edited by hand after it was generated (commit `5337bce`), so the regeneration puts the placeholder text back. Restore the two rows:

```bash
python3 - <<'E'
import subprocess
old = subprocess.run(["git", "show", "HEAD:RESULTS.md"], capture_output=True, text=True, check=True).stdout.splitlines()
keep = {ln.split(":")[0]: ln for ln in old if ln.startswith("| Screenshot | Flagsmith results page, experiment ")}
new = open("RESULTS.md", encoding="utf-8").read().splitlines()
out = [keep.get(ln.split(":")[0], ln) if ln.startswith("| Screenshot | ") else ln for ln in new]
open("RESULTS.md", "w", encoding="utf-8").write("\n".join(out) + "\n")
print("restored", sum(a != b for a, b in zip(new, out)), "screenshot row(s)")
E
git diff --stat RESULTS.md assets/
```

`git diff RESULTS.md` must then show only: the "Generated by" timestamp on line 5, the new section, and nothing else. The two SVG figures change only in their timestamp. If any primary or replication number moved, stop: something other than the follow-up changed.

The new section is headed **"Follow-up: skill v2 (exploratory; reported alongside, never pooled, no decision rule)"**. It holds Flagsmith's numbers (exposures, rate, lift, credible interval, win probability, as Flagsmith reports them), our own log with a 95% credible interval per arm, the count cross-check, sanity checks (record count against 110, skill folder, sample ratio, runner errors, guardrail, configuration tuples, the grader-tree note), cost and speed per arm (turns, tokens, cost, duration), failures per check with the list of failed trials, the per-stack table and treatment fidelity. It prints no own-log win probability and no verdict.

Do **not** use `python analysis/analyze.py --stage followup --out RESULTS.md`. That older path still works for a quick look into a scratch file (give it `--out` and `--figures-dir` outside the repository), but it writes a whole report titled as the primary result, applies the decision rule, and by default overwrites `RESULTS.md` and both figures in `assets/`.

Then, by hand, with numbers taken only from the new section:

1. **`data/results_notes.md`**, paragraph "Skill v2 and the follow-up": it says the follow-up was not started. Rewrite it (this file is hand-written prose, not a trial log), then regenerate and restore the screenshot rows again.
2. **Failure labels**: label each failed follow-up trial from its saved diff, as `docs/failure-labels.md` does for the two earlier runs. The declaration asks for failure causes, not just counts.
3. **README sentence.** Print it from the data:

   ```bash
   python analysis/analyze.py --followup-trials data/followup.jsonl \
     --followup-flagsmith-json data/flagsmith_followup_results.json --print-followup-sentence
   ```

   It replaces "skill v2 encodes the fixes and is not yet tested ([blockers](docs/BLOCKERS.md))" at the end of the README's opening result paragraph. The other places that call v2 untested are the scope paragraph ("the proposed v2 is untested"), the table row "Proposes skill v2 (untested)" and the section "Proposed skill v2 (untested)". Keep the words "exploratory" and "never pooled" next to the numbers. Then run `python scripts/check_readme_numbers.py`.
4. **`EXPERIMENT.md`**: append a record entry (run ids, experiment id, dates, record count, runner errors, the snapshot file, that the experiment was completed with `control`). Append only.
5. **`docs/BLOCKERS.md`**: items 1 and 5 (the follow-up and its Flagsmith screenshot at `assets/flagsmith-results-<ID>.png`).
6. `ruff check .`, `pytest runner/tests tests analysis -q`, `python scripts/secret_scan.py`. Commit on a branch.

How to word the result: skill v2 was written after the primary results, on one agent and one model, with 110 trials. Report the two pass rates, their intervals and the failure causes. A comparison with skill v1 across runs is not like for like (different run, different grader tree); the offline regrade table in `RESULTS.md` is the closer reference for v1.

## Budget

Computed from the 440 recorded trials of the primary and the replication (`cost_usd`, runner-error trial included, percentiles by linear interpolation):

| Trials | n | Mean per trial | p90 per trial | Max per trial | 110 x mean | 110 x p90 | 110 x max |
|---|---|---|---|---|---|---|---|
| overall | 440 | $0.0912 | $0.1629 | $0.3944 | $10.03 | $17.91 | $43.38 |
| prompt arm | 216 | $0.1027 | $0.1672 | $0.3679 | $11.30 | $18.39 | $40.47 |
| skill arm (v1) | 224 | $0.0800 | $0.1581 | $0.3944 | $8.80 | $17.39 | $43.38 |

- Expected recorded spend for 110 trials: about **$10.03**. Worst cases: **$17.91** if every trial cost the p90, **$43.38** if every trial cost the most expensive trial seen.
- **The cost of skill v2 is unknown.** v2 is longer than v1 and adds steps; the skill-arm row above is v1. Half of the trials are the prompt arm, whose cost is known.
- The recorded cost uses cache-read pricing (`EXPERIMENT.md`). With no cache discount at all, the same token counts would cost $0.5677 per trial, $62.45 for 110. The balance check after 40 trials (step 4) is what catches this.
- The 440 trials recorded $40.12 in total.
- The Development rehearsal (step 1) adds 2 trials.

Reproduce:

```bash
python3 - <<'E'
import json, sys
sys.path.insert(0, ".")
from analysis.analyze import percentile
rows = [json.loads(x) for f in ("data/trials.jsonl", "data/replication.jsonl") for x in open(f) if x.strip()]
N = 110
def line(label, rs):
    c = sorted(r["cost_usd"] for r in rs)
    mean, p90, mx = sum(c) / len(c), percentile(c, 0.9), c[-1]
    print(f"{label:8} n={len(c)} mean ${mean:.4f} p90 ${p90:.4f} max ${mx:.4f} | x{N}: ${mean * N:.2f} / ${p90 * N:.2f} / ${mx * N:.2f}")
line("overall", rows)
for v in ("prompt", "skill"):
    line(v, [r for r in rows if r["variant"] == v])
print(f"recorded cost of the {len(rows)} trials: ${sum(r['cost_usd'] for r in rows):.2f}")
full = [(r["input_tokens"] * 0.15 + r["output_tokens"] * 0.60) / 1e6 for r in rows]
print(f"no cache discount (all input at $0.15/M): mean ${sum(full) / len(full):.4f} per trial, x{N}: ${sum(full) / len(full) * N:.2f}")
E
```

## What was verified, and how

Verified by running something locally, with no credentials:

- **The runner installs skill v2 and records it.** `HANDOFF_SKILL_DIR=skill/flagsmith-ab-test-v2 HANDOFF_STAGE=followup HANDOFF_ENVIRONMENT=production python -m runner --dry-run --scripted-agent-apply-reference --trial-id trial-followup-check-1 --out-dir <dir>` (scripted agent, local emulator, 4 trial ids): every record has `stage` `followup`, `skill_dir` `skill/flagsmith-ab-test-v2`, `skill_sha` `274b7bef8135...` (the v2 tree; v1 is `eb5aa00e5679...`), `passed` true. A direct call of `workspace.prepare_workspace` with the OpenCode backend shows the skill arm gets `.opencode/skills/flagsmith-ab-test/SKILL.md` byte-identical to the v2 file and the prompt arm gets no skill folder.
- **The analysis.** A synthetic 110-record file outside the repository (replication records relabelled, never committed) goes through `--followup-trials` and yields the section described in step 8. Without the new options the output of the documented primary plus replication command is byte-identical to the output of the code before the change (same pinned clock), and identical to the committed `RESULTS.md` except the two hand-edited Screenshot rows.
- **Collection routing.** `analysis/collect.py` puts stage `followup` records into `followup.jsonl` next to `--out`, skips ids on a second run, and also routes Development follow-up records there.
- **The check script, the workflow guard, the rollover path** have unit tests (`tests/test_check_followup_records.py`, `tests/test_followup_guard.py`, `tests/test_rollover_followup.py`, `analysis/tests/test_followup.py`). The rollover test drives `ops/rollover_experiment.py` against a scripted stub of the Admin API: old experiment completed, new one created with the follow-up hypothesis, started, verified 50/50, second run changes nothing.

Only read, not run (needs credentials): everything in Flagsmith and GitHub Actions. In particular, whether Flagsmith accepts a new experiment on a flag whose last experiment was completed a day earlier, the `gh` commands, and the guard step inside a real workflow run.

## What changed in the code

| File | Change |
|---|---|
| `analysis/analyze.py` | New options `--followup-trials`, `--followup-flagsmith-json`, `--print-followup-sentence`. Additive: output without them is unchanged |
| `ops/rollover_experiment.py`, `ops/rolllib.py` | New option `--hypothesis=<replication\|followup>` for the text stored on the new experiment. Default is the text used before |
| `ops/exp_counts.py` | The experiment name may be written with underscores for spaces (needed through `ops.yml`); an unknown name now exits 1 with the list of names instead of printing nothing |
| `.github/workflows/trials.yml` | Guard step in `prepare` (see step 3) |
| `scripts/check_followup_records.py` | New: the between-batch check |

## Known risks found while tracing

Most serious first. None of these is fixed by this branch.

1. **The stop line has passed and the declaration's "identical grader" no longer holds.** Without an appended `EXPERIMENT.md` entry the run contradicts the pre-registration file. Precondition 2.
2. **Real spend may differ from recorded spend.** `cost_usd` assumes cache-read pricing; the no-discount figure is about six times higher. Skill v2's cost is unmeasured. Only the balance reads (preconditions and step 4) bound it.
3. **Starting the follow-up undoes the Round 04 rollout for as long as it runs.** The Production flag serves 50/50 from step 2 until step 7. If the work is abandoned midway, step 7 still has to be run.
4. **Creating an experiment after a completed one is untested live.** The replication was created in the same script run that completed the primary. The path "old already completed" is covered by a unit test against a scripted stub and by reading the code only. Step 1 rehearses it in Development.
5. **A dispatch with both `stage` and `skill_dir` left at their defaults is not refused.** It would run skill v1, label the records `primary`, expose them in the 'Handoff: Skill v2' experiment (exposures cannot be removed), and `collect.yml` would push them into `data/trials.jsonl` on the `data` branch. The check script and the scratch `--out` in step 5 catch it after the fact, not before.
6. **`collect.yml` does not commit `data/followup.jsonl`** (nor `data/replication.jsonl`); the `data` branch holds `data/trials.jsonl` only. Collection is manual (step 5).
7. **`python analysis/analyze.py --stage followup`**, the command named in `EXPERIMENT.md`, `docs/setup.md` and `docs/BLOCKERS.md`, produces a report that calls the follow-up "Primary result", applies the decision rule to it, appends the primary's notes and regrade table, and by default overwrites `RESULTS.md` and `assets/*.svg`. Use step 8 instead.
8. **Regenerating `RESULTS.md` drops the two hand-edited Screenshot rows.** Step 8 restores them; the durable fix is to move that text into the generator or the snapshot files.
9. **`analysis/crosscheck.py` does not read a raw snapshot.** Run as `docs/setup.md` shows, it reports every row as different, because it expects `exposures` and `events` keys. The cross-check that works is the one inside `analyze.py` (step 6).
10. **`scripts/fetch_trial_records.py` overwrites its output file**, although its docstring says it appends, and its default output path is under `data/`. Always pass an output path, one per run.
11. **Development follow-up records are routed to `followup.jsonl`** by `collect.py`. The analysis filters on `environment`, the file would still hold them. Do not collect the rehearsal.
12. **The object table in `EXPERIMENT.md` names experiment 1142 "Handoff: Prompt vs Skill"**; the snapshot says `Handoff: Replication`. The runbook uses the snapshot's name and gives the fallback.
13. **Skill v2 changed after the follow-up was declared** (commit `37411d8` added results reading, a ship step and rollout verification; the declaration is from `642c9c3`). No follow-up trial had run, so nothing is invalidated, but the record entry should name the tree that was tested (`274b7bef8135`). v2 tells the agent to stop after its step 7; an agent that goes on to read results or complete its sandbox experiment would spend more turns. The grader is not affected (it grades against the local emulator), the over-budget guardrail would show it.
14. **Artifacts expire after 30 days.** The saved diffs are needed for the failure labels.

## Text to append to EXPERIMENT.md (draft for the owner; not appended by this branch)

> ## Amendment: the skill v2 follow-up runs after the stop line (date)
>
> Appended before any follow-up trial. The owner raised the spend cap to $… of recorded spend for the follow-up on (date). The "Stop line" section named the primary and the replication; the follow-up declared above is exploratory and is run after that time. Two points of its declaration are updated, everything else stands: (1) the grader is the final grader tree `814c52706be0` (after the environment-document amendment), not the tree the primary was graded with; both follow-up arms are graded by the same tree; (2) skill v2 is the tree `274b7bef8135` (extended on 2026-11-27 after the declaration, before any follow-up trial). N = 110 records, stage `followup`, experiment 'Handoff: Skill v2', never pooled, decision rule N/A. The Production flag serves 50/50 while the follow-up runs and is returned to `prompt` afterwards (`ops/rollout_winner.py Production prompt`), which is the primary decision and not a verdict on the follow-up. Procedure: `docs/followup-runbook.md`.
