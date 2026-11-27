"""python -m grader --app-dir <path> --stack <react|node|python> --flag <name> --event join_clicked
--variant-values "Join,Join free" --out result.json [--mode proxy|emulator]

Exit code: 0 = all pass-checks passed, 1 = integration failed, 2 = grader/infrastructure error.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sys
import time
import traceback

from grader import checks as chk
from grader import grader_version, report, stacks
from grader.mock import FlagsmithEmulator

# All three Flagsmith SDKs buffer events and flush on a 10 s timer by default (docs/flagsmith-sdk-notes.md), so every
# browser phase waits 10 s + 3 s margin: load, reload and V2 use --load-wait, click uses --click-wait.
DEFAULT_LOAD_WAIT_S = 13.0
DEFAULT_CLICK_WAIT_S = 13.0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="grader", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--app-dir", required=True, type=pathlib.Path)
    ap.add_argument("--stack", required=True, choices=("react", "node", "python", "custom"),
                    help="custom: no install step; needs --start-cmd, health-checks --url (default http://127.0.0.1:<port>/)")  # fmt: skip
    ap.add_argument("--flag", required=True)
    ap.add_argument("--event", default="join_clicked")
    ap.add_argument("--variant-values", default="Join,Join free", help="comma-separated; last one = the variation")
    ap.add_argument("--out", required=True, type=pathlib.Path)
    ap.add_argument(
        "--mode",
        choices=("proxy", "emulator"),
        default="proxy",
        help="proxy: HTTPS MITM proxy answers the default flagsmith.com hosts (for agent-written apps).\n"
        "emulator: app is pointed at the local emulator via FLAGSMITH_API_URL etc. (fixture self-tests).",
    )
    ap.add_argument("--port", type=int, help="port the app listens on (default: react 5173, node 3000, python 5000)")
    ap.add_argument("--load-wait", type=float, default=DEFAULT_LOAD_WAIT_S,
                    help="seconds after network idle on load, reload and V2 (default 13: SDK flush timer 10 s + 3 s; spec said 3)")  # fmt: skip
    ap.add_argument("--click-wait", type=float, default=DEFAULT_CLICK_WAIT_S,
                    help="seconds after network idle on click (default 13: SDK flush timer 10 s + 3 s; spec said 5)")  # fmt: skip
    ap.add_argument("--health-timeout", type=float, default=stacks.HEALTH_TIMEOUT_S)
    ap.add_argument("--reclaim-port", action="store_true",
                    help="kill any process already listening on the app port (e.g. a server the agent left running)")  # fmt: skip
    ap.add_argument("--keep-workdir", action="store_true")
    ap.add_argument("--start-cmd", help="shell command that starts the app in the app dir (default: per stack)")
    ap.add_argument("--url", help="page URL to load and health-check (default: http://127.0.0.1:<port>/)")
    ap.add_argument("--click-selector", help="CSS selector of the element to click (default: #join-btn, else a button named Join)")  # fmt: skip
    ap.add_argument("--report", action="store_true", help="print a readable C1-C7 table with fix hints (default when stdout is a TTY)")  # fmt: skip
    return ap


def _url_port(url: str | None) -> int:
    if url:
        from urllib.parse import urlparse

        p = urlparse(url)
        return p.port or (443 if p.scheme == "https" else 80)
    return stacks.DEFAULT_PORTS["custom"]


MAX_EXTRA_VISITORS = 8


def local_evaluation_extra_visitors(emu, browser, url, proxy_url, a, browser_out) -> list[dict]:
    """SDK local evaluation only (the app downloaded the environment document). The SDK buckets identities by hash,
    so V1 and V2 can land on the same variant, and then a hard-coded button text would pass C6. Remote evaluation
    cannot have this: the emulator gives the first two identities different variants. Fresh visitors (phases v3, v4,
    ...) are therefore added until one identity's expected value differs from V1's (at most MAX_EXTRA_VISITORS).
    C6 compares every visitor's text with the value the SDK computed for that identity. Nothing runs when V1 and V2
    already got different values."""
    v1 = chk.phase_identity(emu.records, "load", a.flag)
    v2 = chk.phase_identity(emu.records, "v2", a.flag)
    if not v1 or not v2 or emu.local_value(v1) != emu.local_value(v2):
        return []
    extras: list[dict] = []
    for i in range(3, 3 + MAX_EXTRA_VISITORS):
        phase = f"v{i}"
        text = browser.run_extra_visitor(url, emu.url, proxy_url, a.load_wait, phase, selector=a.click_selector)
        extras.append({"phase": phase, "text": text})
        ident = chk.phase_identity(emu.records, phase, a.flag)
        if ident and emu.local_value(ident) != emu.local_value(v1):
            break
    return extras


def grade(a: argparse.Namespace) -> dict:
    values = [v.strip() for v in a.variant_values.split(",") if v.strip()]
    if len(values) < 2:
        raise SystemExit("--variant-values needs at least two values")
    if a.stack == "custom":
        if not a.start_cmd:
            raise ValueError("--stack custom needs --start-cmd")
        port = a.port or _url_port(a.url)
    else:
        port = a.port or (_url_port(a.url) if a.url else stacks.DEFAULT_PORTS[a.stack])
    t0 = time.time()
    durations: dict = {}
    c1: dict = {"error": None, "tests_ok": False, "tests_reason": ""}
    browser_out = None
    emu = FlagsmithEmulator(a.flag, values)
    emu.start()
    mitm = app = work = None
    try:
        if not a.app_dir.is_dir():
            raise stacks.StepError(f"app dir not found: {a.app_dir}")
        work = stacks.prepare_workdir(a.app_dir.resolve(), a.stack)
        t = time.time()
        try:
            info = stacks.install(a.stack, work)
            durations["install_s"] = round(time.time() - t, 1)
            t = time.time()
            c1["tests_ok"], c1["tests_reason"] = stacks.app_tests(a.stack, work, info, flag=a.flag)
            durations["tests_s"] = round(time.time() - t, 1)
            if a.reclaim_port and stacks.port_open(port):
                stacks.reclaim_port(port)
            if stacks.port_open(port):
                raise stacks.StepError(f"port {port} is already in use; cannot start the app")
            proxy_url = None
            if a.mode == "proxy":
                mitm = stacks.MitmProxy(emu.port, work.parent / "mitm")
                proxy_url = mitm.url
                env = stacks.app_env(a.flag, mode="proxy", emulator_url=None, proxy_url=proxy_url,
                                     ca_path=mitm.ca_path, port=port)  # fmt: skip
            else:
                env = stacks.app_env(a.flag, mode="emulator", emulator_url=emu.url, port=port)
            t = time.time()
            app = stacks.App(a.stack, work, info, env, port, start_cmd=a.start_cmd, url=a.url)
            app.wait_healthy(a.health_timeout)
            durations["startup_s"] = round(time.time() - t, 1)
            from grader import browser  # a failing existing test does not stop the visitors

            t = time.time()
            browser_out = browser.run_visitors(app.url, emu.url, proxy_url, a.load_wait, a.click_wait,
                                               selector=a.click_selector)  # fmt: skip
            if any(r["kind"] == "environment" for r in emu.records):
                browser_out["extra_visitors"] = local_evaluation_extra_visitors(
                    emu, browser, app.url, proxy_url, a, browser_out)
            durations["browser_s"] = round(time.time() - t, 1)
        except stacks.StepError as e:
            c1["error"] = str(e)
            browser_out = None
        results = chk.evaluate(
            records=emu.records, flag=a.flag, event_name=a.event, variant_values=values, mode=a.mode,
            c1=c1, browser=browser_out, server_key=stacks.PLACEHOLDER_SERVER_KEY, local_value=emu.local_value,
            button_label=f"click target {a.click_selector}" if a.click_selector else "Join",
        )  # fmt: skip
    finally:
        if app:
            app.stop()
        if mitm:
            mitm.stop()
        emu.stop()
        if work and not a.keep_workdir:
            shutil.rmtree(work.parent, ignore_errors=True)
    recs = emu.records
    durations["total_s"] = round(time.time() - t0, 1)
    result = {
        "grader_version": grader_version(),
        "passed": chk.passed(results),
        "checks": results,
        "pass_rule": "C1 AND C2 AND C3 AND C4 AND C5 AND C6 (C7 is diagnostic)",
        "mode": a.mode,
        "stack": a.stack,
        "flag": a.flag,
        "identities": {
            "v1_load": chk.phase_identity(recs, "load", a.flag),
            "v1_reload": chk.phase_identity(recs, "reload", a.flag),
            "v2": chk.phase_identity(recs, "v2", a.flag),
        },
        "button_text": {
            "v1": (browser_out or {}).get("v1_text"),
            "v2": (browser_out or {}).get("v2_text"),
        },
        "request_counts": chk.request_counts(recs),
        "events_observed": [
            {"phase": r["phase"], "host": r["host"], **e} for r in recs if r["kind"] == "events" for e in r["events"]
        ],
        "durations": durations,
        "hints": report.hints_for(results),
    }
    if any(r["kind"] == "environment" for r in recs):  # local evaluation: key present only then
        result["local_evaluation"] = {"environment_document_requests": sum(r["kind"] == "environment" for r in recs)}
    return result


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    try:
        result = grade(a)
        code = 0 if result["passed"] else 1
    except Exception as e:  # infrastructure failure: still write a result so callers do not hang
        traceback.print_exc()
        result = {
            "grader_version": grader_version(),
            "passed": False,
            "error": f"grader error: {e}",
            "checks": {c: {"passed": False, "reason": f"grader error: {e}"} for c in chk.ALL_CHECKS},
        }
        code = 2
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=2))
    if a.report or sys.stdout.isatty():
        print(report.format_report(result))
    else:
        for cid, c in result["checks"].items():
            print(f"{cid}: {'PASS' if c['passed'] else 'FAIL'}" + (f"  {c['reason']}" if c.get("reason") else ""))
        print("OVERALL:", "PASS" if result["passed"] else "FAIL")
    return code


if __name__ == "__main__":
    sys.exit(main())
