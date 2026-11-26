#!/usr/bin/env python3
"""Generate the broken integrations (B1..B7) for each stack.

Each broken app is a copy of apps/reference/<stack> with exactly ONE targeted
patch applied. Output: apps/broken/_generated/<stack>/Bn (gitignored).

    python apps/broken/make_broken.py --all
    python apps/broken/make_broken.py --stack node --id B3
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REFERENCE = HERE.parent / "reference"
OUT = HERE / "_generated"
STACKS = ("react", "node", "python")
IDS = tuple(f"B{i}" for i in range(1, 8))
IGNORE = shutil.ignore_patterns("node_modules", "dist", "__pycache__", ".pytest_cache", ".venv")

# The browser-visible "server key" planted by B7 (react: override with VITE_FLAGSMITH_SERVER_KEY at build time).
DEMO_SERVER_KEY = "ser.DEMO_LEAKED_SERVER_KEY"


def replace(root: Path, rel: str, old: str, new: str) -> None:
    """Replace `old` with `new` in a file; fail loudly if the reference drifted."""
    path = root / rel
    text = path.read_text()
    if old not in text:
        sys.exit(f"patch target not found in {path}:\n{old}")
    path.write_text(text.replace(old, new, 1))


APP_FILE = {"react": "src/App.jsx", "node": "app.js", "python": "app.py"}


# ---- B1: app fails to start (syntax error) ---------------------------------
def b1(stack: str, root: Path) -> None:
    broken_line = {"react": "const = ;\n", "node": "const = ;\n", "python": "def (:\n"}[stack]
    path = root / APP_FILE[stack]
    path.write_text(path.read_text() + "\n" + broken_line)


# ---- B2: plain flag read instead of the experiment method (no exposure) ----
def b2(stack: str, root: Path) -> None:
    if stack == "react":
        replace(root, "src/App.jsx", "flagsmith.getExperimentFlag(FLAG)", "{ value: flagsmith.getValue(FLAG) }")
    elif stack == "node":
        replace(
            root,
            "app.js",
            "const flag = await flagsmith.getExperimentFlag(FLAG, req.vid)",
            "const flag = { value: (await flagsmith.getIdentityFlags(req.vid)).getFeatureValue(FLAG) }",
        )
    else:
        replace(
            root,
            "app.py",
            "flag = flagsmith.get_experiment_flag(FLAG, g.vid)",
            "flag = type('F', (), {'value': flagsmith.get_identity_flags(g.vid).get_feature_value(FLAG)})()",
        )


# ---- B3: conversion sent on page load, not on click ------------------------
def b3(stack: str, root: Path) -> None:
    if stack == "react":
        click = (
            "      flagsmith.trackEvent('join_clicked', { identifier: visitorId })\n"
            "      flagsmith.flushEvents().catch(() => {})\n"
        )
        replace(root, "src/App.jsx", click, "")
        replace(
            root,
            "src/App.jsx",
            "        flagsmith.flushEvents().catch(() => {}) // send the exposure now, not on the timer\n",
            "        flagsmith.trackEvent('join_clicked', { identifier: visitorId })\n"
            "        flagsmith.flushEvents().catch(() => {})\n",
        )
    elif stack == "node":
        click = (
            "      flagsmith.trackEvent('join_clicked', { identifier: req.vid })\n"
            "      await flagsmith.flushEvents()\n"
        )
        replace(root, "app.js", click, "")
        replace(
            root,
            "app.js",
            "      await flagsmith.flushEvents() // send the exposure now, not on the timer\n",
            "      flagsmith.trackEvent('join_clicked', { identifier: req.vid })\n"
            "      await flagsmith.flushEvents()\n",
        )
    else:
        click = (
            '            flagsmith.track_event("join_clicked", identifier=g.vid)\n'
            "            flagsmith.flush_events()\n"
        )
        replace(root, "app.py", click, "            pass\n")
        replace(
            root,
            "app.py",
            "            flagsmith.flush_events()  # send the exposure now, not on the timer\n",
            '            flagsmith.track_event("join_clicked", identifier=g.vid)\n'
            "            flagsmith.flush_events()\n",
        )


# ---- B4: conversion uses a different identity than the exposure ------------
def b4(stack: str, root: Path) -> None:
    if stack == "react":
        replace(root, "src/App.jsx", "{ identifier: visitorId })\n      flagsmith.flushEvents()", "{ identifier: 'other-' + visitorId })\n      flagsmith.flushEvents()")
    elif stack == "node":
        replace(root, "app.js", "{ identifier: req.vid })\n      await flagsmith.flushEvents()\n    } catch", "{ identifier: 'other-' + req.vid })\n      await flagsmith.flushEvents()\n    } catch")
    else:
        replace(root, "app.py", 'track_event("join_clicked", identifier=g.vid)', 'track_event("join_clicked", identifier="other-" + g.vid)')


# ---- B5: new random identity on every load ---------------------------------
def b5(stack: str, root: Path) -> None:
    if stack == "react":
        path = root / "src/visitor.js"
        path.write_text(
            "// BROKEN (B5): a fresh random id on every load, never persisted.\n"
            "export function getVisitorId() {\n  return crypto.randomUUID()\n}\n"
        )
    elif stack == "node":
        replace(root, "app.js", "let vid = req.cookies.vid", "let vid = undefined // BROKEN (B5): ignore the cookie")
    else:
        replace(root, "app.py", 'g.vid = request.cookies.get("vid")', "g.vid = None  # BROKEN (B5): ignore the cookie")


# ---- B6: flag is read, but button text is not driven by it -----------------
def b6(stack: str, root: Path) -> None:
    if stack == "react":
        replace(root, "src/App.jsx", "        {buttonText}\n", "        {CONTROL_TEXT}\n")
    elif stack == "node":
        replace(root, "app.js", "page(escapeHtml(text))", "page(escapeHtml(CONTROL_TEXT))")
    else:
        replace(root, "app.py", 'button_text=text)', "button_text=CONTROL_TEXT)")


# ---- B7 (diagnostic): server-side key embedded in a browser-loaded asset ---
def b7(stack: str, root: Path) -> None:
    if stack == "react":
        replace(
            root,
            "src/App.jsx",
            "const CLIENT_KEY =",
            f"const SERVER_KEY = import.meta.env.VITE_FLAGSMITH_SERVER_KEY || '{DEMO_SERVER_KEY}' // BROKEN (B7)\n"
            "const CLIENT_KEY =",
        )
        replace(root, "src/App.jsx", "data-visitor={visitorId}", "data-visitor={visitorId} data-key={SERVER_KEY}")
    elif stack == "node":
        replace(
            root,
            "app.js",
            "<button id=\"join-btn\">",
            f"<script>window.FLAGSMITH_KEY = '${{process.env.FLAGSMITH_SERVER_KEY || '{DEMO_SERVER_KEY}'}}'</script>\n  <button id=\"join-btn\">",
        )
    else:
        replace(
            root,
            "templates/index.html",
            '<button id="join-btn">',
            "<script>window.FLAGSMITH_KEY = '{{ server_key }}'</script>\n  <button id=\"join-btn\">",
        )
        replace(
            root,
            "app.py",
            'render_template("index.html", button_text=text)',
            f'render_template("index.html", button_text=text, server_key=os.environ.get("FLAGSMITH_SERVER_KEY") or "{DEMO_SERVER_KEY}")',
        )


PATCHES = {"B1": b1, "B2": b2, "B3": b3, "B4": b4, "B5": b5, "B6": b6, "B7": b7}


def generate(stack: str, bid: str, out: Path = OUT) -> Path:
    dest = out / stack / bid
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(REFERENCE / stack, dest, ignore=IGNORE)
    PATCHES[bid](stack, dest)
    return dest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="generate every stack x B1..B7")
    ap.add_argument("--stack", choices=STACKS, action="append")
    ap.add_argument("--id", choices=IDS, action="append", dest="ids")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    if not args.all and not (args.stack and args.ids):
        ap.error("use --all, or --stack and --id")
    for stack in STACKS if args.all else args.stack:
        for bid in IDS if args.all else args.ids:
            print(generate(stack, bid, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
