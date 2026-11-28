# Video script (2 to 3 minutes)

A shot list with voiceover. Every number on screen comes from `RESULTS.md`, `docs/regrade.md`, `docs/mock-vs-real.md` and the Flagsmith results pages. Cards live in `assets/video/` (`python assets/video/build_cards.py` regenerates them): `01-title.png`, `02-architecture.png`, `03-trial.png`, `04-results.png`.

## On-screen assets

| Asset | Where |
|---|---|
| Flagsmith results page, experiment 728 (primary) | live page, or `assets/flagsmith-results-728.png` |
| Flagsmith results page, experiment 1142 (replication) | live page, or `assets/flagsmith-results-1142.png` |
| Flagsmith results page, follow-up experiment 'Handoff: Skill v2' | **not available yet**: the follow-up has not run (`docs/BLOCKERS.md`). Capture it after the run and save it as `assets/flagsmith-results-followup.png` |
| The two handoffs | `prompt/` (Flagsmith's official setup prompt) and `skill/flagsmith-ab-test/SKILL.md` (the skill we wrote) side by side |
| Results figure | `assets/results.svg` |
| Regrade table | `docs/regrade.md`, "Sensitivity table" |
| Agreement table | `docs/mock-vs-real.md`, "Agreement" |
| Skill v2 | `skill/flagsmith-ab-test-v2/SKILL.md` |
| Suggestions | `docs/flagsmith-contribution.md` |

## Shot list and voiceover

| Time | Show | Voiceover |
|---|---|---|
| 0:00-0:15 | `assets/video/01-title.png`, then the two handoffs side by side | "Flagsmith gives coding agents a setup prompt you paste. We wrote an Agent Skill for the same job from Flagsmith's docs, and bet it would do better. Then we let Flagsmith run the test." |
| 0:15-0:35 | `assets/video/02-architecture.png`, `assets/video/03-trial.png`, then 5 s of `python scripts/demo_grader.py` | "One trial is one agent run. Flagsmith assigns the handoff through a flag, fifty-fifty. A grader runs the agent's app, drives it with a browser and judges the wiring from recorded network traffic. Flagsmith receives the verdict and computes the result. The plan was frozen before the first trial." |
| 0:35-0:55 | `assets/results.svg`, then the Flagsmith results page for experiment 728 | "The pre-registered run: the official prompt got 108 of 108 trials correctly wired. Our skill got 96 of 112. Flagsmith's own inference puts the lift at minus 14.3 percent, and the interval excludes zero. Our log matches Flagsmith's counts exactly." |
| 0:55-1:20 | Flagsmith results page for experiment 1142, then the README answer | "Then we ran all of it again: a full 220-trial replication, same frozen setup, its own experiment. The prompt got 106 of 108, the skill 105 of 112. Same direction, smaller gap, and this time the interval includes zero. So the decision rests on the primary, and we report both." |
| 1:20-1:45 | `docs/regrade.md` sensitivity table, then `docs/mock-vs-real.md` agreement table | "We also checked our own judge. A limitation in the grader had failed some correct apps, so we fixed it and regraded the saved diffs of all 440 trials, 439 had one, with the counting rule written first. The primary gap shrinks to about 10 points and keeps its sign; in the replication it is indistinguishable from zero. And we regraded 47 diffs against the real Flagsmith instead of our local emulator: 46 got the same verdict." |
| 1:45-2:10 | `docs/failure-labels.md`, then `skill/flagsmith-ab-test-v2/SKILL.md` | "Every graded failure in the primary run is root-caused. The largest single cause: React apps importing the browser SDK the wrong way. Skill v2 encodes the fixes. Its follow-up experiment is declared and has not run yet, so v2 is untested. The skill arm was also cheaper: 64.8 turns per trial against 84.9 in the primary." |
| 2:10-2:30 | Flagsmith: experiment 1142 completed with rollout decision control; 5 fresh identities returning `prompt` | "The winner ships through the same flag that ran the test. We completed the experiment with the official prompt as the rollout decision, and five fresh identities all get the prompt." |
| 2:30-2:50 | `docs/flagsmith-contribution.md`, then the README top | "For Flagsmith: specific suggestions for the setup prompt and docs, each with its evidence. One agent, one model, three stacks: a clear gap in the pre-registered run, a smaller and inconclusive one in the replication, and everything reproducible from the repo." |

**If the follow-up has run before recording:** replace the 1:45-2:10 voiceover's third and fourth sentences with the follow-up's own numbers from the "Follow-up: skill v2 (exploratory)" section of `RESULTS.md` (counts per arm, Flagsmith lift and interval), show the follow-up results page, and say "exploratory". Do not record numbers that are not in `RESULTS.md`.

## Terminal commands to show

```bash
# grader on a correct app and a broken one (about 40 s once npm deps are cached)
python scripts/demo_grader.py

# one credential-free end-to-end trial
python -m runner --dry-run --scripted-agent-apply-reference --trial-id trial-readme-1 --out-dir out
```

Prerequisites: [`docs/setup.md`](setup.md). The grader demo runs in emulator mode (the app is pointed at the local Flagsmith emulator, so it needs no account and sends no traffic to Flagsmith). Trials use proxy mode.

### Expected output of the grader demo (node stack)

```text
=== reference node: PASS ===
  C1 App runs                               pass  app healthy, existing test passed, Join button clickable
  C2 Exposure sent                          pass  exposure event(s) recorded with the visitor identity
  C3 Conversion on action                   pass  1 join_clicked event(s) in click phase, none on load
  C4 Identity match                         pass  exposure and conversion use the same identity
  C5 Identity stable                        pass  identity stable across reload; V2 differs
  C6 Flag drives the UI                     pass  button text equals the value Flagsmith returned (V1 and V2)
  C7 No server key in client (diagnostic)   pass  no server key in browser-loaded assets

=== broken node/B3: FAIL ===
  C3 Conversion on action                   FAIL  join_clicked was sent during page load, before any click
```

## Pre-recording checklist

- [ ] `python scripts/demo_grader.py` runs clean once beforehand (warms the npm cache).
- [ ] Terminal with a large font and no secrets or environment variables visible.
- [ ] Browser logged in to GitHub and Flagsmith, with the results page open. No API keys on screen.
- [ ] Rehearse once against the 2:55 target; the limit is 3:00.
- [ ] Open both Flagsmith experiment pages (primary and replication) and the `SKILL.md` for v2 before recording. Do not show the rollout confirmation trials' outcome unless it is in the README.
- [ ] Add the video link to the `<!-- VIDEO -->` line in `README.md`.
