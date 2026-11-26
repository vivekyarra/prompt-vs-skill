import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from runner.config import STACKS
from runner.flags import ExposureResult

PASS_RESULT = {
    "passed": True,
    "checks": {f"C{i}": {"passed": True, "reason": "ok"} for i in range(1, 8)},
}


class FakeFlagsmith:
    def __init__(self, variant="prompt", flush_error=False):
        self.variant, self.flush_error = variant, flush_error
        self.events, self.flushed, self.closed, self.exposures = [], 0, False, []

    def get_exposure(self, trial_id, stack):
        self.exposures.append((trial_id, stack))
        return ExposureResult(self.variant, True, self.variant, None)

    def send_event(self, event, trial_id, stack):
        self.events.append((event, trial_id, stack))

    def flush(self):
        if self.flush_error:
            raise OSError("boom")
        self.flushed += 1

    def close(self):
        self.closed = True


class FakeCleaner:
    def __init__(self):
        self.deleted = []

    def delete_flag(self, name):
        self.deleted.append(name)
        return "deleted"


@pytest.fixture
def fixtures(tmp_path):
    apps = tmp_path / "apps"
    for s in STACKS:
        (apps / s).mkdir(parents=True)
        (apps / s / "app.txt").write_text(f"baseline {s}\n")
    skill = tmp_path / "skill" / "flagsmith-ab-test"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# skill\n")
    prompt = tmp_path / "OFFICIAL_PROMPT.md"
    prompt.write_text("header meta\n<!-- PROMPT_START -->\nOFFICIAL TEXT\n<!-- PROMPT_END -->\nfooter\n")
    brief = tmp_path / "TASK_BRIEF.md"
    brief.write_text("Flag: {{FLAG_NAME}} suffix {{TRIAL_SUFFIX}}. Finish with DONE.\n")
    grader = tmp_path / "grader"
    grader.mkdir()
    return {"apps_dir": apps, "skill_dir": skill, "prompt_path": prompt, "brief_path": brief, "grader_dir": grader}
