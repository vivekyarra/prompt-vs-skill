"""Exploratory audit: which saved diffs choose the button text by comparing the flag's VARIANT KEY?

Background (docs/mock-vs-real.md): the local emulator returns synthetic variant keys (`variant_0`, `variant_1`);
real Flagsmith returns the option's own key. An app that compares `flag.variant` with its own key therefore behaves
differently on the emulator. This script reads every trial artifact of both runs and prints, per trial, the lines
the diff ADDS to source files (not tests, docs, lockfiles) that compare something named `variant` with `==`/`!=`.

Read-only: needs only GITHUB_TOKEN, touches nothing in Flagsmith.    usage (ops.yml): variant_key_audit.py [--shard=i/N]
"""

from __future__ import annotations

import io
import json
import os
import pathlib
import re
import sys
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from python_sdk_audit import artifact_index, gh  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[1]
SOURCE = re.compile(r"\.(jsx?|tsx?|mjs|cjs|py|html|vue)$")
SKIP = re.compile(r"(?i)(test|spec|__tests__|\.md$|lock)")
COMPARE = re.compile(r"(?i)variant\w*\s*(?:\?\.)?\s*(?:===|!==|==|!=)|(?:===|!==|==|!=)\s*[\w.?\[\]'\"]*variant")
LITERAL = re.compile(r"""['"](variant_\d+|control|join_free|join-free|treatment|variation|[a-z_]*free[a-z_]*)['"]""", re.I)


def analyse(diff: str) -> dict:
    """Pure: variant-key comparisons in the source lines a diff adds."""
    cur, hits, added = "", [], []
    for ln in diff.splitlines():
        if ln.startswith("+++ "):
            cur = ln[4:].strip()
        elif ln.startswith("+") and not ln.startswith("+++") and SOURCE.search(cur) and not SKIP.search(cur):
            added.append(ln[1:])
            if COMPARE.search(ln[1:]):
                hits.append(ln[1:].strip()[:170])
    code = "\n".join(added)
    return {
        "variant_compare_lines": hits[:6],
        "n_variant_compare": len(hits),
        "key_literals": sorted({m.lower() for m in LITERAL.findall(code)}),
        "reads_value": bool(re.search(r"\.value\b|feature_state_value|getValue\(|get_value\(|\[['\"]value['\"]\]", code)),
    }


def main() -> int:
    shard = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--shard=")), None)
    trials = []
    for stage, f in (("primary", "trials"), ("replication", "replication")):
        for ln in (REPO / f"data/{f}.jsonl").read_text().splitlines():
            r = json.loads(ln)
            trials.append({"trial_id": r["trial_id"], "stage": stage, "variant": r["variant"], "stack": r["stack"],
                           "passed": r["passed"], "failed": sorted(k for k, v in (r.get("checks") or {}).items() if v is False)})  # fmt: skip
    trials.sort(key=lambda t: t["trial_id"])
    if shard:
        i, n = (int(x) for x in shard.split("/"))
        trials = [t for k, t in enumerate(trials) if k % n == i]
    index: dict[str, dict[str, int]] = {}
    for t in trials:
        run_id = t["trial_id"].split("-")[1]
        if run_id not in index:
            index[run_id] = artifact_index(run_id)
        row = dict(t)
        try:
            z = zipfile.ZipFile(io.BytesIO(gh(
                f"repos/{os.environ['GITHUB_REPOSITORY']}/actions/artifacts/{index[run_id][t['trial_id']]}/zip")))
            diff = z.read("diff.patch").decode("utf-8", "replace") if "diff.patch" in z.namelist() else ""
            row.update(analyse(diff), diff_bytes=len(diff.encode()))
        except Exception as e:  # noqa: BLE001
            row["error"] = f"{type(e).__name__}: {str(e)[:120]}"
        print("VKEY " + json.dumps(row, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
