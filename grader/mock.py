"""Local Flagsmith emulator: flags/identities API + events API on one loopback origin.

Every request is recorded with the current *phase* (set through the admin endpoint
``/__grader/phase?name=<phase>``). The flag response is deterministic: the trial's flag is a
multivariate flag enrolled in a running experiment (``metadata.experiment.in_experiment = true`` and a
``variant`` key), which is what makes the SDK experiment methods emit ``$flag_exposure``. Response
shapes are derived from the SDK sources, see docs/flagsmith-sdk-notes.md.

Variant assignment is by first sight of an identity: the 1st identity gets the variation (the last
variant value, "Join free"), the 2nd the next-to-last (control "Join"), and so on, cyclically. It
therefore does not depend on random identity values, so verdicts are deterministic.

SDK local evaluation (post-freeze amendment, see EXPERIMENT.md): ``GET .../environment-document/`` with a
``ser.`` key in ``X-Environment-Key`` returns an environment document for the same flag (shape modelled on the
live document, see docs/grader.md). The SDK then buckets identities itself with the Flagsmith engine's hash, so
the emulator cannot assign "first identity -> variation" there; ``local_value`` reproduces the engine's hash and
tells C6 what the SDK computed. Apps that never call that endpoint see no change.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ADMIN_PREFIX = "/__grader/"

# Environment document constants (local evaluation). The real document carries the CLIENT key as `api_key`.
DOC_API_KEY = "GRADER_PLACEHOLDER_CLIENT_KEY_7f3a9c"
DOC_FEATURE_STATE_ID = 1882647  # `django_id`: the SDKs hash (django_id, "<api_key>_<identifier>") to bucket an identity
DOC_FEATURE_ID = 101
DOC_OPTION_ID_BASE = 37439
DOC_MV_ID_BASE = 389417


def hashed_percentage(object_ids: list) -> float:
    """The engine's get_hashed_percentage_for_object_ids (Python flag-engine 11.1.2, @flagsmith/nodejs 9.5.0)."""
    digest = hashlib.md5(",".join(str(i) for i in object_ids).encode("utf-8")).hexdigest()
    return ((int(digest, 16) % 9999) / 9998) * 100


class FlagsmithEmulator:
    def __init__(self, flag: str, variant_values: list[str]):
        self.flag = flag
        self.values = variant_values
        self.phase = "setup"
        self.phase_starts: dict[str, float] = {}  # phase name -> time.time() of its (last) start
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

    # ---- local evaluation (environment document) -------------------------------------------------------
    def _allocation(self) -> float:
        return 100 / len(self.values)

    def local_value(self, identity: str | None) -> str:
        """The value an SDK doing local evaluation computes for `identity` from the document served here."""
        pct = hashed_percentage([DOC_FEATURE_STATE_ID, f"{DOC_API_KEY}_{identity}"])
        start = 0.0
        for i, v in enumerate(self.values):
            start += self._allocation()
            if pct < start:
                return v
        return self.values[0]

    def environment_document(self) -> dict:
        return {
            "id": 1,
            "api_key": DOC_API_KEY,
            "project": {
                "id": 1,
                "name": "grader",
                "organisation": {
                    "id": 1, "name": "grader", "feature_analytics": False, "stop_serving_flags": False,
                    "persist_trait_data": True,
                },  # fmt: skip
                "hide_disabled_flags": False,
                "segments": [],
                "enable_realtime_updates": False,
                "server_key_only_feature_ids": [],
            },
            "feature_states": [
                {
                    "feature": {"id": DOC_FEATURE_ID, "name": self.flag, "type": "MULTIVARIATE"},
                    "enabled": True,
                    "django_id": DOC_FEATURE_STATE_ID,
                    "feature_segment": None,
                    "featurestate_uuid": "00000000-0000-4000-8000-000000000001",
                    "feature_state_value": self.values[0],
                    "multivariate_feature_state_values": [
                        {
                            "multivariate_feature_option": {
                                "value": v, "id": DOC_OPTION_ID_BASE + i, "key": f"variant_{i}",
                            },  # fmt: skip
                            "percentage_allocation": self._allocation(),
                            "id": DOC_MV_ID_BASE + i,
                            "mv_fs_value_uuid": f"00000000-0000-4000-8000-0000000001{i:02d}",
                        }
                        for i, v in enumerate(self.values)
                    ],
                    "metadata": {"experiment": {"id": 7, "in_experiment": True, "name": "grader-experiment"}},
                }
            ],
            "identity_overrides": [],
            "name": "grader",
            "allow_client_traits": True,
            "updated_at": "2026-01-01T00:00:00Z",
            "hide_sensitive_data": False,
            "hide_disabled_flags": None,
            "use_identity_composite_key_for_hashing": True,
            "use_identity_overrides_in_local_eval": True,
        }

    def handle(self, method: str, raw_path: str, body, headers: dict) -> tuple[int, object]:
        u = urlparse(raw_path)
        path = u.path
        query = {k: v[0] for k, v in parse_qs(u.query).items()}
        if path.startswith(ADMIN_PREFIX):
            if path == ADMIN_PREFIX + "phase":
                self.phase = query.get("name", "setup")
                self.phase_starts[self.phase] = time.time()
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
        elif path.endswith("/environment-document/"):
            rec["kind"] = "environment"
            if lh.get("x-environment-key", "").startswith("ser."):
                resp = (200, self.environment_document())
            else:  # the real endpoint needs a server-side key
                resp = (401, {"detail": "grader emulator: environment document needs a server-side (ser.) key"})
        else:
            resp = (404, {"detail": "grader emulator: unknown path " + path})
        with self._lock:
            self.records.append(rec)
        return resp
