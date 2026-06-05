---
title: kg-automation Architecture Review Issue Roadmap
doc_type: project
status: draft
last_updated: '2026-06-05'
tags: [architecture, roadmap, issues, 516, 520, 281]
---

# Issue Roadmap

This is a candidate backlog, not the authoritative GitHub issue queue. Kent
should accept, edit, merge, or reject entries before filing Epics/issues.

## Epic A — Privacy Boundary Consistency Hardening

**Priority**: P1
**Findings**: F-001

Candidate issue:

- **Fix: Update stale tasker privacy boundary references to
  `04-Growth/_private`**
  - Update repo tasker workspace files, tasker runbook, service inventory, and
    deployed office2 workspace files.
  - Verify no active deployed prompt references `02-Growth/_private`.
  - Acceptance: `rg "02-Growth/_private"` returns only historical migration
    docs or explicitly allowlisted context.

Candidate issue:

- **CI: Add stale private-boundary lint**
  - Validator blocks stale `02-Growth/_private` references outside historical
    allowlist.
  - Acceptance: local validator fails on a synthetic stale active prompt.

## Epic B — CI and Test Enforcement Baseline

**Priority**: P1
**Findings**: F-002

Candidate issue:

- **Fix: Stabilize date-sensitive habits parser correlation test**
  - Inject or monkeypatch clock instead of relying on wall time.
  - Acceptance: `python -m pytest tests/habits/test_parse_morning_reply_48hr_correlation.py -q`
    passes on dates after 2026-06-04.

Candidate issue:

- **CI: Run non-live pytest suite on push to main**
  - Add `make test`.
  - Add GitHub Actions workflow that runs `python -m pytest -q`.
  - Keep `live_smoke` opt-in.
  - Acceptance: workflow passes on main and blocks future failing tests.

## Epic C — Component Status and Observability Contract

**Priority**: P1/P2
**Findings**: F-003
**Related**: #516

Candidate issue:

- **Research/ADR: Define Felix component lifecycle status contract**
  - Decide lifecycle states and minimum required fields.
  - Include `suspended` semantics.
  - Acceptance: ADR or principle maps states to service inventory and
    per-component health files.

Candidate issue:

- **Fix: Reconcile felix-doc-auditor suspended state across inventory, runbook,
  and live status**
  - `service-inventory.json` should not say active with a two-hour success
    health check if the timer is intentionally disabled.
  - Acceptance: repo docs and live read-only checks tell the same story.

## Epic D — Shared Vikunja Client and Configuration Boundary

**Priority**: P2
**Findings**: F-004
**Related**: #520, #281

Candidate issue:

- **ADR: Standardize Vikunja client, base URL, token, timeout, and error policy**
  - Choose hostname vs direct IP default.
  - Define redaction-safe error messages.
  - Define when helpers may override defaults.

Candidate issue:

- **Refactor: Introduce shared Vikunja client library**
  - Likely home: `scripts/lib/vikunja.py` or `scripts/vikunja/client.py`.
  - Acceptance: at least two existing helpers use the shared client with tests.

Candidate issue:

- **Migration: Opportunistically move remaining Vikunja helpers to shared client**
  - File per-domain children as needed; avoid one giant bulk edit unless
    occurrence classification makes it safe.

## Epic E — Architecture Data Validation

**Priority**: P2
**Findings**: F-005

Candidate issue:

- **Tooling: Add semantic validator for architecture JSON**
  - Validate date sanity, status enums, required fields, health-check rules by
    entity type, and allowed schema-version exceptions.
  - Acceptance: catches future dates in credential manifest and active service
    entries without health checks where health checks are required.

Candidate issue:

- **Fix: Clean current architecture-data inconsistencies**
  - Correct Anthropic credential `created_date` or document why it is not a
    real creation date.
  - Reclassify module-like service inventory entries or add entity type.
  - Resolve doc-auditor `active` vs suspended conflict.

## Epic F — Ratify Helper/Library/Skill Conventions

**Priority**: P2
**Findings**: F-006
**Related**: #281

Candidate issue:

- **Governance: Approve helper-script conventions and wire into Directive 6**
  - Move conventions from draft to approved after review.
  - Add reference from Felix Constitution Directive 6.
  - Acceptance: future issue templates and CLAUDE.md point to the conventions.

Candidate issue:

- **Template: Add helper/library/skill decision prompt to feature and infra issues**
  - Acceptance: spec-ready criteria ask whether deterministic work should be a
    helper, shared library, or skill.

## Epic G — Deploy Script Surface Cleanup

**Priority**: P2/P3
**Findings**: F-007

Candidate issue:

- **Audit: Classify deploy scripts as active, deprecated, or historical**
  - Add headers or move historical scripts to archive.
  - Acceptance: active scripts do not preserve deprecated crontab mutation
    examples unless explicitly justified.

Candidate issue:

- **Runbook: Document canonical deploy-script template**
  - Use deploy-149 as reference for dry-run/apply, no system crontab, rollback
    instructions, and smoke verification.
