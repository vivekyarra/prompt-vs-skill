"""Pure evaluation of checks C1..C7 from captured requests (no I/O; unit-testable).

Pass decision (pre-registered, spec section 10): C1 AND C2 AND C3 AND C4 AND C5 AND C6.
C7 is diagnostic only.
"""

from __future__ import annotations

import re

EXPOSURE = "$flag_exposure"
PASS_CHECKS = ("C1", "C2", "C3", "C4", "C5", "C6")
ALL_CHECKS = PASS_CHECKS + ("C7",)
SERVER_KEY_RE = re.compile(r"\bser\.[A-Za-z0-9_\-]{6,}")


def _res(passed: bool, reason: str | None = None, detail: str | None = None) -> dict:
    return {"passed": passed, "reason": None if passed else reason, "detail": detail if passed else None}


def _same_flag(name, flag: str) -> bool:
    return isinstance(name, str) and name.lower().replace(" ", "_") == flag.lower().replace(" ", "_")


def events(records, phases, name=None):
    for r in records:
        if r["kind"] == "events" and r["phase"] in phases:
            for e in r["events"]:
                if name is None or e.get("event") == name:
                    yield e


def _started_in_phase(e, phase: str, phase_starts) -> bool:
    """SDK local evaluation only: an event is buffered and sent by the SDK's 10 s timer, so it can ARRIVE in a
    later phase than the one it was created in (e.g. the exposure of the grader's own health-check request, created
    before any visitor). Its `timestamp` (ms, set when the SDK tracked it) says when it was created."""
    start = (phase_starts or {}).get(phase)
    ts = e.get("timestamp")
    return start is None or not isinstance(ts, (int, float)) or ts / 1000.0 >= start


def phase_identity(records, phase: str, flag: str, phase_starts=None):
    """Identity the app used in `phase`: first flags request, else first exposure, else any event.
    `phase_starts` (phase -> start time) is passed only when the app evaluated flags locally: events created before
    the phase started are then not attributed to it. With remote evaluation the flags request decides, as before."""
    for r in records:
        if r["phase"] == phase and r["kind"] == "flags" and r["identifier"]:
            return r["identifier"]
    for e in events(records, (phase,), EXPOSURE):
        if e.get("identifier") and _started_in_phase(e, phase, phase_starts):
            return e["identifier"]
    for e in events(records, (phase,)):
        if e.get("identifier") and _started_in_phase(e, phase, phase_starts):
            return e["identifier"]
    return None


def expected_value(records, phase: str, identity, local_value=None):
    for r in records:
        if r["phase"] == phase and r["kind"] == "flags" and r["identifier"] == identity:
            return r["returned_value"]
    # SDK local evaluation: the app downloaded the environment document and the SDK computed the value itself, so
    # there is no flags request to read it from. Only then, the value the SDK computes from the served document.
    if local_value is not None and identity and any(r["kind"] == "environment" for r in records):
        return local_value(identity)
    return None


def request_counts(records) -> dict:
    out: dict = {}
    for r in records:
        c = out.setdefault(r["phase"], {"flags": 0, "events": 0, "other": 0, "total": 0})
        c["total"] += 1
        c[r["kind"] if r["kind"] in ("flags", "events") else "other"] += 1
    return out


def no_traffic_reason(mode: str) -> str:
    if mode == "proxy":
        return (
            "no Flagsmith traffic observed: no request reached *.flagsmith.com through the grader's HTTPS proxy "
            "(the app never called Flagsmith, or its HTTP client ignores HTTPS_PROXY / the injected CA bundle)"
        )
    return (
        "no Flagsmith traffic observed: no request reached the grader's Flagsmith emulator "
        "(the app never called Flagsmith, or it does not read FLAGSMITH_API_URL / FLAGSMITH_EVENTS_URL / "
        "VITE_FLAGSMITH_API / VITE_FLAGSMITH_EVENTS_API; use --mode proxy for apps using the default hosts)"
    )


def evaluate(*, records, flag, event_name, variant_values, mode, c1, browser, server_key, button_label="Join",
             local_value=None, phase_starts=None) -> dict:  # fmt: skip
    """c1: {"healthy": bool, "tests_ok": bool, "tests_reason": str, "error": str|None}.
    browser: output of browser.run_visitors (or None when the app never ran)."""
    checks: dict = {}
    values = list(variant_values)

    # ---- C1
    if c1.get("error"):
        checks["C1"] = _res(False, c1["error"])
    elif not c1.get("tests_ok"):
        checks["C1"] = _res(False, c1["tests_reason"])
    elif not browser or not browser.get("button_found"):
        checks["C1"] = _res(False, f"{button_label} button not found on the page")
    elif not browser.get("click_ok"):
        checks["C1"] = _res(False, f"{button_label} button not clickable: {browser.get('click_error')}")
    else:
        note = c1.get("tests_reason") or ""
        what = note if "only with credential variables set" in note or note.startswith("no test step") else "existing test passed"
        checks["C1"] = _res(True, detail=f"app healthy, {what}, {button_label} button clickable")

    if not browser:
        for cid in ALL_CHECKS[1:]:
            checks[cid] = _res(False, "not evaluated: the app did not run (C1 failed)")
        return checks

    # ---- identities
    starts = phase_starts if any(r["kind"] == "environment" for r in records) else None  # local evaluation only
    v1 = phase_identity(records, "load", flag, starts)
    v1_reload = phase_identity(records, "reload", flag, starts)
    v2 = phase_identity(records, "v2", flag, starts)
    traffic = [r for r in records if r["kind"] in ("flags", "events")]

    # ---- C2
    v1_phases = ("load", "click", "reload")
    exposures = [e for e in events(records, v1_phases, EXPOSURE)]
    mine = [e for e in exposures if _same_flag(e.get("feature_name"), flag) and e.get("identifier") == v1]
    if not traffic:
        checks["C2"] = _res(False, no_traffic_reason(mode))
    elif mine:
        checks["C2"] = _res(True, detail=f"{len(mine)} exposure event(s) for '{flag}' with V1 identity")
    elif not exposures:
        checks["C2"] = _res(
            False,
            f"Flagsmith traffic seen but no {EXPOSURE} event for '{flag}' "
            "(the flag must be read with the SDK experiment method, e.g. getExperimentFlag / get_experiment_flag)",
        )
    elif not any(_same_flag(e.get("feature_name"), flag) for e in exposures):
        names = sorted({str(e.get("feature_name")) for e in exposures})
        checks["C2"] = _res(False, f"exposure sent for other flag(s) {names}, not '{flag}'")
    else:
        checks["C2"] = _res(False, f"exposure for '{flag}' was not sent with V1's identity ({v1!r})")

    # ---- C3
    load_ev = list(events(records, ("load",), event_name))
    click_ev = list(events(records, ("click",), event_name))
    if load_ev:
        checks["C3"] = _res(False, f"{event_name} was sent during page load, before any click ({len(load_ev)} event(s))")
    elif not click_ev:
        checks["C3"] = _res(False, f"no {event_name} event was sent after the {button_label} click")
    else:
        checks["C3"] = _res(True, detail=f"{len(click_ev)} {event_name} event(s) in click phase, none on load")

    # ---- C4
    exposure_ids = {e.get("identifier") for e in exposures if _same_flag(e.get("feature_name"), flag)}
    reference = exposure_ids or ({v1} if v1 else set())
    conv_ids = {e.get("identifier") for e in events(records, ("load", "click"), event_name)}
    if not conv_ids:
        checks["C4"] = _res(False, f"not evaluable: no {event_name} event observed to compare identities")
    elif not reference:
        checks["C4"] = _res(False, "not evaluable: no exposure or flag-request identity observed")
    elif conv_ids <= reference:
        checks["C4"] = _res(True, detail="exposure and conversion use the same identity")
    else:
        checks["C4"] = _res(
            False,
            f"{event_name} identity {sorted(map(str, conv_ids - reference))} differs from exposure identity "
            f"{sorted(map(str, reference))}",
        )

    # ---- C5
    if not v1:
        checks["C5"] = _res(False, "no identity observed for V1 (no flag request or event carried an identifier)")
    elif not v1_reload:
        checks["C5"] = _res(False, "no identity observed after V1 reload")
    elif not v2:
        checks["C5"] = _res(False, "no identity observed for V2")
    elif v1 != v1_reload:
        checks["C5"] = _res(False, f"V1 identity changed after reload ({v1!r} -> {v1_reload!r}); it must be persisted")
    elif v2 == v1:
        checks["C5"] = _res(False, "V2 (fresh browser context) got the same identity as V1; it must differ")
    else:
        checks["C5"] = _res(True, detail="identity stable across reload; V2 differs")

    # ---- C6
    problems = []
    visitors = [
        ("V1", browser.get("v1_text"), "load", v1),
        ("V2", browser.get("v2_text"), "v2", v2),
    ]
    for i, extra in enumerate(browser.get("extra_visitors") or [], start=3):  # SDK local evaluation only
        visitors.append((f"V{i}", extra.get("text"), extra["phase"], phase_identity(records, extra["phase"], flag, starts)))
    for label, text, phase, ident in visitors:
        exp = expected_value(records, phase, ident, local_value) if ident else None
        if text not in values:
            problems.append(f"{label} button text {text!r} is not one of the variant values {values}")
        elif exp is None:
            problems.append(f"{label}: no Flagsmith flag response observed for identity {ident!r} to compare with")
        elif text != exp:
            problems.append(f"{label} button shows {text!r} but Flagsmith returned {exp!r} for that identity")
    if problems:
        checks["C6"] = _res(False, "; ".join(problems) + " (the UI must render the flag value)")
    else:
        checks["C6"] = _res(True, detail="button text equals the value Flagsmith returned (V1 and V2)")

    # ---- C7 (diagnostic)
    hits = []
    blobs = dict(browser.get("assets") or {})
    blobs["<rendered DOM>"] = browser.get("dom") or ""
    for url, body in blobs.items():
        if server_key in body or SERVER_KEY_RE.search(body):
            hits.append(url)
    if hits:
        checks["C7"] = _res(False, f"server-side key found in browser-loaded content: {sorted(hits)}")
    else:
        checks["C7"] = _res(True, detail=f"no server key in {len(blobs)} browser-loaded assets")
    return checks


def passed(checks: dict) -> bool:
    return all(checks[c]["passed"] for c in PASS_CHECKS)
