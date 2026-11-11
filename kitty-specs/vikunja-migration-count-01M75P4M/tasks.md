# Tasks: vikunja-migration-count-01M75P4M

The Vikunja release route takes the migration count from the release's reviewed inputs, not a constant (#1098).

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Builder takes the expected count (baseline.build and CLI) | WP01 | |
| T002 | Verifier relies on the sha-bound baseline | WP01 | |
| T003 | Release history records and predecessor-aware change-set tests | WP01 | |
| T004 | Tests for 10 and 0, CLI and mismatch cases | WP01 | |
| T005 | Runbook builder command and count | WP01 | |
| T006 | Full suite and doc validation | WP01 | |

## WP01 — Migration count from reviewed inputs

Prompt: [tasks/WP01-migration-count.md](tasks/WP01-migration-count.md). Priority P1. No dependencies. Implementer Codex gpt-6.1-sol; reviewer Claude Sonnet 5.5.

T001 Builder takes the expected count (baseline.build and CLI) (WP01)
T002 Verifier relies on the sha-bound baseline (WP01)
T003 Release history records and predecessor-aware change-set tests (WP01)
T004 Tests for 10 and 0, CLI and mismatch cases (WP01)
T005 Runbook builder command and count (WP01)
T006 Full suite and doc validation (WP01)
