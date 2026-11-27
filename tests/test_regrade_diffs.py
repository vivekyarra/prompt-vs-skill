"""Unit tests for scripts/regrade_diffs.py (no grader run, no network)."""

import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("regrade_diffs", ROOT / "scripts" / "regrade_diffs.py")
rg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rg)

DIFF = """diff --git a/src/App.jsx b/src/App.jsx
--- a/src/App.jsx
+++ b/src/App.jsx
@@ -1,3 +1,9 @@
+const k = import.meta.env.VITE_FLAGSMITH_ENVIRONMENT_KEY
+const id = import.meta.env['VITE_FLAGSMITH_ENVIRONMENT_ID']
+const url = process.env.FLAGSMITH_API_URL
+const s = process.env.FLAGSMITH_SERVER_KEY
+key = os.environ["FLAGSMITH_CLIENT_KEY"] or os.getenv('FLAGSMITH_ENVIRONMENT_KEY') or os.environ.get("FLAGSMITH_FLAG_NAME")
-const gone = process.env.REMOVED_VAR
 context line process.env.NOT_ADDED
"""


def test_env_names_read_only_from_added_lines():
    names = rg.env_names_read(DIFF)
    assert "REMOVED_VAR" not in names and "NOT_ADDED" not in names
    assert {"VITE_FLAGSMITH_ENVIRONMENT_KEY", "VITE_FLAGSMITH_ENVIRONMENT_ID", "FLAGSMITH_API_URL", "FLAGSMITH_SERVER_KEY",
            "FLAGSMITH_CLIENT_KEY", "FLAGSMITH_ENVIRONMENT_KEY", "FLAGSMITH_FLAG_NAME"} <= set(names)  # fmt: skip


def test_placeholders_skip_grader_supplied_urls_and_flags_get_the_trial_flag():
    names = rg.env_names_read(DIFF)
    vals = rg.placeholders_for(names, "react", "join_button_trial_1_2")
    assert "FLAGSMITH_SERVER_KEY" not in vals and "FLAGSMITH_CLIENT_KEY" not in vals  # the grader supplies them
    assert "FLAGSMITH_API_URL" not in vals  # URLs are never supplied: the app's own default applies
    assert vals["VITE_FLAGSMITH_ENVIRONMENT_KEY"].startswith("GRADER_PLACEHOLDER_CLIENT_KEY")
    assert vals["VITE_FLAGSMITH_ENVIRONMENT_ID"].startswith("GRADER_PLACEHOLDER_CLIENT_KEY")
    assert vals["FLAGSMITH_FLAG_NAME"] == "join_button_trial_1_2"
    server = rg.placeholders_for(["FLAGSMITH_ENVIRONMENT_KEY", "FLAGSMITH_DISABLED", "FLAGSMITH_DEBUG"], "node", "f")
    assert server == {"FLAGSMITH_ENVIRONMENT_KEY": rg.PLACEHOLDER_SERVER_KEY}


def test_write_env_files_keeps_existing_values(tmp_path):
    (tmp_path / ".env").write_text("A=1\nVITE_X_KEY=real")
    written = rg.write_env_files(tmp_path, {"VITE_X_KEY": "placeholder", "B_KEY": "p"})
    assert written == [".env", ".env.local"]
    assert (tmp_path / ".env").read_text() == "A=1\nVITE_X_KEY=real\nB_KEY=p\n"
    assert (tmp_path / ".env.local").read_text() == "VITE_X_KEY=placeholder\nB_KEY=p\n"
    assert rg.write_env_files(tmp_path / "none", {}) == []


def test_shards_partition_the_sorted_list():
    items = list(range(440))
    parts = [rg.pick_shard(items, f"{i}/20") for i in range(20)]
    assert sorted(x for p in parts for x in p) == items and all(len(p) == 22 for p in parts)
    assert rg.pick_shard(items, None) == items


def test_failed_checks_reads_both_shapes():
    assert rg.failed_checks({"C1": True, "C2": False, "C7": False}) == ["C2", "C7"]
    assert rg.failed_checks({"C1": {"passed": False}, "C2": {"passed": True}}) == ["C1"]
