# The grader

An independent, deterministic judge of whether an app's Flagsmith A/B test is correctly wired (BUILD_SPEC section 10).
It never talks to the real Flagsmith: it has no credentials and trial apps must not send traffic there.

```
python -m grader --app-dir <path> --stack <react|node|python> --flag <name> --event join_clicked \
                 --variant-values "Join,Join free" --out result.json [--mode proxy|mock]
```

Exit code: 0 = pass, 1 = integration failed, 2 = grader error (a `result.json` is still written).

## Procedure

1. Copy the app to a temp dir, install dependencies (`npm ci` / venv + `pip install -r requirements.txt`; installs are
   cached by a hash of `package.json`+`package-lock.json` / `requirements.txt`, disable with `GRADER_NO_CACHE=1`).
2. Run the app's own test (`npm test` / `pytest`).
3. Start the app (`npm start` / `python app.py`) on the stack's default port (react 5173, node 3000, python 5000; `--port`
   overrides, also passed as `PORT`), wait up to 120 s for HTTP 200.
4. Playwright (Chromium): **V1** loads the page (network idle + 13 s, phase `load`), clicks Join (idle + 13 s, phase
   `click`), reloads in the same context (idle + 13 s, phase `reload`); **V2** loads in a fresh context (idle + 13 s,
   phase `v2`). The 13 s waits are explained in the next section.
5. Every Flagsmith request is recorded with its phase. The phase marker is flipped through the mock's admin endpoint
   `/__grader/phase?name=...`. Evaluate C1..C7, write `result.json`.

## Waits: why 13 s (grader bug found in the pilot, 2026-11-26)

All three Flagsmith SDKs buffer analytics events and flush them on a **10 s timer** by default (`verified-facts.md` 1.3).
BUILD_SPEC section 10 specified 3 s after load and 5 s after the click. A *correct* integration that calls
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
phase. Offline re-grade of the saved pilot diffs: `docs/pilot-regrade.md`.

## Test-env fix for C1 (found after 40 production trials)

C1 runs the app's existing test in a clean environment. That environment lacked the fake credential variables the
grader supplies when it starts the app, so an app that reads its key from the environment at import time (good
practice) failed C1 spuriously (3 of 40 production trials). The fix is **one-directional**: the test first runs in the
clean env exactly as before; only if that run FAILS is it re-run once with the fake `FLAGSMITH_CLIENT_KEY`,
`FLAGSMITH_SERVER_KEY`, `VITE_FLAGSMITH_CLIENT_KEY`, `FLAGSMITH_FLAG`, `VITE_FLAGSMITH_FLAG`; if that second run passes,
C1 passes and its detail says "existing test passed only with credential variables set". An earlier pass is never
turned into a fail, so tests written for a keyless setup are unaffected, and a genuinely failing test still fails
(B1). Self-tests: Python and Node reference apps made to throw at import without the key
(`test_c1_passes_when_test_needs_key_at_import`) pass C1. Replays: `docs/pilot-regrade.md`.

## Known limitation (C6)

The grader's mock Flagsmith returns a fixed variant key and the value `Join free`. An integration that branches on the
variation KEY (e.g. `flag.variant === 'Join_free'`) instead of the flag VALUE cannot be verified against the mock and is
scored as failing C6. This was observed in one pilot trial (prompt arm, React). In principle it applies to both arms
equally. C6's pass condition is unchanged.

## The fake Flagsmith and how traffic is intercepted (read this)

No Flagsmith credentials exist in the grader, so a **local mock Flagsmith** (`grader/mock.py`) answers both APIs:
flags/identities (`GET /identities/?identifier=` for the browser SDK, `POST /identities/` for server SDKs) and events
(`POST /v1/events`). For the trial's flag it returns a multivariate flag with `metadata.experiment.in_experiment = true`
and a variant key; that is what makes the SDK experiment methods emit `$flag_exposure` (verified-facts.md).
The variant is assigned by first sight of an identity: the first identity gets the variation (`Join free`), the next the
control (`Join`), so verdicts do not depend on random ids, and a hard-coded button text cannot pass C6 for both visitors.

How does the app reach the mock? Two modes, with an honest trade-off:

| | `--mode proxy` (default; used for trials) | `--mode mock` (fixture self-tests, cross-check) |
|---|---|---|
| Mechanism | The app keeps its **default** hosts (`edge.api.flagsmith.com`, `events.api.flagsmith.com`). mitmproxy (`grader/mitm_addon.py`) answers every `*.flagsmith.com` request itself from the mock. App process gets `HTTPS_PROXY`/`https_proxy` (+ `HTTP_*`, `ALL_PROXY`), `NODE_USE_ENV_PROXY=1`, and the mitmproxy CA via `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, `NODE_EXTRA_CA_CERTS`, `CURL_CA_BUNDLE`; `NO_PROXY` is reset to loopback. Chromium runs with the proxy and `ignore_https_errors`. | The app is pointed at the mock by env vars: `FLAGSMITH_API_URL`, `FLAGSMITH_EVENTS_URL`, `VITE_FLAGSMITH_API`, `VITE_FLAGSMITH_EVENTS_API` (the names the reference apps use). |
| Depends on agent cooperation | No. Works with whatever env var names / SDK options the agent chose, as long as the app uses the default hosts | **Yes**: the brief does not tell agents these URL variable names (`brief/TASK_BRIEF.md` names only the four key variables), so an agent app will usually *not* honour them |
| Needs | `mitmproxy`, Node >= 22.21 for Node apps (older Node ignores `HTTPS_PROXY`) | nothing extra |

Env vars the grader always sets for the app: `FLAGSMITH_CLIENT_KEY`, `FLAGSMITH_SERVER_KEY`, `VITE_FLAGSMITH_CLIENT_KEY`
(React bakes `VITE_*` at build time, so the grader builds with them), `FLAGSMITH_FLAG`, `VITE_FLAGSMITH_FLAG`, `PORT`.
The keys are distinctive **fakes** (`GRADER_FAKE_CLIENT_KEY_...`, `ser.GRADER_FAKE_SERVER_KEY_...`); the real
`FLAGSMITH_*`, `FS_*`, `ANTHROPIC_*` variables of the calling environment are stripped from the app's environment.

**What the grader relies on (the contract).** The app (1) uses the Flagsmith SDK (or any client) against the default
Flagsmith hosts over HTTP(S) honouring `HTTPS_PROXY` and the CA env vars (all three official SDKs do, Node with
`NODE_USE_ENV_PROXY=1`), (2) reads the key from `FLAGSMITH_CLIENT_KEY` / `FLAGSMITH_SERVER_KEY` (React: from a build-time
`VITE_` variable the app maps itself; the grader provides `VITE_FLAGSMITH_CLIENT_KEY`), (3) renders a button with id
`join-btn` (or any button whose text contains "Join"), (4) serves on the stack's default port.

**What a failure of interception means.** If no request reaches the mock/proxy, C2 fails with
`no Flagsmith traffic observed ...`. That means one of: the app never called Flagsmith; it uses a custom/self-hosted host
(only `*.flagsmith.com` is intercepted); its HTTP client ignores `HTTPS_PROXY` or pins its own CA; or (mock mode) it ignores
the URL env vars. It is a failure of the *app's integration as the grader can observe it*, not a silent skip. This is a
known limit of the design: an app that hard-wires its own proxy/CA or a non-Flagsmith-domain host cannot be graded.
If a trial agent could not possibly succeed under these conditions that is a grader/brief bug, so the self-test
`test_no_traffic_is_reported_explicitly` pins the exact wording of the failure.
Not verified: pointing the SDKs at the real hosts through mitmproxy *in forwarding mode* (the addon here never forwards).

## Checks (pass = C1 and C2 and C3 and C4 and C5 and C6; C7 is diagnostic)

Identity of a visitor = the identifier of the first flags request in that phase (fallback: first exposure, then any event).

| ID | In plain language | Broken example that fails it |
|---|---|---|
| C1 App runs | Dependencies install, the app's own test passes, the app serves HTTP, and the Join button exists and is clickable. If C1 fails the browser phase is skipped and C2..C7 report "not evaluated". | **B1** syntax error in the app source |
| C2 Exposure sent | V1's identity sent a `$flag_exposure` for the trial's flag (read with `getExperimentFlag` / `get_experiment_flag`). No traffic at all -> `no Flagsmith traffic observed`. | **B2** flag read with a plain getter: no exposure |
| C3 Conversion on action | `join_clicked` arrives in the click phase and none during load. | **B3** event sent on page load |
| C4 Identity match | Every `join_clicked` identity equals the exposure identity (if there is no exposure, the identity V1 used for the flag request). | **B4** conversion identity prefixed `other-` |
| C5 Identity stable | V1 keeps its identity after reload; V2 (fresh context) gets a different one. | **B5** new random identity on every load |
| C6 Flag drives the UI | The rendered button text is a variant value and equals what the mock returned for that identity, for V1 *and* V2. | **B6** button keeps the hard-coded control text |
| C7 No server key in client (diagnostic) | No browser-loaded response body or the rendered DOM contains the grader's fake server key or any `ser.<token>` string. Recorded, never part of the verdict. | **B7** server key embedded in the page/bundle |

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
