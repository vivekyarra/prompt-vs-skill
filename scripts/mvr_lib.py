"""Mock vs real Flagsmith agreement check (exploratory): the parts that need no network.

The frozen grader (`grader/`) answers every *.flagsmith.com request from its local emulator. For this check the app
talks to the REAL Flagsmith instead: a pass-through mitmproxy addon (`ops/mvr_mitm_addon.py`) forwards each request
unchanged and reports the request and the real response to a `Recorder` here. The Recorder turns them into records
of exactly the shape `grader/mock.py` writes (phase, kind, identifier, events, returned_value), so the frozen
`grader/checks.py` evaluates C1-C7 on real traffic with no change. It also serves `/__grader/phase`, the endpoint
`grader/browser.py` calls between visitor phases.

Also here: the agreement table for docs/mock-vs-real.md (`agreement`).
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ADMIN_PREFIX = "/__grader/"


def _same_flag(name, flag: str) -> bool:
    return isinstance(name, str) and name.lower().replace(" ", "_") == flag.lower().replace(" ", "_")


def _json(text):
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return text


def _flag_value(flags, flag: str):
    """feature_state_value of `flag` in a flags list (real responses carry every flag of the environment)."""
    for f in flags if isinstance(flags, list) else []:
        feat = (f or {}).get("feature") or {}
        if _same_flag(feat.get("name"), flag):
            return f.get("feature_state_value")
    return None


def classify(flow: dict, flag: str) -> dict:
    """One record in the emulator's format from one proxied flow.

    flow: {t, method, host, path (with query), req_body (text), status, resp_body (text)}"""
    u = urlparse(flow["path"])
    path = u.path
    query = {k: v[0] for k, v in parse_qs(u.query).items()}
    body = _json(flow.get("req_body"))
    resp = _json(flow.get("resp_body"))
    rec = {
        "t": flow["t"],
        "method": flow["method"],
        "path": path,
        "host": flow.get("host", ""),
        "via_proxy": True,
        "status": flow.get("status"),
        "kind": "other",
        "identifier": None,
        "events": [],
        "returned_value": None,
    }
    m = flow["method"]
    if m == "OPTIONS":
        rec["kind"] = "preflight"
    elif path.endswith("/v1/events"):
        rec["kind"] = "events"
        evs = body.get("events") if isinstance(body, dict) else body
        for e in evs if isinstance(evs, list) else []:
            if isinstance(e, dict):
                rec["events"].append({k: e.get(k) for k in ("event", "feature_name", "identifier", "value", "timestamp")})
    elif path.endswith("/analytics/flags/"):
        rec["kind"] = "analytics"
    elif path.endswith("/identities/"):
        rec["kind"] = "flags"
        rec["identifier"] = body.get("identifier") if isinstance(body, dict) else query.get("identifier")
        if isinstance(resp, dict):
            rec["returned_value"] = _flag_value(resp.get("flags"), flag)
    elif path.endswith("/flags/"):
        rec["kind"] = "flags"
        rec["returned_value"] = _flag_value(resp, flag)
    elif path.endswith("/environment-document/"):
        rec["kind"] = "environment"
    return rec


class Recorder:
    """Stand-in for grader.mock.FlagsmithEmulator: same `.records`, `.phase_starts`, `.url`, `/__grader/phase`,
    but it answers nothing itself; the mitm addon POSTs every real flow to `/__grader/flow`."""

    def __init__(self, flag: str):
        self.flag = flag
        self.records: list[dict] = []
        self.phase_starts: dict[str, float] = {}
        self._timeline: list[tuple[float, str]] = [(0.0, "setup")]
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None
        self.port = 0

    def phase_at(self, t: float) -> str:
        name = "setup"
        for start, n in self._timeline:
            if start <= t:
                name = n
        return name

    def set_phase(self, name: str, t: float | None = None) -> None:
        t = time.time() if t is None else t
        with self._lock:
            self.phase_starts[name] = t
            self._timeline.append((t, name))

    def add_flow(self, flow: dict) -> dict:
        rec = classify(flow, self.flag)
        rec["phase"] = self.phase_at(rec["t"])  # phase when the request STARTED, as the emulator records it
        with self._lock:
            self.records.append(rec)
        return rec

    def start(self) -> None:
        recorder = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _send(self, obj) -> None:
                data = json.dumps(obj).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):  # noqa: N802
                u = urlparse(self.path)
                if u.path == ADMIN_PREFIX + "phase":
                    name = parse_qs(u.query).get("name", ["setup"])[0]
                    recorder.set_phase(name)
                    self._send({"phase": name})
                else:
                    self._send({})

            def do_POST(self):  # noqa: N802
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n).decode("utf-8", "replace") if n else "{}"
                if urlparse(self.path).path == ADMIN_PREFIX + "flow":
                    recorder.add_flow(json.loads(raw))
                self._send({})

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


# ---- agreement table ------------------------------------------------------------------------------------------
def agreement(selection: dict, real: dict[str, dict], mock: dict[str, dict]) -> dict:
    """real/mock: trial_id -> {"passed": bool, "failed_checks": [...]} (mock = offline emulator regrade).
    Returns counts overall and by group, plus the list of disagreements and of trials not compared."""
    rows, missing = [], []
    for group, items in (("failing", selection["failing"]), ("passing_sample", selection["passing_sample"])):
        for it in items:
            tid = it["trial_id"]
            r, m = real.get(tid), mock.get(tid)
            if not r or r.get("passed") is None or not m or m.get("passed") is None:
                missing.append({"trial_id": tid, "why": "no real verdict" if not r or r.get("passed") is None
                                else "no emulator verdict"})  # fmt: skip
                continue
            rows.append({**it, "group": group, "real": r, "mock": m, "agree": r["passed"] == m["passed"],
                         "checks_agree": sorted(r.get("failed_checks") or []) == sorted(m.get("failed_checks") or [])})  # fmt: skip

    def count(sel):
        n = len(sel)
        return {"n": n, "agree": sum(x["agree"] for x in sel), "checks_agree": sum(x["checks_agree"] for x in sel)}

    by = {"overall": count(rows)}
    for key in ("group", "stage", "variant", "stack"):
        for v in sorted({x[key] for x in rows}):
            by[f"{key}={v}"] = count([x for x in rows if x[key] == v])
    per_check = {}
    for c in ("C1", "C2", "C3", "C4", "C5", "C6", "C7"):
        per_check[c] = sum((c in (x["real"].get("failed_checks") or [])) == (c in (x["mock"].get("failed_checks") or []))
                           for x in rows)  # fmt: skip
    return {
        "by": by,
        "per_check": per_check,
        "disagreements": [x for x in rows if not x["agree"]],
        "check_differences": [x for x in rows if x["agree"] and not x["checks_agree"]],
        "not_compared": missing,
    }
