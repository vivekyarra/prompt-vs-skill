"""Offline regrade of saved agent diffs with the CURRENT grader. Sends nothing to Flagsmith.

For each trial artifact folder (trial-<run>-<index>/ with diff.patch, trial_record.json, grader_result.json):
copy apps/<stack>, apply the diff, supply placeholder values for credential env names the code reads but the grader
does not provide (the agent's untracked `.env` / `.env.local` were dropped by `git add -A`: they were gitignored and
are not in the diff), run `python -m grader --mode proxy --reclaim-port` exactly as the runner did, and write one JSON
result per trial: original verdict and failed checks, regrade verdict and failed checks, flipped?

A trial whose regrade differs from its original verdict is regraded again (up to `--confirm` runs in total), so
that a difference is only called reproducible after 3 of 3 runs agree on the new verdict.

usage:
    python scripts/regrade_diffs.py --artifacts /tmp/primary_art /tmp/replication_art --out out/regrade
    python scripts/regrade_diffs.py --artifacts DIR --out OUT --shard 3/20      (0-based shard i of N)
    python scripts/regrade_diffs.py --artifacts DIR --out OUT --only trial-45912277670-1
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from runner.config import CONTROL_VALUE, EVENT_NAME, VARIATION_VALUE  # noqa: E402

PASS_CHECKS = ("C1", "C2", "C3", "C4", "C5", "C6")
EXCLUDES = ("node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build", "*.pyc")

# Names the grader itself supplies to the app (grader/stacks.py app_env): never written to an env file.
GRADER_SUPPLIED = {
    "PORT", "FLAGSMITH_CLIENT_KEY", "FLAGSMITH_SERVER_KEY", "VITE_FLAGSMITH_CLIENT_KEY", "FLAGSMITH_FLAG",
    "VITE_FLAGSMITH_FLAG",
}  # fmt: skip
PLACEHOLDER_CLIENT_KEY = "GRADER_PLACEHOLDER_CLIENT_KEY_7f3a9c"
PLACEHOLDER_SERVER_KEY = "ser.GRADER_PLACEHOLDER_SERVER_KEY_7f3a9c"

ENV_READ_PATTERNS = [
    re.compile(r"import\.meta\.env\.([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"import\.meta\.env\[\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*\]"),
    re.compile(r"process\.env\.([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"process\.env\[\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*\]"),
    re.compile(r"os\.environ\[\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*\]"),
    re.compile(r"os\.environ\.get\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]"),
    re.compile(r"os\.getenv\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]"),
    re.compile(r"\benv\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]"),  # local helper `env("NAME")` seen in agent code
]
CREDENTIAL_NAME = re.compile(r"(KEY|TOKEN|ENVIRONMENT_ID|ENVIRONMENT|ENV_ID)$", re.I)
FLAG_NAME = re.compile(r"(^|_)FLAG(_NAME|_KEY)?$|FEATURE", re.I)


def added_lines(diff: str) -> str:
    return "\n".join(ln[1:] for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++"))


def env_names_read(diff: str) -> list[str]:
    """Env var names read by code the diff ADDS (sorted, unique)."""
    text = added_lines(diff)
    names = {m.group(1) for pat in ENV_READ_PATTERNS for m in pat.finditer(text)}
    return sorted(names)


def placeholders_for(names, stack: str, flag: str) -> dict[str, str]:
    """Placeholder values for names the code reads and the grader does not already supply.

    * names ending in KEY/TOKEN/ENVIRONMENT/ENVIRONMENT_ID: a distinctive placeholder key (server stacks get the
      `ser.` one, react the client one: a `ser.` gate then behaves as it would for the grader's own server key);
    * names that look like a flag/feature name: the trial's flag name;
    * everything else (URLs, DEBUG, DISABLED, MODE, ...): NOT supplied, so the app's own default applies.
    """
    out: dict[str, str] = {}
    for n in names:
        if n in GRADER_SUPPLIED or n in ("DEV", "MODE", "PROD", "SSR", "BASE_URL", "NODE_ENV"):
            continue
        if FLAG_NAME.search(n) and not re.search(r"(DISABLED|DEBUG|ENABLE)", n, re.I):
            out[n] = flag
        elif CREDENTIAL_NAME.search(n):
            out[n] = PLACEHOLDER_SERVER_KEY if stack in ("node", "python") else PLACEHOLDER_CLIENT_KEY
    return out


def write_env_files(work: pathlib.Path, values: dict[str, str]) -> list[str]:
    """Append missing names to `.env` and `.env.local` (a name already set in an existing file is left alone)."""
    written = []
    for fname in (".env", ".env.local"):
        p = work / fname
        have = set()
        if p.is_file():
            have = {ln.split("=", 1)[0].strip() for ln in p.read_text(errors="replace").splitlines() if "=" in ln}
        add = {k: v for k, v in values.items() if k not in have}
        if add:
            body = p.read_text(errors="replace") if p.is_file() else ""
            if body and not body.endswith("\n"):
                body += "\n"
            p.write_text(body + "".join(f"{k}={v}\n" for k, v in add.items()))
            written.append(fname)
    return written


def pick_shard(items: list, shard: str | None) -> list:
    if not shard:
        return items
    i, n = (int(x) for x in shard.split("/"))
    if not (n >= 1 and 0 <= i < n):
        raise SystemExit(f"bad --shard {shard!r}: want i/N with 0 <= i < N")
    return [x for k, x in enumerate(items) if k % n == i]


def failed_checks(checks: dict) -> list[str]:
    """Failed checks C1..C7 from {id: bool} (trial_record) or {id: {passed: bool}} (grader result)."""
    out = []
    for cid in (*PASS_CHECKS, "C7"):
        v = checks.get(cid)
        ok = v.get("passed") if isinstance(v, dict) else v
        if ok is False:
            out.append(cid)
    return out


def apply_diff(app_src: pathlib.Path, diff_path: pathlib.Path, work: pathlib.Path) -> None:
    shutil.copytree(app_src, work, ignore=shutil.ignore_patterns(*EXCLUDES))
    if diff_path.stat().st_size == 0:
        return
    env = {**os.environ, "GIT_AUTHOR_NAME": "regrade", "GIT_AUTHOR_EMAIL": "r@invalid",
           "GIT_COMMITTER_NAME": "regrade", "GIT_COMMITTER_EMAIL": "r@invalid"}  # fmt: skip
    subprocess.run(["git", "init", "-q"], cwd=work, check=True, env=env)
    r = subprocess.run(["git", "apply", "--binary", "--whitespace=nowarn", str(diff_path)], cwd=work,
                       capture_output=True, text=True, env=env)  # fmt: skip
    if r.returncode != 0:
        raise RuntimeError(f"git apply failed: {r.stderr.strip()[-400:]}")
    shutil.rmtree(work / ".git", ignore_errors=True)


def grader_env() -> dict:
    env = dict(os.environ)
    for k in list(env):
        if k.upper().startswith(("FLAGSMITH", "VITE_FLAGSMITH", "FS_", "ANTHROPIC", "GH_", "GITHUB_TOKEN")):
            del env[k]
    return env


def run_grader_once(work: pathlib.Path, stack: str, flag: str, out_json: pathlib.Path) -> dict:
    cmd = [
        sys.executable, "-m", "grader", "--app-dir", str(work), "--stack", stack, "--flag", flag,
        "--event", EVENT_NAME, "--variant-values", f"{CONTROL_VALUE},{VARIATION_VALUE}",
        "--out", str(out_json), "--mode", "proxy", "--reclaim-port",
    ]  # fmt: skip
    if out_json.exists():
        out_json.unlink()
    subprocess.run(cmd, cwd=REPO, env=grader_env(), capture_output=True, text=True, timeout=1500, check=False)
    if not out_json.is_file():
        raise RuntimeError("grader produced no result.json")
    return json.loads(out_json.read_text())


def regrade_trial(adir: pathlib.Path, apps: pathlib.Path, out_dir: pathlib.Path, confirm: int) -> dict:
    rec = json.loads((adir / "trial_record.json").read_text())
    orig = json.loads((adir / "grader_result.json").read_text())
    tid, stack, flag = rec["trial_id"], rec["stack"], rec["flag_name"]
    diff = (adir / "diff.patch").read_text(errors="replace")
    row = {
        "trial_id": tid, "variant": rec["variant"], "stack": stack, "flag": flag,
        "original_passed": bool(rec["passed"]), "original_failed_checks": failed_checks(rec.get("checks") or {}),
        "original_grader_sha": rec.get("grader_sha"), "runner_error": bool(rec.get("runner_error")),
        "original_mode": orig.get("mode"),
    }  # fmt: skip
    names = env_names_read(diff)
    values = placeholders_for(names, stack, flag)
    row["env_names_read"] = names
    row["env_placeholders_supplied"] = sorted(values)
    runs = []
    result = None
    for k in range(max(1, confirm)):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="regrade-"))
        try:
            work = tmp / "app"
            apply_diff(apps / stack, adir / "diff.patch", work)
            row["env_files_written"] = write_env_files(work, values)
            result = run_grader_once(work, stack, flag, tmp / "result.json")
        except Exception as e:  # noqa: BLE001
            row["regrade_error"] = f"{type(e).__name__}: {e}"
            shutil.rmtree(tmp, ignore_errors=True)
            break
        shutil.rmtree(tmp, ignore_errors=True)
        runs.append({"passed": bool(result.get("passed")), "failed_checks": failed_checks(result.get("checks") or {})})
        if runs[0]["passed"] == row["original_passed"]:
            break  # same verdict: no repeat needed
    if runs:
        row["regrade_passed"] = runs[0]["passed"]
        row["regrade_failed_checks"] = runs[0]["failed_checks"]
        row["regrade_runs"] = runs
        row["regrade_grader_version"] = result.get("grader_version")
        row["local_evaluation"] = "local_evaluation" in result
        row["button_text"] = result.get("button_text")
        row["failure_reasons"] = {c: v.get("reason") for c, v in (result.get("checks") or {}).items()
                                  if v.get("reason")}  # fmt: skip
        row["flipped"] = runs[0]["passed"] != row["original_passed"]
        row["flip_reproduced"] = (
            row["flipped"] and len(runs) >= confirm and all(r["passed"] == runs[0]["passed"] for r in runs)
        )
        row["checks_changed"] = sorted(set(row["original_failed_checks"]) ^ set(runs[0]["failed_checks"]))
    else:
        row["flipped"] = None
    (out_dir / f"{tid}.json").write_text(json.dumps(row, indent=1, sort_keys=True))
    return row


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--artifacts", nargs="+", required=True, type=pathlib.Path,
                    help="folders that contain trial-<run>-<index>/ artifact directories")  # fmt: skip
    ap.add_argument("--out", required=True, type=pathlib.Path)
    ap.add_argument("--shard", help="i/N: the i-th (0-based) of N shards of the sorted trial list")
    ap.add_argument("--only", nargs="*", help="regrade only these trial ids")
    ap.add_argument("--confirm", type=int, default=3, help="runs in total for a trial whose verdict differs (default 3)")
    ap.add_argument("--apps-dir", type=pathlib.Path, default=REPO / "apps")
    a = ap.parse_args(argv)
    dirs = sorted(
        (d for root in a.artifacts for d in root.iterdir() if (d / "diff.patch").is_file()), key=lambda d: d.name
    )
    if a.only:
        dirs = [d for d in dirs if d.name in set(a.only)]
    dirs = pick_shard(dirs, a.shard)
    a.out.mkdir(parents=True, exist_ok=True)
    print(f"regrading {len(dirs)} trial(s)", flush=True)
    for d in dirs:
        done = a.out / f"{d.name}.json"
        if done.is_file():
            continue
        row = regrade_trial(d, a.apps_dir, a.out, a.confirm)
        print(d.name, "orig", row["original_passed"], "regrade", row.get("regrade_passed"),
              "FLIP" if row.get("flipped") else "", row.get("regrade_error", ""), flush=True)  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
