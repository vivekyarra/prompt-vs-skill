"""Spike: JS SDK in Chromium (Playwright). Loads the SDK's UMD browser bundle from node_modules.

  python spike/js/browser_spike.py --api http://127.0.0.1:8765/api/v1/ --events http://127.0.0.1:8765/   # Design A (mock)
  python spike/js/browser_spike.py --proxy http://127.0.0.1:8080                                         # Design B (mitmproxy, default hosts)
"""
import argparse
import os
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLE = os.path.join(HERE, "node_modules/@flagsmith/flagsmith/index.js")

ap = argparse.ArgumentParser()
ap.add_argument("--api")
ap.add_argument("--events")
ap.add_argument("--proxy")
a = ap.parse_args()

# A page on a fake https origin so the browser treats it as a normal web app; served via route fulfil.
# Loopback page origin when talking to a loopback mock (avoids Chrome private-network/mixed-content blocks);
# a fake https origin when the SDK calls the real (default) hosts through the proxy.
PAGE = "http://127.0.0.1:9999/" if a.api else "https://spike.example.test/"
HTML = "<!doctype html><html><body><script src='/sdk.js'></script></body></html>"

with sync_playwright() as p:
    # Chromium Local Network Access blocks page->loopback XHR to another port ("Permission was denied ... loopback
    # address space") unless this feature is disabled. Needed for Design A with a browser app; see verified-facts.
    launch = {"args": ["--disable-features=LocalNetworkAccessChecks"]}
    if a.proxy:
        launch["proxy"] = {"server": a.proxy}
    b = p.chromium.launch(**launch)
    ctx = b.new_context(ignore_https_errors=True)
    page = ctx.new_page()
    page.on("requestfailed", lambda r: print("requestfailed:", r.method, r.url, r.failure))
    page.on("console", lambda m: print("console:", m.text))
    page.route(PAGE, lambda r: r.fulfill(status=200, content_type="text/html", body=HTML))
    page.route(PAGE + "sdk.js", lambda r: r.fulfill(status=200, content_type="application/javascript",
                                                   body=open(BUNDLE).read()))
    page.goto(PAGE)
    result = page.evaluate(
        """async ({api, events}) => {
            const fs = window.flagsmith;   // UMD bundle assigns window.flagsmith
            const opts = {environmentID: 'spike-fake-key', enableEvents: true, preventFetch: false};
            if (api) opts.api = api;
            if (events) opts.eventProcessorConfig = {eventsApiUrl: events};
            await fs.init(opts);
            await fs.identify('spike-1');
            const flag = fs.getExperimentFlag('spike_flag');
            fs.trackEvent('spike_event', {value: 1.5});
            await fs.flushEvents();
            return flag;
        }""",
        {"api": a.api, "events": a.events},
    )
    print("flag:", result)
    b.close()
