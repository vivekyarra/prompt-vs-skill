"""Mock vs real Flagsmith agreement check (exploratory; declared in EXPERIMENT.md before it ran). SANDBOX ONLY.

Regrades the trials in data/mock_vs_real_selection.json against the REAL Flagsmith (sandbox project) instead of the
grader's local emulator. Everything else is the offline regrade (docs/regrade.md): same app copy, same diff, same
env-name placeholder rule (keys get the real sandbox keys instead of placeholders), same stacks, same browser
visitors, same waits, and the frozen `grader/checks.py` decides C1-C7. `grader/` is not changed.

Per trial, in the sandbox project only: the trial's flag (same name, the app code hard-codes it) with control `Join`
and option `Join free`, and a running experiment "MVR <trial id>" on it (50/50), so that the SDK experiment methods
see `in_experiment` and send `$flag_exposure`, as the emulator always pretended.

usage (through ops.yml, environment development):
    mock_vs_real_regrade.py run --shard i/N [--only trial-...,trial-...]   setup, grade, print MVR_RESULT lines
    mock_vs_real_regrade.py counts                                          read each MVR experiment's counts
    mock_vs_real_regrade.py cleanup                                         complete MVR experiments, delete their flags

Refuses to run unless the sandbox environment belongs to FS_SANDBOX_PROJECT_ID and that is not the experiment project.
Never touches the experiment project, its flags, experiments or events. Prints no secret values.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
sys.path[:0] = [str(HERE), str(REPO)]

from fslib import Api, out, register_secret, scrub_exact  # noqa: E402

EXPERIMENT_PROJECT_IDS = {"56666", os.environ.get("FS_EXPERIMENT_PROJECT_ID") or "56666"}
EXP_PREFIX = "MVR "
METRIC = "join_clicked"
CONTROL, VARIATION = "Join", "Join free"
DEADLINE_S = 24 * 60  # ops.yml kills the job at 30 min; stop starting trials after this
T0 = time.time()


def emit(tag: str, obj) -> None:
    print(f"{tag} " + scrub_exact(json.dumps(obj, sort_keys=True, default=str)), flush=True)


# ---- safety + connection -------------------------------------------------------------------------------------
def sandbox():
    for n in ("FS_SANDBOX_ADMIN_KEY", "FS_SANDBOX_CLIENT_KEY", "FS_SANDBOX_SERVER_KEY", "FS_SANDBOX_PROJECT_ID"):
        if not os.environ.get(n):
            sys.exit(f"{n} not set")
        register_secret(os.environ[n] if n != "FS_SANDBOX_PROJECT_ID" else None)
    register_secret(os.environ.get("GITHUB_TOKEN"))
    pid = str(os.environ["FS_SANDBOX_PROJECT_ID"])
    if pid in EXPERIMENT_PROJECT_IDS:
        sys.exit("FS_SANDBOX_PROJECT_ID is the experiment project; refusing")
    api = Api(os.environ["FS_SANDBOX_ADMIN_KEY"])
    ck = os.environ["FS_SANDBOX_CLIENT_KEY"]
    code, env = api.call("GET", f"environments/{ck}/", quiet=True)
    if code != 200 or str((env or {}).get("project")) != pid:
        sys.exit(f"sandbox client key does not belong to sandbox project (GET -> {code}); refusing")
    out(f"sandbox project {pid}, environment {env.get('id')} ({env.get('name')})")
    return api, pid, f"environments/{ck}"


def find_feature(api, pid, name):
    fs = [f for f in api.results(f"projects/{pid}/features/?search={name}") if f["name"] == name]
    return fs[0] if fs else None


def metric_id(api, E) -> int:
    ms = sorted((m for m in api.results(f"{E}/experiment-metrics/") if m.get("name") == METRIC), key=lambda m: m["id"])
    if ms:
        return ms[0]["id"]
    code, m = api.call("POST", f"{E}/experiment-metrics/", {
        "name": METRIC, "aggregation": "occurrence", "direction": "up", "definition": {"version": 1, "event": METRIC}})  # fmt: skip
    if code >= 300:
        sys.exit("could not create metric")
    return m["id"]


def setup_flag(api, pid, E, flag: str, trial_id: str, mid: int) -> dict:
    """Flag with control Join and option Join free, plus a running experiment 'MVR <trial>' on it."""
    f = find_feature(api, pid, flag)
    if not f:
        code, f = api.call("POST", f"projects/{pid}/features/",
                           {"name": flag, "type": "MULTIVARIATE", "initial_value": CONTROL, "default_enabled": True})  # fmt: skip
        if code >= 300:
            return {"error": f"flag create -> {code}"}
    fid = f["id"]
    opts = api.results(f"projects/{pid}/features/{fid}/mv-options/")
    opt = next((o for o in opts if o.get("string_value") == VARIATION), None)
    if not opt:
        code, opt = api.call("POST", f"projects/{pid}/features/{fid}/mv-options/", {
            "type": "unicode", "string_value": VARIATION, "key": "join_free", "default_percentage_allocation": 0,
            "feature": fid})  # fmt: skip
        if code >= 300:
            return {"error": f"mv option create -> {code}"}
    name = EXP_PREFIX + trial_id
    exp = next((x for x in api.results(f"{E}/experiments/") if x.get("name") == name), None)
    if not exp:
        code, exp = api.call("POST", f"{E}/experiments/", {
            "feature": fid, "name": name,
            "hypothesis": "Exploratory mock-vs-real grader agreement check (not a product experiment).",
            "metrics": [{"metric": mid, "expected_direction": "increase"}],
            "experiment_rollout": {
                "enabled": True, "rollout_percentage": 100,
                "feature_state_value": {"type": "string", "value": CONTROL},
                "multivariate_feature_state_values": [{"multivariate_feature_option": opt["id"], "percentage_allocation": 50}],
            },
        })  # fmt: skip
        if code >= 300:
            return {"error": f"experiment create -> {code}"}
    if exp.get("status") != "running":
        code, _ = api.call("POST", f"{E}/experiments/{exp['id']}/start/")
        if code >= 300:
            return {"error": f"experiment start -> {code}"}
    return {"feature_id": fid, "experiment_id": exp["id"]}


def in_experiment(flag: str) -> bool:
    from flagsmith import Flagsmith

    fs = Flagsmith(environment_key=os.environ["FS_SANDBOX_SERVER_KEY"])
    try:
        f = fs.get_identity_flags(f"mvr-probe-{flag}", {}).get_flag(flag)
        exp = getattr(f, "experiment", None)
        return bool(exp and exp.in_experiment)
    except Exception:  # noqa: BLE001
        return False
    finally:
        try:
            fs.close()
        except Exception:  # noqa: BLE001
            pass


def remote_value_lookup(flag: str):
    """Value the REAL service evaluates for an identity (used by C6 only when the app downloaded the environment
    document and evaluated locally, where no flags response exists to read the value from)."""
    from flagsmith import Flagsmith

    fs = Flagsmith(environment_key=os.environ["FS_SANDBOX_SERVER_KEY"])
    cache: dict = {}

    def lookup(identity):
        if identity not in cache:
            try:
                cache[identity] = fs.get_identity_flags(identity, {}).get_flag(flag).value
            except Exception:  # noqa: BLE001
                cache[identity] = None
        return cache[identity]

    return lookup


# ---- toolchain -----------------------------------------------------------------------------------------------
def sh(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        out("command failed:", " ".join(map(str, cmd))[:200], (r.stdout + r.stderr)[-1500:])
        sys.exit(1)
    return r.stdout


def node_ok() -> bool:
    try:
        v = subprocess.run(["node", "-v"], capture_output=True, text=True).stdout.strip().lstrip("v")
        major, minor = (int(x) for x in v.split(".")[:2])
        return major == 22 and minor >= 21  # the trials and the emulator baseline ran Node 22
    except Exception:  # noqa: BLE001
        return False


def bootstrap() -> None:
    t = time.time()
    sh([sys.executable, "-m", "pip", "install", "-q", "playwright==1.63.0", "mitmproxy", "flask", "pyyaml", "pytest"])
    sh([sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"])
    if not node_ok():
        base = "https://nodejs.org/dist/latest-v22.x/"
        sums = urllib.request.urlopen(base + "SHASUMS256.txt", timeout=60).read().decode()  # noqa: S310
        sha, name = next((ln.split() for ln in sums.splitlines() if ln.endswith("-linux-x64.tar.xz")))
        blob = urllib.request.urlopen(base + name, timeout=300).read()  # noqa: S310
        if hashlib.sha256(blob).hexdigest() != sha:
            sys.exit("node tarball checksum mismatch")
        dest = pathlib.Path.home() / "node22"
        dest.mkdir(exist_ok=True)
        tar = dest / name
        tar.write_bytes(blob)
        sh(["tar", "-xJf", str(tar), "-C", str(dest), "--strip-components=1"])
        os.environ["PATH"] = f"{dest / 'bin'}:{os.environ['PATH']}"
    out("toolchain ready in", round(time.time() - t), "s; node", sh(["node", "-v"]).strip())


# ---- artifacts -----------------------------------------------------------------------------------------------
def gh(path: str) -> bytes:
    """GitHub API GET. requests drops the Authorization header when the artifact zip redirects to blob storage
    (urllib forwards it, and the storage host answers 401)."""
    import requests

    r = requests.get(f"https://api.github.com/{path}", timeout=300, headers={
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json"})  # fmt: skip
    r.raise_for_status()
    return r.content


def download_artifact(trial_id: str, dest: pathlib.Path) -> pathlib.Path:
    run_id = trial_id.split("-")[1]
    repo = os.environ["GITHUB_REPOSITORY"]
    arts = json.loads(gh(f"repos/{repo}/actions/runs/{run_id}/artifacts?name={trial_id}&per_page=10"))["artifacts"]
    arts = [a for a in arts if a["name"] == trial_id and not a.get("expired")]
    if not arts:
        raise RuntimeError(f"artifact {trial_id} not found or expired")
    blob = gh(f"repos/{repo}/actions/artifacts/{arts[0]['id']}/zip")
    d = dest / trial_id
    d.mkdir(parents=True, exist_ok=True)
    zipfile.ZipFile(io.BytesIO(blob)).extractall(d)
    return d


# ---- grading -------------------------------------------------------------------------------------------------
class PassMitm:
    def __init__(self, recorder_port: int, confdir: pathlib.Path):
        from grader import stacks

        exe = pathlib.Path(sys.executable).parent / "mitmdump"
        exe_s = str(exe) if exe.is_file() else shutil.which("mitmdump")
        self.port = stacks.free_port()
        self._log = open(confdir.parent / "mitm.log", "w")
        self.proc = subprocess.Popen(
            [exe_s, "-q", "-p", str(self.port), "--listen-host", "127.0.0.1", "--set", f"confdir={confdir}",
             "--set", "connection_strategy=lazy", "-s", str(HERE / "mvr_mitm_addon.py"),
             "--set", f"mvr_recorder_port={recorder_port}"],
            env=stacks.clean_env(proxy_passthrough=False), stdout=self._log, stderr=subprocess.STDOUT,
            start_new_session=True,
        )  # fmt: skip
        self.ca_path = str(confdir / "mitmproxy-ca-cert.pem")
        deadline = time.time() + 30
        while time.time() < deadline:
            if stacks.port_open(self.port) and pathlib.Path(self.ca_path).is_file():
                return
            time.sleep(0.2)
        raise stacks.StepError("mitmdump did not start within 30s")

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def stop(self) -> None:
        import signal

        try:
            os.killpg(self.proc.pid, signal.SIGTERM)
            self.proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            pass
        self._log.close()


MAX_EXTRA_VISITORS = 8


def _grade_real(work: pathlib.Path, stack: str, flag: str) -> dict:
    """grader/cli.py `grade` in proxy mode, with the Recorder + pass-through proxy in place of the emulator."""
    from grader import checks as chk
    from grader import stacks
    from runner.config import EVENT_NAME
    from scripts.mvr_lib import Recorder

    values = [CONTROL, VARIATION]
    port = stacks.DEFAULT_PORTS[stack]
    ck, sk = os.environ["FS_SANDBOX_CLIENT_KEY"], os.environ["FS_SANDBOX_SERVER_KEY"]
    rec = Recorder(flag)
    rec.start()
    lookup = remote_value_lookup(flag)
    c1: dict = {"error": None, "tests_ok": False, "tests_reason": ""}
    browser_out = None
    mitm = app = None
    wd = stacks.prepare_workdir(work, stack)
    try:
        try:
            info = stacks.install(stack, wd)
            c1["tests_ok"], c1["tests_reason"] = stacks.app_tests(stack, wd, info, flag=flag)
            if stacks.port_open(port):
                stacks.reclaim_port(port)
            mitm = PassMitm(rec.port, wd.parent / "mitm")
            env = stacks.app_env(flag, mode="proxy", emulator_url=None, proxy_url=mitm.url, ca_path=mitm.ca_path,
                                 port=port)  # fmt: skip
            env.update(FLAGSMITH_CLIENT_KEY=ck, FLAGSMITH_SERVER_KEY=sk, VITE_FLAGSMITH_CLIENT_KEY=ck)
            app = stacks.App(stack, wd, info, env, port)
            app.wait_healthy(stacks.HEALTH_TIMEOUT_S)
            from grader import browser

            browser_out = browser.run_visitors(app.url, rec.url, mitm.url, 13.0, 13.0)
            # Real Flagsmith buckets every identity by hash (remote AND local evaluation), so V1 and V2 can get the
            # same value; then a hard-coded text could pass C6 by chance. Same remedy as grader/cli.py applies under
            # local evaluation: fresh visitors until one identity's expected value differs from V1's.
            local = any(r["kind"] == "environment" for r in rec.records)
            starts = rec.phase_starts if local else None

            def expected(phase):
                ident = chk.phase_identity(rec.records, phase, flag, starts)
                return chk.expected_value(rec.records, phase, ident, lookup) if ident else None

            e1 = expected("load")
            extras = []
            if e1 is not None and expected("v2") == e1:
                for i in range(3, 3 + MAX_EXTRA_VISITORS):
                    phase = f"v{i}"
                    text = browser.run_extra_visitor(app.url, rec.url, mitm.url, 13.0, phase)
                    extras.append({"phase": phase, "text": text})
                    ev = expected(phase)
                    if ev is not None and ev != e1:
                        break
            if extras:
                browser_out["extra_visitors"] = extras
        except stacks.StepError as e:
            c1["error"] = str(e)
            browser_out = None
        results = chk.evaluate(
            records=rec.records, flag=flag, event_name=EVENT_NAME, variant_values=values, mode="proxy", c1=c1,
            browser=browser_out, server_key=sk, local_value=lookup, phase_starts=rec.phase_starts, button_label="Join",
        )  # fmt: skip
    finally:
        if app:
            app.stop()
        if mitm:
            mitm.stop()
        rec.stop()
        shutil.rmtree(wd.parent, ignore_errors=True)
    recs = rec.records
    local = any(r["kind"] == "environment" for r in recs)
    starts = rec.phase_starts if local else None
    idents = {p: chk.phase_identity(recs, p, flag, starts) for p in ("load", "reload", "v2")}
    return {
        "passed": chk.passed(results),
        "failed_checks": [c for c in chk.ALL_CHECKS if not results[c]["passed"]],
        "reasons": {c: v["reason"] for c, v in results.items() if v.get("reason")},
        "local_evaluation": local,
        "identities": idents,
        "button_text": {"v1": (browser_out or {}).get("v1_text"), "v2": (browser_out or {}).get("v2_text"),
                        "extra": [x["text"] for x in (browser_out or {}).get("extra_visitors") or []]},  # fmt: skip
        "request_counts": chk.request_counts(recs),
        "http_status": sorted({f"{r['kind']}:{r.get('status')}" for r in recs}),
        "events": [{"phase": r["phase"], **{k: e.get(k) for k in ("event", "feature_name", "identifier")}}
                   for r in recs if r["kind"] == "events" for e in r["events"]],  # fmt: skip
    }


def regrade_one(trial: dict, art_root: pathlib.Path, setup: dict) -> dict:
    from scripts.regrade_diffs import apply_diff, env_names_read, placeholders_for, write_env_files

    tid, stack, flag = trial["trial_id"], trial["stack"], trial["flag_name"]
    row = {"trial_id": tid, "stack": stack, "variant": trial["variant"], "stage": trial["stage"],
           "experiment_id": setup.get("experiment_id")}  # fmt: skip
    try:
        adir = download_artifact(tid, art_root)
    except Exception as e:  # noqa: BLE001
        return {**row, "passed": None, "error": f"artifact download: {type(e).__name__}: {str(e)[:200]}"}
    dp = adir / "diff.patch"
    if not dp.is_file():
        return {**row, "passed": None, "error": "no diff.patch"}
    diff = dp.read_text(errors="replace")
    names = env_names_read(diff)
    values = placeholders_for(names, stack, flag)
    # Real keys where the offline regrade wrote placeholders (same names, same rule).
    real = {"ser.": os.environ["FS_SANDBOX_SERVER_KEY"], "client": os.environ["FS_SANDBOX_CLIENT_KEY"]}
    values = {k: (real["ser."] if v.startswith("ser.") else real["client"]) if "PLACEHOLDER" in v else v
              for k, v in values.items()}  # fmt: skip
    row["env_names_supplied"] = sorted(values)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="mvr-"))
    try:
        work = tmp / "app"
        apply_diff(REPO / "apps" / stack, dp, work)
        write_env_files(work, values)
        t = time.time()
        row.update(_grade_real(work, stack, flag))
        row["grade_s"] = round(time.time() - t, 1)
    except Exception as e:  # noqa: BLE001
        row.update(passed=None, error=f"{type(e).__name__}: {str(e)[:300]}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return row


def load_selection() -> list[dict]:
    sel = json.loads((REPO / "data/mock_vs_real_selection.json").read_text())
    return sorted(sel["failing"] + sel["passing_sample"], key=lambda x: x["trial_id"])


def cmd_run(args: list[str]) -> int:
    shard = next((a.split("=", 1)[1] for a in args if a.startswith("--shard=")), None)
    only = next((a.split("=", 1)[1].split(",") for a in args if a.startswith("--only=")), None)
    trials = load_selection()
    if only:
        trials = [t for t in trials if t["trial_id"] in set(only)]
    if shard:
        i, n = (int(x) for x in shard.split("/"))
        trials = [t for k, t in enumerate(trials) if k % n == i]
    trials = [t for t in trials if t.get("diff_bytes")]  # no diff: not replayable (listed in the report)
    api, pid, E = sandbox()
    out("trials this run:", [t["trial_id"] for t in trials])
    bootstrap()
    mid = metric_id(api, E)
    setups = {t["trial_id"]: setup_flag(api, pid, E, t["flag_name"], t["trial_id"], mid) for t in trials}
    for tid, s in setups.items():
        out("setup", tid, json.dumps(s))
    pending = {t["flag_name"] for t in trials if "error" not in setups[t["trial_id"]]}
    for attempt in range(1, 19):  # experiment state takes a while to reach the edge API
        pending = {f for f in pending if not in_experiment(f)}
        out(f"propagation probe {attempt}: {len(pending)} flag(s) not yet in_experiment")
        if not pending:
            break
        time.sleep(20)
    art = pathlib.Path(tempfile.mkdtemp(prefix="mvr-art-"))
    for t in trials:
        s = setups[t["trial_id"]]
        if "error" in s or t["flag_name"] in pending:
            emit("MVR_RESULT", {"trial_id": t["trial_id"], "passed": None,
                                "error": s.get("error") or "flag never reported in_experiment"})  # fmt: skip
            continue
        if time.time() - T0 > DEADLINE_S:
            emit("MVR_SKIPPED", {"trial_id": t["trial_id"], "why": "job deadline"})
            continue
        emit("MVR_RESULT", regrade_one(t, art, s))
    return 0


def mvr_experiments(api, E):
    return [x for x in api.results(f"{E}/experiments/") if str(x.get("name", "")).startswith(EXP_PREFIX)]


def cmd_counts(_args) -> int:
    from rolllib import refresh_fresh

    api, _pid, E = sandbox()
    for x in mvr_experiments(api, E):
        r, fresh = refresh_fresh(api, E, x["id"], out, max_wait_s=120)
        p = (((r or {}).get("results") or {}).get("payload")) or {}
        exp_ids = sum(sum((pt.get("new_identities") or {}).values())
                      for pt in (p.get("exposures_timeseries") or {}).get("points", []))  # fmt: skip
        emit("MVR_COUNTS", {"experiment": x["name"], "id": x["id"], "status": x.get("status"), "fresh": fresh,
                            "exposure_identities": exp_ids, "metrics": p.get("metrics")})  # fmt: skip
    return 0


def cmd_cleanup(_args) -> int:
    api, pid, E = sandbox()
    for x in mvr_experiments(api, E):
        if x.get("status") == "running":
            api.call("POST", f"{E}/experiments/{x['id']}/complete/", {"rollout_decision": "control"})
        fid = x["feature"]["id"] if isinstance(x.get("feature"), dict) else x.get("feature")
        flags = [f for f in api.results(f"projects/{pid}/features/") if f["id"] == fid]
        name = flags[0]["name"] if flags else None
        if name and re.fullmatch(r"join_button_trial_\d+_\d+", name):
            code, _ = api.call("DELETE", f"projects/{pid}/features/{fid}/", quiet=True)
            out("delete flag", name, "->", code)
    return 0


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("run", "counts", "cleanup"):
        sys.exit(__doc__)
    return {"run": cmd_run, "counts": cmd_counts, "cleanup": cmd_cleanup}[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    sys.exit(main())
