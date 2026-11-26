"""python -m grader --app-dir <path> --stack <react|node|python> --flag <name> --event join_clicked
--variant-values "Join,Join free" --out result.json [--mode proxy|mock]

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
from grader import grader_version, stacks
from grader.mock import MockFlagsmith


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="grader", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--app-dir", required=True, type=pathlib.Path)
    ap.add_argument("--stack", required=True, choices=("react", "node", "python"))
    ap.add_argument("--flag", required=True)
    ap.add_argument("--event", default="join_clicked")
    ap.add_argument("--variant-values", default="Join,Join free", help="comma-separated; last one = the variation")
    ap.add_argument("--out", required=True, type=pathlib.Path)
    ap.add_argument(
        "--mode",
        choices=("proxy", "mock"),
        default="proxy",
        help="proxy: HTTPS MITM proxy answers the default flagsmith.com hosts (for agent-written apps).\n"
        "mock: app is pointed at the local mock via FLAGSMITH_API_URL etc. (fixture self-tests).",
    )
    ap.add_argument("--port", type=int, help="port the app listens on (default: react 5173, node 3000, python 5000)")
    ap.add_argument("--load-wait", type=float, default=3.0, help="seconds after network idle on load (spec: 3)")
    ap.add_argument("--click-wait", type=float, default=5.0, help="seconds after network idle on click (spec: 5)")
    ap.add_argument("--health-timeout", type=float, default=stacks.HEALTH_TIMEOUT_S)
    ap.add_argument("--keep-workdir", action="store_true")
    return ap


def grade(a: argparse.Namespace) -> dict:
    values = [v.strip() for v in a.variant_values.split(",") if v.strip()]
    if len(values) < 2:
        raise SystemExit("--variant-values needs at least two values")
    port = a.port or stacks.DEFAULT_PORTS[a.stack]
    t0 = time.time()
    durations: dict = {}
    c1: dict = {"error": None, "tests_ok": False, "tests_reason": ""}
    browser_out = None
    mock = MockFlagsmith(a.flag, values)
    mock.start()
    mitm = app = work = None
    try:
        if not a.app_dir.is_dir():
            raise stacks.StepError(f"app dir not found: {a.app_dir}")
        work = stacks.prepare_workdir(a.app_dir.resolve())
        t = time.time()
        try:
            info = stacks.install(a.stack, work)
            durations["install_s"] = round(time.time() - t, 1)
            t = time.time()
            c1["tests_ok"], c1["tests_reason"] = stacks.app_tests(a.stack, work, info)
            durations["tests_s"] = round(time.time() - t, 1)
            if stacks.port_open(port):
                raise stacks.StepError(f"port {port} is already in use; cannot start the app")
            proxy_url = None
            if a.mode == "proxy":
                mitm = stacks.MitmProxy(mock.port, work.parent / "mitm")
                proxy_url = mitm.url
                env = stacks.app_env(a.flag, mode="proxy", mock_url=None, proxy_url=proxy_url,
                                     ca_path=mitm.ca_path, port=port)  # fmt: skip
            else:
                env = stacks.app_env(a.flag, mode="mock", mock_url=mock.url, port=port)
            t = time.time()
            app = stacks.App(a.stack, work, info, env, port)
            app.wait_healthy(a.health_timeout)
            durations["startup_s"] = round(time.time() - t, 1)
            from grader import browser  # a failing existing test does not stop the visitors

            t = time.time()
            browser_out = browser.run_visitors(app.url, mock.url, proxy_url, a.load_wait, a.click_wait)
            durations["browser_s"] = round(time.time() - t, 1)
        except stacks.StepError as e:
            c1["error"] = str(e)
            browser_out = None
        results = chk.evaluate(
            records=mock.records, flag=a.flag, event_name=a.event, variant_values=values, mode=a.mode,
            c1=c1, browser=browser_out, server_key=stacks.FAKE_SERVER_KEY,
        )  # fmt: skip
    finally:
        if app:
            app.stop()
        if mitm:
            mitm.stop()
        mock.stop()
        if work and not a.keep_workdir:
            shutil.rmtree(work.parent, ignore_errors=True)
    recs = mock.records
    durations["total_s"] = round(time.time() - t0, 1)
    return {
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
    }


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
    for cid, c in result["checks"].items():
        print(f"{cid}: {'PASS' if c['passed'] else 'FAIL'}" + (f"  {c['reason']}" if c.get("reason") else ""))
    print("OVERALL:", "PASS" if result["passed"] else "FAIL")
    return code


if __name__ == "__main__":
    sys.exit(main())
