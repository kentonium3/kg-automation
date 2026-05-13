# Spec: Auto-apply audit edits; gate reserved for future judgment classes

**Mission**: `auto-apply-audit-edits-01KRG1BG`
**Source issue**: [#259](https://github.com/kentonium3/kg-automation/issues/259)
**Mission type**: `software-dev`
**Status**: draft
**Target branch**: `main`

## Summary

The felix-doc-auditor agent currently routes every edit-bearing audit through a Level-1 approval gate (AGENTS.md § 7.9 + § 7.10), regardless of the proposed edit's `change_type`. Every `frontmatter_date`, `version_bump`, `path_rename`, `dead_ref_removal`, `registry_entry_add`, and `registry_autonomy_update` edit produces a pending-approval GitHub issue that requires Kent's manual `audit-approve` label before the auditor can commit.

This is structural over-gating. The auditor's existing `change_type` enumeration is by definition the "deterministic-known-fix" surface: if the auditor emitted an edit proposal of one of those types, it identified the drift AND the correct value from a system-state source (commit history, filesystem, registry source, etc.). No human judgment is needed. Cases that *do* require judgment — prose drift, content gaps, missing context — are already routed by § 7.8 to autonomous `docs-debt` issues, which is the right place for them.

This mission removes the gate for known change_types by:
1. Codifying the invariant in § 7.5: edit proposals are only emitted when the correct value is deterministic; judgment cases become docs-debt instead.
2. Adding `route_audit_decisions.py` that partitions an audit's edit proposals into auto-apply (known change_types in an allowlist) and gate (anything else — fail-safe).
3. Updating § 7.9 routing to invoke the script and act on its partition.
4. Mirroring AGENTS.md changes to AGENTS.md.tmpl (C-002).

The result: `frontmatter_date`-only audits commit and close in the same cron tick they detect drift. Kent's notifications compress to docs-debt issues (judgment-required) and the rare gate (only triggered by future change_types not yet in the allowlist).

## User Scenarios & Testing

### Primary scenario — frontmatter_date-only audit auto-applies

**As** Felix doc-auditor (currently Level 1 / Assisted),
**when** I detect frontmatter drift on a doc directly modified by a commit and emit a single `frontmatter_date` edit proposal,
**then** I commit the proposed edit in the same cron tick, post the audit summary on the originating audit issue, and close both audit and any associated tracking state,
**so that** Kent is not notified for a mechanical date bump whose correct value I already computed.

**Acceptance**:
- Audit cycle producing only known change_types commits and closes the originating audit without filing an `audit-pending-approval` issue.
- Audit summary posted on originating audit issue includes the change_type, file path, and commit SHA.
- No `audit-pending-approval` issue exists for that audit cycle.

### Secondary scenario — unknown change_type fail-safes to gate

**As** Felix doc-auditor,
**when** I emit an edit proposal of a `change_type` not in the auto-apply allowlist (e.g., a future `prose_replacement` class added to the auditor),
**then** I file a pending-approval issue covering that edit and exit the turn,
**so that** Kent reviews edit classes that haven't yet been vetted into the allowlist.

**Acceptance**:
- Given an audit with an `unknown_change_type` edit proposal, an `audit-pending-approval` issue is filed and the auditor exits without auto-committing.
- The pending-approval body identifies which edits could not be auto-applied and why (allowlist miss).

### Tertiary scenario — mixed audit (some auto, some gated)

**As** Felix doc-auditor,
**when** I emit a mix of known and unknown change_types in a single audit,
**then** I auto-commit the known set, then file a pending-approval issue covering only the unknown set,
**so that** mechanical work doesn't sit waiting for a human review of orthogonal judgment work.

**Acceptance**:
- Auto-commit happens before the pending-approval issue is filed.
- Pending-approval issue's "Proposed edits" section lists only the gated edits (the auto-applied ones are reported in the audit summary on the originating audit issue, not the pending-approval).

### Edge cases

- **Empty audit** (zero edits, zero debt): unchanged — § 7.9 already handles this autonomously.
- **Debt-only audit** (zero edits, debt filed by § 7.8): unchanged — autonomous, no gate.
- **All-known auto-apply but commit fails** (e.g., conflict): treat as commit error per existing § 7.11 error handling; do not file gate as fallback.
- **Existing pending-approvals** (#236, #249, #250 as of 2026-05-13): out of scope. They remain as test cases per the originating issue; Kent will manually `audit-approve` to drain them after verification.

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | Add `scripts/openclaw/agents/felix-doc-auditor/route_audit_decisions.py` that accepts a JSON tempfile (`@<path>` convention) containing serialized Edit Proposals (data-model E-004 shape) and returns a partition: `{auto_apply: [...], gated: [...]}` based on whether each proposal's `change_type` appears in a hardcoded auto-apply allowlist. | proposed |
| FR-002 | The auto-apply allowlist must include all current change_types: `frontmatter_date`, `version_bump`, `path_rename`, `dead_ref_removal`, `registry_entry_add`, `registry_autonomy_update`. Future change_types default to the `gated` set (fail-safe). | proposed |
| FR-003 | Update `scripts/openclaw/agents/felix-doc-auditor/AGENTS.md` § 7.5 to state the invariant: edit proposals are emitted only when the correct value is deterministically known from a system-state source; judgment-required cases become docs-debt issues per § 7.8. | proposed |
| FR-004 | Update `AGENTS.md` § 7.9 routing to (a) invoke `route_audit_decisions.py` on the serialized proposals, (b) auto-commit the auto-apply partition per § 7.11, (c) file a pending-approval issue covering only the gated partition (if any) per § 7.10, (d) post the audit summary on the originating audit issue covering all applied edits. | proposed |
| FR-005 | Update `AGENTS.md.tmpl` identically (C-002). | proposed |
| FR-006 | Add unit tests in `tests/openclaw/agents/felix-doc-auditor/` (or matching existing test location) covering: all-known-auto, all-unknown-gate, mixed partition, empty input, malformed JSON. | proposed |

### Non-Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| NFR-001 | `route_audit_decisions.py` completes within 100 ms on a typical audit (≤ 10 edit proposals). | proposed |
| NFR-002 | No new pip dependencies — stdlib only. | proposed |
| NFR-003 | Inference token budget on a `frontmatter_date`-only audit drops by ≥ 50% compared to current (LLM no longer reasons through the routing decision), measured via openclaw `cron runs` usage `total_tokens` field on comparable audits before and after. | proposed |

### Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | The auto-apply allowlist lives in the script, not in AGENTS.md prose. AGENTS.md describes the *invariant* and *behavior*; the script is the source of truth for *which change_types* are auto-apply. | accepted |
| C-002 | AGENTS.md and AGENTS.md.tmpl are the contract surface and must be updated together (template/runtime drift would re-introduce the bug). | accepted |
| C-003 | The existing § 7.10 pending-approval-issue logic is retained — the routing change narrows when it's invoked, not what it does when invoked. This preserves backward compatibility for the rare gated-edit case. | accepted |
| C-004 | The script is doc-auditor-specific and lives next to the agent files (`scripts/openclaw/agents/felix-doc-auditor/`), not in a generic `scripts/inbox/` style location. | accepted |
| C-005 | This mission does NOT promote felix-doc-auditor's autonomy level. The Constitution requires Kent's explicit decision for level changes (per Directive 2). | accepted |
| C-006 | The 3 existing pending-approvals (#236, #249, #250) are explicitly preserved as test cases — not closed or auto-resolved by this mission. They will be drained by Kent's normal `audit-approve` labels after the new logic is verified on a fresh audit cycle. | accepted |

## Success Criteria

- **SC-001**: After deploy, a fresh audit cycle producing only known-change_type edits auto-commits and closes the originating audit without filing an `audit-pending-approval` issue.
- **SC-002**: A synthetic test audit with a fabricated `unknown_change_type` edit proposal still produces a pending-approval issue (fail-safe behavior preserved).
- **SC-003**: The 3 existing pending-approvals (#236, #249, #250) remain open and unchanged after the deploy; they are drained by Kent's manual `audit-approve` action as a post-deploy verification step.
- **SC-004**: Measured token budget on a comparable `frontmatter_date`-only audit (pre- vs. post-mission) shows ≥ 50% reduction in `total_tokens` per the cron-run usage entry.

## Assumptions

- The auditor already produces structured Edit Proposals (data-model E-004) — confirmed by AGENTS.md § 7.5. Serializing them to a tempfile is straightforward.
- felix-doc-auditor remains at Level 1 (Assisted) for this mission; the script-based routing simplification is orthogonal to autonomy level.
- The deploy mechanism for felix-doc-auditor (per `reference_felix_doc_auditor_ops.md` — hourly systemd-user timer on office2) does not need changes; the new script and updated AGENTS.md ride the existing deploy pipeline.

## Dependencies

- Builds on the **Self-documenting system epic** (roadmap entry); reduces manual-review surface area in the same direction as #105 / #198 work.
- No dependency on other open missions.

## Out of Scope

- Promoting felix-doc-auditor to Level 2 (Observed) — separate Constitution decision per Directive 2.
- Retroactive auto-resolution of #236, #249, #250.
- Adding new change_types or modifying the existing classification logic in § 7.5.
- Changing the docs-debt issue path (§ 7.8) — that flow remains untouched.
- Modifying the `docs-debt` template or autonomous filing behavior.
