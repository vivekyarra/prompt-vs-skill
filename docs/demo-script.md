# Demo video script (2-3 minutes)

A human records and uploads (H8) by the morning of 29 Nov at the latest. Nothing here is a result: every number on screen must come from the final Flagsmith results page and `RESULTS.md`. Where a number is needed, this script says `{{PLACEHOLDER}}`.

Cards live in `assets/video/` (regenerate with `python assets/video/build_cards.py`):
`01-title.png`, `02-architecture.png`, `03-trial.png`, `04-results-TEMPLATE.png` (placeholders only, see "Results insertion").

## Shot list and voiceover

| Time | Show (exact command / URL) | Voiceover |
|---|---|---|
| 0:00-0:15 | `assets/video/01-title.png` | "Every devtool now onboards AI agents, with a prompt or a skill. Which works? We ran a real Flagsmith experiment. Flagsmith assigns every trial's variant, records the exposure, receives a ground-truth grader's verdict, and computes the winner." |
| 0:15-0:40 | Browser: Flagsmith's official setup prompt page, then the hackathon page (https://wemakedevs.org/hackathons/flagsmith) with the Track 04 skills idea | "Flagsmith offers a setup prompt, and skills are the new alternative. Which one gets an agent to a correctly wired A/B test is a live decision for Flagsmith and for every devtool." |
| 0:40-1:00 | `assets/video/02-architecture.png`, then `assets/video/03-trial.png` | "One GitHub Actions job is one trial. The trial ID is the Flagsmith identity, so the variant, exposure and verdict all attach to it." |
| 1:00-1:10 | Browser: Actions run of the `trials` workflow with the matrix expanded; one job log showing `trial-<run_id>-<index>`; Flagsmith identity view for that ID showing `onboarding_method` | "Flagsmith assigned this trial `onboarding_method` = the value shown. Then the agent works." |
| 1:10-1:35 | Terminal: `python scripts/demo_grader.py` (output below) | "The grader runs the agent's app, simulates visitors and checks seven things from recorded traffic. Here a correct app passes. This copy sends the conversion on page load, so C3 fails, and the verdict is fail." |
| 1:35-2:15 | `assets/video/04-results-TEMPLATE.png` replaced by the real results screenshot; then the live Flagsmith results page | "Exposures {{EXPOSURES}}, rates {{RATE_PROMPT}} and {{RATE_SKILL}}, credible interval {{CREDIBLE_INTERVAL}}, win probability {{WIN_PROBABILITY}}, guardrail {{OVER_BUDGET_PROMPT}} / {{OVER_BUDGET_SKILL}}. Read honestly: one agent, small sample apps." |
| 2:15-2:35 | Browser: flag `onboarding_method` set to the winner, then the confirmation trial logs. If inconclusive: show the flag staying 50/50 and say so | "The same flag ships the winner. {{DECISION}}" |
| 2:35-2:50 | Browser: the issue/PR posted to Flagsmith (H9), then the repo README | "Here is what Flagsmith can do with this: specific fixes to the prompt and skill, tied to observed failures." |

## Terminal commands to show

```bash
# offline grader demo: correct reference vs broken B3 (about 40 s once npm deps are cached)
python scripts/demo_grader.py

# optional extras
python -m grader --help
python -m runner --trial-id trial-dry-1 --out-dir out --dry-run   # no credentials needed
python analysis/analyze.py --trials data/trials.jsonl --out RESULTS.md
python analysis/crosscheck.py --flagsmith-json flagsmith.json
```

### Grader demo prerequisites

Python 3.10+, `pip install playwright mitmproxy`, a browser (`python -m playwright install chromium`, or `export GRADER_CHROME_PATH=/usr/bin/google-chrome`), and Node >= 22.21 with npm. The first run needs network for `npm ci`; installs are cached by lockfile hash afterwards. Mock mode: no Flagsmith account or credentials. Options: `--stack node|python|react`, `--broken B1..B7`.

### Expected output (observed, node stack, mock mode, about 36 s on the build machine)

```
Grading the correct reference app (node) in mock mode ...
Grading the broken app (node/B3) in mock mode ...

=== reference node: PASS ===
  C1 App runs                               pass  app healthy, existing test passed, Join button clickable
  C2 Exposure sent                          pass  2 exposure event(s) for 'onboarding_demo' with V1 identity
  C3 Conversion on action                   pass  1 join_clicked event(s) in click phase, none on load
  C4 Identity match                         pass  exposure and conversion use the same identity
  C5 Identity stable                        pass  identity stable across reload; V2 differs
  C6 Flag drives the UI                     pass  button text equals the value Flagsmith returned (V1 and V2)
  C7 No server key in client (diagnostic)   pass  no server key in 2 browser-loaded assets

=== broken node/B3: FAIL ===
  C1 App runs                               pass  app healthy, existing test passed, Join button clickable
  C2 Exposure sent                          pass  2 exposure event(s) for 'onboarding_demo' with V1 identity
  C3 Conversion on action                   FAIL  join_clicked was sent during page load, before any click (1 event(s))
  C4 Identity match                         pass  exposure and conversion use the same identity
  C5 Identity stable                        pass  identity stable across reload; V2 differs
  C6 Flag drives the UI                     pass  button text equals the value Flagsmith returned (V1 and V2)
  C7 No server key in client (diagnostic)   pass  no server key in 2 browser-loaded assets

Verdict = C1..C6 all pass (C7 is diagnostic only).
```

Note for the narration: the demo grades in mock mode (the app is pointed at a local fake Flagsmith). Trials use proxy mode. Say "a local fake Flagsmith" if asked; do not imply the demo touched real Flagsmith.

## Pre-recording checklist

- [ ] `git pull`; `python scripts/demo_grader.py` runs clean once beforehand (warms the npm cache; exit code 0).
- [ ] Terminal: large font, dark theme, 100+ columns, no secrets or env vars visible (`history -c`, no `.env` open).
- [ ] Browser: logged in to GitHub and Flagsmith; bookmarks for the Actions `trials` run, the identity view, the results page, the issue/PR; notifications off.
- [ ] Cards open as images in order (`assets/video/01..03`), results screenshot ready in place of card 04.
- [ ] Flagsmith dashboard shows the final data; no API keys on screen.
- [ ] Rehearse once against the 2:50 target; limit is 3:00.

## Results insertion checklist (after the run)

- [ ] `RESULTS.md` generated and `crosscheck.py` agrees with the Flagsmith dashboard within tolerance.
- [ ] Screenshot of the Flagsmith results page; note the date and time read.
- [ ] Edit `RESULTS_ROWS` in `assets/video/build_cards.py` with the real values (source: the dashboard), re-render, rename the file without `TEMPLATE`; or just use the screenshot.
- [ ] Replace every `{{PLACEHOLDER}}` in the 1:35-2:35 narration; if the result is inconclusive, say inconclusive.
- [ ] If there is a winner: record the flag flip and 5 confirmation trials. If not: record the flag staying 50/50.
- [ ] Update README section 2 (result) and links (video, issue/PR); remove "TBD".
- [ ] Upload (YouTube unlisted or as the form requires) and add the link to README.
