"""Does Chromium block a page REALLY served from loopback (http.server) from calling the mock on another loopback port?
Tests with and without --disable-features=LocalNetworkAccessChecks. Needs the mock running on 127.0.0.1:8767.
  python spike/js/browser_lna_test.py
"""
import functools
import http.server
import os
import tempfile
import threading
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLE = os.path.join(HERE, "node_modules/@flagsmith/flagsmith/index.js")
root = tempfile.mkdtemp()
open(os.path.join(root, "index.html"), "w").write("<!doctype html><script src='sdk.js'></script>")
open(os.path.join(root, "sdk.js"), "w").write(open(BUNDLE).read())
h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=root)
h.log_message = lambda *a, **k: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 9998), h)
threading.Thread(target=srv.serve_forever, daemon=True).start()

JS = """async () => {
  const fs = window.flagsmith;
  await fs.init({environmentID:'spike-fake-key', enableEvents:true, api:'http://127.0.0.1:8767/api/v1/',
                 eventProcessorConfig:{eventsApiUrl:'http://127.0.0.1:8767/'}});
  await fs.identify('spike-1');
  const f = fs.getExperimentFlag('spike_flag'); fs.trackEvent('spike_event'); await fs.flushEvents(); return !!f;
}"""
with sync_playwright() as p:
    for args in ([], ["--disable-features=LocalNetworkAccessChecks"]):
        b = p.chromium.launch(args=args)
        page = b.new_page()
        msgs = []
        page.on("console", lambda m: msgs.append(m.text[:140]))
        page.goto("http://127.0.0.1:9998/index.html")
        try:
            print(args or "no flag", "-> OK flag returned:", page.evaluate(JS))
        except Exception as e:
            print(args or "no flag", "-> FAILED:", str(e)[:60], msgs[:1])
        b.close()
srv.shutdown()
