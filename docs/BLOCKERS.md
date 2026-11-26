# Blockers (human-only checkpoints, see docs/BUILD_SPEC.md section 5)

| ID | Task | Status |
|---|---|---|
| H1 | Flagsmith Cloud account + org, managed warehouse for Experimentation | PENDING |
| H2 | Create projects `handoff-experiment`, `handoff-sandbox` (+ Production/Development envs) | PENDING |
| H3 | Create API credentials (experiment server key, sandbox keys/admin key) | PENDING |
| H4 | Anthropic API key with spend limit | PENDING |
| H5 | Add keys as GitHub Actions secrets (names in `.env.example`) | PENDING |
| H6 | Approve pilot cost and final sample target | PENDING (after pilot) |
| H7 | Start experiment in dashboard if CLI/API cannot | PENDING, probably not needed: official docs start it via `POST ./experiments/<id>/start/` through `flagsmith api` (UNVERIFIED live, needs H1-H3; see docs/verified-facts.md section 5) |
| H8 | Record and upload demo video | PENDING |
| H9 | Post the issue/PR on Flagsmith's GitHub | PENDING |
| H10 | Register, star Flagsmith, submit form | PENDING |
