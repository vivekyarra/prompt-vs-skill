# Demo video script (2-3 minutes)

DRAFT. Numbers on screen must come from the final Flagsmith dashboard and `RESULTS.md`. Nothing is recorded or invented here. A human records and uploads (H8) by the morning of 29 Nov at the latest.

## Timing table

| Time | Shows | Says |
|---|---|---|
| 0:00–0:15 | Title card | "Every devtool now onboards AI agents, with a prompt or a skill. Which works? We ran a real Flagsmith experiment." |
| 0:15–0:40 | Flagsmith's setup prompt page and the Track 04 skills idea | Why this is a live decision for Flagsmith and every devtool |
| 0:40–1:10 | Actions run: a trial starting, Flagsmith assigning the variant, agent working | How a trial runs; identity = trial ID |
| 1:10–1:35 | Grader output on one pass and one fail (e.g. C3 conversion on page load) | What "correctly wired" means, checked from real traffic |
| 1:35–2:15 | Flagsmith results page | Exposures, rates, credible interval, win probability, guardrail, read honestly |
| 2:15–2:35 | Flipping the flag to the winner; confirmation trials | Shipping the winner with the same flag (or, if inconclusive, say so and keep 50/50) |
| 2:35–2:50 | The issue/PR to Flagsmith; repo link | What Flagsmith can do with this |

## Shot list

1. Title card (see below), static, 15 s.
2. Browser: Flagsmith's official setup prompt page; then the hackathon page showing the skills idea.
3. Browser: GitHub Actions run of `trials` with the matrix expanded; open one job log and show the `trial-<run_id>-<index>` ID.
4. Browser: Flagsmith experiment-project identity view for that trial ID showing the assigned `onboarding_method` value.
5. Terminal: grader output for one passing and one failing run.
6. Browser: Flagsmith results page (the same one captured in the final screenshot).
7. Browser: flag value being set to the winner (only if there is a winner by the decision rule), then the confirmation trial logs.
8. Browser: the Flagsmith issue/PR, then the repo README.

## Terminal commands to show

```bash
# one trial, locally
python -m runner --trial-id trial-local-1 --out-dir out

# grade a workspace on its own (see README for the exact flags once the grader CLI is final)
python -m grader --help

# aggregate logs into RESULTS.md
python analysis/analyze.py --trials data/trials.jsonl --out RESULTS.md

# our counts vs Flagsmith's
python analysis/crosscheck.py --flagsmith-json flagsmith.json
```

## Title card text

> **Handoff: Prompt vs Skill**
> Does an Agent Skill beat the official setup prompt at getting coding agents to a correctly wired Flagsmith experiment?
> Built for Toggle Wars: The Flagsmith Experimentation Hackathon, Track 01

## Asset checklist

- [ ] Title card image
- [ ] Screenshot of the Flagsmith results page (human captures; note date and time read)
- [ ] Screen recording of an Actions `trials` run
- [ ] Terminal recording: one grader pass and one grader fail
- [ ] Flagsmith identity view for one trial ID
- [ ] Recording of the flag flip to the winner and 5 confirmation trials (only if a winner exists)
- [ ] Link to the posted Flagsmith issue/PR (H9)
- [ ] Final numbers pasted from `RESULTS.md` (replace every TBD in the narration)
- [ ] Upload (YouTube unlisted or as the form requires) and link in README
