---
title: kg-automation Architecture Review Governance Update Map
doc_type: project
status: draft
last_updated: '2026-06-05'
tags: [architecture, governance, review, 516]
---

# Governance Update Map

## `.CLAUDE.md`

Proposed updates:

- Add a short "Engineering Principles" section that points to the accepted
  principles document.
- Add an explicit rule that suspended services must be represented in
  architecture data and health checks as suspended, not merely disabled.
- Add a reminder that new Vikunja integrations should use the shared client once
  created.

## Felix Constitution

Proposed updates:

- Directive 6: reference `docs/design/helper-script-conventions.md` after that
  document is approved.
- New or amended observability directive: every deployed component has a
  machine-readable lifecycle/status signal and named observer.
- Privacy boundary: retain the current `04-Growth/_private` rule and add a note
  that stale historical path references are lint violations outside migration
  docs.

## Spec Kitty Charter

Proposed updates:

- Testing standards: require non-live pytest in CI for Python changes.
- Quality gates: require architecture-data validation when authoritative JSON
  files change.
- Deployment constraints: active deploy scripts must not use deprecated cron
  mutation patterns unless explicitly grandfathered and labeled.

## Issue Templates

Feature template:

- Add "Observability / operation" prompt:
  "How will we know this feature is healthy, failed, stale, or suspended?"
- Expand spec-ready criteria to require a health/failure observer for deployed
  or scheduled work.

Infra template:

- Add lifecycle-state check: active, disabled, suspended, deprecated, removed.
- Add architecture-data validation requirement for touched JSON files.

Bug/debt templates:

- Keep Directive 8's symptom/observer/cost discipline.
- Add a "guardrail gap" field: could this class be prevented by CI, schema,
  shared helper, or template update?

Research template:

- Add "principle extraction" output when research is Felix-wide or
  architecture-shaping.

## Architecture Docs

Proposed updates:

- `docs/design/architecture/change-control.md`: clarify which JSON files are
  schema-definition files exempt from `schema_version` metadata.
- `docs/design/architecture/data/service-inventory.json`: add/standardize
  lifecycle states such as `active`, `suspended`, `disabled`, `deprecated`.
- `docs/design/architecture/service-inventory.md`: update tasker privacy path
  and doc-auditor suspended state.

## CI and Tooling

Proposed updates:

- Add `make test` for non-live pytest.
- Add GitHub Actions workflow for non-live pytest on push to `main`.
- Add `validate_architecture_data.py` or extend `validate_docs.py` for
  architecture JSON semantic checks.
- Add stale privacy-boundary lint: block `02-Growth/_private` outside explicitly
  allowed historical/migration files.

## Runbooks

Proposed updates:

- `docs/runbooks/tasker-ops.md`: update privacy boundary.
- `docs/runbooks/doc-auditor-driver-ops.md`: define suspended-state health
  expectations, including what stale last-tick means while suspended.
- Deployment runbook: define active/deprecated/archived deploy-script states.

## ADRs

Likely ADR candidates:

- Shared Vikunja client and URL normalization.
- Component status-emission lifecycle contract, depending on #516 outcome.
- Architecture-data validation contract if it becomes a first-class policy.
