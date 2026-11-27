# Wiring check: additivity proof

The generic wiring check (`--start-cmd`, `--url`, `--click-selector`, `--stack custom`, `--report`, `hints` in
`result.json`) is additive: with none of the new flags the grader must behave as before. This page re-grades saved
production trial diffs with the **new CLI and no new flags** and compares the verdicts with each trial's recorded
`grader_result.json`.

Method: for each trial the artifact's `diff.patch` was applied (`patch -p1`, no rejects) to a clean copy of
`apps/<stack>`, then graded with `python -m grader --app-dir <copy> --stack <stack> --flag <recorded flag>
--event join_clicked --variant-values "Join,Join free" --mode proxy --reclaim-port` (the runner's own arguments; the
default waits). Grader code under test: commit `8404f628e710e0ee19232ac457490a41dd7a179d` (the code of the
`feat/wiring-check` branch; later commits only touch docs). Sample: 20 trials from production runs 45912277670 (1),
45914099371 (16, including the three trials with a documented C1 correction) and 45925699686 (3), covering react, node
and python, both arms, passes and failures. Vectors list C1..C7 (P = pass, F = fail).

Result: **17 of 20 verdicts identical check by check, 3 differ only by the three documented C1 corrections, 0 unexplained
differences.** The pass conditions and defaults of C1-C7 are unchanged.

| Trial | Stack | Arm | Recorded | Re-graded | Recorded C1-C7 | Re-graded C1-C7 | Status |
|---|---|---|---|---|---|---|---|
| trial-45912277670-9 | node | skill | PASS | PASS | PPPPPPP | PPPPPPP | identical |
| trial-45914099371-1 | python | prompt | PASS | PASS | PPPPPPP | PPPPPPP | identical |
| trial-45914099371-2 | node | prompt | PASS | PASS | PPPPPPP | PPPPPPP | identical |
| trial-45914099371-7 | python | skill | FAIL | PASS | FPPPPPP | PPPPPPP | documented C1 correction (see data/corrections.jsonl) |
| trial-45914099371-8 | python | prompt | PASS | PASS | PPPPPPP | PPPPPPP | identical |
| trial-45914099371-10 | node | prompt | PASS | PASS | PPPPPPP | PPPPPPP | identical |
| trial-45914099371-11 | react | skill | FAIL | FAIL | PFFFPPP | PFFFPPP | identical |
| trial-45914099371-12 | node | skill | FAIL | FAIL | PFPFFFP | PFPFFFP | identical |
| trial-45914099371-13 | python | skill | PASS | PASS | PPPPPPP | PPPPPPP | identical |
| trial-45914099371-14 | python | skill | FAIL | PASS | FPPPPPP | PPPPPPP | documented C1 correction (see data/corrections.jsonl) |
| trial-45914099371-15 | react | skill | PASS | PASS | PPPPPPP | PPPPPPP | identical |
| trial-45914099371-16 | react | prompt | PASS | PASS | PPPPPPP | PPPPPPP | identical (note 2) |
| trial-45914099371-18 | node | skill | PASS | PASS | PPPPPPP | PPPPPPP | identical |
| trial-45914099371-19 | python | prompt | PASS | PASS | PPPPPPP | PPPPPPP | identical |
| trial-45914099371-20 | react | skill | FAIL | FAIL | PFFFPPP | PFFFPPP | identical |
| trial-45914099371-23 | react | skill | PASS | PASS | PPPPPPP | PPPPPPP | identical |
| trial-45914099371-30 | node | prompt | FAIL | PASS | FPPPPPP | PPPPPPP | documented C1 correction (see data/corrections.jsonl) |
| trial-45925699686-1 | python | prompt | PASS | PASS | PPPPPPP | PPPPPPP | identical |
| trial-45925699686-4 | node | skill | FAIL | FAIL | PFPFFFP | PFPFFFP | identical |
| trial-45925699686-19 | node | skill | PASS | PASS | PPPPPPP | PPPPPPP | identical |

## Notes

1. **Corrections.** Trials 45914099371-7, -14 and -30 were recorded as C1 failures because the app's own test needs a
   credential variable at import time; the later one-directional test-env fix (`docs/grader.md`) passes them. All other
   checks of those trials are unchanged. This is the expected change, not a regression.
2. **Trial 45914099371-16 (react)** needs a key that is not in `diff.patch`: the app reads `VITE_FLAGSMITH_ENVIRONMENT_KEY`
   from a git-ignored `.env.local` that existed in the agent's workspace. Re-graded from the diff alone it sends no
   Flagsmith traffic and fails C2-C6. The **previous** grader (`origin/main`) gives the same verdicts on that input, so
   the new code is not the cause; with a `.env.local` holding a fake key in the copy (as the original workspace had) the
   new CLI passes all seven checks, identical to the record.
3. Not compared: identities (random UUIDs per run), durations, `grader_version`, request counts. The reason strings of
   the 17 non-corrected trials were also identical. `result.json` keys: the only difference from the recorded files is the
   added `hints` key.
4. The React sample app's `npm start` ignores `--port` (it always serves on 5173), so React trials were graded on the
   default port, one at a time; Node and Python trials used distinct ports in parallel.
5. The mock Flagsmith already serves the **last** `--variant-values` entry as the variation, so `--variant-values
   "Sign up,Create account"` needed no mock change; `grader/tests/test_wiring_check.py` pins both the default and a
   custom value order.
