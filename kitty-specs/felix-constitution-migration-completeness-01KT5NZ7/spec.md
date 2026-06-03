# Felix Constitution — Migration Completeness Directive

**Mission**: `felix-constitution-migration-completeness-01KT5NZ7`
**Mission type**: software-dev
**Source issue**: [#514](https://github.com/kentonium3/kg-automation/issues/514)
**Target branch**: `main`
**Created**: 2026-06-02

---

## Intent Summary

Add Directive 7 to the Felix Constitution at `docs/constitution/FELIX-CONSTITUTION.md`, codifying the rule that a migration is not done until all transitional artifacts (parity writes, v1 substrates, dead readers, soak-window scaffolding, doc references to the transitional phase) are removed. The directive's enforcement mechanism is the existing charter-context loading flow — agents driving spec-kitty already consult the constitution via `spec-kitty charter context --action specify --json`, so once Directive 7 is in the file, future migration missions will pick it up at specify and plan time without any spec-kitty template surgery (per #514 C-003).

## Background & Motivation

Two recent failures share the same root cause: cleanup work that follows a substrate migration has no forcing function and drifts indefinitely.

- **#309 → #376**: the escalation→JSONL migration shipped a parity dual-write (Vikunja `[Felix-Escalation]` comments alongside JSONL records) as soak-window safety. The cleanup phase was filed as follow-on issue #376 and gated on a 3-day soak-window checklist. The checklist never got filled in. The dual-write ran 12+ days past the planned soak end, with no runtime consumer reading the v1 comments — pure write-only dead weight on every escalation event. Mission #62 (`remove-escalation-v1-parity-01KT4VTD`) finally cleared it on 2026-06-02.
- **OpenClaw v2026.3.24 → v2026.5.28** upgrade on 2026-06-01: the upgrade migrated WhatsApp from a built-in module to an external plugin, but the migration step (`openclaw plugins install clawhub:@openclaw/whatsapp`) wasn't tracked in any issue or runbook. The system ran in a half-migrated state for 19 hours before being noticed — `habits-morning-checkin`, `inbox-7am`, `escalation-daily`, and other crons all failed with `Unsupported channel: whatsapp`.

Both incidents share the pattern: the migration's cleanup or follow-through step had no forcing function, so the system drifted into a half-completed state. Kent stated the principle directly on 2026-06-02: *"I really despise dev actions that leave this kind of debt behind. Clean it up... the definition of done for a migration is there are no unnecessary vestiges of the migration."*

This mission codifies that principle in the constitution so the next migration's `/spec-kitty.specify` and `/spec-kitty.plan` run pick it up via charter context and route the spec author to enumerate transitional artifacts up front.

## User Scenarios & Testing

### Primary scenario: future migration mission picks up the directive

1. A future operator (or agent driving spec-kitty autonomously) invokes `/spec-kitty.specify` for a mission that introduces a new substrate or replaces an existing one.
2. The agent runs `spec-kitty charter context --action specify --json`. The charter context now surfaces Directive 7 as applicable governance.
3. The spec author (operator or LLM) enumerates the mission's transitional artifacts (parity writes, dead readers, dual-write paths, etc.) and decides whether to (a) sequence their removal as late WPs within the same mission with an explicit gate, or (b) explicitly accept them as permanent infrastructure with renamed framing.
4. The mission's spec, plan, and tasks reflect Directive 7's structure; the cleanup step is no longer a follow-on issue with no forcing function.

### Secondary scenario: validating an existing or near-finished migration

1. An operator reviewing a mission near completion checks the spec against Directive 7's two-part definition of done.
2. If the migration's substrate is shipped but transitional artifacts remain, the operator either (a) opens a tracking follow-on with an explicit forcing function per Directive 7's deferral allowance, or (b) cleans up within the same mission before declaring it complete.

### Edge cases

- **Migration with no transitional artifacts** (rare — pure substitution with no dual-write): the directive's enumeration step trivially produces an empty list; the mission proceeds normally.
- **Migration whose transitional artifact is genuinely permanent** (e.g., a feature flag intended as a long-term toggle): the directive explicitly permits accepting the artifact as permanent infrastructure with the framing renamed — option (b) in the proposed text.
- **Multi-mission migrations sequenced across calendar quarters**: the directive's deferral allowance permits a follow-on issue, provided the original mission's spec acknowledges the weak link explicitly.

## Requirements

### Functional

| ID | Status | Requirement |
|---|---|---|
| FR-001 | proposed | Add a new directive titled **Directive 7: Migration completeness — no orphaned transitional artifacts** to `docs/constitution/FELIX-CONSTITUTION.md`, inserted between Directive 6 (Deterministic Detection, AI Interpretation) and the "Privacy and Communication Boundaries" section. |
| FR-002 | proposed | The directive's prose MUST follow the same format as Directives 1 through 6: title as a level-2 heading; opening sentence stating the principle; explanatory bullet list or paragraphs; a closing "Rationale:" paragraph grounded in concrete incidents. |
| FR-003 | proposed | The directive body MUST include the two-part definition of done from #514: (1) new substrate in production AND (2) all transitional artifacts removed. It MUST enumerate the categories of transitional artifacts to consider (parity writes, v1 readers, dual-write code paths, schema fields kept only for the old shape, feature flags that gate the swap, dead callers, docstrings/comments that describe the old shape or the soak phase). |
| FR-004 | proposed | The directive MUST permit the "follow-on issue" pattern only with explicit conditions — the cleanup work has its own owner and forcing function, AND the original mission's spec acknowledges the deferral as a known weak link. |
| FR-005 | proposed | The rationale section MUST cite at least two concrete incidents: #309 → #376 (escalation parity dual-write that drifted 12+ days) and the OpenClaw v2026.5.28 plugin migration (19-hour silent gap). |
| FR-006 | proposed | The mission MUST cross-reference the `feedback_migration_no_vestiges` operator memory in the directive's body where the memory's principle applies, so the link from constitution → operator memory is traceable. |

### Non-Functional

| ID | Status | Requirement |
|---|---|---|
| NFR-001 | proposed | The directive prose MUST be reviewable in ≤5 minutes by an operator new to the codebase (per #514 NFR-001). |
| NFR-002 | proposed | No other content in `FELIX-CONSTITUTION.md` MAY be altered by this mission. The mission's diff is constrained to inserting one new directive section plus any minimal Reference Index update if such a section enumerates directives by number. |
| NFR-003 | proposed | No code changes. No test changes. No architecture-data changes. The mission is a constitution-only edit. |

### Constraints

| ID | Status | Constraint |
|---|---|---|
| C-001 | proposed | Tier classification: Tier 4 (Auto-Commit — Schema/Metadata / governance documentation). No pre-flight checklist required. |
| C-002 | proposed | Enforcement mechanism is charter-context loading (`spec-kitty charter context --action <action> --json`), NOT spec-kitty CLI template modification (which is upstream-owned per #514 C-003). |
| C-003 | proposed | The directive number MUST be 7 (the next unused number after Directive 6). Confirmed via `grep -E "^## Directive [0-9]+:" docs/constitution/FELIX-CONSTITUTION.md` returning 1 through 6. |
| C-004 | proposed | `docs/constitution/AGENT-REGISTRY.md` does NOT currently enumerate directives by number (verified during specify), so no registry update is required. If a future audit identifies a directive index elsewhere, that update is out of scope for this mission. |

## Success Criteria

| ID | Criterion | Measurement |
|---|---|---|
| SC-001 | Directive 7 exists in `docs/constitution/FELIX-CONSTITUTION.md` between Directive 6 and the "Privacy and Communication Boundaries" section. | `grep -nE "^## Directive 7:" docs/constitution/FELIX-CONSTITUTION.md` returns exactly one match; the match's line number falls between the Directive 6 heading and the Privacy heading. |
| SC-002 | The directive's prose includes the two-part definition of done and enumerates the artifact categories. | Inspection. |
| SC-003 | The directive's rationale cites #309/#376 and the OpenClaw v2026.5.28 incident. | `grep -E "#309\|#376\|v2026\.5\.28" docs/constitution/FELIX-CONSTITUTION.md` returns matches inside the Directive 7 section. |
| SC-004 | A future `/spec-kitty.specify` or `/spec-kitty.plan` for a migration mission picks up the directive via charter context. | Verifiable in the next migration mission's spec doc; out-of-scope for this mission's acceptance, but called out here as the operational confirmation. |

## Out of Scope

- Modifying spec-kitty's command templates or CLI (upstream-owned per #514 C-003 and confirmed during the #514 FR-003 drop).
- Modifying any agent prompt, runbook, architecture data, or code file.
- Creating helper scripts or automation. The directive's enforcement is charter-context loading; no new tooling is introduced.
- Retroactively auditing existing missions for Directive 7 compliance.

## Assumptions

- The Felix Constitution at `docs/constitution/FELIX-CONSTITUTION.md` is the canonical governance doc and is loaded by `spec-kitty charter context`. Verified during recent mission #62.
- Agent profile loading already consults the constitution during `specify` and `plan` action contexts. Verified during recent mission flows.
- `docs/constitution/AGENT-REGISTRY.md` does not enumerate directives by number (verified by grep during specify); no cross-reference update is needed.
- Operator memory `feedback_migration_no_vestiges` already exists (saved during the #376 review session); the directive cross-references it rather than re-stating its body.

## Dependencies

- **Operator memory**: `feedback_migration_no_vestiges` (already saved 2026-06-02).
- **Related missions**: #62 (`remove-escalation-v1-parity-01KT4VTD`) is the worked example the directive draws on for one of its cited incidents.
- **Reference memory**: `reference_openclaw_upgrade_gotchas` documents the OpenClaw incident the directive cites.

## Key Entities

- **Directive 7**: the new constitution section being added. Located in `docs/constitution/FELIX-CONSTITUTION.md` between Directive 6 and "Privacy and Communication Boundaries".
- **Charter-context loading flow**: `spec-kitty charter context --action <action> --json` is the existing surface that surfaces governance directives to agents driving the workflow. Directive 7 will reach future missions via this flow without any CLI template change.
