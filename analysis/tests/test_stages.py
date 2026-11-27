"""Stage selection in analyze.py and routing in collect.py.."""

import json

from analysis import analyze, collect

from .test_analysis import rec


def _staged(i, stage=None, **kw):
    r = rec(i, "skill")
    r["trial_id"] = f"s-{stage}-{i}"
    if stage is not None:
        r["stage"] = stage
    r.update(kw)
    return r


def test_is_experiment_record_stage_selection():
    a = analyze
    legacy, prim = _staged(0), _staged(1, "primary")
    repl, roll = _staged(2, "replication"), _staged(3, "rollout", assignment="rollout")
    assert a.is_experiment_record(legacy) and a.is_experiment_record(prim)  # no stage == primary
    assert not a.is_experiment_record(repl) and not a.is_experiment_record(roll)
    assert a.is_experiment_record(repl, "replication") and not a.is_experiment_record(prim, "replication")
    assert a.is_experiment_record(roll, "rollout") and not a.is_experiment_record(repl, "rollout")
    assert all(a.is_experiment_record(r, "all") for r in (legacy, prim, repl, roll))
    # rollout assignment never counts toward primary/replication, even if mislabelled with a stage
    mislabelled = _staged(4, "primary", assignment="rollout")
    assert not a.is_experiment_record(mislabelled) and not a.is_experiment_record(mislabelled, "replication")
    assert not a.is_experiment_record(_staged(5, "rollout", assignment="local"), "all")
    assert not a.is_experiment_record(_staged(6, "replication", environment="development"), "replication")


def _run(src, out, tmp_path, *extra):
    analyze.main(["--trials", str(src), "--out", str(out), "--corrections", str(tmp_path / "none"), *extra])
    return out.read_text()


def test_analyze_cli_stage_filter_and_header(tmp_path):
    rows = [_staged(0), _staged(1, "primary"), _staged(2, "replication"),
            _staged(3, "rollout", assignment="rollout")]  # fmt: skip
    src = tmp_path / "t.jsonl"
    src.write_text("".join(json.dumps(r) + "\n" for r in rows))
    out = tmp_path / "R.md"
    text = _run(src, out, tmp_path)
    assert "**Stage analysed:** `primary`" in text and "(2 records)" in text
    text = _run(src, out, tmp_path, "--stage", "replication")
    assert "**Stage analysed:** `replication`" in text and "(1 records)" in text
    text = _run(src, out, tmp_path, "--stage", "rollout")
    assert "**Stage analysed:** `rollout`" in text and "(1 records)" in text
    text = _run(src, out, tmp_path, "--stage", "all")
    assert "(4 records)" in text and "`all`" in text


def test_collect_routes_stages(tmp_path):
    def w(name, r):
        d = tmp_path / "art" / name
        d.mkdir(parents=True)
        (d / "trial_record.json").write_text(json.dumps(r))

    base = {"environment": "production", "variant": "skill", "assignment": "flagsmith"}
    w("a", {**base, "trial_id": "a"})
    w("b", {**base, "trial_id": "b", "stage": "primary"})
    w("c", {**base, "trial_id": "c", "stage": "replication"})
    w("d", {**base, "trial_id": "d", "stage": "rollout", "assignment": "rollout"})
    w("e", {**base, "trial_id": "e", "assignment": "rollout"})  # no stage but rollout assignment
    w("f", {**base, "trial_id": "f", "stage": "replication", "dry_run": True})
    w("g", {**base, "trial_id": "g", "environment": "development"})
    out = tmp_path / "data" / "trials.jsonl"

    def ids(name):
        p = tmp_path / "data" / name
        return sorted(json.loads(x)["trial_id"] for x in p.read_text().splitlines()) if p.exists() else []

    assert collect.collect(tmp_path / "art", out) == 7
    assert ids("trials.jsonl") == ["a", "b"]
    assert ids("replication.jsonl") == ["c"]
    assert ids("rollout.jsonl") == ["d", "e"]
    assert ids("pilot.jsonl") == ["f", "g"]
    assert collect.collect(tmp_path / "art", out) == 0


def test_followup_stage_selection_header_and_routing(tmp_path):
    a = analyze
    fu, prim = _staged(0, "followup"), _staged(1, "primary")
    assert "followup" in a.STAGE_CHOICES
    assert a.is_experiment_record(fu, "followup") and not a.is_experiment_record(prim, "followup")
    assert not a.is_experiment_record(fu) and not a.is_experiment_record(fu, "replication")
    assert a.is_experiment_record(fu, "all")
    assert not a.is_experiment_record(_staged(2, "followup", environment="development"), "followup")
    src = tmp_path / "t.jsonl"
    src.write_text("".join(json.dumps(r) + "\n" for r in (fu, prim, _staged(3, "followup"))))
    text = _run(src, tmp_path / "R.md", tmp_path, "--stage", "followup")
    assert "**Stage analysed:** `followup`" in text and "(2 records)" in text

    base = {"environment": "production", "variant": "skill", "assignment": "flagsmith"}
    for name, extra in (("a", {"stage": "followup"}), ("b", {"stage": "followup", "dry_run": True})):
        d = tmp_path / "art" / name
        d.mkdir(parents=True)
        (d / "trial_record.json").write_text(json.dumps({**base, "trial_id": name, **extra}))
    out = tmp_path / "data" / "trials.jsonl"
    assert collect.collect(tmp_path / "art", out) == 2

    def ids(n):
        return [json.loads(x)["trial_id"] for x in (tmp_path / "data" / n).read_text().splitlines()]

    assert ids("followup.jsonl") == ["a"] and ids("pilot.jsonl") == ["b"] and not out.exists()
