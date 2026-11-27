"""Stdlib-only SVG figures for RESULTS.md.

This module only draws. Every number comes in through the ``stats`` dict built by
``analysis.analyze.figure_stats`` (same Beta-Binomial posterior, same seeds, same decision rule as the
report), so the figures can never disagree with RESULTS.md. Nothing here is hard-coded data.

Accessibility: <title>/<desc>, colour-blind-safe Okabe-Ito colours plus distinct marker shapes, text in
currentColor with a dark-mode media query inside the SVG (GitHub renders README images as <img>, so the
page's own CSS cannot reach them).
"""

from __future__ import annotations

from xml.sax.saxutils import escape

W = 800
COLORS = {"prompt": "#E69F00", "skill": "#0072B2"}  # Okabe-Ito orange / blue
LABEL_X, PLOT_L, PLOT_R = 24, 190, 740

STYLE = """
  svg{color:#1f2328}
  .t{fill:currentColor;font-family:Helvetica,Arial,sans-serif}
  .h{font-size:20px;font-weight:700}
  .s{font-size:13px;opacity:.78}
  .m{font-size:14px}
  .b{font-size:15px;font-weight:700}
  .f{font-size:11px;opacity:.7}
  .ax{stroke:currentColor;opacity:.35;fill:none}
  .gr{stroke:currentColor;opacity:.12}
  .bg{fill:#ffffff}
  @media (prefers-color-scheme: dark){svg{color:#e6edf3}.bg{fill:#0d1117}}
"""


def _x(v: float, lo: float, hi: float) -> float:
    return PLOT_L + (v - lo) / (hi - lo) * (PLOT_R - PLOT_L)


def _svg(height: int, title: str, desc: str, body: list[str]) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {height}" width="{W}" height="{height}" '
        f'role="img" aria-labelledby="ttl dsc">\n<title id="ttl">{escape(title)}</title>\n'
        f'<desc id="dsc">{escape(desc)}</desc>\n<style>{STYLE}</style>\n'
        f'<rect class="bg" width="{W}" height="{height}"/>\n' + "\n".join(body) + "\n</svg>\n"
    )


def _text(x, y, s, cls="m", anchor="start") -> str:
    return f'<text class="t {cls}" x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}">{escape(s)}</text>'


def _footer(generated: str, stage: str, height: int) -> str:
    return _text(24, height - 14, f"generated from data/trials.jsonl at {generated}; stage {stage}", "f")


def _marker(arm: str, cx: float, cy: float) -> str:
    c = COLORS[arm]
    if arm == "prompt":
        return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="7" fill="{c}" stroke="currentColor" stroke-width="1"/>'
    return (
        f'<rect x="{cx - 6:.1f}" y="{cy - 6:.1f}" width="12" height="12" fill="{c}" stroke="currentColor" '
        f'stroke-width="1" transform="rotate(45 {cx:.1f} {cy:.1f})"/>'
    )


def pct(x: float) -> str:
    return f"{x:.1%}"


def _nice_bound(v: float, floor: float = 0.1) -> float:
    return min(1.0, (int(max(floor, v) * 10) + 1) / 10)


def no_data_svg(kind: str, generated: str, stage: str) -> str:
    h = 200
    what = "Pass rate per arm" if kind == "results" else "Failure rate per check"
    body = [
        _text(24, 44, what, "h"),
        _text(W / 2, 108, "No data yet", "h", "middle"),
        _text(W / 2, 134, "data/trials.jsonl has no analysable trials for this stage.", "s", "middle"),
        _footer(generated, stage, h),
    ]
    return _svg(h, f"{what}: no data yet", "No analysable trials exist yet, so no figure is drawn.", body)


def _verdict_text(decision: dict) -> str:
    o = decision["outcome"]
    if o == "ship":
        return f"Own-log verdict: SHIP {decision['winner']} (win probability {pct(decision['win_prob'])})"
    if o == "inconclusive":
        return "Own-log verdict: INCONCLUSIVE"
    return "Own-log verdict: no decision possible"


def results_svg(stats: dict | None, generated: str, stage: str) -> str:
    """Pass rate per arm with 95% credible intervals, plus the difference panel."""
    if not stats:
        return no_data_svg("results", generated, stage)
    h = 470
    n, passed, rate, ci = stats["n"], stats["passed"], stats["rate"], stats["ci"]
    d, dec = stats["diff"], stats["decision"]
    body = [
        _text(24, 36, "Pass rate per arm, prompt vs skill", "h"),
        _text(
            24,
            58,
            "Point = observed pass rate; line = 95% credible interval (Beta(1,1) prior, Monte Carlo). "
            "Runner errors excluded.",
            "s",
        ),
    ]
    top = 90
    for v in (0, 0.25, 0.5, 0.75, 1.0):
        gx = _x(v, 0, 1)
        body.append(f'<line class="gr" x1="{gx:.1f}" x2="{gx:.1f}" y1="{top}" y2="{top + 120}"/>')
        body.append(_text(gx, top + 138, f"{v:.0%}", "s", "middle"))
    body.append(_text((PLOT_L + PLOT_R) / 2, top + 158, "pass rate (integration_verified)", "s", "middle"))
    for i, arm in enumerate(("prompt", "skill")):
        cy = top + 35 + i * 55
        body.append(_text(LABEL_X, cy + 5, f"{arm}  (n = {n[arm]})", "b"))
        if rate[arm] is None:
            body.append(_text(PLOT_L + 8, cy + 5, "no analysable trials", "s"))
            continue
        lo, hi = ci[arm]
        body.append(
            f'<line x1="{_x(lo, 0, 1):.1f}" x2="{_x(hi, 0, 1):.1f}" y1="{cy}" y2="{cy}" '
            f'stroke="{COLORS[arm]}" stroke-width="5" stroke-linecap="round"/>'
        )
        body.append(_marker(arm, _x(rate[arm], 0, 1), cy))
        body.append(_text(PLOT_R + 6, cy - 4, pct(rate[arm]), "b"))
        body.append(_text(PLOT_R + 6, cy + 12, f"{passed[arm]}/{n[arm]}", "s"))
        body.append(_text(_x(rate[arm], 0, 1), cy - 14, f"95% CI {pct(lo)} to {pct(hi)}", "s", "middle"))

    ytop = 300
    body.append(_text(24, ytop, "Difference in pass rate (skill minus prompt)", "b"))
    if d is not None:
        bound = _nice_bound(max(abs(d["ci_low"]), abs(d["ci_high"])))
        cy = ytop + 38
        for v in (-bound, 0, bound):
            gx = _x(v, -bound, bound)
            body.append(f'<line class="{"ax" if v == 0 else "gr"}" x1="{gx:.1f}" x2="{gx:.1f}" y1="{cy - 18}" y2="{cy + 18}"/>')
            body.append(_text(gx, cy + 34, f"{v:+.1f}" if v else "0", "s", "middle"))
        body.append(
            f'<line x1="{_x(d["ci_low"], -bound, bound):.1f}" x2="{_x(d["ci_high"], -bound, bound):.1f}" '
            f'y1="{cy}" y2="{cy}" stroke="currentColor" stroke-width="4" stroke-linecap="round"/>'
        )
        body.append(
            f'<rect x="{_x(d["mean_diff"], -bound, bound) - 6:.1f}" y="{cy - 6}" width="12" height="12" '
            f'fill="currentColor"/>'
        )
        body.append(
            _text(
                24,
                ytop + 92,
                f"Mean {d['mean_diff']:+.3f}; 95% credible interval [{d['ci_low']:+.3f}, "
                f"{d['ci_high']:+.3f}]; P(skill > prompt) = {pct(d['p_b_better'])}",
                "m",
            )
        )
    else:
        body.append(_text(24, ytop + 30, "Not computable: a variant has no analysable trials.", "m"))
    body.append(_text(24, ytop + 122, _verdict_text(dec), "b"))
    if dec["outcome"] == "inconclusive":
        body.append(_text(24, ytop + 144, "; ".join(dec["reasons"]), "s"))
    body.append(
        _text(
            24,
            ytop + 164,
            "Decision rule (pre-registered): win probability >= 95% and the 95% interval excludes zero "
            "and the guardrail is not worse.",
            "s",
        )
    )
    body.append(_footer(generated, stage, h))
    desc = "Pass rate per arm; at least one arm has no analysable trials."
    if None not in rate.values():
        desc = f"Pass rate: prompt {pct(rate['prompt'])} of {n['prompt']}, skill {pct(rate['skill'])} of {n['skill']}."
    if d is not None:
        desc += (
            f" Difference skill minus prompt {d['mean_diff']:+.3f}, 95% credible interval "
            f"[{d['ci_low']:+.3f}, {d['ci_high']:+.3f}], P(skill > prompt) {pct(d['p_b_better'])}."
        )
    desc += " " + _verdict_text(dec) + "."
    return _svg(h, "Pass rate per arm, prompt vs skill", desc, body)


def failures_svg(stats: dict | None, generated: str, stage: str) -> str:
    """Grouped horizontal bars: failure rate of each primary check, per arm."""
    if not stats:
        return no_data_svg("failures", generated, stage)
    checks, n, fails = stats["checks"], stats["n"], stats["check_fail"]
    h = 120 + len(checks) * 50 + 40
    rates = [fails[a][c] / n[a] for a in fails for c in checks if n[a]]
    hi = _nice_bound(max(rates, default=0.0))
    top = 100
    body = [
        _text(24, 36, "Where agents fail: failure rate per check", "h"),
        _text(
            24,
            58,
            f"Share of analysed trials in which each check failed (prompt n = {n['prompt']}, "
            f"skill n = {n['skill']}). Lower is better.",
            "s",
        ),
        f'<rect x="{PLOT_L}" y="70" width="12" height="12" fill="{COLORS["prompt"]}"/>',
        _text(PLOT_L + 18, 81, "prompt", "s"),
        f'<rect x="{PLOT_L + 90}" y="70" width="12" height="12" fill="{COLORS["skill"]}"/>',
        _text(PLOT_L + 108, 81, "skill", "s"),
    ]
    for k in range(5):
        v = hi * k / 4
        gx = _x(v, 0, hi)
        body.append(f'<line class="gr" x1="{gx:.1f}" x2="{gx:.1f}" y1="{top - 8}" y2="{top + len(checks) * 50}"/>')
        body.append(_text(gx, top + len(checks) * 50 + 16, f"{v:.0%}", "s", "middle"))
    for i, c in enumerate(checks):
        y0 = top + i * 50
        body.append(_text(LABEL_X, y0 + 26, c, "b"))
        for j, arm in enumerate(("prompt", "skill")):
            y = y0 + 4 + j * 20
            if not n[arm]:
                continue
            r = fails[arm][c] / n[arm]
            bw = max(1.5, _x(r, 0, hi) - PLOT_L)
            body.append(f'<rect x="{PLOT_L}" y="{y}" width="{bw:.1f}" height="16" fill="{COLORS[arm]}"/>')
            body.append(_text(PLOT_L + bw + 6, y + 13, f"{fails[arm][c]}/{n[arm]} ({pct(r)})", "s"))
    body.append(_footer(generated, stage, h))
    desc = (
        "Failure rate per check, prompt then skill: "
        + "; ".join(f"{c} " + " / ".join(f"{a} {fails[a][c]}/{n[a]}" for a in ("prompt", "skill")) for c in checks)
        + "."
    )
    return _svg(h, "Failure rate per check, prompt vs skill", desc, body)
