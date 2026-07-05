---
title: Cross-Repo Standing Rules Sweep
doc_type: spec
status: approved
owners: [kgale]
last_updated: '2026-07-05'
last_validated: '2026-07-05'
---

# Cross-Repo Standing Rules Sweep

## Intent Summary

Complete GitHub issue #649 by finishing the remaining sweep for universal agent
rules. The primary actor is an agent starting work in a repository other than
kg-automation. The trigger is a new agent session or tooling-bug workflow where
the agent would otherwise miss rules that currently live only in kg-automation
context. The desired outcome is a short canonical standing-rules library that
loads globally and carries only always-on rules, while longer protocols remain
linked in their existing runbooks.

## User Scenarios & Testing

### Primary Scenario: Cross-repo agent receives universal rules

An agent starts in any repository with global Claude context loaded. Before it
posts public copy, files local tracking records, or reports sibling-tool bugs
upstream, it has access to the short universal rules required to avoid the known
failure mode from spec-kitty#2330.

### Exception Scenario: Candidate rule is not universal

During the sweep, a rule appears important but is specific to kg-automation,
office2, a single OpenClaw agent, or a long operational protocol. The mission
must leave that rule in its current source and avoid promoting it into the
always-on cross-repo file.

### Validation Scenario: Standing-rules file remains small

After the sweep, reviewers can inspect the diff and see that the canonical file
is still a concise behavioral layer, not a duplicated template library or
runbook collection.

## Scope

### In Scope

- Sweep kg-automation guidance surfaces for candidate universal agent rules.
- Classify each candidate as universal, repo-specific, agent-specific,
  procedural, unclear, or already represented.
- Update `.agents/rules/cross-repo-standing-rules.md` only when a rule is both
  universal and suitable for always-on context.
- Correct stale or misleading wording in the existing standing-rules file if it
  conflicts with the current linked runbook.
- Record why significant candidates were not promoted when that decision affects
  reviewability.

### Out of Scope

- Changing global `~/.claude/CLAUDE.md` unless a separate explicit approval is
  given.
- Editing `.kittify/`, existing mission artifacts, or unrelated Spec Kitty
  state outside this mission.
- Rewriting long runbooks, issue templates, or agent-specific standing orders.
- Filing upstream issues or posting public comments as part of this mission.

## Domain Language

| Term | Meaning |
| --- | --- |
| Cross-repo standing rule | A short imperative rule that must apply in every repository session. |
| Always-on context | Instruction text loaded into every agent session through the global import path. |
| Linked protocol | A longer runbook or template referenced from the standing rules instead of copied into them. |
| Local tracking record | A local/internal issue, memory, note, or ticket that should not notify external people. |

## Requirements

### Functional Requirements

| ID | Requirement | Status |
| --- | --- | --- |
| FR-001 | The mission MUST inventory candidate universal rules from kg-automation guidance surfaces, including repo guidance, runbooks, constitution-level boundaries, agent rule files, and relevant diagnostics. | Locked |
| FR-002 | The mission MUST classify each reviewed candidate before changing the canonical standing-rules file. | Locked |
| FR-003 | The mission MUST promote a rule into `.agents/rules/cross-repo-standing-rules.md` only when it is universal across repositories, short enough for always-on context, and not already represented. | Locked |
| FR-004 | The mission MUST leave long procedural guidance in its existing runbook or template and link to it instead of duplicating it. | Locked |
| FR-005 | The mission MUST update stale standing-rules wording when the canonical linked runbook has changed, including the current spec-kitty bug-reporting flow. | Locked |
| FR-006 | The mission MUST preserve the public-post copy approval, no local `@mentions`, and dual-track sibling-tool bug-reporting protections already present in the library. | Locked |
| FR-007 | The mission MUST document non-promoted high-signal candidates in a reviewable artifact or mission note when the exclusion is not obvious from the diff. | Proposed |

### Non-Functional Requirements

| ID | Requirement | Status |
| --- | --- | --- |
| NFR-001 | The standing-rules file SHOULD remain short enough to review in under 3 minutes. | Locked |
| NFR-002 | The final diff SHOULD be limited to the canonical standing-rules file and mission-owned artifacts unless validation reveals a necessary adjacent documentation correction. | Locked |
| NFR-003 | The sweep SHOULD avoid reading forbidden private paths and SHOULD not expose local private paths beyond already-approved repo references. | Locked |
| NFR-004 | Validation MUST include the docs validator and a targeted check for stale spec-kitty paste-buffer language in the standing-rules file. | Locked |

### Constraints

| ID | Requirement | Status |
| --- | --- | --- |
| C-001 | The global `~/.claude/CLAUDE.md` import is considered already installed by #649 and is not modified in this mission without explicit operator approval. | Locked |
| C-002 | Public issue or upstream copy changes require exact copy approval before posting. | Locked |
| C-003 | Work must stay isolated from the active `fix/felix-admin-cron-path-fix` mission state. | Locked |
| C-004 | The issue #649 body remains the specification input and the mission closes only the remaining sweep task, not the already-merged bootstrap work. | Locked |

## Success Criteria

| ID | Criterion | Measurement |
| --- | --- | --- |
| SC-001 | Candidate sweep completed | At least the primary repo guidance, standing-rules file, spec-kitty bug-reporting runbook, constitution boundaries, and agent rule surfaces are reviewed. |
| SC-002 | Canonical rule library stays concise | `.agents/rules/cross-repo-standing-rules.md` remains under 80 nonblank lines after the mission unless Kent explicitly approves expansion. |
| SC-003 | Existing protections remain intact | The final standing-rules file still contains public-copy approval, no local `@mentions`, and sibling-tool bug-reporting rules. |
| SC-004 | Stale spec-kitty reporting guidance removed | The standing-rules file no longer instructs agents to generate a separate external paste file when the current runbook says to embed the upstream draft in the internal issue. |
| SC-005 | Validation passes | `python tooling/scripts/validate_docs.py` exits successfully in the mission checkout. |

## Assumptions

- Kent's approval of the execution plan and instruction to start this mission is
  sufficient approval to use #649 as the mission input even though the GitHub
  issue is still labelled `spec: brief`.
- The mission should use a dedicated feature branch to avoid interfering with
  the active `fix/felix-admin-cron-path-fix` mission.
- This mission should not edit global user-level instruction files while another
  Spec Kitty mission is active.

## Architecture & Documentation Impact

This is a Tier 4 documentation/governance change. It does not deploy services,
change credentials, alter data flows, modify network topology, or touch audited
runtime surfaces. The expected live artifact is
`.agents/rules/cross-repo-standing-rules.md`. Architecture JSON and narrative
architecture docs are not expected to change.

Documentation synchronization is limited to validating that linked runbooks and
the standing-rules file do not contradict each other. If the sweep reveals a
separate documentation drift outside the standing-rules library, it should be
recorded rather than folded into this mission unless it directly blocks the
cross-repo rule contract.

## Risks

- Over-promoting repo-specific instructions would bloat global context and make
  unrelated repositories inherit kg-automation operational assumptions.
- Under-promoting true universal rules would preserve the original failure mode:
  agents in other repositories missing required behavioral constraints.
- Editing global user-level instruction files mid-mission could affect other
  active sessions; this mission avoids that surface by default.

## Open Questions

None. Any candidate whose universality is unclear should remain unpromoted and
be called out for operator judgment rather than blocking the mission.
