# Tasks: Off-host dead-man pings for the on-host watchers
**Mission**: `offhost-deadman-pings-01M50990` · **Issue**: kentonium3/kg-automation#1077 (RFC #1069) · **Branch**: `feat/offhost-deadman-pings`
Inputs: [spec.md](spec.md) · [plan.md](plan.md) (read the four "Post-plan … dispositions" sections; round 3 and round 4 are authoritative) · [data-model.md](data-model.md) · [research.md](research.md)

## Subtask Index
| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Env-file loader + canonical URL parsing (success/fail endpoints) | WP01 | |
| T002 | Hardened ping transport (curl -q, stdin -K, minimal env, 2 attempts) + `ping()` | WP01 | |
| T003 | `channel_ok()`: topic check + ntfy `/v1/health` probe in delivery's transport context | WP01 | |
| T004 | Operator CLI (`python3 -m scripts.common.deadman`) + `deadman.env.sample` | WP01 | |
| T005 | Module tests incl. secrecy, hostile .curlrc, timeouts, URL rejections | WP01 | |
| T006 | Canary: count `alerts_undelivered` (summary only, never persisted) | WP02 | |
| T007 | Canary: ping from `main()` with outcome rules | WP02 | |
| T008 | Canary tests (outcomes, exit codes, tick-signal schema unchanged) | WP02 | |
| T009 | Health-check: execution-fault + delivery outcome, ping after record write | WP03 | [P] |
| T010 | Health-check tests | WP03 | [P] |
| T011 | Architecture data: credential, flow, inventory notes | WP04 | [P] |
| T012 | Docs: observability §5a, canary-registry-ops runbook section | WP04 | [P] |
| T013 | Docs test | WP04 | [P] |

## WP01 — `scripts/common/deadman.py`

**Prompt**: [tasks/WP01-deadman-module.md](tasks/WP01-deadman-module.md) · **Depends on**: none

T001 (WP01)
T002 (WP01)
T003 (WP01)
T004 (WP01)
T005 (WP01)

## WP02 — felix-canary pings

**Prompt**: [tasks/WP02-canary-hook.md](tasks/WP02-canary-hook.md) · **Depends on**: WP01

T006 (WP02)
T007 (WP02)
T008 (WP02)

## WP03 — felix-health-check pings

**Prompt**: [tasks/WP03-healthcheck-hook.md](tasks/WP03-healthcheck-hook.md) · **Depends on**: WP01

T009 (WP03)
T010 (WP03)

## WP04 — Architecture data, docs, runbook

**Prompt**: [tasks/WP04-docs-and-arch-data.md](tasks/WP04-docs-and-arch-data.md) · **Depends on**: WP01

T011 (WP04)
T012 (WP04)
T013 (WP04)
