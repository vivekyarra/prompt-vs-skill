#!/usr/bin/env python3
"""Mock Flagsmith server for the Phase 0 spike (stdlib only).

Serves, on ONE origin (default http://127.0.0.1:8765):
  API URL    = http://127.0.0.1:8765/api/v1/     (flags / identities / analytics)
  EVENTS URL = http://127.0.0.1:8765/            (SDK appends v1/events)
              (or http://127.0.0.1:8765/api/ -> /api/v1/events, the self-hosted form)

Every request is appended as one JSON line to the capture file:
  {"ts","method","path","query","headers":{...},"body":<parsed JSON or raw str or null>}

Response shapes are derived from the SDK sources (see docs/verified-facts.md):
the identities response carries one multivariate flag `spike_flag` whose
`metadata.experiment.in_experiment` is true and `variant` is the keyed variation,
which is what makes get_experiment_flag / getExperimentFlag emit an exposure.

Usage: mock_flagsmith.py [--port 8765] [--log spike/capture.jsonl] [--no-experiment]
"""
import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

LOCK = threading.Lock()
ARGS = argparse.Namespace(port=8765, log="spike/capture.jsonl", no_experiment=False)  # overwritten by main()


def flag_payload():
    return {
        "id": 1,
        "feature": {"id": 101, "name": "spike_flag", "type": "MULTIVARIATE"},
        "enabled": True,
        "feature_state_value": "treatment",
        "variant": "treatment_key",
        "reason": "SPLIT; weight=50",
        "metadata": {
            "id": 101,
            **({} if ARGS.no_experiment else {
                "experiment": {"id": 7, "name": "spike-experiment", "in_experiment": True}
            }),
        },
    }


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # silence default stderr logging
        pass

    def _read(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode("utf-8", "replace") if n else ""
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return raw

    def _send(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        # permissive CORS so a browser page (other origin) can call the mock
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()
        self.wfile.write(data)

    def _record(self, body):
        u = urlparse(self.path)
        rec = {
            "ts": time.time(),
            "method": self.command,
            "path": u.path,
            "query": parse_qs(u.query),
            "headers": {k: v for k, v in self.headers.items()
                        if k.lower() in ("x-environment-key", "content-type",
                                         "user-agent", "flagsmith-sdk-user-agent",
                                         "host", "origin")},
            "body": body,
        }
        with LOCK:
            with open(ARGS.log, "a") as f:
                f.write(json.dumps(rec) + "\n")

    def _handle(self):
        body = self._read()
        self._record(body)
        path = urlparse(self.path).path
        if self.command == "OPTIONS":
            return self._send(204, {})
        if path.endswith("/v1/events"):
            return self._send(200, {})  # status < 400 == delivered for all SDKs
        if path.endswith("/analytics/flags/"):
            return self._send(200, {})
        if path.endswith("/identities/"):
            ident = None
            if isinstance(body, dict):
                ident = body.get("identifier")
            else:
                ident = (parse_qs(urlparse(self.path).query).get("identifier") or [None])[0]
            return self._send(200, {"identifier": ident, "traits": [], "flags": [flag_payload()]})
        if path.endswith("/flags/"):
            return self._send(200, [flag_payload()])
        return self._send(404, {"detail": "mock: unknown path " + path})

    do_GET = do_POST = do_OPTIONS = _handle


def main():
    global ARGS
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--log", default="spike/capture.jsonl")
    p.add_argument("--no-experiment", action="store_true",
                   help="omit metadata.experiment (identity not enrolled)")
    ARGS = p.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", ARGS.port), H)
    print(f"mock flagsmith on http://127.0.0.1:{ARGS.port} -> {ARGS.log}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
