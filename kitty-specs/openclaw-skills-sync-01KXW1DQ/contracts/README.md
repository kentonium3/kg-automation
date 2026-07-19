# Contracts — openclaw-skills-sync-01KXW1DQ

This mission has **no HTTP/API/service contracts**. Its interfaces are
**command-line exit-code contracts**, which are specified in
[`../data-model.md`](../data-model.md) ("Exit-code contract" + the drift-check
contract) rather than as OpenAPI/GraphQL schemas:

- `python3 -m scripts.openclaw.deploy.deploy_agent_skills [--dry-run] [--skill NAME]`
  → exit `0` success/no-op/defer/dry-run · `1` partial copy failure · `2` git
  advance failed · `3` validation error. Audit-record shapes (JSONL) + the
  `skills-last-tick.json` freshness pointer shape are in `data-model.md`.
- `python3 -m scripts.openclaw.enforcement.skills_drift_check [--json]`
  → exit `0` clean · `1` drift/orphan · `2` unreadable; `--json` row shape
  `{skill, state, repo_md5, deployed_md5}`.

This directory exists to satisfy the software-dev mission's path convention; the
authoritative interface specs live in `data-model.md`.
