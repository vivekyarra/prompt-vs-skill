"""Recompute the SHA-256 of the verbatim prompt in OFFICIAL_PROMPT.md and compare with the header."""
import hashlib
import pathlib
import re
import sys

md = pathlib.Path(__file__).with_name("OFFICIAL_PROMPT.md").read_text()
body = md.split("<!-- BEGIN OFFICIAL PROMPT -->\n", 1)[1].split("\n<!-- END OFFICIAL PROMPT -->", 1)[0]
got = hashlib.sha256(body.encode()).hexdigest()
want = re.search(r"SHA-256 of the prompt text \| `([0-9a-f]{64})`", md).group(1)
print(got, "OK" if got == want else "MISMATCH")
sys.exit(got != want)
