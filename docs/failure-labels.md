# Root causes of the 18 failed trials (primary run, 220 trials)

Scope: every trial that was graded as a failure in the 220-trial primary run (18), plus the three later corrected to PASS
by the documented C1 grader fix (`data/corrections.jsonl`; marked "corrected"; they are among the 18). The corrected
three carry the cause of their original (pre-fix) failure. Nothing frozen (skill, prompt, grader, apps) was changed.

Method: for each trial the `diff.patch`, `grader_result.json`, `trial_record.json` and `agent_output.jsonl` under
`/tmp/primary_art/<trial>/` were read. Evidence line numbers are line numbers in that trial's `diff.patch` (not in the
file). One replay was run (trial 45947367007-68, see below). Ten React and four Node failures share signatures that
were already replayed in `docs/production-failure-diagnosis.md` (trials 11, 20, 12); the other members of those groups
are labelled from the identical grader signature plus the code in the diff, without a separate replay. That is an
inference, stated here so it is not mistaken for 14 separate replays.

Causes used (fixed list): 1 SDK-BROWSER-FETCH, 2 LOCAL-EVAL-GRADER-LIMIT, 3 ENV/KEY-HANDLING, 4 NO-EXPOSURE,
5 CONVERSION-WRONG, 6 IDENTITY-UNSTABLE, 7 UI-NOT-DRIVEN, 8 APP-BROKEN, 9 FLUSH/DELIVERY, 10 OTHER.

## Count by cause and arm

| Cause | Skill | Prompt | Total |
|---|---|---|---|
| 1 SDK-BROWSER-FETCH (react) | 10 | 0 | 10 |
| 2 LOCAL-EVAL-GRADER-LIMIT (node) | 4 | 0 | 4 |
| 3 ENV/KEY-HANDLING (all 3 corrected to PASS) | 2 | 1 | 3 |
| 10 OTHER (node, reload cache, see trial 68) | 1 | 0 | 1 |
| 4, 5, 6, 7, 8, 9 | 0 | 0 | 0 |
| **Total graded failures** | **17** | **1** | **18** |
| of which still failures after corrections | 15 | 0 | 15 |

By stack: react 10, node 5 (+1 corrected prompt trial = 6 node), python 2 (both corrected). No failure had the
cause NO-EXPOSURE, CONVERSION-WRONG, IDENTITY-UNSTABLE, UI-NOT-DRIVEN, APP-BROKEN or FLUSH/DELIVERY (as a cause of its
own; in the 10 React failures events are lost in delivery, but the cause is the SDK/fetch interaction, label 1).

## Table of all 18

"Failing checks" are the original grader verdicts. Variant is from `trial_record.json`.

| # | Trial | Arm | Stack | Failing checks | Cause | Evidence (diff.patch line / grader_result) |
|---|---|---|---|---|---|---|
| 1 | trial-45914099371-11 | skill | react | C2 C3 C4 | 1 SDK-BROWSER-FETCH | `src/flagsmith.js` diff:194 `import flagsmith from '@flagsmith/flagsmith/isomorphic'`; `events: 0` in every phase, `events_observed: []` |
| 2 | trial-45914099371-20 | skill | react | C2 C3 C4 | 1 SDK-BROWSER-FETCH | `src/flagsmith.js` diff:272 same isomorphic import; `events: 0`, `events_observed: []` |
| 3 | trial-45947367007-35 | skill | react | C2 C3 C4 | 1 SDK-BROWSER-FETCH | `src/flagsmith.js` diff:252 `import { createFlagsmithInstance } from '@flagsmith/flagsmith/isomorphic'`; `fetch` is only an optional parameter (diff:261, 268) that the Node verify script supplies, the browser app never does; `events: 0` |
| 4 | trial-45947367007-37 | skill | react | C2 C3 C4 | 1 SDK-BROWSER-FETCH | `src/flagsmith.js` diff:261 `import flagsmith from '@flagsmith/flagsmith/isomorphic'`; `events: 0` |
| 5 | trial-45947370678-14 | skill | react | C2 C3 C4 | 1 SDK-BROWSER-FETCH | `src/flagsmith.js` diff:168 `createFlagsmithInstance` from `.../isomorphic`; `events: 0` |
| 6 | trial-45947370678-22 | skill | react | C2 C3 C4 | 1 SDK-BROWSER-FETCH | `src/flagsmith.js` diff:179 same; `events: 0` |
| 7 | trial-45947370678-36 | skill | react | C2 C3 C4 | 1 SDK-BROWSER-FETCH | default entry, but `src/flagsmith.js` diff:281 `fetch: globalThis.fetch,` passed into `init` (the unbound-fetch pattern from the Development batch); `events: 0` |
| 8 | trial-45947370678-45 | skill | react | C2 C3 C4 | 1 SDK-BROWSER-FETCH | `src/flagsmith.js` diff:292 isomorphic import; `events: 0` |
| 9 | trial-45947370678-64 | skill | react | C2 C3 C4 | 1 SDK-BROWSER-FETCH | `src/flagsmith.js` diff:178 `import flagsmith from '@flagsmith/flagsmith/isomorphic'`; `events: 0` |
| 10 | trial-45947370678-78 | skill | react | C2 C3 C4 | 1 SDK-BROWSER-FETCH | `src/flagsmith.js` diff:90 isomorphic import; `events: 0` |
| 11 | trial-45914099371-12 | skill | node | C2 C4 C5 C6 | 2 LOCAL-EVAL-GRADER-LIMIT | `flagsmith.js` diff:109 `const enableLocalEvaluation = Boolean(serverKey && serverKey.startsWith('ser.'))`; `flags: 0` in all phases, only `join_clicked` seen |
| 12 | trial-45925699686-4 | skill | node | C2 C4 C5 C6 | 2 LOCAL-EVAL-GRADER-LIMIT | `flagsmith.js` diff:124 `const canEvaluateLocally = Boolean(environmentKey?.startsWith('ser.'))`, diff:134 `enableLocalEvaluation: canEvaluateLocally`; `flags: 0` |
| 13 | trial-45947367007-3 | skill | node | C2 C4 C5 C6 | 2 LOCAL-EVAL-GRADER-LIMIT | `flagsmith.js` diff:98 `enableLocalEvaluation: environmentKey.startsWith('ser.'),`; `flags: 0` |
| 14 | trial-45947367007-49 | skill | node | C2 C4 C5 C6 | 2 LOCAL-EVAL-GRADER-LIMIT | `app.js` diff:96 `enableLocalEvaluation: environmentKey.startsWith('ser.'),`; `flags: 0` |
| 15 | trial-45914099371-7 (corrected to PASS) | skill | python | C1 (original) | 3 ENV/KEY-HANDLING | the agent's `verify_ab_test.py` (diff:226) `ENV_KEY = os.environ["FLAGSMITH_CLIENT_KEY"]`; C1 reason `KeyError: 'FLAGSMITH_CLIENT_KEY'` during pytest collection |
| 16 | trial-45914099371-14 (corrected to PASS) | skill | python | C1 (original) | 3 ENV/KEY-HANDLING | C1 reason `ERROR verify_ab_test.py - AttributeError: 'NoneType' object has no attribute ...` at collection; keys come from `FLAGSMITH_SERVER_KEY`/`FLAGSMITH_CLIENT_KEY` (diff:76); the agent's own verification test needed credentials at import. Inferred from the C1 text and the fix's stated reason ("app test needs the credential variable at import"); the failure text is truncated |
| 17 | trial-45914099371-30 (corrected to PASS) | prompt | node | C1 (original) | 3 ENV/KEY-HANDLING | `environmentKey: process.env.FLAGSMITH_SERVER_KEY` (diff:70); C1 `test/app.test.js ... not ok` in a clean env. Inferred from the correction record, as for 16 |
| 18 | trial-45947367007-68 | skill | node | C5 | 10 OTHER | `flagsmith.js` diff:84 `const CACHE_TTL_MS = 30 * 1000` plus `valueCache` (diff:86-99): the reload within 30 s is served from an in-process cache, so no `/identities/` request, no exposure, and the grader sees `v1_reload: None` ("no identity observed after V1 reload"). C2-C4, C6 pass |

### Notes on the labels

- **Label 1 (10 trials).** Same mechanism as `docs/production-failure-diagnosis.md` trials 11 and 20: the SDK's event
  processor calls an unbound `fetch`, which a browser rejects with "Illegal invocation" (swallowed). Flags still load,
  events never leave, so C2/C3/C4 fail while C5/C6 pass (identity and button text are right: see the `identities`
  field, `v1_load == v1_reload`). The isomorphic entry causes it in 9 trials; trial 36 reaches it through
  `fetch: globalThis.fetch`. Not a harness artefact: a real browser would also lose events. Every one of these agents
  verified in Node with a wrapped `fetch` (`verify-flagsmith.*` in the diff), which cannot show the bug.
- **Label 2 (4 trials).** The grader injects `FLAGSMITH_SERVER_KEY=ser.GRADER_FAKE_SERVER_KEY_...`
  (`grader/stacks.py:19`). The agents turn on local evaluation when the key starts with `ser.`; the Node SDK then reads
  `environment-document/`, which `grader/mock.py` does not serve, so no identity flags request is made and the SDK
  falls back to the default flag (no exposure metadata). This is the previously diagnosed grader limitation. The cause
  is agent-chosen but the failure is the harness's. Whether local evaluation would also work in production (the
  environment document carrying experiment enrolment) is not established, so these are not counted as agent bugs and
  not as passes.
- **Label 3 (3 trials, corrected).** C1 failed only because the existing test ran without the credential variables
  the grader supplies at app start. They are PASS after the documented correction. They are listed here because they
  were graded failures.
- **Label 10, trial 68.** Replayed: the diff applied unchanged fails C5 (original). With the single line changed to
  `const CACHE_TTL_MS = 0` the same diff passes C1-C7 (replay: apps/node copy, unmodified grader, `--mode proxy`).
  So the cause is the agent's added 30 s cache, not identity (the visitor id is stable, `v1_load` and the click use it)
  and not delivery. It is arguably a design choice (no second read within 30 s means no second exposure), so it is
  not clearly a defect for a real deployment; it is a grader observability limit that the agent triggered by adding a cache nobody asked for.

## Does SKILL.md contain, encourage, or lack a warning for each pattern?

Line numbers refer to `skill/flagsmith-ab-test/SKILL.md`.

| Cause | Contains or encourages? | Lacks a warning that would have prevented it? | Verdict |
|---|---|---|---|
| 1 SDK-BROWSER-FETCH (10) | No: `isomorphic`, `fetch` never appear. Lines 69-70 show `flagsmith.getExperimentFlag(...)` and `useExperiment(...)` with **no import path or entry point**, so the agent must pick one. The agents found `isomorphic.d.ts` in `node_modules` (trials 14, 64, 37 `ls node_modules/@flagsmith/flagsmith`) and chose it | Yes. Line 11 "Do not browse docs or explore unless a command fails" removes the docs page that shows `import flagsmith from '@flagsmith/flagsmith'`. Lines 91-94 (step 7) ask for "one script/run" with "SDK debug log, request log, or a short script", which agents wrote in Node; line 14 "Do not re-verify" then stops them. No line says the browser path must be verified in a browser or that the browser needs the default entry | Absence of guidance plus a rule that discourages the safety net (docs); it neither teaches nor forbids the pattern |
| 2 LOCAL-EVAL (4) | No: local evaluation is never mentioned | Partly: lines 20 and 107 distinguish a client key from a server key and warn never to put a server key in browser code, but nothing says "use remote evaluation; do not enable local evaluation". The brief itself supplies `FLAGSMITH_SERVER_KEY` (`brief/TASK_BRIEF.md:20`), which invites the Node agents to use it and then to key behaviour on its `ser.` prefix | Unrelated to the skill's text; the trigger is the brief plus the grader fake key. Weak lack-of-warning |
| 3 ENV/KEY (3) | No. Line 20 says "Never commit keys; read them from env/config" (correct, but it does not say tests must not need the key at import) | Yes, mildly: no line about keeping the existing test runnable without credentials | Grader bug, fixed by correction. Prompt arm had one as well, so unrelated to the arm's text |
| 10 trial 68 cache | No. Line 26 says identity must be "stable across reloads"; line 93 asks to confirm "a second call for the same id gives the same value" | Not directly: nothing discourages a result cache, nothing says every page view should call `getExperimentFlag` | Unrelated; agent-added optimisation |

## Suggestions for a future SKILL revision and prompt (NOT applied)

Each is tied to observed counts (among the 18 failures unless noted).

1. **Name the browser import explicitly (fixes 10 of 15 remaining failures).** In step 6 give the exact imports:
   `import flagsmith from '@flagsmith/flagsmith'` for browser JS and `import { FlagsmithProvider, useExperiment, useFlagsmith } from '@flagsmith/flagsmith/react'`, and add "Do not use `@flagsmith/flagsmith/isomorphic` in browser code and never pass `fetch: globalThis.fetch` / `window.fetch` into `init` (the SDK calls it unbound and every event is lost)". Count: 10 failures (9 isomorphic import, 1 unbound `fetch`).
2. **Require verification in the real runtime (10 failures).** Step 7 should say: for browser apps, verify in a browser (or a jsdom/Playwright run) that a network request to the events URL is actually made. A Node script with a wrapped `fetch` passes while the browser path is broken; all 10 React failures had exactly that script. Relax line 14 ("Do not re-verify") so it does not stop after a verification that cannot see the failure mode.
3. **Allow one targeted docs read (10 failures, hypothesis).** Replace line 11's blanket "Do not browse docs" with "read https://docs.flagsmith.com/experimentation/run-an-experiment once for the stack's tab and copy its import lines". Observed: all 108 prompt-arm trials fetched that page (244 `webfetch` calls) and none used the isomorphic entry; 1 of 112 skill-arm trials fetched it, and 10 skill-arm React diffs import the isomorphic entry in `src/` (9 of them are failures; the tenth, trial 45947370678-57, passed a bound fetch) against 0 in the prompt arm.
4. **State "remote evaluation only" (4 failures).** Add: "Do not enable local evaluation (`enableLocalEvaluation`) and do not branch on the key's prefix; initialise the server SDK for remote evaluation with the key provided." This also removes the grader/mock dependency. Independently, the grader could implement `environment-document/` or stop injecting a `ser.`-prefixed key (see `docs/production-failure-diagnosis.md`); that is a harness decision, not a skill one.
5. **Tests must not need credentials at import (3 failures, all grader-corrected).** Add "any test you add must pass with no Flagsmith env vars set; read keys lazily and skip, do not raise, when absent". The prompt has the same exposure ("Keep keys out of source control" is its only key advice), so both texts could carry it.
6. **Do not cache the experiment flag (1 failure).** Add "call `getExperimentFlag` on each render/request; do not memoise its result" so that reloads re-record exposure; if caching is wanted, key the exposure call on the first read only and say so. This is a low-value suggestion (1 trial, arguably acceptable behaviour).
7. **Show the import in every snippet.** Lines 69-71 give calls without the import or construction (`flagsmith` is undefined in the snippets). Each of the three lines should carry the `import`/constructor line so the agent does not infer the entry point from `node_modules` (supports 1; zero direct count beyond the 10 React cases).
8. **Official prompt (observation, not a skill change).** Step 8 recommends `EventProcessorConfig(max_buffer_items=1)` for Python, which loses exposures (already in `prompt/OFFICIAL_PROMPT.md:29` and `docs/verified-facts.md`); no failure in this run had that cause, so this suggestion rests on the spike, not on the 18. The prompt's key advice is also silent on test-time credentials (3 failures, one in each of the two arms' texts).

## What the prompt arm's result might mean (hypothesis, not fact)

All of the following comes from reading the two texts and the passing diffs plus the tool counts above; none of it was
tested by an intervention.

- The prompt sends the agent to a docs page (step 2: "Read https://docs.flagsmith.com/experimentation/run-an-experiment
  and follow its tab for this app's language"). The agent fetched it in 108 of 108 prompt trials, and the fetched React
  tab shows `import flagsmith from '@flagsmith/flagsmith'` in every example. No prompt-arm React diff uses the
  isomorphic entry. The skill instead says "Do not browse docs" (line 11) and holds no import path, so agents inspect
  `node_modules`, see `isomorphic.d.ts` and take it. Hypothesis: the official prompt works because it delegates SDK
  specifics to a living page that contains the right import; the skill, in compressing, dropped the one detail that
  mattered.
- The docs page also supplies the Node tab (remote evaluation by default), and no prompt-arm Node diff enables local
  evaluation, while 4 of the 5 residual Node skill failures do. The skill gives the Node key rule (line 20) without
  the evaluation mode.
- Of the 10 skill-arm React diffs that import the isomorphic entry in `src/`, 9 are failures and 1 (trial
  45947370678-57) passed because the agent noticed the problem, wrote a comment about "Illegal invocation" and passed
  a bound `safeFetch` (diff:389-412). So the skill's outcome depends on whether the agent happens to discover the
  fetch problem on its own; the docs-derived import avoids the question. (Counts are of trials whose `src/` imports
  the isomorphic entry; mentions in test or verify scripts are excluded. One skill trial, 45947367007-33, has no
  grader result and is not counted anywhere here.)
- The prompt asks for step-by-step verification and an approval gate that headless trials answer from the brief; the
  skill compresses this into a single verification (lines 14, 91-97). Hypothesis: the prompt's longer procedure gives
  more chances for a browser-side problem to surface, but this was not examined (the prompt arm's verification
  behaviour was not compared trial by trial).
- Caveat: the prompt arm may also differ in other ways not checked here (turns, token budget per trial, the cost of the
  docs fetch). The comparison is observational and the arms are not matched on those.
