# Blockers: what a human still has to do

Written 2026-11-28. Nothing here was simulated or skipped silently; each item says what is blocked and why.

## Blocked on a human

1. **Raise the spend cap, then run the skill v2 follow-up** (runbook: `docs/followup-runbook.md`). The declared 110-trial follow-up (skill v2 vs the official prompt, `EXPERIMENT.md`, "Follow-up experiment") has not run. `EXPERIMENT.md` records that the working cap of $35 was reached after the replication (recorded trial cost in `data/`: $20.09 primary + $20.03 replication, plus the pilots), and no confirmation that the cap was raised reached the session that did this work. The trials spend the owner's Nebius balance, so they were not started on an assumption. Estimated cost: 110 trials at the measured primary mean cost per trial (see `RESULTS.md`, cost table). To run: confirm the new cap, create and start a separate Flagsmith experiment named 'Handoff: Skill v2' on `onboarding_method` (the replication used `ops/rollover_experiment.py`; check it against the current flag state first, the flag now serves the rollout winner), then dispatch `trials.yml` with `stage=followup`, `skill_dir=skill/flagsmith-ab-test-v2`, and analyse with `python analysis/analyze.py --stage followup`. Until then RESULTS.md has no "Follow-up: skill v2" section and the README says v2 is not yet tested.
2. **Exploratory cross-agent run (Claude Code as the agent): skipped.** It was requested only if budget remained after the follow-up, which has not run. It is not declared in `EXPERIMENT.md`; declare it there before running it.
3. **Post the Flagsmith GitHub issue** (text: `docs/flagsmith-contribution.md`) and replace the `<!-- FLAGSMITH_ISSUE -->` placeholder in the README Proof section with its link.
4. **Record and upload the video** (`docs/video-script.md`) and replace the `<!-- VIDEO -->` placeholder in the README.
5. **Add the Flagsmith results screenshot for the follow-up** to the video and README once the follow-up has run (screenshots for experiments 728 and 1142 are in `assets/`).
6. **Submit the form, in Track 01 only.**

## Not blocked, for information

- Local emulator vs real Flagsmith agreement check: done (`docs/mock-vs-real.md`), including a scan of all 440 trials for the one emulator limitation it found.
- Python SDK exit-flush question: done (`docs/python-sdk-close.md`).
