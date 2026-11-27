"""Scan trials.yml artifacts (last 5 runs) and data-branch files for the VALUES of secrets and key patterns.

Prints only file names and counts, never matched text. Needs GITHUB_TOKEN (see ops.yml) and the repo in
GITHUB_REPOSITORY. usage: python ops/scan_secrets.py
"""

import base64
import io
import os
import re
import zipfile

import requests
from fslib import out

API = "https://api.github.com"
REPO = os.environ.get("GITHUB_REPOSITORY", "vivekyarra/prompt-vs-skill")
H = {"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json"}
NAMES = ("FS_EXPERIMENT_SERVER_KEY", "FS_SANDBOX_CLIENT_KEY", "FS_SANDBOX_SERVER_KEY",
         "FS_SANDBOX_ADMIN_KEY", "FS_EXPERIMENT_ADMIN_KEY", "NEBIUS_API_KEY")  # fmt: skip
SECRETS = {n: os.environ[n] for n in NAMES if len(os.environ.get(n, "")) >= 8}
PATTERNS = {"ser.*": re.compile(r"ser\.[A-Za-z0-9]{20,}"), "sk-*": re.compile(r"sk-[A-Za-z0-9]{20,}")}
out("secrets present in env (names only):", sorted(SECRETS), "| missing:", sorted(set(NAMES) - set(SECRETS)))
# Env-key values are 'client keys' too: also try the Development client key forms of the project? (not available)


def scan(label: str, data: bytes) -> dict:
    t = data.decode("utf-8", "replace")
    hits = {n: t.count(v) for n, v in SECRETS.items() if v in t}
    hits.update({k: len(p.findall(t)) for k, p in PATTERNS.items() if p.search(t)})
    return hits


def is_text(b: bytes) -> bool:
    return b"\x00" not in b[:4096]


def get(url, **kw):
    r = requests.get(url, headers=H, timeout=120, **kw)
    return r


tot_files = tot_hits = 0
runs = get(f"{API}/repos/{REPO}/actions/workflows/trials.yml/runs", params={"per_page": 5, "status": "completed"}).json()
for run in runs.get("workflow_runs", []):
    arts = get(f"{API}/repos/{REPO}/actions/runs/{run['id']}/artifacts", params={"per_page": 100}).json()
    n_art = 0
    n_files = n_hit_files = 0
    for a in arts.get("artifacts", []):
        if a.get("expired"):
            continue
        r = get(a["archive_download_url"])
        if r.status_code != 200:
            out(f"run {run['id']} artifact download -> {r.status_code}")
            continue
        n_art += 1
        z = zipfile.ZipFile(io.BytesIO(r.content))
        for info in z.infolist():
            if info.is_dir():
                continue
            b = z.read(info)
            if not is_text(b):
                continue
            n_files += 1
            h = scan(info.filename, b)
            if h:
                n_hit_files += 1
                out(f"HIT run {run['id']} {a['name']}/{info.filename}: {h}")
    out(f"run {run['id']} ({run.get('conclusion')}): artifacts={n_art} text_files={n_files} files_with_hits={n_hit_files}")
    tot_files += n_files
    tot_hits += n_hit_files

for path in ("data/trials.jsonl", "data/pilot.jsonl"):
    r = get(f"{API}/repos/{REPO}/contents/{path}", params={"ref": "data"})
    if r.status_code != 200:
        out(f"{path} -> {r.status_code}")
        continue
    j = r.json()
    if j.get("content"):
        b = base64.b64decode(j["content"])
    else:  # >1MB: use the raw media type
        b = requests.get(f"{API}/repos/{REPO}/contents/{path}", params={"ref": "data"},
                         headers={**H, "Accept": "application/vnd.github.raw"}, timeout=120).content  # fmt: skip
    h = scan(path, b)
    out(f"data branch {path}: bytes={len(b)} lines={b.count(b'\n')} hits={h or 0}")
    tot_files += 1
    tot_hits += 1 if h else 0
out(f"TOTAL text files scanned={tot_files} files_with_hits={tot_hits}")
