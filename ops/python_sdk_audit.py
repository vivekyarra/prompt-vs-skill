"""Exploratory audit: which Python `flagsmith` SDK version did each Python trial use, and does its code flush/close?

Read-only. For every Python trial in data/trials.jsonl and data/replication.jsonl it downloads the saved artifact
(diff.patch, agent_output.jsonl) and prints one PYSDK line with:
  * requirement: the `flagsmith...` line(s) the diff adds to a requirements/pyproject file (what the grader installed);
  * agent_versions: versions pip reported in the agent's own output (`flagsmith-6.x.y`, `flagsmith==6.x.y`, ...);
  * flush_events / close / atexit / max_buffer_items: counts in the lines the diff adds to .py files.
Then each distinct requirement is resolved with pip (dry run) to show what an unpinned spec installs today.

usage (ops.yml): python_sdk_audit.py [--shard=i/N]      needs only GITHUB_TOKEN; touches nothing in Flagsmith.
"""

from __future__ import annotations

import io
import json
import os
import pathlib
import re
import subprocess
import sys
import zipfile

import requests

REPO = pathlib.Path(__file__).resolve().parents[1]
VERSION_RE = re.compile(r"(?<![\w-])flagsmith(?:-|==| )(\d+\.\d+\.\d+)")
REQ_RE = re.compile(r"^\s*[\"']?(flagsmith(?!-)[^#\n\"']*)", re.I)


def gh(path: str) -> bytes:
    r = requests.get(f"https://api.github.com/{path}", timeout=300, headers={
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json"})  # fmt: skip
    r.raise_for_status()
    return r.content


def artifact_index(run_id: str) -> dict[str, int]:
    out, page = {}, 1
    while True:
        d = json.loads(gh(f"repos/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{run_id}/artifacts?per_page=100&page={page}"))
        for a in d["artifacts"]:
            if not a.get("expired"):
                out[a["name"]] = a["id"]
        if len(d["artifacts"]) < 100:
            return out
        page += 1


def analyse(diff: str, agent_out: str) -> dict:
    """Pure: facts from one trial's diff and agent output."""
    req, py_added, cur = [], [], ""
    for ln in diff.splitlines():
        if ln.startswith("+++ "):
            cur = ln[4:].strip()
            continue
        if not ln.startswith("+") or ln.startswith("+++"):
            continue
        body = ln[1:]
        if re.search(r"(requirements[^/]*\.txt|pyproject\.toml|Pipfile|setup\.py)$", cur):
            m = REQ_RE.match(body)
            if m:
                req.append(m.group(1).strip().rstrip(","))
        elif cur.endswith(".py"):
            py_added.append(body)
    code = "\n".join(py_added)
    return {
        "requirement": sorted(set(req)),
        "agent_versions": sorted(set(VERSION_RE.findall(agent_out))),
        "flush_events": len(re.findall(r"\.flush_events\(", code)),
        "close": len(re.findall(r"(?i)\b\w*(?:flagsmith|fs|client)\w*\.close\(", code)),
        "atexit": len(re.findall(r"\batexit\b", code)),
        "max_buffer_items": len(re.findall(r"max_buffer_items", code)),
        "in_test_files_only": bool(py_added) and all("test" in ln.lower() for ln in py_added if "flush_events(" in ln)
        and "flush_events(" in code,
    }


def main() -> int:
    shard = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--shard=")), None)
    trials = []
    for stage, f in (("primary", "trials"), ("replication", "replication")):
        for ln in (REPO / f"data/{f}.jsonl").read_text().splitlines():
            r = json.loads(ln)
            if r["stack"] == "python":
                trials.append({"trial_id": r["trial_id"], "stage": stage, "variant": r["variant"], "passed": r["passed"]})
    trials.sort(key=lambda t: t["trial_id"])
    if shard:
        i, n = (int(x) for x in shard.split("/"))
        trials = [t for k, t in enumerate(trials) if k % n == i]
    index: dict[str, dict[str, int]] = {}
    specs: set[str] = set()
    for t in trials:
        run_id = t["trial_id"].split("-")[1]
        if run_id not in index:
            index[run_id] = artifact_index(run_id)
        row = dict(t)
        try:
            z = zipfile.ZipFile(io.BytesIO(gh(
                f"repos/{os.environ['GITHUB_REPOSITORY']}/actions/artifacts/{index[run_id][t['trial_id']]}/zip")))
            names = z.namelist()
            diff = z.read("diff.patch").decode("utf-8", "replace") if "diff.patch" in names else ""
            agent = z.read("agent_output.jsonl").decode("utf-8", "replace") if "agent_output.jsonl" in names else ""
            row.update(analyse(diff, agent), diff_bytes=len(diff.encode()))
            specs.update(row["requirement"])
        except Exception as e:  # noqa: BLE001
            row["error"] = f"{type(e).__name__}: {str(e)[:120]}"
        print("PYSDK " + json.dumps(row, sort_keys=True), flush=True)
    for spec in sorted(specs):
        r = subprocess.run([sys.executable, "-m", "pip", "install", "--dry-run", "--no-deps", "--ignore-installed",
                            "--quiet", "--report", "-", spec], capture_output=True, text=True)  # fmt: skip
        try:
            ver = json.loads(r.stdout)["install"][0]["metadata"]["version"]
        except Exception:  # noqa: BLE001
            ver = None
        print("PYSPEC " + json.dumps({"spec": spec, "resolves_today": ver}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
