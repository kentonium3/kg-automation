---
title: kg-automation Architecture Review Evidence Log
doc_type: project
status: draft
last_updated: '2026-06-05'
tags: [architecture, review, evidence, 516, 281]
---

# Evidence Log

This is a compact evidence index. It intentionally excludes raw secrets, raw
prompt transcripts, and large logs.

| ID | Kind | Evidence | Supports |
|---|---|---|---|
| E-001 | Repo read | `README.md`, `CLAUDE.md`, `.kittify/charter/charter.md` establish Felix as office2/OpenClaw/Vikunja/Obsidian personal OS with risk tiers and doc-sync rules. | Context |
| E-002 | GitHub issue read | #516 scopes Felix-wide observability/status-emission framework research. | F-003 |
| E-003 | GitHub issue read | #281 scopes Felix-wide Directive 6 audit and helper-script management hardening. | F-006 |
| E-004 | Repo inventory | `find scripts` shows 158 Python files; `find tests` shows 102 top-level test files. | F-002 |
| E-005 | Local test run | `python -m pytest -q` on 2026-06-05: 1 failed, 2857 passed, 2 skipped in 50.18s. | F-002 |
| E-006 | Test source | `tests/habits/test_parse_morning_reply_48hr_correlation.py:318` says fixtures are within 48h of any plausible now; fixtures are 2026-06-01/02 and current date is 2026-06-05. | F-002 |
| E-007 | CI read | `.github/workflows/docs-ci.yml` runs only `python tooling/scripts/validate_docs.py`; no pytest workflow found. | F-002 |
| E-008 | Makefile read | `Makefile` has `docs-check` and `diagrams-sync`, no `test` target. | F-002 |
| E-009 | Live probe | `ssh office2-claude 'systemctl --user list-unit-files ...'` shows `felix-doc-auditor.timer` disabled and other timers enabled. | F-003 |
| E-010 | Live probe | `systemctl --user status felix-doc-auditor.service` shows failed timeout since 2026-05-25. | F-003 |
| E-011 | Live probe | `last-tick.json` for doc-auditor says `status=success`, timestamp `2026-05-25T13:28:34Z`. | F-003 |
| E-012 | Repo read | `docs/runbooks/doc-auditor-driver-ops.md` says doc-auditor is suspended indefinitely as of 2026-05-26. | F-003 |
| E-013 | Repo read | `service-inventory.json` marks `felix-doc-auditor` `status=active` and expects success tick within 2 hours. | F-003 |
| E-014 | Repo search | Multiple helpers define direct Vikunja base URLs and urllib wrappers; newer `scripts/sync/http.py` centralizes this for sync. | F-004 |
| E-015 | Repo search | Defaults split between `http://100.92.197.90:3456/api/v1/` and `https://office2.tail0f5f56.ts.net/api/v1`. | F-004 |
| E-016 | JSON validation | `jq empty` passes for all `docs/design/architecture/data/*.json`. | F-005 |
| E-017 | Repo search | No CI/tooling schema validation found for service inventory, data flows, credentials, or mutation surfaces. | F-005 |
| E-018 | JSON query | `credential-manifest.json` has Anthropic `created_date=2026-10-18`, future relative to 2026-06-05. | F-005 |
| E-019 | JSON query | `service-inventory.json` has 30 services; 11 lack `health_check`. | F-005 |
| E-020 | Repo read | `docs/design/helper-script-conventions.md` is `status: draft` and awaiting Kent review. | F-006 |
| E-021 | Repo count | Agent prompt sizes: capture 950 lines, tasker template 497, doc-auditor 485, tasker 337, escalation 304, main 257, habits 211. | F-006 |
| E-022 | Repo read | `scripts/deploy/deploy-149.sh` explicitly avoids system crontab and uses OpenClaw cron. | F-007 |
| E-023 | Repo read | `scripts/deploy/deploy-f026.sh` includes fallback direct `crontab` edits. | F-007 |
| E-024 | Repo read | `scripts/deploy/deploy-028.sh` creates a user crontab entry for drift-check. | F-007 |
| E-025 | Repo read | Constitution names `04-Growth/_private` as the absolute privacy boundary. | F-001 |
| E-026 | Repo read | Tasker AGENTS.md, tasker runbook, and service inventory still name `02-Growth/_private`. | F-001 |
| E-027 | Live probe | Deployed tasker workspace files on office2 still contain `02-Growth/_private`. | F-001 |
| E-028 | Repo read | `scripts/vault/paths.json` omits `_private`; `scripts/vault/README.md` describes this as intentional defense-in-depth. | Strength |
| E-029 | Test source | `tests/conftest.py` autouse fixture blocks live `urllib.request.urlopen` by default. | Strength |
| E-030 | Test source | Sync, escalation, and inbox tests include privacy redaction/private-skip coverage. | Strength |
