import json
import pathlib

from scripts.mock_vs_real_select import select

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_selection_is_deterministic_and_matches_committed_file():
    sel = select(ROOT)
    assert sel == select(ROOT)
    committed = json.loads((ROOT / "data/mock_vs_real_selection.json").read_text())
    assert sel == committed


def test_selection_contents():
    sel = select(ROOT)
    assert all(not r["recorded_passed"] for r in sel["failing"])
    assert len(sel["passing_sample"]) == 20
    assert all(r["recorded_passed"] and r["diff_bytes"] for r in sel["passing_sample"])
    ids = [r["trial_id"] for r in sel["failing"] + sel["passing_sample"]]
    assert len(ids) == len(set(ids))
