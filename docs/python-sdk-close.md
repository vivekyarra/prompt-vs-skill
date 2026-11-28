# Python SDK: events at process exit, `close()` and our verdicts (exploratory)

Exploratory check, run on 2026-11-28 after both runs. It reads saved artifacts and runs local tests against the grader's local emulator. No Flagsmith event, trial record or pre-registered result is changed.

## Question

The Python `flagsmith` SDK buffers experiment events and sends them on a timer. A process that exits without `flush_events()` or `close()` can lose what is still in the buffer. Could that have changed any verdict of our Python trials?

## Short answer

No. Our Python sample app is a long-lived Flask server, not a script that exits. The SDK's 10 s flush timer delivers the events while the server runs, and the grader waits 13 s in every phase. Verified three ways: a direct test of the reference app with every explicit flush removed, the 13 saved skill-arm trials that never flush, close or register an exit hook (all passed), and the version every trial installed.

## 1. Which SDK version the Python trials used

Source: `ops/python_sdk_audit.py` (ops workflow run 46124460108) read the artifact of all 156 Python trials (66 primary, 90 replication); output in `data/python_sdk_audit.jsonl`.

| what the diff adds to its requirements | trials | version installed |
|---|---|---|
| `flagsmith==6.7.0` | 145 | 6.7.0 |
| `flagsmith>=6.3.0` | 8 | 6.7.0 by resolution (see note) |
| nothing (0-byte diff: the agent committed its work, see `docs/regrade.md`) | 3 | not known from the artifact |

Note on the 8 unpinned trials: pip resolves `flagsmith>=6.3.0` to 6.7.0 today, and 6.7.0 was already the version in our SDK notes before the trials (`docs/flagsmith-sdk-notes.md`), so the grader's install at trial time resolved to 6.7.0 as well. This is an inference from the resolver, not a saved install log: the grader did not save pip's output. One of the 8 agent transcripts shows 6.7.0; the other 7 show no version.

The agents' own output mentions `flagsmith` 6.7.0 in 136 of the 156 trials, 6.3.0 alone in 1, and no version in 19 (regex over `agent_output.jsonl`; a mention is not proof of what was installed; 9 transcripts also mention 6.3.0 and 2 mention other version strings). No requirement line resolves below 6.7.0.

## 2. Does the exit behaviour affect delivery from our app?

**Short script (the case that loses events).** A script that calls `get_experiment_flag` and `track_event` and then exits, against the grader's local emulator, one run per cell (local runs on 2026-11-28; the outputs are not committed):

| SDK version | exits without flush | `flush_events()` | `close()` |
|---|---|---|---|
| 6.5.1 | no event delivered | method does not exist | method does not exist |
| 6.6.0 | no event delivered | exposure + conversion delivered | exposure + conversion delivered |
| 6.7.0 | no event delivered | exposure + conversion delivered | exposure + conversion delivered |

So a short script must flush or close. In our test this was also true for 6.5.1, which has neither method.

**Long-lived server (our case).** The reference Python app (`apps/reference/python`) with both `flush_events()` calls deleted and no `close()`, graded by the unchanged grader in proxy mode with default 13 s waits (local runs on 2026-11-28; outputs not committed):

| SDK version | result | events the grader captured |
|---|---|---|
| 6.6.0 | PASS, C1-C7 | exposure in load, `join_clicked` in click, exposure in reload and V2 |
| 6.7.0 | PASS, C1-C7 | the same |

The conversion arrives in the click phase without any flush or close: the timer sends it.

## 3. What the saved Python diffs do

Counted in the lines each diff adds to `.py` files (153 trials with a non-empty diff). `atexit` counts any use of the module (a `close` passed by reference, as in `atexit.register(client.close)`, is not counted in the `close()` column).

| run | arm | diffs | `flush_events()` | `close()` | either | `atexit` | none of the three | of those, passed |
|---|---|---|---|---|---|---|---|---|
| primary | prompt | 33 | 11 | 10 | 20 | 33 | 0 | - |
| primary | skill | 32 | 12 | 15 | 21 | 22 | 6 | 6 |
| replication | prompt | 42 | 19 | 13 | 29 | 42 | 0 | - |
| replication | skill | 46 | 16 | 22 | 30 | 33 | 7 | 7 |
| both | prompt | 75 | 30 | 23 | 49 | 75 | 0 | - |
| both | skill | 78 | 28 | 37 | 51 | 55 | 13 | 13 |

- 13 skill-arm apps never flush, close or register an exit hook. All 13 passed the grader as recorded: their events were delivered by the timer.
- The 3 Python trials recorded as failed (`trial-45914099371-7`, `-14`, `trial-45967755797-22`, all skill) all call `flush_events()`; all three failed C1 (the app's own test), not an event check: two are the documented C1 corrections (`data/corrections.jsonl`), the third's test script exits when no key is configured.
- 12 prompt-arm diffs set `max_buffer_items`, the pitfall described in `docs/flagsmith-sdk-notes.md`. All 77 prompt-arm Python trials passed as recorded.

## Limits

- The grader exercises a running server. It does not test what happens to events still buffered when the server is stopped; a real deployment should call `close()` on shutdown.
- One run per cell in the short-script table; the 0-byte diffs (3 trials) could not be read.
- The grader's own pip output was not saved, so the installed version is read from the requirement line.
