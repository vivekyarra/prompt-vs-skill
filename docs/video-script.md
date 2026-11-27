# Video script (2 to 3 minutes)

A shot list with voiceover. Every number on screen comes from `RESULTS.md` and the Flagsmith results page. Cards live in `assets/video/` (`python assets/video/build_cards.py` regenerates them): `01-title.png`, `02-architecture.png`, `03-trial.png`, `04-results.png`.

## Shot list and voiceover

| Time | Show | Voiceover |
|---|---|---|
| 0:00-0:15 | `assets/video/01-title.png` | "Every devtool now onboards AI agents, with a prompt or with a skill. Which one works better? We measured it. 220 real runs, one pre-registered experiment, and the results come straight from Flagsmith." |
| 0:15-0:35 | Browser: Flagsmith's [set up with a coding agent](https://docs.flagsmith.com/experimentation/set-up-with-a-coding-agent) page, then the hackathon page | "Flagsmith ships a setup prompt for coding agents, and skills are the new alternative. Which one gets an agent to a correctly wired A/B test is a live product decision, for Flagsmith and for any devtool." |
| 0:35-1:00 | `assets/video/02-architecture.png`, then `assets/video/03-trial.png` | "One GitHub Actions job is one trial. The trial ID is the Flagsmith identity, so the variant, the exposure and the verdict all attach to it. Flagsmith assigns the variant, a ground-truth grader judges the agent's app from real network traffic, and Flagsmith receives the verdict." |
| 1:00-1:10 | Browser: the Actions `trials` run with the matrix expanded; the Flagsmith identity view for one trial ID | "This trial was assigned `onboarding_method` equal to the value shown. Then the agent works." |
| 1:10-1:35 | Terminal: `python scripts/demo_grader.py` (output below) | "The grader runs the agent's app, simulates visitors and checks wiring from recorded traffic. A correct app passes. This copy sends the conversion on page load, so check C3 fails." |
| 1:35-2:15 | `assets/video/04-results.png`, then `assets/results.svg` and the live Flagsmith results page | "The official prompt got agents to a correctly wired experiment in 108 of 108 runs. The skill we wrote without it did in 96 of 112. Flagsmith's own inference puts the difference at minus 14 points with a credible interval from minus 0.21 to minus 0.08. Our counts match Flagsmith's exactly, and a blind review of 24 passing diffs found no false pass." |
| 2:15-2:40 | `docs/failure-labels.md` table, then `skill/flagsmith-ab-test-v2/SKILL.md` | "We root-caused all 18 failures. Ten lost events in the browser because the skill never named the right SDK import. The failure analysis shows exactly why and how to close the gap, and skill v2 encodes those fixes." |
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
- [ ] Rehearse once against the 2:50 target; the limit is 3:00.
- [ ] Add the video link to the `<!-- VIDEO -->` line in `README.md`.
