"""Download TRIAL_RECORD_JSON blocks from the job logs of a trials.yml run (uses the `gh` CLI, REST only).

usage: python scripts/fetch_trial_records.py <run_id> [out.jsonl]
Records are appended to out.jsonl (default data/pilot_<run_id>.jsonl), de-duplicated by trial_id.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

REPO = "vivekyarra/prompt-vs-skill"
MARK = "TRIAL_RECORD_JSON:"


def gh(path: str) -> str:
    return subprocess.run(["gh", "api", path], capture_output=True, text=True, check=True).stdout


def records_from_log(log: str) -> list[dict]:
    lines = [re.sub(r"^\d{4}-\d\d-\d\dT[\d:.]+Z ", "", ln) for ln in log.splitlines()]
    out, i = [], 0
    while i < len(lines):
        if MARK in lines[i]:
            buf = [lines[i].split(MARK, 1)[1]]
            i += 1
            depth_text = "".join(buf)
            while i < len(lines):
                try:
                    out.append(json.loads(depth_text))
                    break
                except ValueError:
                    depth_text += "\n" + lines[i]
                    i += 1
        i += 1
    return out


def main() -> int:
    run_id = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else f"data/pilot_{run_id}.jsonl"
    jobs = json.loads(gh(f"repos/{REPO}/actions/runs/{run_id}/jobs?per_page=100"))["jobs"]
    seen, recs = set(), []
    for j in jobs:
        if j.get("conclusion") not in ("success", "failure"):
            continue
        for r in records_from_log(gh(f"repos/{REPO}/actions/jobs/{j['id']}/logs")):
            if r.get("trial_id") not in seen:
                seen.add(r.get("trial_id"))
                recs.append(r)
    with open(out_path, "w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r) + "\n")
    print(f"{len(recs)} records from {len(jobs)} jobs -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
