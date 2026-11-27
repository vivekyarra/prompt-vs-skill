"""Playwright visitors V1 (load, click, reload) and V2 (fresh context)."""

from __future__ import annotations

import os
import pathlib
import re
import time
import urllib.request
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

TEXT_TYPES = ("text/", "javascript", "json", "xml", "html", "css")
BUTTON_RE = re.compile("join", re.I)


def _launch_kwargs(proxy_url: str | None) -> dict:
    kw: dict = {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
    if proxy_url:
        kw["proxy"] = {"server": proxy_url}
    exe = os.environ.get("GRADER_CHROME_PATH")
    if exe:
        kw["executable_path"] = exe
    return kw


def _launch(p, proxy_url):
    kw = _launch_kwargs(proxy_url)
    try:
        return p.chromium.launch(**kw)
    except Exception:
        # Playwright's bundled chromium is not installed: fall back to a system Chrome/Chromium.
        for cand in ("/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"):
            if pathlib.Path(cand).is_file():
                kw["executable_path"] = cand
                return p.chromium.launch(**kw)
        raise


def set_phase(emulator_url: str, name: str) -> None:
    urllib.request.urlopen(f"{emulator_url}/__grader/phase?name={name}", timeout=5).read()  # noqa: S310


def _find_button(page, selector: str | None = None):
    if selector:
        loc = page.locator(selector)
        return loc.first if loc.count() else None
    loc = page.locator("#join-btn")
    if loc.count() == 0:
        loc = page.get_by_role("button", name=BUTTON_RE)
    return loc.first if loc.count() else None


def _settle(page, extra_s: float) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    time.sleep(extra_s)


def _visit(browser, url, emulator_url, phase, ctx_kwargs, assets, load_wait, selector=None):
    ctx = browser.new_context(**ctx_kwargs)
    page = ctx.new_page()
    parts = urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"  # scan every asset of the app, not only those under --url's path

    def on_response(resp):
        if not resp.url.startswith(origin):
            return
        ct = (resp.headers.get("content-type") or "").lower()
        if not any(t in ct for t in TEXT_TYPES):
            return
        try:
            assets[resp.url] = assets.get(resp.url, "") + resp.text()
        except Exception:
            pass

    page.on("response", on_response)
    set_phase(emulator_url, phase)
    page.goto(url, wait_until="load", timeout=30000)
    try:
        page.wait_for_selector(f"{selector}, button" if selector else "#join-btn, button", timeout=10000)
    except Exception:
        pass
    _settle(page, load_wait)
    return ctx, page


def _button_text(page, selector=None):
    btn = _find_button(page, selector)
    return btn.inner_text().strip() if btn else None


def run_visitors(url: str, emulator_url: str, proxy_url: str | None, load_wait: float, click_wait: float,
                 selector: str | None = None) -> dict:  # fmt: skip
    """Returns {"v1_text", "v2_text", "button_found", "click_ok", "click_error", "assets", "dom"}."""
    out: dict = {"assets": {}, "click_error": None}
    ctx_kwargs = {"ignore_https_errors": True} if proxy_url else {}
    with sync_playwright() as p:
        browser = _launch(p, proxy_url)
        try:
            # V1: load
            ctx, page = _visit(browser, url, emulator_url, "load", ctx_kwargs, out["assets"], load_wait, selector)
            out["v1_text"] = _button_text(page, selector)
            out["button_found"] = _find_button(page, selector) is not None
            out["dom"] = page.content()
            # V1: click
            set_phase(emulator_url, "click")
            out["click_ok"] = False
            btn = _find_button(page, selector)
            if btn is not None:
                try:
                    btn.click(timeout=5000)
                    out["click_ok"] = True
                except Exception as e:
                    out["click_error"] = str(e).splitlines()[0][:200]
            _settle(page, click_wait)
            # V1 again: reload in the same context (cookies + storage kept)
            set_phase(emulator_url, "reload")
            page.reload(wait_until="load", timeout=30000)
            _settle(page, load_wait)
            ctx.close()
            # V2: fresh context
            ctx2, page2 = _visit(browser, url, emulator_url, "v2", ctx_kwargs, out["assets"], load_wait, selector)
            out["v2_text"] = _button_text(page2, selector)
            ctx2.close()
        finally:
            browser.close()
    return out
