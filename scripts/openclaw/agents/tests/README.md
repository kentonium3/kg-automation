# OpenClaw agent verification tests

Deterministic helpers authored under DIRECTIVE_034 (test-first) for mission
`felix-calendar-subagent-extraction-01KTTA33`. The tests assert two
contracts on the OpenClaw agent surface:

- **NFR-001 / NFR-004** — `main/AGENTS.md` and
  `felix-admin-calendar/AGENTS.md` must each stay under 12,000 chars
  (`test_agents_md_size.py`).
- **openclaw.json registry entry** — the sanitized fixture at
  `fixtures/openclaw-sample.json` must contain a well-formed
  `felix-admin-calendar` entry (`test_openclaw_config_schema.py`). The
  fixture is the offline-safe stand-in for the live
  `~/.openclaw/openclaw.json` on office2; `gateway.auth.token` is the
  literal `REDACTED-DO-NOT-USE` sentinel and no real secrets live here.

## Run

```bash
pytest scripts/openclaw/agents/tests/ -v
```

## Expected red -> green progression

At WP01 landing the suite is intentionally RED:

| Test | WP01 (now) | Flipped by |
|---|---|---|
| `test_main_agents_md_under_12k` | FAIL (main is ~25,982 chars) | WP03 — tightens main/AGENTS.md |
| `test_felix_admin_calendar_agents_md_under_12k` | FAIL (file missing) | WP02 — creates `felix-admin-calendar/AGENTS.md` |
| `test_openclaw_json_parses` | PASS | — |
| `test_felix_admin_calendar_entry_present` | FAIL (entry absent) | WP02/WP04 — adds the entry to the fixture |
| `test_felix_admin_calendar_entry_complete` | FAIL (entry absent) | WP02/WP04 |
| `test_workspace_path_pattern` | FAIL (entry absent) | WP02/WP04 |
| `test_agentdir_path_pattern` | FAIL (entry absent) | WP02/WP04 |
| `test_model_known` | FAIL (entry absent) | WP02/WP04 |

Pre-WP02/WP03 summary: **7 failed, 1 passed**. Reviewers can confirm the
red state by running pytest from the repo root and matching this table.
