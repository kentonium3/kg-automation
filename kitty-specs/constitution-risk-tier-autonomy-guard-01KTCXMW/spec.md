# Constitution Risk-Tier Autonomy Guard

**Status**: Specification (post-discovery, ready for `/spec-kitty.plan`)
**Mission ID**: `01KTCXMWWGDBM4Y0HJS25YZ4FP`
**Mission slug**: `constitution-risk-tier-autonomy-guard-01KTCXMW`
**Mission type**: software-dev
**Target branch**: main
**Source issue**: [#528](https://github.com/kentonium3/kg-automation/issues/528)
**Created**: 2026-06-05

---

## Intent Summary

Amend the Felix Constitution so agent autonomy is explicitly constrained by the
five-tier deployed-change risk taxonomy. Autonomy level remains the model for
how much routine agent activity is surfaced to Kent; risk tier remains the model
for what gates apply before production-impacting changes. The constitution must
state that autonomy never grants permission to bypass Tier 0, Tier 1, or Tier 2
change-control obligations.

The amendment is principle-level only. The canonical tier definitions stay in
`docs/design/architecture/data/change-risk-taxonomy.json`, with procedural
details in the change-control and governance runbooks.

## Background & Motivation

The project already has strong risk-tier guidance in several context-setting
surfaces:

- `CLAUDE.md` describes the Tier 0-4 protocol for Claude Code sessions.
- `.kittify/charter/charter.md` describes the same protocol for Spec Kitty
  workflow governance.
- `scripts/openclaw/agents/main/GOVERNANCE.md` gives Felix main-agent operating
  instructions for Tier 0-4 changes.
- `.github/ISSUE_TEMPLATE/infra.md`, `.github/ISSUE_TEMPLATE/feature.md`, and
  `docs/runbooks/deployment.md` route new deployed work through risk-tier
  classification.

The Felix Constitution remains the top-level governance source for Felix agent
autonomy, safety, scope, logging, and privacy. It currently defines Assisted,
Observed, and Autonomous operation, but it does not explicitly connect those
autonomy levels to the deployed-change risk taxonomy. That leaves a small but
load-bearing interpretive gap: a future reader could treat "Autonomous" as
permission to make production-impacting changes whenever an agent's standing
orders appear broad enough.

This mission closes that gap.

## User Scenarios & Testing

### Primary scenario: future agent interprets autonomy safely

1. A future Felix agent or Claude Code/Codex session reads the Felix
   Constitution before acting.
2. The agent sees that autonomy level does not override risk-tier gates.
3. The agent classifies a proposed production-impacting change by the canonical
   Tier 0-4 taxonomy before acting.
4. If the change is Tier 0, the agent generates instructions for Kent instead
   of executing. If Tier 1 or Tier 2, the agent follows the required gates
   before mutation.

### Secondary scenario: operator reviews a promoted agent

1. Kent reviews an agent promotion or standing-order update.
2. The constitution makes clear that promotion to Observed or Autonomous changes
   activity surfacing, not permission to bypass deployed-change safeguards.
3. Kent can evaluate agent autonomy independently from production mutation
   authority.

### Acceptance Scenarios

- **AS-001**: A reader of Directive 2 can determine that autonomy level is not
  permission to bypass the risk-tier protocol.
- **AS-002**: A reader looking for the canonical Tier 0-4 definition is pointed
  to `docs/design/architecture/data/change-risk-taxonomy.json`.
- **AS-003**: A reader can determine that Tier 0 is operator-only regardless of
  autonomy level, urgency framing, or user phrasing.
- **AS-004**: A reader can determine that Tier 1 and Tier 2 changes remain
  gated by their required pre-flight, approval, backup/snapshot, and
  verification requirements where applicable.

### Edge Cases

- **EC-001**: The amendment duplicates the full risk-tier table and later drifts
  from the canonical JSON. This must be avoided by keeping the constitution
  principle-level and linking to the canonical source.
- **EC-002**: The amendment is placed too late in the document, after privacy or
  other sections, and is missed by a reader interpreting Directive 2. Placement
  must keep the autonomy/risk relationship near the autonomy directive.
- **EC-003**: The amendment is broad enough to imply new runtime behavior or
  changed autonomy-promotion rules. The mission must clarify the relationship
  between autonomy and risk tiers without changing the autonomy model itself.

## Requirements

### Functional

| ID | Status | Requirement |
|---|---|---|
| FR-001 | proposed | `docs/constitution/FELIX-CONSTITUTION.md` MUST state that agent autonomy level does not grant permission to bypass deployed-change risk-tier protocols. |
| FR-002 | proposed | The amendment MUST state that Tier 0 remains operator-only regardless of autonomy level, urgency, or user phrasing. |
| FR-003 | proposed | The amendment MUST state that Tier 1 and Tier 2 changes remain subject to their defined gates, including pre-flight, approval, backup/snapshot, and verification obligations where applicable. |
| FR-004 | proposed | The amendment MUST reference `docs/design/architecture/data/change-risk-taxonomy.json` as the canonical Tier 0-4 taxonomy. |
| FR-005 | proposed | The amendment MUST be placed where a cold-start reader interpreting Directive 2 will encounter it before inferring that autonomy is production-mutation authority. |
| FR-006 | proposed | The mission MUST check `CLAUDE.md`, `.kittify/charter/charter.md`, and `docs/design/architecture/change-control.md` for consistency with the new constitution wording, and update only if a concrete inconsistency is found. |

### Non-Functional

| ID | Status | Requirement | Threshold / Measurement |
|---|---|---|---|
| NFR-001 | proposed | Constitution wording remains concise and principle-level. | Amendment is reviewable in under 5 minutes and does not duplicate the full Tier 0-4 table. |
| NFR-002 | proposed | Existing constitution directives are not weakened. | Diff preserves existing scope, safety, logging, privacy, and communication-boundary requirements. |
| NFR-003 | proposed | Companion-doc changes are minimal. | Only files with concrete inconsistency are changed; no broad rewording pass. |
| NFR-004 | proposed | Documentation validation passes. | `python tooling/scripts/validate_docs.py` exits 0 after implementation. |

### Constraints

| ID | Status | Constraint |
|---|---|---|
| C-001 | proposed | Risk tier for this mission is Tier 4 (schema/metadata/governance documentation). No backup or production pre-flight is required. |
| C-002 | proposed | The canonical Tier 0-4 source remains `docs/design/architecture/data/change-risk-taxonomy.json`; this mission does not change the taxonomy. |
| C-003 | proposed | This mission does not implement `felix-change.py`, deterministic mutation wrappers, deployment changes, or prompt deployment to office2. |
| C-004 | proposed | The mission must not directly edit generated Spec Kitty artifacts outside this mission's own `kitty-specs/constitution-risk-tier-autonomy-guard-01KTCXMW/` directory except through normal Spec Kitty workflow commands. |

## Success Criteria

| ID | Criterion | Measurement |
|---|---|---|
| SC-001 | Felix Constitution clearly binds autonomy to risk-tier gates. | Inspection of `docs/constitution/FELIX-CONSTITUTION.md` finds explicit wording that autonomy never overrides the risk-tier protocol. |
| SC-002 | Canonical risk taxonomy is discoverable from the constitution. | `grep -n "change-risk-taxonomy.json" docs/constitution/FELIX-CONSTITUTION.md` returns a match in the new/updated autonomy wording. |
| SC-003 | Tier 0, Tier 1, and Tier 2 obligations are named at principle level. | Inspection confirms Tier 0 is operator-only and Tier 1/2 gates remain required where applicable. |
| SC-004 | Companion context remains consistent. | Implementation notes or diff show `CLAUDE.md`, `.kittify/charter/charter.md`, and `docs/design/architecture/change-control.md` were checked and either unchanged by decision or minimally updated. |
| SC-005 | Documentation validation passes. | `python tooling/scripts/validate_docs.py` exits 0. |

## Out of Scope

- Implementing deterministic mutation tooling such as `felix-change.py`.
- Changing the Tier 0-4 taxonomy.
- Changing deployment mechanics.
- Changing agent autonomy levels, promotion timing, or demotion rules beyond
  clarifying their relationship to risk tiers.
- Deploying updated OpenClaw prompts or workspace files to office2.
- Auditing historical incidents or filing additional follow-on issues.

## Assumptions

- The issue body for #528 is the completed discovery record for this mission.
- A short addition under Directive 2 is the preferred placement unless planning
  discovers a stronger constitution-local pattern.
- No architecture JSON changes are required because the taxonomy itself is not
  changing.
- No `docs/INDEX.md` update is required unless planning adds or moves a
  document; editing an existing constitution page alone does not require an
  index change.

## Dependencies

- **Source issue**: #528.
- **Canonical taxonomy**:
  `docs/design/architecture/data/change-risk-taxonomy.json`.
- **Companion governance references**:
  `CLAUDE.md`, `.kittify/charter/charter.md`,
  `docs/design/architecture/change-control.md`,
  `scripts/openclaw/agents/main/GOVERNANCE.md`.

## Key Entities

- **Autonomy level**: Felix's agent-behavior and activity-surfacing model
  defined in Directive 2.
- **Risk tier**: deployed-change guardrail model defined in
  `change-risk-taxonomy.json`.
- **Tier 0**: operator-only host/foundational changes.
- **Tier 1 / Tier 2 gates**: required verification, approval, backup/snapshot,
  and post-change controls for higher-risk deployed changes.
