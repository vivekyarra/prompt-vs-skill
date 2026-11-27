"""Per-stack install / test / start logic, app environment construction, process handling."""

from __future__ import annotations

import hashlib
import os
import pathlib
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

FAKE_TAG = "7f3a9c"
FAKE_CLIENT_KEY = f"GRADER_FAKE_CLIENT_KEY_{FAKE_TAG}"
FAKE_SERVER_KEY = f"ser.GRADER_FAKE_SERVER_KEY_{FAKE_TAG}"

DEFAULT_PORTS = {"react": 5173, "node": 3000, "python": 5000}
HEALTH_TIMEOUT_S = 120
COPY_IGNORE = shutil.ignore_patterns(
    "node_modules", "dist", "build", ".venv", "venv", "__pycache__", ".pytest_cache", ".git", ".mitmproxy"
)
# Environment names never forwarded to the app (real credentials / agent plumbing).
_STRIP_PREFIXES = ("FLAGSMITH", "VITE_FLAGSMITH", "FS_", "ANTHROPIC", "GITHUB_", "GH_", "AWS_", "CLOUDSDK")
_PROXY_NAMES = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE",
                "NODE_EXTRA_CA_CERTS", "CURL_CA_BUNDLE", "NODE_USE_ENV_PROXY")  # fmt: skip


class StepError(RuntimeError):
    pass


def clean_env(proxy_passthrough: bool) -> dict:
    """The ambient environment minus credentials. proxy_passthrough keeps the sandbox proxy/CA vars
    (needed for npm/pip downloads); the running app never gets them (see app_env)."""
    env = {}
    for k, v in os.environ.items():
        if k.upper().startswith(_STRIP_PREFIXES):
            continue
        if not proxy_passthrough and k.upper() in _PROXY_NAMES:
            continue
        env[k] = v
    return env


def app_env(
    flag: str, *, mode: str, mock_url: str | None, proxy_url: str | None = None, ca_path: str | None = None,
    port: int,
) -> dict:  # fmt: skip
    env = clean_env(proxy_passthrough=False)
    env.update(
        PORT=str(port),
        NO_PROXY="127.0.0.1,localhost",
        no_proxy="127.0.0.1,localhost",
        FLAGSMITH_CLIENT_KEY=FAKE_CLIENT_KEY,
        FLAGSMITH_SERVER_KEY=FAKE_SERVER_KEY,
        VITE_FLAGSMITH_CLIENT_KEY=FAKE_CLIENT_KEY,
        FLAGSMITH_FLAG=flag,
        VITE_FLAGSMITH_FLAG=flag,
    )
    if mode == "mock":
        # Design A: the app is pointed at the mock through the env var names the reference apps use.
        env.update(
            FLAGSMITH_API_URL=f"{mock_url}/api/v1/",
            FLAGSMITH_EVENTS_URL=f"{mock_url}/",
            VITE_FLAGSMITH_API=f"{mock_url}/api/v1/",
            VITE_FLAGSMITH_EVENTS_API=f"{mock_url}/",
        )
    else:
        # Design B: the app keeps its default (real) hosts; an HTTPS MITM proxy answers them.
        assert proxy_url and ca_path
        for k in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
            env[k] = proxy_url
        for k in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "NODE_EXTRA_CA_CERTS", "CURL_CA_BUNDLE"):
            env[k] = ca_path
        env["NODE_USE_ENV_PROXY"] = "1"  # Node >= 22.21: honour HTTP(S)_PROXY in fetch/undici
    return env


def run(cmd, cwd, env, timeout, log: pathlib.Path | None = None) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout, check=False)
    if log is not None:
        log.write_text((proc.stdout or "") + "\n--- stderr ---\n" + (proc.stderr or ""))
    return proc


def tail(text: str, n: int = 400) -> str:
    text = " ".join((text or "").split())
    return text[-n:]


# ---- workdir + dependency install (cached by lockfile hash) ---------------------------------------
def cache_root() -> pathlib.Path:
    return pathlib.Path(os.environ.get("GRADER_CACHE_DIR") or pathlib.Path.home() / ".cache" / "handoff-grader")


def _digest(app: pathlib.Path, names: tuple[str, ...]) -> str:
    h = hashlib.sha256()
    for n in names:
        p = app / n
        h.update(n.encode())
        h.update(p.read_bytes() if p.is_file() else b"-")
    return h.hexdigest()[:20]


def prepare_workdir(app_dir: pathlib.Path) -> pathlib.Path:
    work = pathlib.Path(tempfile.mkdtemp(prefix="grader-app-")) / "app"
    shutil.copytree(app_dir, work, ignore=COPY_IGNORE)
    return work


def install(stack: str, work: pathlib.Path, timeout: int = 900) -> dict:
    """Install dependencies in `work`. Returns {"python": <venv python>} for the python stack."""
    env = clean_env(proxy_passthrough=True)
    use_cache = not os.environ.get("GRADER_NO_CACHE")
    if stack in ("react", "node"):
        if not (work / "package.json").is_file():
            raise StepError("no package.json in app dir")
        key = _digest(work, ("package.json", "package-lock.json"))
        cached = cache_root() / "node" / key / "node_modules"
        if use_cache and cached.is_dir():
            (work / "node_modules").symlink_to(cached, target_is_directory=True)
            return {}
        cmd = ["npm", "ci", "--no-audit", "--no-fund"] if (work / "package-lock.json").is_file() else [
            "npm", "install", "--no-audit", "--no-fund"]  # fmt: skip
        proc = run(cmd, work, env, timeout)
        if proc.returncode != 0:
            raise StepError(f"npm install failed: {tail(proc.stderr or proc.stdout)}")
        if use_cache:
            cached.parent.mkdir(parents=True, exist_ok=True)
            tmp = cached.parent / f"tmp-{os.getpid()}"
            shutil.move(str(work / "node_modules"), tmp)
            try:
                tmp.rename(cached)
            except OSError:  # another process won the race
                shutil.rmtree(tmp, ignore_errors=True)
            (work / "node_modules").symlink_to(cached, target_is_directory=True)
        return {}
    # python
    key = _digest(work, ("requirements.txt",))
    venv = (cache_root() / "python" / key / "venv") if use_cache else (work.parent / "venv")
    py = venv / "bin" / "python"
    if not py.is_file():
        venv.parent.mkdir(parents=True, exist_ok=True)
        tmp = venv.parent / f"tmp-{os.getpid()}"
        proc = run([sys.executable, "-m", "venv", str(tmp)], work, env, 300)
        if proc.returncode != 0:
            raise StepError(f"venv creation failed: {tail(proc.stderr)}")
        req = work / "requirements.txt"
        if req.is_file():
            proc = run([str(tmp / "bin" / "python"), "-m", "pip", "install", "-q", "-r", "requirements.txt"],
                       work, env, timeout)  # fmt: skip
            if proc.returncode != 0:
                shutil.rmtree(tmp, ignore_errors=True)
                raise StepError(f"pip install failed: {tail(proc.stderr or proc.stdout)}")
        if use_cache:
            try:
                # venvs embed their absolute path, so move only when we are the one creating `venv`.
                shutil.rmtree(venv, ignore_errors=True)
                tmp.rename(venv)
            except OSError as e:
                raise StepError(f"venv cache failure: {e}") from e
        else:
            tmp.rename(venv)
    return {"python": str(py)}


# NOTE: a venv that was created at `tmp` and renamed has stale absolute paths in its scripts, but
# `bin/python -m <module>` (all we use) does not depend on them.


def app_tests(stack: str, work: pathlib.Path, info: dict, timeout: int = 600,
              flag: str = "grader_test_flag") -> tuple[bool, str]:  # fmt: skip
    """Run the app's existing test in the clean env. One-directional fallback: only if that run FAILS,
    re-run once with the same fake credential variables the app gets at runtime (an app that reads its
    key from the environment at import time must not fail C1 for that alone). An earlier pass is never
    turned into a fail."""
    clean = clean_env(proxy_passthrough=False)
    ok, reason = _run_app_test(stack, work, info, clean, timeout)
    if ok:
        return True, reason
    keyed = dict(clean)
    keyed.update(
        FLAGSMITH_CLIENT_KEY=FAKE_CLIENT_KEY, FLAGSMITH_SERVER_KEY=FAKE_SERVER_KEY,
        VITE_FLAGSMITH_CLIENT_KEY=FAKE_CLIENT_KEY, FLAGSMITH_FLAG=flag, VITE_FLAGSMITH_FLAG=flag,
    )  # fmt: skip
    ok2, _ = _run_app_test(stack, work, info, keyed, timeout)
    if ok2:
        return True, "existing test passed only with credential variables set"
    return False, reason


def _run_app_test(stack: str, work: pathlib.Path, info: dict, env: dict, timeout: int) -> tuple[bool, str]:
    if stack == "python":
        cmd = [info["python"], "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    else:
        cmd = ["npm", "test", "--silent"]
    try:
        proc = run(cmd, work, env, timeout)
    except subprocess.TimeoutExpired:
        return False, f"existing test timed out after {timeout}s"
    if proc.returncode == 0:
        return True, "existing test passed"
    out = tail((proc.stdout or "") + " " + (proc.stderr or ""))
    if stack == "python" and proc.returncode == 5:
        return False, "existing test failed: pytest collected no tests"
    return False, f"existing test failed (exit {proc.returncode}): {out}"


# ---- running the app -------------------------------------------------------------------------------
def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def reclaim_port(port: int, wait_s: float = 8.0) -> list[int]:
    """Kill processes LISTENing on `port` (e.g. a dev server the agent left running) and wait for it to
    free up. Linux only (/proc). Returns the killed pids. Opt-in via the grader's --reclaim-port flag."""
    import os
    import signal
    import time

    inodes = set()
    for name in ("tcp", "tcp6"):
        try:
            with open(f"/proc/net/{name}") as fh:
                next(fh)
                for line in fh:
                    f = line.split()
                    if f[3] == "0A" and int(f[1].rsplit(":", 1)[1], 16) == port:
                        inodes.add(f[9])
        except OSError:
            continue
    killed = []
    if inodes:
        for pid in filter(str.isdigit, os.listdir("/proc")):
            try:
                for fd in os.listdir(f"/proc/{pid}/fd"):
                    link = os.readlink(f"/proc/{pid}/fd/{fd}")
                    if link.startswith("socket:[") and link[8:-1] in inodes and int(pid) != os.getpid():
                        os.kill(int(pid), signal.SIGKILL)
                        killed.append(int(pid))
                        break
            except OSError:
                continue
    deadline = time.time() + wait_s
    while port_open(port) and time.time() < deadline:
        time.sleep(0.2)
    return killed


class App:
    def __init__(self, stack: str, work: pathlib.Path, info: dict, env: dict, port: int):
        self.stack, self.work, self.port = stack, work, port
        self.log_path = work.parent / "app.log"
        cmd = [info["python"], "app.py"] if stack == "python" else ["npm", "start"]
        self._log = open(self.log_path, "w")
        self.proc = subprocess.Popen(
            cmd, cwd=work, env=env, stdout=self._log, stderr=subprocess.STDOUT, start_new_session=True
        )  # fmt: skip

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def wait_healthy(self, timeout: float = HEALTH_TIMEOUT_S) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise StepError(f"app exited with code {self.proc.returncode}: {self.log_tail()}")
            try:
                with urllib.request.urlopen(self.url, timeout=3) as r:  # noqa: S310 (loopback)
                    if r.status < 500:
                        return
            except Exception:
                pass
            time.sleep(0.5)
        raise StepError(f"app not healthy on port {self.port} within {timeout:.0f}s: {self.log_tail()}")

    def log_tail(self) -> str:
        try:
            self._log.flush()
            return tail(self.log_path.read_text(errors="replace"))
        except OSError:
            return ""

    def stop(self) -> None:
        if self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
                self.proc.wait(timeout=10)
            except Exception:
                try:
                    os.killpg(self.proc.pid, signal.SIGKILL)
                except Exception:
                    pass
        self._log.close()


class MitmProxy:
    """mitmdump with the grader addon; answers *.flagsmith.com from the mock."""

    def __init__(self, mock_port: int, confdir: pathlib.Path):
        exe = pathlib.Path(sys.executable).parent / "mitmdump"
        exe_s = str(exe) if exe.is_file() else shutil.which("mitmdump")
        if not exe_s:
            raise StepError("mitmdump not found: install mitmproxy (pip install mitmproxy) or use --mode mock")
        self.port = free_port()
        self.confdir = confdir
        addon = pathlib.Path(__file__).with_name("mitm_addon.py")
        env = clean_env(proxy_passthrough=False)
        self._log = open(confdir.parent / "mitm.log", "w")
        self.proc = subprocess.Popen(
            [exe_s, "-q", "-p", str(self.port), "--listen-host", "127.0.0.1", "--set", f"confdir={confdir}",
             "--set", "connection_strategy=lazy", "-s", str(addon), "--set", f"grader_mock_port={mock_port}"],
            env=env, stdout=self._log, stderr=subprocess.STDOUT, start_new_session=True,
        )  # fmt: skip
        self.ca_path = str(confdir / "mitmproxy-ca-cert.pem")
        deadline = time.time() + 30
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise StepError("mitmdump exited during startup")
            if port_open(self.port) and pathlib.Path(self.ca_path).is_file():
                return
            time.sleep(0.2)
        raise StepError("mitmdump did not start within 30s")

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def stop(self) -> None:
        try:
            os.killpg(self.proc.pid, signal.SIGTERM)
            self.proc.wait(timeout=10)
        except Exception:
            pass
        self._log.close()
