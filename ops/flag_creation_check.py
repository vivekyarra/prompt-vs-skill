"""Read-only: list sandbox project features (names/ids only) to see what AdminApiCleaner would match.

usage: python ops/flag_creation_check.py
Sends only GET requests to the SANDBOX project (FS_SANDBOX_PROJECT_ID / FS_SANDBOX_ADMIN_KEY).
"""

import os

from fslib import Api, out

pid = os.environ.get("FS_SANDBOX_PROJECT_ID") or "56668"
api = Api(os.environ.get("FS_SANDBOX_ADMIN_KEY"))
code, data = api.call("GET", f"projects/{pid}/features/", quiet=True)
out("list status", code, "keys", sorted(data) if isinstance(data, dict) else type(data).__name__)
if isinstance(data, dict):
    out("count", data.get("count"), "next page:", bool(data.get("next")), "page size", len(data.get("results", [])))
feats = api.results(f"projects/{pid}/features/")
out("total features:", len(feats))
for f in feats:
    out("feature", f.get("id"), f.get("name"), f.get("type"), "created", f.get("created_date"))
# the exact query the cleaner issues, for a name that should not exist
code, data = api.call("GET", f"projects/{pid}/features/?search=join_button_does_not_exist_probe", quiet=True)
out("cleaner-style search for absent flag ->", code, "results:", len((data or {}).get("results", [])), "(cleaner returns not_found)")
if feats:
    n = feats[0]["name"]
    code, data = api.call("GET", f"projects/{pid}/features/?search={n}", quiet=True)
    out("cleaner-style search for existing name ->", code, "results:", [r.get("name") for r in (data or {}).get("results", [])])
