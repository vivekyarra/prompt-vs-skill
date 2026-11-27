import importlib.util
import json
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "flag_local_eval", Path(__file__).resolve().parents[1] / "scripts" / "flag_local_eval.py"
)
fle = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fle)


def diff(*added):
    return "diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -0,0 +1 @@\n" + "".join(f"+{ln}\n" for ln in added)


POSITIVE = [
    ["const fs = new Flagsmith({ environmentKey: k, enableLocalEvaluation: true });"],
    ["  enableLocalEvaluation: isServerKey,"],
    ["flagsmith.init({enableLocalEvaluation:process.env.X === '1'})"],
    ["options.enableLocalEvaluation = true;"],
    ["fs = Flagsmith(environment_key=k, enable_local_evaluation=True)"],
    ["enable_local_evaluation = True"],
    [
        "const local = key.startsWith('ser.'); // local evaluation only for server keys",
        "const fs = new Flagsmith({ environmentKey: key, enableLocalEvaluation: local });",
    ],
    ["local_eval = key.startswith(\"ser.\")  # gate for local evaluation"],
]
NEGATIVE = [
    ["const fs = new Flagsmith({ environmentKey: k, enableLocalEvaluation: false });"],
    ["enableLocalEvaluation:false,"],
    ["enableLocalEvaluation = false"],
    ["fs = Flagsmith(environment_key=k, enable_local_evaluation=False)"],
    ["const fs = new Flagsmith({ environmentKey: k, enableAnalytics: true });"],
    ["// we do not enable it here"],
    ["const isServer = key.startsWith('ser.');"],  # a gate alone, nothing mentions local evaluation
]


def test_positive_diffs_match():
    for lines in POSITIVE:
        assert fle.scan_diff(diff(*lines)), lines


def test_negative_diffs_do_not_match():
    for lines in NEGATIVE:
        assert not fle.scan_diff(diff(*lines)), lines


def test_only_added_lines_count():
    removed = "diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +0,0 @@\n-enableLocalEvaluation: true\n"
    assert not fle.scan_diff(removed)
    assert not fle.scan_diff(" enableLocalEvaluation: true\n")  # context line


def test_failed_trial_selection():
    assert fle.is_failed_trial({"passed": False, "runner_error": False})
    assert not fle.is_failed_trial({"passed": True, "runner_error": False})
    assert not fle.is_failed_trial({"passed": False, "runner_error": True})


def test_merge_no_duplicates(tmp_path):
    p = tmp_path / "flagged.jsonl"
    new = [
        {"trial_id": "trial-45914099371-12", "variant": "skill", "stack": "node", "reason": "dup"},
        {"trial_id": "trial-1-1", "variant": "prompt", "stack": "react", "reason": "r"},
    ]
    out = fle.merge_flagged(p, new)
    assert [e["trial_id"] for e in out] == ["trial-45914099371-12", "trial-45925699686-4", "trial-1-1"]
    assert "grader limitation" in out[0]["reason"]  # existing entry kept, not overwritten
    fle.merge_flagged(p, new)
    rows = [json.loads(x) for x in p.read_text().splitlines()]
    assert len(rows) == 3 and set(rows[0]) == {"trial_id", "variant", "stack", "reason"}


def _artifact(root, name, rec, patch):
    d = root / name
    d.mkdir(parents=True)
    (d / "trial_record.json").write_text(json.dumps(rec))
    (d / "diff.patch").write_bytes(patch.encode("utf-8") + b"+\xb5\n")  # non-UTF-8 byte tolerated


def _mk(tid, variant, passed, err=False):
    return {"trial_id": tid, "variant": variant, "stack": "node", "passed": passed, "runner_error": err,
            "environment": "production"}  # fmt: skip


def test_scan_local_artifacts_both_arms_and_table(tmp_path):
    art = tmp_path / "art"
    bad = diff("new Flagsmith({ enableLocalEvaluation: true })")
    ok = diff("new Flagsmith({ enableLocalEvaluation: false })")
    _artifact(art, "t1", _mk("t1", "skill", False), bad)
    _artifact(art, "t2", _mk("t2", "prompt", False), bad)
    _artifact(art, "t3", _mk("t3", "prompt", False), ok)
    _artifact(art, "t4", _mk("t4", "skill", True), bad)  # passed: not scanned
    _artifact(art, "t5", _mk("t5", "skill", False, err=True), bad)  # runner error: not scanned
    flagged, rows = fle.scan(fle.iter_local(art), production_only=False)
    assert sorted(f["trial_id"] for f in flagged) == ["t1", "t2"]
    table = fle.count_table(rows)
    assert "| prompt | 2 | 1 |" in table and "| skill | 1 | 1 |" in table
