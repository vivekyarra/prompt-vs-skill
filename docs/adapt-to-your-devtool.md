# Adapt this to your devtool

The method in this repo is not Flagsmith-specific. Any devtool team that onboards AI agents (a prompt to paste, or a skill to install) can answer "which handoff gets agents to a working integration more often?" with the same three parts.

## 1. Two handoffs, one task

- **Prompt**: the text you would paste into an agent today, unmodified (`prompt/`).
- **Skill**: the same knowledge packaged as an Agent Skill (`skill/`): a short trigger plus references the agent loads on demand.
- Keep everything else identical. Same model, same turn and token limits, same sample apps, same clean workspace.

## 2. The task brief

One shared file (`brief/TASK_BRIEF.md`) states the outcome in the user's words, not yours: "make the button copy an A/B test and record how many people click it". It must not mention your SDK method names, otherwise you test the brief, not the handoff. Write down the stacks (here React, Node, Python) and assign them at random per trial.

## 3. The grader contract

The grader decides success, never the agent and never a human. It needs four properties:

1. **Black box**: run the app, drive it with a real browser, observe only network traffic. Nothing about how the agent wrote the code.
2. **Fake backend**: answer your service locally (here a mock behind an HTTPS proxy) so grading needs no credentials and never touches production.
3. **Binary, pre-registered checks**: a small list (here C1-C7) that you freeze before the run. A check is "an exposure event with the visitor's identity exists", not "the code looks right". A diagnostic that must not decide the verdict (C7) is allowed if declared up front.
4. **Self-tested**: one known-good app that must pass every check, and one broken copy per check that must fail exactly that check (`apps/broken/`, `grader/tests/`). If you cannot build the broken copy, the check is not testable.

To point it at your product, change what the mock serves and what the checks look for (events, identity, rendered value). The CLI flags `--event`, `--click-selector`, `--variant-values`, `--start-cmd` and `--stack custom` already cover apps that are not Flagsmith's sample shape (`apps/reference/custom-signup/`).

## 4. Run it honestly

Pre-register the question, the checks, the stopping rule and the analysis before the first trial (`EXPERIMENT.md`). Randomise the arm, run both arms the same number of times, and report an inconclusive result as inconclusive. Fix grader bugs only in ways that cannot change a pass condition, document each one, and re-grade saved outputs to prove it (`docs/pilot-regrade.md`).
