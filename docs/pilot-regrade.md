# Pilot re-grade with the 13 s waits (OFFLINE, pilot data, not results)

Context: the grader waited only 3 s (load) / 5 s (click), but all three Flagsmith SDKs flush buffered events on a
10 s timer, so correct integrations without an explicit flush were failed on C3/C4 (see `docs/grader.md`, "grader bug
found in the pilot (2026-11-26)"). The waits are now 13 s in every phase; C1-C6 pass conditions are unchanged.

Method: the saved `diff.patch` of every trial of CI runs 45884668673 (the 60-turn pilot), 45886843273 and 45890705758
(30 trials) was applied to a copy of the `apps/<stack>` baseline and graded with the grader at commit
`25f7365` (new default waits), `--mode proxy --reclaim-port`, flag name from `trial_record.json`, default ports (one
sequential stream per stack). "Old" = the verdict recorded in `trial_record.json`. Trials with `limit_hit = turns`
(all of run 45884668673) are included as recorded.

| trial (run-no) | variant | stack | old checks failed | new checks failed | flipped |
|---|---|---|---|---|---|
| 45884668673-1 | skill | node | - | - | no |
| 45884668673-2 | skill | python | C2,C3,C4,C5,C6 | C2,C3,C4,C5,C6 | no |
| 45884668673-3 | prompt | python | - | - | no |
| 45884668673-4 | skill | react | - | - | no |
| 45884668673-5 | skill | python | - | - | no |
| 45884668673-6 | skill | react | - | - | no |
| 45884668673-7 | skill | python | - | - | no |
| 45884668673-8 | skill | react | C1,C2,C3,C4,C5,C6 | - | fail->pass |
| 45884668673-9 | skill | react | - | - | no |
| 45884668673-10 | prompt | node | C3,C4 | - | fail->pass |
| 45886843273-1 | prompt | python | - | - | no |
| 45886843273-2 | prompt | python | C3,C4 | - | fail->pass |
| 45886843273-3 | prompt | node | - | - | no |
| 45886843273-4 | prompt | node | - | - | no |
| 45886843273-5 | skill | python | - | - | no |
| 45886843273-6 | skill | python | - | - | no |
| 45886843273-7 | prompt | node | - | - | no |
| 45886843273-8 | prompt | python | - | - | no |
| 45886843273-9 | skill | node | - | - | no |
| 45886843273-10 | prompt | react | C2,C3,C4 | - | fail->pass |
| 45890705758-1 | prompt | node | C3,C4 | - | fail->pass |
| 45890705758-2 | prompt | react | C2,C3,C4,C6 | C6 | no |
| 45890705758-3 | skill | python | C3,C4 | - | fail->pass |
| 45890705758-4 | skill | node | C3,C4 | - | fail->pass |
| 45890705758-5 | skill | node | - | - | no |
| 45890705758-6 | prompt | node | C3,C4 | - | fail->pass |
| 45890705758-7 | prompt | react | - | - | no |
| 45890705758-8 | skill | react | C2,C3,C4 | - | fail->pass |
| 45890705758-9 | skill | python | - | - | no |
| 45890705758-10 | skill | python | - | - | no |

## Summary

- **fail -> pass: 9** (8 in the first offline pass, plus 45886843273-10 after the `.env.local` replay below). Seven are the flush bug (old reason `no join_clicked event was sent after the Join click`; the
  new run shows `join_clicked` in the `click` phase and exposures in `load`, `reload`, `v2`): 45884668673-10,
  45886843273-2, 45890705758-1, -3, -4, -6, -8 (-8 also had a spurious old C2 about a missing exposure that the longer
  load wait removes). The eighth, 45884668673-8, is **not** the flush bug: its old C1 was `port 5173 is already in use`
  (a stale dev server; that run predates `--reclaim-port`), so it is an infrastructure flip.
- **pass -> fail: 0.**
- Still failing: 45884668673-2 (python, never reaches Flagsmith) and 45890705758-2 (react, C6 only, see the update below).
- Two React trials (45886843273-10, 45890705758-2) could not be replayed in the first pass: they read their key from
  `VITE_FLAGSMITH_ENVIRONMENT_KEY`, a name the grader does not set (it provides `VITE_FLAGSMITH_CLIENT_KEY`) and which is
  not in the diff, so the first replay saw no Flagsmith traffic and their old verdict (fail) was kept. See the update.

## Update: React trials replayed with a placeholder `.env.local`

The two React trials that could not be replayed earlier were replayed again with a `.env.local` holding a placeholder
`VITE_FLAGSMITH_ENVIRONMENT_KEY` (the name those apps read; the value is irrelevant because the grader's proxy answers
every `*.flagsmith.com` request):

- **45886843273-10 (prompt, react): fail -> pass**, all C1-C7 pass. Its old failure (C2,C3,C4) was the flush bug.
- **45890705758-2 (prompt, react): still fails, C6 only.** C1-C5 and C7 pass; the app branches on the variation **key**
  (`.variant`) instead of the flag **value**, which the mock cannot satisfy (see "Known limitation (C6)" in
  `docs/grader.md`). The old failing set was C2,C3,C4,C6; the flush-related C2-C4 now pass.

## Recomputed pass rates (PILOT data, not results; denominators are all 30 trials)

| | skill | prompt | pooled |
|---|---|---|---|
| Recorded (old) | 12/17 (70.6%) | 7/13 (53.8%) | 19/30 (63.3%) |
| Re-graded (new) | 16/17 (94.1%) | 12/13 (92.3%) | 28/30 (93.3%) |

Excluding the 60-turn run (all 10 trials hit the turn limit): runs 45886843273 + 45890705758 only, old 12/20 (60%), new
19/20 (95%).

Arithmetic (from the table): the only change versus the first pass is 45886843273-10 (prompt), fail -> pass. Prompt
trials that pass: 11 + 1 = 12 of 13 (92.3%); skill unchanged at 16/17 (94.1%); pooled 16 + 12 = 28 of 30 (93.3%). Old
(recorded) rates are unchanged: skill 12/17, prompt 7/13, pooled 19/30. Excluding 45884668673: old 12/20, new
(28 - 9 passing in that run = 19)/20 = 95%. The nine fail -> pass flips are 45884668673-8, -10, 45886843273-2, -10,
45890705758-1, -3, -4, -6, -8; 28 = 19 old passes + 9 flips. The two remaining fails are 45884668673-2 and 45890705758-2.

## Production corrections (grader test-env fix)

After the 40 production trials, 3 trials failed C1 only because the app's existing test ran without the fake credential
variables (the apps read their key from the environment at import time). The grader now runs the test clean first and,
only if that fails, re-runs it once with the fake keys (one-directional; see `docs/grader.md`, "Test-env fix for C1").

Replay of the three saved diffs of CI run 45914099371 with the final fix, 3 replays each (`--mode proxy
--reclaim-port`, flag `join_button_trial_45914099371_<n>`, diff applied to a copy of `apps/<stack>`):

| trial (run-no) | stack | replay 1 | replay 2 | replay 3 | C1 detail |
|---|---|---|---|---|---|
| 45914099371-14 | python | PASS | PASS | PASS | existing test passed only with credential variables set |
| 45914099371-7 | python | PASS | PASS | PASS | existing test passed only with credential variables set |
| 45914099371-30 | node | PASS | PASS | PASS | existing test passed only with credential variables set |

9/9 replays pass (C1-C7 all pass). Full grader self-test suite: 42 tests; in one full run 13 failed with
"port 3000 is already in use" because another process was using the grader's default ports concurrently; all 13 passed
when re-run alone, and the two new tests passed (42/42 effective).
