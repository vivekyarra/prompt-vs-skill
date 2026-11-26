#!/usr/bin/env python3
"""Render the demo-video cards to PNG (1920x1080 at deviceScaleFactor 2 is overkill; we use 1280x720 @2x).

    pip install playwright && python -m playwright install chromium   # or GRADER_CHROME_PATH=/usr/bin/google-chrome
    python assets/video/build_cards.py

Writes 01-title.png, 02-architecture.png, 03-trial.png, 04-results-TEMPLATE.png next to this file.
The results card contains placeholders only; it must be re-rendered with real values after the run
(edit RESULTS_ROWS below, never invent numbers).
"""

from __future__ import annotations

import html
import os
import pathlib

from playwright.sync_api import sync_playwright

OUT = pathlib.Path(__file__).resolve().parent

CSS = """
*{box-sizing:border-box;margin:0}
body{width:1280px;height:720px;background:#0f172a;color:#e2e8f0;font-family:Helvetica,Arial,sans-serif;
padding:56px 72px;display:flex;flex-direction:column}
h1{font-size:64px;color:#fff;letter-spacing:-1px}
h2{font-size:38px;color:#fff;margin-bottom:20px}
.acc{color:#38bdf8}
.sub{font-size:28px;line-height:1.4;color:#cbd5e1;margin-top:28px}
.foot{margin-top:auto;font-size:20px;color:#94a3b8}
.step{display:flex;gap:18px;align-items:flex-start;margin:9px 0;font-size:23px;line-height:1.3}
.n{flex:none;width:36px;height:36px;border-radius:18px;background:#38bdf8;color:#0f172a;font-weight:700;
text-align:center;line-height:36px;font-size:20px}
.box{border:2px solid #38bdf8;border-radius:14px;padding:16px 22px;font-size:22px;background:#1e293b}
.row{display:flex;gap:18px;align-items:stretch}
.arrow{align-self:center;font-size:34px;color:#38bdf8}
table{border-collapse:collapse;width:100%;font-size:21px}
td,th{border-bottom:1px solid #334155;padding:8px 12px;text-align:left}
th{color:#94a3b8;font-weight:600}
td.v{font-family:Menlo,Consolas,monospace;color:#fbbf24}
.banner{background:#7c2d12;color:#fed7aa;border-radius:10px;padding:12px 20px;font-size:19px;margin-bottom:14px}
"""

RESULTS_ROWS = [
    ("Trials per variant (prompt / skill)", "{{N_PROMPT}} / {{N_SKILL}}"),
    ("Exposures (Flagsmith)", "{{EXPOSURES}}"),
    ("integration_verified rate: prompt / skill", "{{RATE_PROMPT}} / {{RATE_SKILL}}"),
    ("Credible interval for the difference", "{{CREDIBLE_INTERVAL}}"),
    ("Win probability (skill)", "{{WIN_PROBABILITY}}"),
    ("Guardrail over_budget: prompt / skill", "{{OVER_BUDGET_PROMPT}} / {{OVER_BUDGET_SKILL}}"),
    ("Decision (pre-registered rule)", "{{DECISION}}"),
]


def page(body: str) -> str:
    return f"<!doctype html><meta charset=utf-8><style>{CSS}</style><body>{body}</body>"


def cards() -> dict[str, str]:
    title = page(
        """<div style="margin-top:110px"><h1>Handoff: <span class=acc>Prompt vs Skill</span></h1>
<p class=sub>Does an Agent Skill beat the official setup prompt at getting coding agents to a
correctly wired Flagsmith A/B test? We ran a real Flagsmith experiment to find out.</p></div>
<div class=foot>Toggle Wars: The Flagsmith Experimentation Hackathon &middot; Track 01</div>"""
    )
    arch = page(
        """<h2>Architecture: one job = one trial</h2>
<div class=row>
<div class=box><b>GitHub Actions</b><br>matrix of N trials</div><div class=arrow>&rarr;</div>
<div class=box><b>Runner</b><br>asks Flagsmith for<br><code>onboarding_method</code><br>identity = trial ID</div>
<div class=arrow>&rarr;</div>
<div class=box><b>Coding agent</b><br>prompt or skill<br>+ same task brief</div><div class=arrow>&rarr;</div>
<div class=box><b>Grader</b><br>proxy + Playwright<br>checks C1&ndash;C6</div></div>
<div class=row style="margin-top:34px">
<div class=box style="flex:1"><b>Flagsmith (experiment project)</b><br>assigns variant, records exposure,
receives <code>integration_verified</code> / <code>over_budget</code>, computes the result</div>
<div class=box style="flex:1"><b>After the trials</b><br>trial records &rarr; <code>data/trials.jsonl</code>
&rarr; <code>RESULTS.md</code> (own cross-check)</div></div>
<div class=foot>Two Flagsmith projects, never mixed: experiment (runner only) and sandbox (agents).</div>"""
    )
    steps = [
        "Runner picks a sample app (React, Node or Python), seeded by trial ID.",
        "Flagsmith assigns <code>onboarding_method</code> (prompt or skill); exposure recorded.",
        "Clean workspace; agent gets the official prompt or the skill, plus the same brief.",
        "Claude Code works headlessly with fixed turn and token limits.",
        "Grader runs the app behind a proxy, simulates visitors, checks C1&ndash;C6 from real traffic.",
        "Runner sends <code>integration_verified</code> and/or <code>over_budget</code> to Flagsmith.",
    ]
    trial = page(
        "<h2>How a trial works</h2>"
        + "".join(f"<div class=step><div class=n>{i}</div><div>{s}</div></div>" for i, s in enumerate(steps, 1))
        + "<div class=foot>Identity = trial ID, so Flagsmith counts one visitor per trial.</div>"
    )
    rows = "".join(f"<tr><td>{html.escape(k)}</td><td class=v>{html.escape(v)}</td></tr>" for k, v in RESULTS_ROWS)
    results = page(
        "<h2>Results</h2><div class=banner>TEMPLATE: filled after the run from the final Flagsmith "
        "dashboard and RESULTS.md. Placeholders are not results.</div>"
        f"<table><tr><th>Measure</th><th>Value</th></tr>{rows}</table>"
        "<div class=foot>Source: Flagsmith results page; date and time read: {{DATE_TIME_READ}}</div>"
    )
    return {"01-title": title, "02-architecture": arch, "03-trial": trial, "04-results-TEMPLATE": results}


def main() -> None:
    exe = os.environ.get("GRADER_CHROME_PATH")
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=2)
        for name, doc in cards().items():
            pg = ctx.new_page()
            pg.set_content(doc)
            pg.screenshot(path=str(OUT / f"{name}.png"))
            pg.close()
        b.close()


if __name__ == "__main__":
    main()
