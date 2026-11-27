# Production run 45914099371: root cause of three skill-arm failures

Scope: trials 12 (node), 11 (react) and 20 (react), all `variant: skill`, which still failed after the grader fix
(grader `c74e237`). Method: artifacts `trial-45914099371-<n>` (`diff.patch`, `grader_result.json`, `agent_output.jsonl`)
were downloaded; each diff was applied to a clean copy of `apps/<stack>` and graded with the unmodified grader in
`--mode proxy`; then one hypothesised change was applied to a second copy and graded again. Nothing in the grader,
skill, prompt or runner was edited. The failures reproduce exactly outside CI.

| Trial | Stack | Label | One-line cause |
|---|---|---|---|
| 11 | react | AGENT MISTAKE | `@flagsmith/flagsmith/isomorphic` in a browser with the default fetch: the SDK's event processor calls its fetch unbound, so no event is ever sent |
| 20 | react | AGENT MISTAKE | same as trial 11 |
| 12 | node | HARNESS ARTEFACT (with one caveat, below) | the agent enables SDK local evaluation because the grader's fake key starts with `ser.`; the mock serves no environment document, so no identity flags are evaluated |

No trial is labelled SKILL-INDUCED. The skill does not name the isomorphic entry point, a fetch option, or local evaluation.
It does shape how the agents verified, see "Skill involvement".

## Trials 11 and 20 (react): AGENT MISTAKE

Evidence from the grader results (identical signature in both): `request_counts` per phase is
`flags: 1, events: 0, other: 1`; `events_observed: []`. C2 (no `$flag_exposure`), C3 (no `join_clicked`) and C4 fail;
C5 and C6 pass, so the flag is fetched and the button renders the right variant. Only event delivery is lost.

Cause. Both diffs import `flagsmith from '@flagsmith/flagsmith/isomorphic'` (`src/flagsmith.js`) and run it in the
browser with no `fetch` option. The isomorphic build takes the global fetch as a bare function reference
(`_fetch = fetch`, `src/flagsmith-core.ts` around line 79-82) and hands it to the event processor
(`fetch: _fetch`, line 478), which calls `this.fetch(this.endpoint, ...)`. With `this` set to the EventProcessor,
a browser's native `fetch` throws `Illegal invocation`, and the SDK swallows the error. The flags request is made by
the core, not the event processor, so it still works. This is the same mechanism as the earlier bug where the agent
passed `fetch: globalThis.fetch` into `init`; here the agent triggers it simply by using the isomorphic entry in a
browser. Neither diff contains `fetch: globalThis.fetch`, so that exact pattern is not the cause. The reference app
avoids the problem by importing the default `@flagsmith/flagsmith` entry, which uses XHR/unfetch. This is not a harness
quirk: a real browser deployment of these diffs would also send no exposure or conversion events.

Replay. Unmodified diffs: grader FAIL (C2, C3, C4), reproducing the CI numbers. With one added line in the `init`
options, `fetch: (...args) => globalThis.fetch(...args),`, in `src/flagsmith.js` of each: C1 to C7 all PASS for both
trials (events observed with the correct identity, exposure and conversion on the same id).

## Trial 12 (node): HARNESS ARTEFACT, one caveat

Evidence: `request_counts` show `flags: 0` in every phase and one `other` request per phase; the only event the
mock saw was `join_clicked` in the click phase. So the conversion path works but the flag read never produced an
exposure and never issued an identity flags request: C2 fails with "Flagsmith traffic seen but no $flag_exposure",
and C4/C5/C6 fail with "no identity observed" (the grader derives identity from `/identities/` requests or exposure
events, and there are none). The button stays `Join` in V1 and V2.

How the flag is read: `app.js` calls `await flagsmith.getExperimentFlag(JOIN_BUTTON_FLAG, vid)`, the
identity-specific experiment method with a per-visitor id. That is correct. The problem is in `flagsmith.js`:

    const enableLocalEvaluation = Boolean(serverKey && serverKey.startsWith('ser.'))

`grader/stacks.py` injects `FLAGSMITH_SERVER_KEY=ser.GRADER_FAKE_SERVER_KEY_...`, so the agent's code turns on local
evaluation. In `@flagsmith/nodejs` 9.5.0, local evaluation reads the environment document
(`GET <api>environment-document/`, `sdk/index.js` line ~115) and evaluates flags in-process, so no `/identities/`
request is made. `grader/mock.py` `handle()` implements `/identities/`, `/flags/`, `/v1/events` and analytics only;
every other path returns 404, which is the `other` request (inferred from the SDK code and the request counts, not
separately logged). `getIdentityFlags` then catches the error and returns the agent's `DefaultFlag('Join', true)`,
which has no experiment metadata, so `getExperimentFlag` records no exposure. `trackEvent` is independent of flag
evaluation, hence the one event that did arrive.

Replay. Unmodified diff: grader FAIL with the same C2/C4/C5/C6 messages. With the single line changed to
`const enableLocalEvaluation = false`, remote evaluation is used, `/identities/` is hit, and C1 to C7 all PASS.

Why harness artefact: the grader's own fake key format flips the app into a code path whose required endpoint the
mock does not implement; a real deployment with a real server key would not 404 on the environment document.
Caveat (not verified): whether a real environment document carries the experiment enrolment
(`metadata.experiment.in_experiment`) so that local evaluation emits exposures is not established by this harness. The
SDK maps `metadata.experiment` from environment-document feature states, so it may work, but if it does not, local
evaluation would be an agent choice that loses exposures in production as well. The skill never asks for local
evaluation (see below), so this is the least clear-cut of the three.

## Skill involvement

`skill/flagsmith-ab-test/SKILL.md` (frozen, read only) does not contain or recommend any of the offending patterns:
`isomorphic`, `fetch` and local evaluation do not appear in it. Relevant lines:

- Lines 69-71: `const flag = useExperiment('<flag>');  // React` and
  `const flag = await flagsmith.getExperimentFlag('<flag>', visitorId);  // Node`. Both agents followed these correctly.
- Line 89: "Long-running servers and browsers flush on a timer (about every 10 seconds); flush explicitly only in scripts and
  tests." This is why neither react app flushes in-app; flushing would not have helped, because the flush uses the same
  broken fetch.
- Line 91-94, step 7: "Verify once, then stop ... In one script/run: 1. Use a fresh visitor id; call the
  experiment-flag method, then perform the action once, then flush. 2. Check the output ... shows: an exposure for
  `<flag>` with identity X, the conversion `<event>` with the same identity X ...". Line 14: "After ONE successful
  verification (step 7), stop ... Do not re-verify or polish."

Contributing factor for 11 and 20: step 7 asks for a script run, and both agents wrote a Node-side script
(`verify-flagsmith.mjs` in trial 11, `scripts/verify-experiment.verify.js` run under a `node` vitest environment in
trial 20) that wraps `globalThis.fetch`. In Node an unbound global fetch works, so the verification passed while the
real browser path was broken, and the one-verification rule then told them to stop. The skill does not tell the agent
to verify in a browser, nor to use the isomorphic entry, so this is a verification gap rather than a skill-induced
coding error.

## Does the grader need a change?

- Trials 11, 20: no. The grader correctly reports a real defect (no events leave the browser).
- Trial 12: yes, to be fair to apps that use local evaluation with the grader's fake `ser.` key. Precisely, in
  `grader/mock.py` `handle()`, add a handler for `path.endswith("/environment-document/")` that returns an environment
  document containing the trial flag as a multivariate feature state with `metadata.experiment.in_experiment = true`
  (plus the project/environment objects the engine needs). Caveats: with local evaluation the variant is chosen by the
  SDK's hashing, not by the mock's first-seen rule, and no `/identities/` request is recorded, so the identity and
  expected-value derivation for C5/C6 (`phase_identity`, `expected_value` in `grader/checks.py`) would also have to use
  exposure identities and a document-derived expected value. The cheaper alternative is to stop injecting a
  `ser.`-prefixed value as `FLAGSMITH_SERVER_KEY` (`FAKE_SERVER_KEY` in `grader/stacks.py`), which keeps apps on remote
  evaluation; the C7 leak check would still match the exact string. That alternative hides the local-evaluation case
  rather than grading it, so it should be a recorded decision. Either way, trial 12 should be reported as a harness
  failure, not an agent failure.
