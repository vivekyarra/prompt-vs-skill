import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_env_example_has_no_values():
    for line in (ROOT / ".env.example").read_text().splitlines():
        if line and not line.startswith("#"):
            assert line.endswith("="), line
