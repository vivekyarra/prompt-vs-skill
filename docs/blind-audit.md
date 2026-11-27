# Blind audit of passing diffs

**Purpose.** Every correction made after the pilot moved a failure to a pass, so passes needed an independent
check: could the grader be passing code that does not really record exposures and conversions correctly?

**Method.** 12 passing trials per arm were sampled at random (seed 20261127) from the 220 primary trials,
shuffled, and given random ids (A01-A24) with only the stack revealed. A reviewer who could not see which method
produced a diff (the key below was withheld until after the review) read each `diff.patch` against C2-C6 plus
events enabled, no server key in browser code, and a sound app, and judged REAL PASS / FALSE PASS / UNCERTAIN.
The reviewer read code only; no app was run. Untracked files (such as `.env.local`) are not in a diff.

**Result.** 24 of 24 REAL PASS, 0 FALSE PASS, 0 UNCERTAIN. The grader's passes held up. No fix was applied and
none was needed.

**Minor observations** (none changed a verdict; kept for transparency): one diff commits a client-side key file
(public, not a secret); one calls the experiment read outside a try/except; several rely on the SDK's 10 s timer
instead of an explicit flush on exit; several fall back to the client key on the server when no server key is set;
one does not HTML-escape the flag value in a server-rendered page.

## Reviewer report (verbatim)

# Blind audit: Flagsmith Join-button A/B diffs (A01..A24)

Method: read each diff.patch (code, not tests) against C2..C6 plus events enabled / delivery / key exposure / app not broken. No graders run, no network, audit key not read. Judgement is from code only; SDK behaviour (e.g. that getExperimentFlag/useExperiment records an exposure, trackEvent signature) is taken from how the diffs consistently use the SDK.

| id | stack | verdict | reason |
|---|---|---|---|
| A01 | python | REAL PASS | app.py: get_experiment_flag(.., identifier=g.vid) in index, track_event in POST /join with g.vid, enable_events=True, flush_events after each + atexit close; value drives button |
| A02 | python | REAL PASS | join_button_text(g.vid) uses get_experiment_flag; track_event+flush_events in /join; atexit close; server key from env |
| A03 | react | REAL PASS | App.jsx useExperiment(EXPERIMENT_FLAG), label=flag.value??'Join'; trackEvent only in handleJoin; provider options identity=getVisitorId(), enableEvents; pagehide/beforeunload flush; key via VITE_ env (client key only) |
| A04 | node | REAL PASS | getExperimentFlag(flag, req.vid) in GET /, trackEvent({identifier:req.vid}) + flushEvents in POST /join; enableEvents; server key env |
| A05 | node | REAL PASS | flagsmith.js getExperimentFlag(visitorId); trackEvent in /join; SIGTERM/SIGINT close(); relies on SDK timer in between (acceptable) |
| A06 | node | REAL PASS | same pattern; flag.enabled gate then value; close() on shutdown |
| A07 | node | REAL PASS | getExperimentFlag(FLAG_NAME, vid); trackEvent(..,{identifier:vid,value:1}) on /join; close on signal. No HTML escaping of flag value (value is operator-controlled; not a requirement) |
| A08 | node | REAL PASS | resolveJoinButtonText -> getExperimentFlag(req.vid); trackEvent('join_clicked') in /join; close on shutdown |
| A09 | python | REAL PASS | get_experiment_flag(identifier=g.vid) under lock; track_event in /join; atexit close; default_flag_handler. Minor: the flag call is not in try/except, so an SDK exception would 500 the page (robustness, not a criterion) |
| A10 | node | REAL PASS | experimentButtonText -> getExperimentFlag(req.vid); trackConversion in /join; close on shutdown. Notes: commits flagsmith.json (CLI binding with client-side env key, public key class, not a server secret); `value !== 'control'` guard is odd but harmless |
| A11 | python | REAL PASS | get_experiment_flag(g.vid) in index, track_event in /join, enable_events, atexit close (timer-based delivery, fine for long-lived server) |
| A12 | python | REAL PASS | get_experiment_flag(g.vid), track_event+flush_events in /join, enable_events, atexit close |
| A13 | react | REAL PASS | App.jsx useExperiment + flagsmith.trackEvent in click handler only; flagsmith.js identity=getVisitorId(), enableEvents; main.jsx provider + flush on beforeunload; envPrefix limited to FLAGSMITH_CLIENT_ (client key only) |
| A14 | node | REAL PASS | getExperimentFlag(visitorId), trackEvent+flushEvents in /join; server key from env; no shutdown close but explicit flush on conversion |
| A15 | node | REAL PASS | getExperimentFlag(req.vid), button limited to exactly 'Join free' else 'Join'; trackEvent in /join; close on shutdown |
| A16 | react | REAL PASS | useExperiment + trackEvent in handleJoin; options identity=getVisitorId(), enableEvents; envPrefix 'FLAGSMITH_CLIENT' exposes only client key; no unload flush (SDK timer; SPA) |
| A17 | python | REAL PASS | get_experiment_flag(g.vid) in index, track_event in /join, enable_events, atexit close; falls back to client key if no server key (works, degraded) |
| A18 | python | REAL PASS | get_experiment_flag(g.vid), track_event in /join, enable_events; no atexit close/flush (relies on SDK timer; minor tail-loss risk at shutdown only); value limited to Join/Join free |
| A19 | node | REAL PASS | getExperimentFlag(req.vid), trackEvent + awaited flushEvents in /join; close on shutdown; escapes HTML |
| A20 | python | REAL PASS | get_experiment_flag(g.vid) via lazy client, track_event in /join, enable_events, atexit close |
| A21 | react | REAL PASS | useExperiment(FLAG_NAME), flagsmith.trackEvent in handleJoin; same singleton in FlagsmithProvider with identity=getVisitorId(), enableEvents; pagehide flush; key injected via vite define (client key) |
| A22 | node | REAL PASS | getExperimentFlag(visitorId), trackJoinClicked in /join; flush on signal; key from env |
| A23 | node | REAL PASS | getExperimentFlag(req.vid), trackEvent in /join; flushEvents on signal (no close; timer otherwise) |
| A24 | python | REAL PASS | get_experiment_flag(g.vid) lazy thread-safe client, track_event in /join, enable_events, atexit close |

## Summary
- FALSE PASS: 0
- UNCERTAIN: 0
- REAL PASS: 24

I found no diff that fails C2..C6. Every diff reads the flag with the experiment method using the cookie/localStorage visitor id, sends join_clicked only from the click path (React onClick handler; Node/Flask POST /join, which the existing page script calls only on click), uses the same identity for both, reuses the existing persisted visitor id, and renders the flag value (control fallback `Join`) as button text. All enable events; no server-side key ships to browser code (React diffs use client-key env vars only).

Non-blocking observations (none changed a verdict):
- A10 commits flagsmith.json (CLI binding including a client-side environment key; public-class key, not a secret).
- A09 calls get_experiment_flag outside try/except (page 500s on an SDK exception).
- A18, A16, A23 have weaker flush-on-exit behaviour than the rest (rely on SDK timer / no atexit close in A18).
- Several server-side diffs (A04, A06, A09, A17, A18, A19, A22, A24) fall back to the client-side key when no server key is set; works but is not the intended key type.
- A07 does not HTML-escape the flag value in the Node page (others do); value is operator-controlled.
- No mapping of diffs to methods was seen or guessed.


## Key (revealed after the review)

| id | trial | arm |
|---|---|---|
| A01 | `trial-45914099371-1` | prompt |
| A02 | `trial-45947367007-51` | prompt |
| A03 | `trial-45947367007-58` | prompt |
| A04 | `trial-45947370678-71` | skill |
| A05 | `trial-45947367007-11` | skill |
| A06 | `trial-45947367007-41` | prompt |
| A07 | `trial-45947367007-27` | skill |
| A08 | `trial-45925699686-20` | prompt |
| A09 | `trial-45947370678-47` | prompt |
| A10 | `trial-45914099371-17` | prompt |
| A11 | `trial-45947370678-79` | prompt |
| A12 | `trial-45947370678-65` | skill |
| A13 | `trial-45947370678-49` | prompt |
| A14 | `trial-45947367007-74` | skill |
| A15 | `trial-45947370678-44` | prompt |
| A16 | `trial-45947370678-74` | skill |
| A17 | `trial-45947367007-10` | skill |
| A18 | `trial-45947367007-12` | skill |
| A19 | `trial-45914099371-21` | prompt |
| A20 | `trial-45947367007-63` | skill |
| A21 | `trial-45914099371-6` | skill |
| A22 | `trial-45925699686-8` | skill |
| A23 | `trial-45947367007-13` | skill |
| A24 | `trial-45947367007-52` | prompt |
