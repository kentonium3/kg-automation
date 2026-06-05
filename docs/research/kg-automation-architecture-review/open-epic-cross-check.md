---
title: Open Epic Cross-Check
doc_type: project
status: draft
last_updated: '2026-06-05'
last_validated: '2026-06-05'
---

# Open Epic Cross-Check

This addendum checks whether open GitHub epics reinforce, expand, or are neutral
to the system-wide architecture review findings.

## Scope

Open issues with `Epic:` in the title as of 2026-06-05:

- #137 — LLM spend awareness and cost governance across services
- #164 — Felix EA Calendar Management Capability
- #165 — Felix EA Email Management Capability
- #270 — Felix governance discipline: tier-aware change protocol + issue queueing
- #271 — Felix as mirror: back-chaining intent to priorities, surfacing tangents
- #281 — Felix-wide Directive 6 audit + helper script management hardening
- #507 — Felix-Vikunja bi-directional sync foundation
- #516 — Felix-wide observability and status-emission framework

## Classification

| Issue | Classification | Review impact |
| --- | --- | --- |
| #137 | Reinforces and expands | Reinforces F-003 observability. Expands the review lens: cost is an operational signal, not only a billing concern. New LLM-consuming services should require cost projection, budget tier, and usage observability at design time. |
| #164 | Reinforces | Reinforces F-001 privacy-boundary consistency and F-003 observability. Calendar automation has sensitive data, external OAuth credentials, and user-visible consequences, so it should inherit privacy, approval, and status-emission requirements. |
| #165 | Reinforces | Reinforces F-001 privacy-boundary consistency and defense-in-depth. Email is high-sensitivity data and outbound send is explicitly approval-gated. Child issues should require no-autonomous-send tests and audit trails. |
| #270 | Expands | Adds a distinct architecture concern: agent-initiated mutation governance. The review should treat deterministic mutation wrappers, approval references, doc-update enforcement, and declared-state drift detection as first-class governance requirements. |
| #271 | Mostly neutral | Product-behavior epic. It indirectly reinforces privacy-boundary consistency because mirror analysis must not read private growth material. |
| #281 | Reinforces | Directly reinforces F-006 and the deterministic-helper principle. It also reinforces that helper conventions must become ratified governance, not remain a draft doc. |
| #507 | Reinforces | Directly reinforces F-004 shared integration boundary, F-003 observability, and F-005 authoritative data validation. The epic's core problem is the cost of ad hoc integration surfaces. |
| #516 | Reinforces | Directly reinforces F-003 and validates the proposed component status contract direction. |

## Recommended Review Expansion

The findings remain directionally correct. The open-epic queue adds one missing
cross-cutting theme that should be explicit in follow-on governance:

**Agent mutation governance must be enforced by deterministic tooling.**

Prompt-level governance is useful, but it is not sufficient for agents that can
change service configuration, deployed prompts, credentials metadata, cron
state, systemd units, or architecture records. For Tier 2+ changes, the expected
shape should be:

- classify the change tier;
- require an approval reference;
- snapshot or preflight the current state when appropriate;
- perform the mutation through a wrapper or narrowly scoped tool;
- update authoritative docs/data in the same change;
- verify the deployed/runtime state after mutation;
- leave an audit trail on the originating issue.

This theme is adjacent to F-006 and F-007, but broad enough to warrant a
governance update item of its own if #270 is accepted as load-bearing.

## Roadmap Adjustment

No existing proposed roadmap epic needs to be removed. Add one candidate:

**Epic H — Agent Mutation Governance Enforcement**

- Parent evidence: #270 plus the system-wide review's deploy-script and
  governance findings.
- Priority: P1/P2 depending on how much autonomous mutation Felix is allowed to
  perform before the wrapper exists.
- Outcome: a ratified mutation protocol and a deterministic helper/wrapper for
  approved mutation classes.
- Acceptance: Tier 2+ mutations cannot be completed by the standard Felix path
  without an approval reference, verification result, doc/data update decision,
  and audit-trail comment.

## CI Note

The open epics also reinforce F-002. Calendar, email, cost, governance, and
Vikunja work all increase the number of places where a local-only regression can
escape. A non-live pytest workflow is the low-friction guardrail that catches
deterministic regressions before they land on `main`.
