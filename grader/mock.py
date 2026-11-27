"""Local Flagsmith emulator: flags/identities API + events API on one loopback origin.

Every request is recorded with the current *phase* (set through the admin endpoint
``/__grader/phase?name=<phase>``). The flag response is deterministic: the trial's flag is a
multivariate flag enrolled in a running experiment (``metadata.experiment.in_experiment = true`` and a
``variant`` key), which is what makes the SDK experiment methods emit ``$flag_exposure``. Response
shapes are derived from the SDK sources, see docs/flagsmith-sdk-notes.md.

Variant assignment is by first sight of an identity: the 1st identity gets the variation (the last
variant value, "Join free"), the 2nd the next-to-last (control "Join"), and so on, cyclically. It
therefore does not depend on random identity values, so verdicts are deterministic.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ADMIN_PREFIX = "/__grader/"


class FlagsmithEmulator:
    def __init__(self, flag: str, variant_values: list[str]):
        self.flag = flag
        self.values = variant_values
        self.phase = "setup"
        self.records: list[dict] = []
        self.assignments: dict[str, int] = {}
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None
        self.port = 0

    # ---- lifecycle -------------------------------------------------------
    def start(self) -> None:
        emu = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _send(self, code: int, obj) -> None:
                data = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Headers", "*")
                self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
                self.send_header("Access-Control-Allow-Private-Network", "true")
                self.end_headers()
                self.wfile.write(data)

            def _handle(self) -> None:
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n).decode("utf-8", "replace") if n else ""
                try:
                    body = json.loads(raw) if raw else None
                except ValueError:
                    body = raw
                code, obj = emu.handle(self.command, self.path, body, dict(self.headers.items()))
                self._send(code, obj)

            do_GET = do_POST = do_OPTIONS = do_PUT = _handle

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

    # ---- behaviour ---------------------------------------------------------
    def value_for(self, identity: str | None) -> tuple[str, int]:
        key = identity or ""
        with self._lock:
            if key not in self.assignments:
                self.assignments[key] = len(self.assignments)
            n = self.assignments[key]
        idx = (len(self.values) - 1 - n) % len(self.values)
        return self.values[idx], idx

    def flag_payload(self, identity: str | None) -> dict:
        value, idx = self.value_for(identity)
        return {
            "id": 1,
            "feature": {"id": 101, "name": self.flag, "type": "MULTIVARIATE"},
            "enabled": True,
            "feature_state_value": value,
            "variant": f"variant_{idx}",
            "reason": "SPLIT; weight=50",
            "metadata": {"id": 101, "experiment": {"id": 7, "name": "grader-experiment", "in_experiment": True}},
        }

    def handle(self, method: str, raw_path: str, body, headers: dict) -> tuple[int, object]:
        u = urlparse(raw_path)
        path = u.path
        query = {k: v[0] for k, v in parse_qs(u.query).items()}
        if path.startswith(ADMIN_PREFIX):
            if path == ADMIN_PREFIX + "phase":
                self.phase = query.get("name", "setup")
            return 200, {"phase": self.phase}
        lh = {k.lower(): v for k, v in headers.items()}
        rec = {
            "t": time.time(),
            "phase": self.phase,
            "method": method,
            "path": path,
            "host": lh.get("x-grader-orig-host") or lh.get("host", ""),
            "via_proxy": "x-grader-orig-host" in lh,
            "kind": "other",
            "identifier": None,
            "events": [],
            "returned_value": None,
        }
        resp: tuple[int, object]
        if method == "OPTIONS":
            rec["kind"] = "preflight"
            resp = (204, {})
        elif path.endswith("/v1/events"):
            rec["kind"] = "events"
            evs = body.get("events") if isinstance(body, dict) else body
            for e in evs if isinstance(evs, list) else []:
                if isinstance(e, dict):
                    rec["events"].append(
                        {k: e.get(k) for k in ("event", "feature_name", "identifier", "value", "timestamp")}
                    )
            resp = (200, {})
        elif path.endswith("/analytics/flags/"):
            rec["kind"] = "analytics"
            resp = (200, {})
        elif path.endswith("/identities/"):
            rec["kind"] = "flags"
            ident = body.get("identifier") if isinstance(body, dict) else query.get("identifier")
            rec["identifier"] = ident
            payload = self.flag_payload(ident)
            rec["returned_value"] = payload["feature_state_value"]
            resp = (200, {"identifier": ident, "traits": [], "flags": [payload]})
        elif path.endswith("/flags/"):
            rec["kind"] = "flags"
            payload = self.flag_payload(None)
            rec["returned_value"] = payload["feature_state_value"]
            resp = (200, [payload])
        else:
            resp = (404, {"detail": "grader emulator: unknown path " + path})
        with self._lock:
            self.records.append(rec)
        return resp
