# Video script (2 to 3 minutes)

A shot list with voiceover. Every number on screen comes from `RESULTS.md` and the Flagsmith results page. The replication numbers come from the Flagsmith replication experiment and `RESULTS.md`. Cards live in `assets/video/` (`python assets/video/build_cards.py` regenerates them): `01-title.png`, `02-architecture.png`, `03-trial.png`, `04-results.png`.

## Shot list and voiceover

| Time | Show | Voiceover |
|---|---|---|
| 0:00-0:12 | `assets/video/01-title.png` | "Every devtool now onboards AI agents, with a prompt or with a skill. Which one works better? We measured it, in a real Flagsmith experiment, and then ran it a second time." |
| 0:12-0:30 | `assets/video/02-architecture.png`, then `assets/video/03-trial.png` | "One GitHub Actions job is one trial. The trial ID is the Flagsmith identity, so the variant, the exposure and the verdict all attach to it. Flagsmith assigns the variant, a ground-truth grader judges the agent's app from real network traffic, and Flagsmith receives the verdict." |
| 0:30-0:50 | Terminal: `python scripts/demo_grader.py` (output below) | "The grader runs the agent's app, simulates visitors and checks wiring from recorded traffic. A correct app passes. This copy sends the conversion on page load, so check C3 fails." |
| 0:50-1:25 | `assets/video/04-results.png`, then `assets/results.svg` and the Flagsmith results page for experiment 728 | "The official prompt got agents to a correctly wired experiment in 108 of 108 runs. The skill we wrote without it did in 96 of 112. Flagsmith's own inference puts the difference at minus 14.3 percent, with a credible interval from minus 0.208 to minus 0.078. Our counts match Flagsmith's exactly. That is the pre-registered decision." |
| 1:25-1:45 | README results table, then Flagsmith results page for experiment 1142 | "We replicated it with the same frozen setup, as its own experiment. The prompt got 106 of 108, the skill 105 of 112. Same direction, smaller gap, and the interval includes zero, so the decision rests on the primary. Both runs are reported." |
| 1:45-2:05 | Flagsmith: the replication experiment completed with rollout decision control; terminal or dashboard showing 5 fresh identities returning `prompt` | "Round four: the winner ships through the same flag. We completed the experiment with the official prompt as the rollout decision, and five fresh identities all get the prompt." |
| 2:05-2:40 | `skill/flagsmith-ab-test-v2/SKILL.md`, scrolling the whole-job steps (flag, metric, experiment, SDK wiring, verify in the real runtime, results with `--json --jq`, decision rule, ask a human, ship and verify), then the README skill v2 section | "Skill v2 is a proposal for the whole job with the Flagsmith CLI, asking a human before any production change. The skill arm used fewer turns, tokens and dollars per trial than the prompt in both runs: 64.8 turns and 2.79 million tokens against 84.9 and 4.50 million in the primary. Skill v1 was measured; v2 encodes the fixes from the failure analysis and is not yet measured." |
| 2:40-2:55 | `docs/flagsmith-contribution.md`, then the README | "Here is what Flagsmith can use today: six specific fixes for the setup prompt and docs, each with the evidence. Everything is reproducible with one command." |

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
