# Specification Quality Checklist: Prefix IDLE Cron Replies With Agent Slug

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-06-13
**Feature**: [spec.md](../spec.md)
**Mission**: `idle-cron-reply-agent-prefix-01KV1BSS`
**Source issue**: [#592](https://github.com/kentonium3/kg-automation/issues/592)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs) — spec describes *what* changes, not how the WhatsApp egress pipeline implements it
- [x] Focused on user value and business needs — the value is operator observability during observed-mode operation
- [x] Written for non-technical stakeholders — observer/operator framing throughout, no protocol/code references
- [x] All mandatory sections completed — Overview, Scenarios, FR/NFR/C tables, Success Criteria, Domain Language, Doc Sync, Assumptions, Dependencies, Out of Scope

## Requirement Completeness

- [x] No `[NEEDS CLARIFICATION]` markers remain
- [x] Requirements are testable and unambiguous — each FR/NFR/SC names a concrete byte format, threshold, or observable
- [x] Requirement types are separated (Functional / Non-Functional / Constraints) — three distinct tables, no mixing
- [x] IDs are unique across FR-### (FR-001..FR-008), NFR-### (NFR-001..NFR-003), and C-### (C-001..C-007)
- [x] All requirement rows include a non-empty Status value — `Locked` on confirmed items, `Proposed` on FR-002 pending plan-phase slug verification
- [x] Non-functional requirements include measurable thresholds — NFR-001 (byte-identical diff), NFR-002 (≤15K source bytes, ≤5% per-agent growth), NFR-003 (no out-of-scope code changes in merge diff)
- [x] Success criteria are measurable — SC-001 (5/5 byte-exact match), SC-002 (24h zero-violation observation), SC-005 (rebaseline commit-message marker)
- [x] Success criteria are technology-agnostic — described in operator-visible terms (WhatsApp message contents, observability, rebaseline state)
- [x] All acceptance scenarios are defined — AS-1 (routine attribution), AS-2 (recovery window), AS-3 (anti-narrative invariants), AS-4 (non-IDLE unchanged)
- [x] Edge cases are identified — EC-1 (calendar agent scope), EC-2 (slug vs deploy-dir), EC-3 (drift), EC-4 (token budget), EC-5 (rebaseline)
- [x] Scope is clearly bounded — explicit Out of Scope section names mechanical enforcement, non-IDLE replies, cadence reduction, non-cron paths, non-IDLE-emitting agents
- [x] Dependencies and assumptions identified — Dependencies section enumerates runbooks + memories; Assumptions section names the agent-set, mirror-pipeline, token-budget, and egress-path assumptions

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria — FR-001/FR-002/FR-006 verified by SC-001 byte-exact match; FR-003/FR-008 verified by deploy-pipeline outcome; FR-004/FR-005/FR-007 verified by source diff review
- [x] User scenarios cover primary flows — routine no-op (AS-1), recovery window (AS-2), invariants holding (AS-3), non-IDLE unchanged (AS-4)
- [x] Feature meets measurable outcomes defined in Success Criteria — every FR is reachable from one or more SCs; SC-002 closes the 24h regression door; SC-005 closes the rebaseline door
- [x] No implementation details leak into specification — the AGENTS.md file format is named because it IS the user-visible surface for this change, not as an implementation choice

## Notes

- FR-002 carries `Proposed` status because the canonical agent-slug list is verified in the plan phase against `docs/constitution/AGENT-REGISTRY.md` and OpenClaw registry; if the registry surfaces an additional or differently-named agent, FR-002 updates before plan-phase exit.
- The change is editorial across five sibling prompt files, not a code-level rename/migration; `change_mode` stays at default rather than `bulk_edit` per analysis: the 8-category bulk-edit model (code_symbols / serialized_keys / cli_commands / etc.) does not map to per-file prose rule-text changes. If the implement-time inference engine flags a Bulk Edit Inference Warning later, it will be dismissed with `--acknowledge-not-bulk-edit` citing this rationale.
- This is also a friction-test pass for spec-kitty 3.2.0rc43 — the goal is to confirm rc40/rc41/rc42 quirks at #1716, #1764, #1784, #1817, plus per-agent auth shadows at #596, do not recur on the post-upgrade toolchain.
