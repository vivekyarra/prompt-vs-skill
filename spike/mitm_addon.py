"""mitmproxy addon for the interception spike (Design B: capture at an HTTPS MITM proxy).

Pretends to be the real Flagsmith hosts (edge.api.flagsmith.com, events.api.flagsmith.com) WITHOUT
contacting them (no credentials exist in this environment): every request to a *.flagsmith.com host
is logged as JSONL (same record shape as mock_flagsmith.py) and answered with the mock's responses.
With real credentials one would simply delete the `request` short-circuit and let it forward.

Run:  mitmdump -p 8080 -s spike/mitm_addon.py --set spike_log=spike/capture_mitm.jsonl
"""
import json
import os
import sys
import time

from mitmproxy import ctx, http

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mock_flagsmith as m  # noqa: E402


def load(loader):
    loader.add_option("spike_log", str, "spike/capture_mitm.jsonl", "capture file")


def request(flow: http.HTTPFlow):
    host = flow.request.pretty_host
    if not host.endswith("flagsmith.com"):
        return
    body = flow.request.get_text(strict=False) or None
    try:
        body = json.loads(body) if body else None
    except Exception:
        pass
    rec = {
        "ts": time.time(), "via": "mitmproxy", "scheme": flow.request.scheme, "host": host,
        "method": flow.request.method, "path": flow.request.path.split("?")[0],
        "query": dict(flow.request.query.items(multi=False)) if flow.request.query else {},
        "headers": {k: v for k, v in flow.request.headers.items()
                    if k.lower() in ("x-environment-key", "content-type", "user-agent", "flagsmith-sdk-user-agent")},
        "body": body,
    }
    with open(ctx.options.spike_log, "a") as f:
        f.write(json.dumps(rec) + "\n")
    path = rec["path"]
    if path.endswith("/v1/events") or path.endswith("/analytics/flags/"):
        out = {}
    elif path.endswith("/identities/"):
        ident = body.get("identifier") if isinstance(body, dict) else rec["query"].get("identifier")
        out = {"identifier": ident, "traits": [], "flags": [m.flag_payload()]}
    elif path.endswith("/flags/"):
        out = [m.flag_payload()]
    else:
        flow.response = http.Response.make(404, b"{}", {"Content-Type": "application/json"})
        return
    flow.response = http.Response.make(200, json.dumps(out), {"Content-Type": "application/json",
                                                              "Access-Control-Allow-Origin": "*"})
