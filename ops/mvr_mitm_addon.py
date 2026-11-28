"""mitmproxy addon for the mock-vs-real check: pass every request through UNCHANGED to the real host, and report
each *.flagsmith.com request with its real response to the Recorder (scripts/mvr_lib.py).

    mitmdump -p <port> -s ops/mvr_mitm_addon.py --set mvr_recorder_port=<recorder port>

Contrast with grader/mitm_addon.py, which rewrites the same requests to the local emulator.
"""

import json
import urllib.request

from mitmproxy import ctx, http


def load(loader):
    loader.add_option("mvr_recorder_port", int, 0, "port of the Recorder on 127.0.0.1")


def _is_flagsmith(host: str) -> bool:
    return host == "flagsmith.com" or host.endswith(".flagsmith.com")


def response(flow: http.HTTPFlow):
    host = flow.request.pretty_host
    if not _is_flagsmith(host):
        return
    payload = {
        "t": flow.request.timestamp_start,
        "method": flow.request.method,
        "host": host,
        "path": flow.request.path,
        "req_body": flow.request.get_text(strict=False) or "",
        "status": flow.response.status_code if flow.response else None,
        "resp_body": (flow.response.get_text(strict=False) or "") if flow.response else "",
    }
    req = urllib.request.Request(
        f"http://127.0.0.1:{ctx.options.mvr_recorder_port}/__grader/flow",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=5).read()  # noqa: S310 (loopback)
    except Exception as e:  # noqa: BLE001
        ctx.log.warn(f"mvr: could not report flow: {type(e).__name__}")


def error(flow: http.HTTPFlow):
    """A request that never got a response (connection error) is still reported, with status None."""
    if flow.response is None and _is_flagsmith(flow.request.pretty_host):
        response(flow)
