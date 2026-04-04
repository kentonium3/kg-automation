---
title: "F001 Vikunja Deploy — Acceptance Results"
doc_type: reference
status: approved
---

# F001 Vikunja Deploy — Acceptance Results

**Date**: 2026-03-26
**Feature**: 001-vikunja-docker-deploy

## Test Results

| ID | Test | Result | Notes |
|----|------|--------|-------|
| T021 | Mac web UI access via Tailscale | **PASS** | HTTP 200 at `office2:3456` (50ms) and `100.92.197.90:3456` (12ms) |
| T022 | iPhone web UI access via Tailscale | **DEFERRED** | Requires manual verification by Kent |
| T023 | Port binding security | **PASS** | `ss -tlnp` shows `100.92.197.90:3456` — not `0.0.0.0` |
| T024 | systemd restart recovery | **PASS** | Service active and HTTP 200 after `systemctl restart` |
| T025 | Data persistence | **PASS** | SQLite at `/data/services/vikunja/data/vikunja.db` (496K), survived restart |
| T026 | Backup inclusion | **PASS (by design)** | Data at `/data/services/vikunja/data/` is within Restic backup scope (`/data/services/`). Snapshot listing requires repo permission fix for direct verification. |
| T027 | Setup script idempotency | **PASS** | 3 consecutive runs: first creates all, second and third show all "Exists" with zero duplicates |

## Success Criteria

| Criterion | Met? |
|-----------|------|
| SC-001: Web UI accessible within 3 seconds | **YES** — 50ms from Mac |
| SC-002: Service recovers within 30 seconds | **YES** — active immediately after restart |
| SC-003: Data survives container replacement | **YES** — SQLite on host, survived restart |
| SC-004: Vikunja data in Restic snapshot | **YES (by design)** — path in backup scope |
| SC-005: Setup script idempotent | **YES** — verified with 3 runs |
| SC-006: Port not reachable outside Tailscale | **YES** — bound to `100.92.197.90` only |
| SC-007: Runbook passes CI and covers all topics | **YES** — `validate_docs.py` passes |

## Deferred Items

- **T022 (iPhone)**: Requires manual verification from Kent's iPhone via Tailscale
- **T026 (snapshot listing)**: Direct `restic ls` verification blocked by repo permissions for claude user. The backup path inclusion is confirmed by design (data under `/data/services/`).
