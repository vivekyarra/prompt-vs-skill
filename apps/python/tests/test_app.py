import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402


def test_page_renders_with_join_button():
    client = app.test_client()
    res = client.get("/")
    assert res.status_code == 200
    assert b'id="join-btn"' in res.data
    assert "vid=" in res.headers.get("Set-Cookie", "")
    assert client.post("/join").status_code == 200
