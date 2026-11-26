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
| 45886843273-10 | prompt | react | C2,C3,C4 | C2,C3,C4,C5,C6 | no |
| 45890705758-1 | prompt | node | C3,C4 | - | fail->pass |
| 45890705758-2 | prompt | react | C2,C3,C4,C6 | C2,C3,C4,C5,C6 | no |
| 45890705758-3 | skill | python | C3,C4 | - | fail->pass |
| 45890705758-4 | skill | node | C3,C4 | - | fail->pass |
| 45890705758-5 | skill | node | - | - | no |
| 45890705758-6 | prompt | node | C3,C4 | - | fail->pass |
| 45890705758-7 | prompt | react | - | - | no |
| 45890705758-8 | skill | react | C2,C3,C4 | - | fail->pass |
| 45890705758-9 | skill | python | - | - | no |
| 45890705758-10 | skill | python | - | - | no |

## Summary

- **fail -> pass: 8.** Seven are the flush bug (old reason `no join_clicked event was sent after the Join click`; the
  new run shows `join_clicked` in the `click` phase and exposures in `load`, `reload`, `v2`): 45884668673-10,
  45886843273-2, 45890705758-1, -3, -4, -6, -8 (-8 also had a spurious old C2 about a missing exposure that the longer
  load wait removes). The eighth, 45884668673-8, is **not** the flush bug: its old C1 was `port 5173 is already in use`
  (a stale dev server; that run predates `--reclaim-port`), so it is an infrastructure flip.
- **pass -> fail: 0.**
- Still failing, unchanged verdict: 45884668673-2 (python, never reaches Flagsmith), 45886843273-10 and 45890705758-2
  (react). The latter two are **not reproducible offline**: the new grade shows no Flagsmith traffic at all and C5/C6
  extra failures, because those apps read their key from `VITE_FLAGSMITH_ENVIRONMENT_KEY`, a name the grader does not
  set (it provides `VITE_FLAGSMITH_CLIENT_KEY`) and which is not in the diff. Hypothesis (not verified): in CI the
  agent's untracked `.env.local` supplied the key. Their old verdict (fail) is kept; neither is attributed to the flush
  bug.

## Recomputed pass rates (PILOT data, not results; denominators are all 30 trials)

| | skill | prompt | pooled |
|---|---|---|---|
| Recorded (old) | 12/17 (70.6%) | 7/13 (53.8%) | 19/30 (63.3%) |
| Re-graded (new) | 16/17 (94.1%) | 11/13 (84.6%) | 27/30 (90.0%) |

Excluding the 60-turn run (all 10 trials hit the turn limit): runs 45886843273 + 45890705758 only, old 12/20 (60%), new
18/20 (90%).
