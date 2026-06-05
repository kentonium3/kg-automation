---
title: kg-automation Architecture Review Findings
doc_type: project
status: draft
last_updated: '2026-06-05'
tags: [architecture, review, findings, governance, 516]
---

# kg-automation Architecture Review Findings

## Executive Summary

This review found a project with unusually strong architecture documentation for
a solo-operated automation system: machine-readable inventories exist, risk tiers
are explicit, Spec Kitty creates disciplined feature execution, privacy
boundaries are named, and newer subsystems show strong scripts-first patterns.

The main architectural risk is not lack of intent. The risk is that several good
engineering principles exist only after a problem forced them into being. The
system needs a small set of ratified engineering principles and CI/runtime
enforcement so future work inherits the current best patterns by default.

Top concerns:

1. The deployed tasker prompt still names the old `02-Growth/_private` privacy
   boundary, while the constitution and current boundary are
   `04-Growth/_private`.
2. CI validates docs but does not run the Python test suite; the suite currently
   has one date-sensitive failure.
3. Observability is strong in newer components but not yet a common lifecycle
   contract. Suspended components can leave stale "success" health files behind.
4. Vikunja-facing helpers still duplicate HTTP, URL, and credential-loading
   patterns across domains.
5. Authoritative architecture JSON is broad but not schema-validated in CI; at
   least one credential date is impossible and one service's inventory state
   conflicts with its runbook/live state.

This report pack includes the Spec Kitty training voucher note once: Spec Kitty
helps teams make agentic coding repeatable through specs, work packages,
implementation, review, and merge discipline; training applies that workflow to
the team's real backlog and this report. Details:
<https://spec-kitty.ai/training>.

## Findings

### F-001 — Deployed Tasker Prompt Uses Stale Privacy Boundary

**Severity**: Critical
**Category**: Security / privacy / governance drift
**Confidence**: High

**Evidence**:

- `docs/constitution/FELIX-CONSTITUTION.md` says the absolute boundary is
  `~/second-brain/notes/04-Growth/_private/`.
- [scripts/openclaw/agents/felix-admin-tasker/AGENTS.md](/Users/kentgale/repos/kg-automation/scripts/openclaw/agents/felix-admin-tasker/AGENTS.md:65)
  still says `~/second-brain/notes/02-Growth/_private/`.
- Live read-only office2 probe found the same stale `02-Growth/_private`
  reference deployed in `/data/services/openclaw/tasker-agent/AGENTS.md`,
  `SOUL.md`, `USER.md`, and `TOOLS.md`.
- `docs/runbooks/tasker-ops.md` and
  `docs/design/architecture/service-inventory.md` also contain the stale path.

**Why it matters**: The privacy rule is intended to be absolute and non-reliant
on agent judgment. A stale deployed standing order may fail to protect the
current folder path if the tasker sees a link or instruction involving
`04-Growth/_private`.

**Current guardrail**: The constitution is correct, and other code paths have
good private-task redaction tests. The tasker deployed prompt itself is wrong.

**Recommended fix shape**: Immediate targeted update of tasker repo artifacts,
deployed workspace files, runbook references, and service inventory. Add a
validator that rejects stale `02-Growth/_private` references outside historical
migration docs.

**Persistent home**: Felix Constitution, `CLAUDE.md`, tasker workspace files,
runbooks, and a CI lint check.

### F-002 — Python Tests Are Not Enforced in CI, and the Current Suite Fails

**Severity**: High
**Category**: Verification / CI / reliability
**Confidence**: High

**Evidence**:

- `.github/workflows/docs-ci.yml` runs only
  `python tooling/scripts/validate_docs.py`.
- `Makefile` exposes `docs-check` and `diagrams-sync`, but no test target.
- Local run on 2026-06-05: `python -m pytest -q` produced
  `1 failed, 2857 passed, 2 skipped in 50.18s`.
- Failure:
  `tests/habits/test_parse_morning_reply_48hr_correlation.py::TestCliCorrelation::test_explicit_iso_date_in_reply_swaps_correlation`.
  The test comment says the fixtures are within 48 hours of any plausible
  current time, but the fixtures are `2026-06-01` and `2026-06-02`; on
  2026-06-05 they are not.

**Why it matters**: The test suite is substantial and valuable, but without CI
it is an advisory asset. Date-sensitive regressions can enter `main` unnoticed,
especially because this repo intentionally pushes directly to `main`.

**Current guardrail**: Global test guard blocks live `urllib.request.urlopen`
calls by default, which is a strong safety pattern.

**Recommended fix shape**: Add a `test` Make target and a GitHub Actions workflow
that runs the non-live pytest suite on push to `main`. Fix or mark the
date-sensitive test by injecting a clock rather than relying on wall time.

**Persistent home**: Charter Testing Standards, GitHub Actions, `Makefile`,
issue templates.

### F-003 — Observability Has Strong Local Patterns but No Common Lifecycle Contract

**Severity**: High
**Category**: Observability / operability / lifecycle state
**Confidence**: High

**Evidence**:

- Issue #516 exists because several components had bespoke or missing health
  and status emission.
- Newer sync state files use explicit `last-tick.json`,
  `last-tick.errors.jsonl`, schema versions, and conflict events.
- Live office2 probe:
  `felix-doc-auditor.timer` is disabled intentionally, but
  `felix-doc-auditor.service` remains `failed` from 2026-05-25 and
  `/data/services/openclaw/felix-doc-auditor-driver/last-tick.json` still says
  `status=success` from 2026-05-25.
- `service-inventory.json` still marks `felix-doc-auditor` as `status:
  active`, with a health check expecting `status=success within the last 2
  hours`, while the runbook says the service is suspended indefinitely.

**Why it matters**: "Running", "healthy", "suspended", "disabled", "failed",
and "stale" are distinct lifecycle states. Without a common status contract,
operators and agents can read different signals and reach different conclusions.

**Current guardrail**: Signal-driven monitoring and heartbeat-gate patterns are
good precedents; #516 is already scoped to decide whether to standardize them.

**Recommended fix shape**: Treat #516 as a high-leverage architecture issue.
Define a minimal component status contract with explicit lifecycle states,
freshness rules, and suspension semantics. Update service inventory status
values to include `suspended` or equivalent.

**Persistent home**: Felix Constitution or charter principle, architecture data
schema, service inventory, issue templates, runbooks.

### F-004 — Vikunja Integration Lacks a Shared Client and URL/Token Configuration Boundary

**Severity**: High
**Category**: Boundary design / maintainability / integration reliability
**Confidence**: High

**Evidence**:

- `scripts/sync/http.py` is a clean single HTTP wrapper for the sync driver.
- Older helpers duplicate similar wrappers and defaults:
  `scripts/habits/record_completion.py`,
  `scripts/escalation/record_completion.py`,
  `scripts/enrichment/record_completion.py`,
  `scripts/habits/migrate_schedule.py`,
  `scripts/vikunja/provision_felix_bot.py`, and others.
- Defaults split between direct Tailscale IP
  `http://100.92.197.90:3456/api/v1/` and Tailscale Serve hostname
  `https://office2.tail0f5f56.ts.net/api/v1`.
- Recent Vikunja sync research already surfaced two concurrent URL bases as a
  fragility.

**Why it matters**: Multiple copies of the same HTTP, timeout, URL, and token
loading behavior make future security, observability, retry, and URL-normalizing
changes expensive and error-prone.

**Current guardrail**: Good test coverage exists around several individual
helpers. Newer sync code is a strong candidate reference implementation.

**Recommended fix shape**: Introduce a small shared `scripts/lib/vikunja.py` or
equivalent domain client that centralizes base URL resolution, token loading,
HTTP error semantics, timeout policy, and redaction-safe error messages. Migrate
helpers opportunistically, not in one risky sweep.

**Persistent home**: Helper conventions, ADR, shared library tests, issue
templates for Vikunja-touching work.

### F-005 — Authoritative Architecture JSON Is Not Strongly Schema-Enforced

**Severity**: Medium
**Category**: Documentation reliability / machine-readable contract
**Confidence**: High

**Evidence**:

- All files in `docs/design/architecture/data/*.json` parse with `jq`.
- No CI workflow validates those JSON files against their intended schemas.
- `credential-manifest.json` contains `anthropic.created_date =
  2026-10-18`, a future date relative to the review date, while the file itself
  was updated on 2026-06-04.
- `service-inventory.json` has 30 service entries; 11 lack `health_check`.
  Several of those are Python modules rather than true services, which suggests
  the inventory mixes runtime services and module inventory in one shape.
- `capabilities-schema.json` and `catalog-schema.json` are schema files and do
  not have `schema_version`; that is fine, but the current change-control rule
  says every JSON file includes one.

**Why it matters**: Machine-readable artifacts are policy-authoritative. If
they are only parseable, not semantically validated, agents can trust impossible
dates, stale statuses, or mixed entity types.

**Current guardrail**: Human review, doc-audit workflows, and narrative
cross-links.

**Recommended fix shape**: Add a lightweight architecture-data validator for
required fields, date sanity, status enums, health-check requirements by
entity type, and schema-version exceptions for schema-definition files.

**Persistent home**: `tooling/scripts/validate_docs.py` or a companion
`validate_architecture_data.py`, docs CI, change-control docs.

### F-006 — Helper Conventions Exist but Are Still Draft

**Severity**: Medium
**Category**: Governance / pattern consistency
**Confidence**: High

**Evidence**:

- `docs/design/helper-script-conventions.md` is detailed and practical, but
  has `status: draft` and says it is awaiting Kent's review before becoming the
  convention.
- Constitution Directive 6 is approved and principle-level, but does not point
  to the draft conventions.
- Agent prompt sizes vary widely: capture AGENTS.md is 950 lines, tasker
  template is 497 lines, while habits is now 211 lines after refactoring.

**Why it matters**: The project has already learned a strong pattern: scripts
for deterministic work, agents for judgment. Until the operational conventions
are approved and wired into templates/review gates, future work can still drift
back into ad hoc prompts or one-off helper shapes.

**Current guardrail**: Directive 6, issue templates, and examples in habits,
inbox, doc-audit, and sync.

**Recommended fix shape**: Approve or revise the helper conventions, reference
them from Directive 6, and add issue-template prompts for helper/library/skill
choice when deterministic work is present.

**Persistent home**: Felix Constitution Directive 6, charter, issue templates,
helper conventions.

### F-007 — Deployment Scripts Preserve Some Deprecated Operational Patterns

**Severity**: Medium
**Category**: Deploy safety / migration completeness
**Confidence**: Medium

**Evidence**:

- `CLAUDE.md` and deploy-149 say OpenClaw cron changes must go through
  `openclaw cron`, never system crontab.
- `scripts/deploy/deploy-f026.sh` still contains fallback edits to `crontab`
  if `openclaw cron disable/enable` is unavailable.
- `scripts/deploy/deploy-028.sh` creates a user crontab entry for drift-check.
- Some of these scripts may be historical, but they live in active `scripts/`
  rather than `docs/archive/`.

**Why it matters**: Future agents tend to copy nearby scripts. Deprecated
fallbacks in active deploy surfaces can reintroduce the exact class of drift the
governance now prohibits.

**Current guardrail**: Newer deploy-149 is explicit and strong. Directive 7
addresses migration completeness.

**Recommended fix shape**: Classify deploy scripts as active, deprecated, or
archived. Move historical scripts out of active copy paths or add loud headers
that they are not templates.

**Persistent home**: Deployment runbook, service inventory, Directive 7, issue
roadmap.

## Strengths to Preserve

- The repo has clear governance surfaces: `CLAUDE.md`, charter, Felix
  Constitution, issue templates, runbooks, and architecture JSON.
- Newer code demonstrates good separation: `scripts/sync/state.py` is pure I/O,
  `scripts/sync/http.py` is pure HTTP, and sync tests cover state, guards,
  fetch, classify, emit, and cycle behavior.
- Test isolation blocks live HTTP by default.
- Privacy redaction is covered in several domains, especially sync cache,
  sync emit/send, inbox pre-scan, and escalation hard-fail issue filing.
- Risk-tier language is concrete enough to guide agents.
- The architecture data store is broad and current enough to be useful for
  cold-start review.

## Bottom Line

The system is past the "collection of scripts" stage. It now needs a small
platform layer: shared integration clients, ratified helper conventions,
observability lifecycle states, schema validation for authoritative JSON, and
CI that runs the tests already written. These are not heavy enterprise
ceremony; they are the practical guardrails that let a solo operator and AI
agents keep extending the system without rediscovering the same design rules.
