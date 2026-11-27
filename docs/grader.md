# The grader

An independent, deterministic judge of whether an app's Flagsmith A/B test is correctly wired.
It never talks to the real Flagsmith: it has no credentials and trial apps must not send traffic there.

```
python -m grader --app-dir <path> --stack <react|node|python> --flag <name> --event join_clicked \
                 --variant-values "Join,Join free" --out result.json [--mode proxy|emulator]
```

Exit code: 0 = pass, 1 = integration failed, 2 = grader error (a `result.json` is still written).

## Optional flags for apps of any shape (additive)

None of these changes anything when absent: `--start-cmd "<cmd>"` (shell command that starts the app; default per stack),
`--url` (page URL to load and health-check; default `http://127.0.0.1:<port>/`), `--click-selector "<css>"` (element to click;
default `#join-btn`, else a button named Join; `--event` and `--variant-values` already name the conversion event and the
button texts), `--stack custom` (no install, no app test; needs `--start-cmd`; the port comes from `--port` or `--url`,
else 3000; the app is copied keeping `node_modules`, so install dependencies before grading; a `.venv` does not survive the copy) and `--report`
(readable C1-C7 table with one fix hint per failed check; the default on a TTY, otherwise the one-line-per-check output is
unchanged). `result.json` has the same schema plus a `hints` object (failed check -> fix hint). The emulator already serves the
last `--variant-values` entry as the variation, so no emulator change was needed. The new flags are additive; `grader/tests/test_wiring_check.py` pins that.

## Procedure

1. Copy the app to a temp dir, install dependencies (`npm ci` / venv + `pip install -r requirements.txt`; installs are
   cached by a hash of `package.json`+`package-lock.json` / `requirements.txt`, disable with `GRADER_NO_CACHE=1`).
2. Run the app's own test (`npm test` / `pytest`).
3. Start the app (`npm start` / `python app.py`) on the stack's default port (react 5173, node 3000, python 5000; `--port`
   overrides, also passed as `PORT`), wait up to 120 s for HTTP 200.
4. Playwright (Chromium): **V1** loads the page (network idle + 13 s, phase `load`), clicks Join (idle + 13 s, phase
   `click`), reloads in the same context (idle + 13 s, phase `reload`); **V2** loads in a fresh context (idle + 13 s,
   phase `v2`). The 13 s waits are explained in the next section.
5. Every Flagsmith request is recorded with its phase. The phase marker is flipped through the emulator's admin endpoint
   `/__grader/phase?name=...`. Evaluate C1..C7, write `result.json`.

## Waits: why 13 s (grader bug found in the pilot, 2026-11-26)

All three Flagsmith SDKs buffer analytics events and flush them on a **10 s timer** by default (`docs/flagsmith-sdk-notes.md`).
The original design waited 3 s after load and 5 s after the click. A *correct* integration that calls
`trackEvent` / `track_event` without an explicit flush (delivered by the SDK's own timer in any real long-running
server) was therefore wrongly failed on C3/C4, and exposures from the load phase could land in the next phase.
Evidence: trial 4 of CI run 45890705758 (exposure only observed in the `reload` phase, no `join_clicked`); the same app
re-graded locally passed.

Fix: `--load-wait` and `--click-wait` now default to **13 s** (longest default flush interval 10 s + 3 s margin). The
load wait is used for the `load`, `reload` and `v2` phases and the click wait for `click`, so every buffered event is
flushed inside its own phase. Both flags remain overridable (the fast self-tests pass short explicit waits).

This **deviates from the spec's 3 s / 5 s waits** for the reason above. It is a longer wait only: no timestamp logic
was added and the **C1-C6 pass conditions are UNCHANGED**. Fixtures: `NF` (reference with every explicit flush removed)
must pass C1-C6 with the default waits on three identical runs, and `B3NF` (conversion on page load, no flush anywhere)
must still fail C3, which shows the longer load wait stops an unflushed load-time conversion from leaking into the click
phase. The saved pilot diffs were re-graded offline with the new waits (`archive/process-notes` branch).

## Test-env fix for C1 (found after 40 production trials)

C1 runs the app's existing test in a clean environment. That environment lacked the placeholder credential variables the
grader supplies when it starts the app, so an app that reads its key from the environment at import time (good
practice) failed C1 spuriously (3 of 40 production trials). The fix is **one-directional**: the test first runs in the
clean env exactly as before; only if that run FAILS is it re-run once with the placeholder `FLAGSMITH_CLIENT_KEY`,
`FLAGSMITH_SERVER_KEY`, `VITE_FLAGSMITH_CLIENT_KEY`, `FLAGSMITH_FLAG`, `VITE_FLAGSMITH_FLAG`; if that second run passes,
C1 passes and its detail says "existing test passed only with credential variables set". An earlier pass is never
turned into a fail, so tests written for a keyless setup are unaffected, and a genuinely failing test still fails
(B1). Self-tests: Python and Node reference apps made to throw at import without the key
(`test_c1_passes_when_test_needs_key_at_import`) pass C1. Replays are recorded in `data/corrections.jsonl`.

## Known limitation (C6)

The grader's Flagsmith emulator returns a fixed variant key and the value `Join free`. An integration that branches on the
variation KEY (e.g. `flag.variant === 'Join_free'`) instead of the flag VALUE cannot be verified against the emulator and is
scored as failing C6. This was observed in one pilot trial (prompt arm, React). In principle it applies to both arms
equally. C6's pass condition is unchanged.

## The local Flagsmith emulator and how traffic is intercepted

No Flagsmith credentials exist in the grader, so a **local Flagsmith emulator** (`grader/mock.py`) answers both APIs:
flags/identities (`GET /identities/?identifier=` for the browser SDK, `POST /identities/` for server SDKs) and events
(`POST /v1/events`). For the trial's flag it returns a multivariate flag with `metadata.experiment.in_experiment = true`
and a variant key; that is what makes the SDK experiment methods emit `$flag_exposure` (`docs/flagsmith-sdk-notes.md`).
The variant is assigned by first sight of an identity: the first identity gets the variation (`Join free`), the next the
control (`Join`), so verdicts do not depend on random ids, and a hard-coded button text cannot pass C6 for both visitors.

How does the app reach the emulator? Two modes, with an trade-off:

| | `--mode proxy` (default; used for trials) | `--mode emulator` (fixture self-tests, cross-check) |
|---|---|---|
| Mechanism | The app keeps its **default** hosts (`edge.api.flagsmith.com`, `events.api.flagsmith.com`). mitmproxy (`grader/mitm_addon.py`) answers every `*.flagsmith.com` request itself from the emulator. App process gets `HTTPS_PROXY`/`https_proxy` (+ `HTTP_*`, `ALL_PROXY`), `NODE_USE_ENV_PROXY=1`, and the mitmproxy CA via `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, `NODE_EXTRA_CA_CERTS`, `CURL_CA_BUNDLE`; `NO_PROXY` is reset to loopback. Chromium runs with the proxy and `ignore_https_errors`. | The app is pointed at the emulator by env vars: `FLAGSMITH_API_URL`, `FLAGSMITH_EVENTS_URL`, `VITE_FLAGSMITH_API`, `VITE_FLAGSMITH_EVENTS_API` (the names the reference apps use). |
| Depends on agent cooperation | No. Works with whatever env var names / SDK options the agent chose, as long as the app uses the default hosts | **Yes**: the brief does not tell agents these URL variable names (`brief/TASK_BRIEF.md` names only the four key variables), so an agent app will usually *not* honour them |
| Needs | `mitmproxy`, Node >= 22.21 for Node apps (older Node ignores `HTTPS_PROXY`) | nothing extra |

Env vars the grader always sets for the app: `FLAGSMITH_CLIENT_KEY`, `FLAGSMITH_SERVER_KEY`, `VITE_FLAGSMITH_CLIENT_KEY`
(React bakes `VITE_*` at build time, so the grader builds with them), `FLAGSMITH_FLAG`, `VITE_FLAGSMITH_FLAG`, `PORT`.
The keys are distinctive **placeholders** (`GRADER_PLACEHOLDER_CLIENT_KEY_...`, `ser.GRADER_PLACEHOLDER_SERVER_KEY_...`); the real
`FLAGSMITH_*`, `FS_*`, `ANTHROPIC_*` variables of the calling environment are stripped from the app's environment.

**What the grader relies on (the contract).** The app (1) uses the Flagsmith SDK (or any client) against the default
Flagsmith hosts over HTTP(S) honouring `HTTPS_PROXY` and the CA env vars (all three official SDKs do, Node with
`NODE_USE_ENV_PROXY=1`), (2) reads the key from `FLAGSMITH_CLIENT_KEY` / `FLAGSMITH_SERVER_KEY` (React: from a build-time
`VITE_` variable the app maps itself; the grader provides `VITE_FLAGSMITH_CLIENT_KEY`), (3) renders a button with id
`join-btn` (or any button whose text contains "Join"), (4) serves on the stack's default port.

**What a failure of interception means.** If no request reaches the emulator/proxy, C2 fails with
`no Flagsmith traffic observed ...`. That means one of: the app never called Flagsmith; it uses a custom/self-hosted host
(only `*.flagsmith.com` is intercepted); its HTTP client ignores `HTTPS_PROXY` or pins its own CA; or (emulator mode) it ignores
the URL env vars. It is a failure of the *app's integration as the grader can observe it*, not a silent skip. This is a
known limit of the design: an app that hard-wires its own proxy/CA or a non-Flagsmith-domain host cannot be graded.
If a trial agent could not possibly succeed under these conditions that is a grader/brief bug, so the self-test
`test_no_traffic_is_reported_explicitly` pins the exact wording of the failure.
Not verified: pointing the SDKs at the real hosts through mitmproxy *in forwarding mode* (the addon here never forwards).

## SDK local evaluation: the emulator serves the environment document (post-freeze, 2026-11-27)

An app may legitimately use SDK local evaluation (`enableLocalEvaluation: true` / `enable_local_evaluation=True`, which needs a server key beginning `ser.`). The SDK then downloads `GET <api>/environment-document/` (header `X-Environment-Key: ser.<token>`, no body), buckets identities itself and sends exposures from that result. Until this amendment the emulator had no such endpoint, so the SDK fell back to defaults and no exposure fired: a grader limitation, not a failure of the app (8 saved skill-arm Node trials, `data/flagged.jsonl`). See `EXPERIMENT.md`, "Amendment: emulator serves the environment document".

**What the emulator returns.** `ops/dump_env_document.py` printed the structure of the live Development document. Top level: `id, api_key (client key), name, project{id, name, organisation{id, name, feature_analytics, stop_serving_flags, persist_trait_data}, hide_disabled_flags, segments[], enable_realtime_updates, server_key_only_feature_ids[]}, feature_states[], identity_overrides[], allow_client_traits, updated_at, hide_sensitive_data, hide_disabled_flags, use_identity_composite_key_for_hashing, use_identity_overrides_in_local_eval`. A multivariate feature state is `{feature{id, name, type: "MULTIVARIATE"}, enabled, django_id, feature_segment, featurestate_uuid, feature_state_value, multivariate_feature_state_values[{multivariate_feature_option{value, id, key}, percentage_allocation, id, mv_fs_value_uuid}], metadata{experiment{id, in_experiment, name}}}`. The emulator serves the same keys for the trial's flag: control value as `feature_state_value`, one option per variant value (key `variant_<i>`, the same keys as the identities endpoint) with equal `percentage_allocation`, and `metadata.experiment.in_experiment = true`. A non-`ser.` key gets 401. The requests are recorded as kind `environment`, and `result.json` gets a `local_evaluation` block (key absent otherwise).

**How the SDKs use it** (read from `@flagsmith/nodejs` 9.5.0 and `flagsmith` 6.7.0): the Node SDK fetches the document lazily on the first evaluation and again every 60 s; the Python SDK fetches it in the constructor. The flag value is the option whose weight interval contains `hash(django_id, "<api_key>_<identifier>")`, and `getExperimentFlag` / `get_experiment_flag` take `variant` from the option `key` and `in_experiment` from `metadata.experiment`, so exposures fire exactly as with remote evaluation. Real Flagsmith counts such exposures for Node (`ops/rehearsal_node_localeval.py`: 6 locally evaluated Node identities plus 2 remote Python controls gave 8 exposure identities in the experiment results).

**What changed in the checks, and what did not.** Pass conditions and wording of C1 to C7 are unchanged; with remote evaluation nothing is different.
- *C6 expected value.* The value for an identity is the value of the flags request for that identity, as before. Only if there is no flags request for it AND the app downloaded the environment document, it is `FlagsmithEmulator.local_value(identity)`, the engines' hash (`md5` of `"<django_id>,<api_key>_<identifier>"`, `(int % 9999) / 9998 * 100`, cumulative weights in option-id order). Checked against both SDKs for 60 identities each (no mismatch, exposures `in_experiment`).
- *Identity of a visitor under local evaluation* (found by the offline regrade, added the same day): there is no flags request to read it from, so the identity is the first exposure event of the phase. The SDK sends events on its 10 s timer, so the exposure of the grader's own health-check request (made before any visitor, no cookie, a throw-away identity) can ARRIVE inside the `load` phase and be taken for V1's identity (C5 and C6 then failed a correct app). Only when the document was requested, an event is attributed to the phase it was CREATED in: events whose own `timestamp` is earlier than the phase start (`FlagsmithEmulator.phase_starts`) are skipped by `phase_identity`. With remote evaluation the flags request decides as before and nothing changed. Test: `test_local_evaluation_without_explicit_flush_passes_with_default_waits` (no explicit flush, default waits) and a unit test with fabricated records.
- *Assignment order cannot apply.* The hash decides, so the "first identity gets the variation" property of the identities endpoint does not hold here. To keep C6 able to fail a hard-coded text, `grader/cli.py` adds fresh visitors (phases `v3`, `v4`, ..., at most 8, `browser.run_extra_visitor`) when the document was requested and V1 and V2 have the same expected value, until one identity's expected value differs; C6 compares every visitor. Nothing is added when V1 and V2 already differ or the document was not requested. A hard-coded text passes only if all 8 extra identities hash the same as V1 (probability 2^-8 when V1 and V2 share a variant).
- *Self-tests* (`grader/tests/test_local_eval.py`, marker `grader`): `apps/reference/node-local-eval` (the Node reference with `enableLocalEvaluation: true`) passes C1 to C7 in emulator and proxy mode, with zero identities-endpoint requests; broken copies generated from it with the same patches as the other stacks fail exactly their check: B3 conversion on load (C3, both modes), B4 other conversion identity (C4), B5 unstable identity (C5 and, as on the other server stacks, C4), B6 hard-coded button text (C6, both modes). The existing suite (`pytest grader -m grader`) is unchanged and passes.

## Checks (pass = C1 and C2 and C3 and C4 and C5 and C6; C7 is diagnostic)

Identity of a visitor = the identifier of the first flags request in that phase (fallback: first exposure, then any event).

| ID | In plain language | Broken example that fails it |
|---|---|---|
| C1 App runs | Dependencies install, the app's own test passes, the app serves HTTP, and the Join button exists and is clickable. If C1 fails the browser phase is skipped and C2..C7 report "not evaluated". | **B1** syntax error in the app source |
| C2 Exposure sent | V1's identity sent a `$flag_exposure` for the trial's flag (read with `getExperimentFlag` / `get_experiment_flag`). No traffic at all -> `no Flagsmith traffic observed`. | **B2** flag read with a plain getter: no exposure |
| C3 Conversion on action | `join_clicked` arrives in the click phase and none during load. | **B3** event sent on page load |
| C4 Identity match | Every `join_clicked` identity equals the exposure identity (if there is no exposure, the identity V1 used for the flag request). | **B4** conversion identity prefixed `other-` |
| C5 Identity stable | V1 keeps its identity after reload; V2 (fresh context) gets a different one. | **B5** new random identity on every load |
| C6 Flag drives the UI | The rendered button text is a variant value and equals what the emulator returned for that identity, for V1 *and* V2. | **B6** button keeps the hard-coded control text |
| C7 No server key in client (diagnostic) | No browser-loaded response body or the rendered DOM contains the grader's placeholder server key or any `ser.<token>` string. Recorded, never part of the verdict. | **B7** server key embedded in the page/bundle |

Known dependent failures (documented, asserted in the self-tests): on the **server** stacks B5 also fails C4 (the identity is
regenerated per request, so the click request carries a new identity); B1 fails C1 and everything after it is "not evaluated".

## result.json

`passed`, `checks.C1..C7.{passed, reason (failures), detail (passes)}`, `identities` (v1_load, v1_reload, v2),
`button_text`, `request_counts` per phase (flags / events / other / total), `events_observed` (phase, host, event, identity),
`durations` (install, tests, startup, browser, total seconds), `grader_version` (git SHA), `mode`, `stack`, `flag`.

## Self-tests

`python -m pytest grader -m grader` (needs node >= 22.21, npm, Chromium via `playwright install chromium`, `mitmproxy`;
set `GRADER_CHROME_PATH` to use a system Chrome). They prove: every reference passes all checks on all three stacks in both
modes; each broken app (`apps/broken/make_broken.py --all`) fails its matching check with a reason naming the problem;
B7 fails only C7 and the verdict still passes; an app that never calls Flagsmith fails C2 explicitly; 3 runs give the
same verdict; the default 13 s waits work, a reference with no explicit flush passes and an unflushed load-time conversion still fails C3 (the `NF` / `B3NF` fixtures, all three stacks incl. React). CI: `.github/workflows/grader.yml`.

## Adapt it to your devtool

The method is not Flagsmith-specific. Any devtool team that onboards AI agents (a prompt to paste, or a skill to install) can ask "which handoff gets agents to a working integration more often?" with the same parts.

1. **Two handoffs, one task.** The prompt is the text you would paste today, unmodified (`prompt/`). The skill is the same knowledge packaged as an Agent Skill (`skill/`). Keep everything else identical: model, limits, sample apps, clean workspace.
2. **One task brief.** `brief/TASK_BRIEF.md` states the outcome in the user's words and never names your SDK methods, so the experiment tests the handoff and not the brief. Assign stacks at random per trial.
3. **A grader contract.** The grader decides success, never the agent and never a human. It is a black box that drives the app with a real browser and observes only network traffic. It answers your service locally, so grading needs no credentials. It applies binary checks frozen before the run. It is self-tested with one known-good app that passes every check and one broken copy per check that fails exactly that check (`apps/broken/`, `grader/tests/`).
4. **Honest reporting.** Pre-register the question, the checks, the stopping rule and the analysis (`EXPERIMENT.md`). Randomise the arm, run both arms equally, fix grader bugs only in ways that cannot change a pass condition, and document each fix.

To point the grader at your product, change what the emulator serves and what the checks look for. The flags `--event`, `--click-selector`, `--variant-values`, `--start-cmd` and `--stack custom` already cover apps outside Flagsmith's sample shape (`apps/reference/custom-signup/`).
