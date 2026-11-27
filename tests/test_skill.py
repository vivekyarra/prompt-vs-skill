import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skill"))
from validate_skill import parse_front_matter, validate  # noqa: E402

SKILL = ROOT / "skill" / "flagsmith-ab-test"


def test_real_skill_valid():
    assert validate(SKILL) == []


def test_front_matter_fields():
    fm = parse_front_matter((SKILL / "SKILL.md").read_text())
    assert fm["name"] == "flagsmith-ab-test" and fm["description"]


def test_detects_problems(tmp_path):
    d = tmp_path / "foo"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: bar\ndescription: x\n---\nthe grader checks C3\n")
    errs = validate(d)
    assert any("does not match" in e for e in errs)
    assert any("grader" in e for e in errs)


def test_word_limit(tmp_path):
    d = tmp_path / "foo"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: foo\ndescription: x\n---\n" + "word " * 1600)
    assert any("words" in e for e in validate(d))


SKILL_V2 = ROOT / "skill" / "flagsmith-ab-test-v2"


def test_skill_v2_valid_and_name_unchanged():
    assert validate(SKILL_V2) == []
    assert parse_front_matter((SKILL_V2 / "SKILL.md").read_text())["name"] == "flagsmith-ab-test"


def test_skill_v2_content_rules():
    text = (SKILL_V2 / "SKILL.md").read_text()
    assert "@flagsmith/flagsmith/react" in text and "@flagsmith/nodejs" in text
    assert "isomorphic" in text and "Playwright" in text
    assert "Do not browse docs" not in text and "docs.flagsmith.com" in text
    assert "max_buffer_items=1" in text and ".value" in text
    assert "TTL" not in text and "pagehide" not in text


def test_v2_suffix_only_allowed_for_matching_name(tmp_path):
    d = tmp_path / "bar-v2"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: bar\ndescription: x\n---\nok\n")
    assert validate(d) == []
    (d / "SKILL.md").write_text("---\nname: baz\ndescription: x\n---\nok\n")
    assert any("does not match" in e for e in validate(d))


def test_skill_v2_ship_extension():
    import re

    text = (SKILL_V2 / "SKILL.md").read_text()
    assert "## 8. Read the results and decide" in text
    assert "## 9. Ship, only with approval" in text and "## 10. Verify the rollout" in text
    assert "NEVER ship, end or change a production experiment without the human's explicit approval" in text
    assert 'wait for an explicit "yes"' in text
    assert '"rollout_decision":"control"' in text and '"rollout_decision":"variant"' in text
    assert "results/refresh/" in text and "--json --jq" in text and "inconclusive" in text
    assert "PASS" in text and "FAIL" in text and "number of Flagsmith CLI calls" in text
    assert len(text.split()) <= 1500
    for word in ("grader", "trial", "hidden", "handoff", "pre-registered", "this experiment", "prompt-vs-skill"):
        assert word not in text.lower()
    assert not re.search(r"\bC[1-7]\b", text)
