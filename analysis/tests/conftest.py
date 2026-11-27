import pytest


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path, monkeypatch):
    """analyze.main writes figures to a relative `assets` dir by default; never let tests touch the repo's."""
    monkeypatch.chdir(tmp_path)
