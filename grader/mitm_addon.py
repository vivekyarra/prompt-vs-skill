"""mitmproxy addon: answer every request to a *.flagsmith.com host from the grader's emulator.

No request ever reaches the real Flagsmith (the grader has no credentials, and trials must not
send traffic to the real service). The request is rewritten to the emulator's loopback origin; the
original host is preserved in ``X-Grader-Orig-Host`` so it is recorded.

    mitmdump -p <port> -s grader/mitm_addon.py --set grader_emulator_port=<emulator port>
"""

from mitmproxy import ctx, http


def load(loader):
    loader.add_option("grader_emulator_port", int, 0, "port of the grader emulator server on 127.0.0.1")


def request(flow: http.HTTPFlow):
    host = flow.request.pretty_host
    if not (host == "flagsmith.com" or host.endswith(".flagsmith.com")):
        return
    flow.request.headers["X-Grader-Orig-Host"] = host
    flow.request.scheme = "http"
    flow.request.host = "127.0.0.1"
    flow.request.port = ctx.options.grader_emulator_port
