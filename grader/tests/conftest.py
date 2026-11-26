"""Fixtures for the grader self-tests (they run real apps and a real browser: marker `grader`)."""

from __future__ import annotations

import subprocess
import sys

import pytest

from grader.tests.helpers import REPO


def pytest_configure(config):
    config.addinivalue_line("markers", "grader: slow end-to-end grader self-tests (need node, npm, chromium)")


@pytest.fixture(scope="session")
def broken_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("broken")
    subprocess.run(
        [sys.executable, str(REPO / "apps" / "broken" / "make_broken.py"), "--all", "--out", str(out)],
        check=True, capture_output=True,
    )  # fmt: skip
    return out
