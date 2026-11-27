"""Human-readable report for a grader result (additive: result.json keeps its schema, plus a `hints` key)."""

from __future__ import annotations

import textwrap

MEANING = {
    "C1": "app starts, tests pass, button clickable",
    "C2": "exposure recorded",
    "C3": "conversion on click, not on load",
    "C4": "same identity for exposure and conversion",
    "C5": "identity persists; new visitor differs",
    "C6": "UI renders the flag value",
    "C7": "no server key in the browser (diagnostic)",
}

FIX_HINTS = {
    "C1": "the app must start and its tests must pass",
    "C2": "read the flag with getExperimentFlag/get_experiment_flag/useExperiment, "
    "plain flag reads record no exposure",
    "C3": "send the conversion from the click handler, not on load",
    "C4": "use the same identity for exposure and conversion",
    "C5": "persist the visitor id; do not regenerate per request",
    "C6": "render the text from the flag value",
    "C7": "never ship a server key to the browser",
}


def hints_for(checks: dict) -> dict:
    """Fix hint per failed check."""
    return {cid: FIX_HINTS[cid] for cid, c in checks.items() if not c.get("passed") and cid in FIX_HINTS}


def _wrap(text: str) -> list[str]:
    return textwrap.wrap(text, 100, initial_indent=" " * 15, subsequent_indent=" " * 17)


def format_report(result: dict) -> str:
    checks = result.get("checks", {})
    hints = result.get("hints") or hints_for(checks)
    lines = ["Check  Result  What it checks / why it failed", "-----  ------  ------------------------------"]
    for cid, c in checks.items():
        ok = c.get("passed")
        lines.append(f"{cid:<5}  {'PASS' if ok else 'FAIL':<6}  {MEANING.get(cid, '')}")
        if not ok:
            if c.get("reason"):
                lines += _wrap(f"reason: {c['reason']}")
            if hints.get(cid):
                lines += _wrap(f"FIX HINT: {hints[cid]}")
    lines.append("")
    lines.append("OVERALL: " + ("PASS" if result.get("passed") else "FAIL") + "  (pass rule: C1-C6; C7 is diagnostic)")
    return "\n".join(lines)
