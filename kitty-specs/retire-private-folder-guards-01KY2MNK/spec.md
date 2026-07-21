# Specification: Retire _private folder guard apparatus

**Mission**: retire-private-folder-guards-01KY2MNK
**Type**: software-dev
**Status**: draft
**Tracking issue**: kentonium3/kg-automation#848

## Summary

The private growth-work folder (`_private`, formerly under the second-brain vault's Growth
directory) has been moved to a separate Obsidian vault synced only to Kent's laptop and phone;
office2 never joins it. The folder was deleted and its deletion has propagated away from office2
(verified absent). The privacy boundary is now enforced by **physical exclusion** — the sensitive
content is *never present* on the machine Felix runs on — which supersedes the previous in-repo
"never touch `_private`" apparatus.

That apparatus (a lint validator + a CI step + a local pre-commit hook + workspace-validator
invariants + a red-line in every deployed agent prompt + governance/design/runbook prose) now
guards a directory that does not exist. It is stale, misleading, and encodes a model that has been
replaced. This mission **removes the folder-specific apparatus**, **keeps and generalizes** the
still-valuable general vault-path hygiene, and **reframes the graph-ingest privacy model** to
"verify not present".

## Domain Language

- **Physical exclusion** — the resolved privacy model: the private folder lives only on
  devices Felix cannot reach, so its content is never present to be read, written, ingested, or
  leaked. "Never present" replaces "never touched".
- **Folder-specific apparatus** — the in-repo mechanisms whose sole purpose was protecting the
  named `_private` folder: the stale-path lint validator, its CI/pre-commit/Makefile/adapter
  wiring, the workspace-validator privacy invariants, the enforceable per-agent-prompt red-line,
  and the "absolute rule" prose in governance/design/runbook docs.
- **General vault hygiene** — privacy-adjacent behavior that is valuable regardless of the folder:
  redacting vault paths out of surfaced alerts, and refusing to write to arbitrary vault paths.
  Retained and generalized (decoupled from the specific folder).
- **Second-brain repo boundary** — the standing rule that the second brain is a separate repo and
  kg-automation tasks do not write to it. Distinct from the folder guard; **retained**.

## User Scenarios & Testing

### Primary scenario — a maintainer authors an agent prompt after the purge
An engineer (or an authoring agent) edits an OpenClaw agent workspace and runs the workspace
validator. It passes without requiring a `_private` privacy red-line, because that invariant has
been removed. The cleaned prompt deploys to the running fleet via the existing agent-prompt-sync
path, and the agent behaves correctly (post-deploy smoke passes).

### Secondary scenario — the general hygiene still holds
A caller smuggles a vault-looking path into an escalation title/body/URL, or asks to mark-process a
file outside the allowed inbox area. The system still redacts the vault path from the surfaced
alert and still refuses the out-of-area write — the protection is retained, now expressed as a
general vault-path rule rather than keyed on the defunct folder.

### Edge case — an unrelated "private" feature must not regress
The Vikunja "private project" feature (whose task views carry an `is_private` field) is a different
concept from the vault folder. It and its tests are left entirely unchanged.

### Edge case — ordering safety
No guard is removed while the protected data could still be present. The private folder's absence
from office2 is verified *before* any guard removal, so there is never a
guard-gone-while-data-present window.

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | The folder-specific privacy-boundary lint validator is removed, along with every invocation of it — the local pre-commit hook step, the CI workflow step, the Makefile target, and the autopilot-adapter reference — so it no longer runs anywhere. | Draft |
| FR-002 | The workspace-authoring validator no longer enforces the folder-specific privacy red-line: its privacy-boundary and privacy-path-canonical invariants (and their supporting constants and owner-set config) are removed, and its test suite and the standalone privacy-pointer guard test are updated/removed accordingly. | Draft |
| FR-003 | The enforceable `_private` red-line is removed from every deployed agent prompt (all affected agents), and the cleaned prompts are deployed to the running fleet on office2. | Draft |
| FR-004 | Governance and instruction docs (root agent instructions, the alternate-agent instructions, the per-tool instruction files, and the constitution) no longer state the `_private` "absolute rule"; the general "the second brain is a separate repo; do not write to second-brain paths" guidance is retained. | Draft |
| FR-005 | Design, architecture, and runbook docs that presented the folder rule as a *current, enforced guard* are reframed to the physical-exclusion model (the boundary is now the folder's absence, not an in-repo rule). | Draft |
| FR-006 | The graph-ingest privacy model in the second-brain-graph-layer / executive-assistant-architecture design is reframed from "never ingest `_private`" enforcement to "verify the private content is not present" (physical exclusion), replacing the old gate description with the new mechanism. | Draft |
| FR-007 | The general vault hygiene is retained and generalized: vault paths are still redacted from surfaced alert output, and writes to arbitrary vault paths are still refused — both decoupled from the specific `_private` folder so they no longer depend on that folder existing. | Draft |
| FR-008 | Functionality that merely shares the word "private" but is unrelated to the vault folder (e.g., the Vikunja private-project handling and its `is_private` field) is left unchanged. | Draft |

### Non-Functional Requirements

| ID | Requirement | Threshold / Measure | Status |
|----|-------------|---------------------|--------|
| NFR-001 | Removal leaves the gates green. | Local pre-commit and CI complete successfully with no privacy-boundary lint step; the full `tests/` suite passes (0 failures). | Draft |
| NFR-002 | Ordering safety is preserved. | The private folder's absence from office2 is verified before the first guard is removed; the mission records that verification. 0 guard-gone-while-data-present windows. | Draft |
| NFR-003 | General-hygiene coverage is not weakened. | The redaction and refuse-write behaviors retain test coverage with at least as many leak/refusal assertions as before; those tests pass. | Draft |
| NFR-004 | Deployed prompts match the repo after redeploy. | Every affected agent's deployed prompt files match the repo (content/md5 parity) and each affected agent passes a post-deploy smoke. | Draft |

### Constraints

| ID | Constraint | Status |
|----|------------|--------|
| C-001 | Do not create, edit, move, or delete frozen or workflow-owned surfaces: `docs/archive/`, `kitty-specs/`, `.kittify/` (except this mission's own artifacts). The migration runbook's intentional dual-path documentation stays as-is. | Draft |
| C-002 | This mission removes only the folder-specific apparatus. It must NOT remove the general vault-boundary hygiene (redaction, refuse-write) or the second-brain-repo boundary. | Draft |
| C-003 | Agent-prompt changes deploy through the existing agent-prompt-sync mechanism (no new deploy manifest). Rebaseline is handled per the audited-surface protocol — agent prompts are not content-hashed by the security audit, so a rebaseline is expected to be not-required; this must be confirmed against the live audit rather than assumed. | Draft |
| C-004 | The change is behavior-preserving for every path except the removed folder guard: no unrelated agent behavior, alert content, or inbox routing changes. | Draft |

## Success Criteria

- **SC-001**: A search for the folder-specific enforcement token across live surfaces (excluding
  `docs/archive/`, `kitty-specs/`, `.kittify/`, and the migration-runbook allowlist) returns no
  remaining *enforcement* occurrences — only, at most, intentional physical-exclusion narrative.
- **SC-002**: Local commit gates and CI pass with the privacy-boundary lint fully removed.
- **SC-003**: All affected agents deploy cleanly to office2 (prompt parity) and pass a post-deploy
  smoke.
- **SC-004**: The general hygiene still prevents vault-path leakage into alerts and still refuses
  arbitrary vault writes — verified by the retained, generalized tests.
- **SC-005**: No unrelated functionality changes — the Vikunja private-project feature and its
  tests remain untouched and green.
- **SC-006**: The graph-ingest privacy model is documented as "verify not present" (physical
  exclusion) in the second-brain-graph / EA-architecture design, with no lingering "never ingest
  `_private`" enforcement language.

## Assumptions

- The private folder's move to a laptop/phone-only vault is complete and its deletion has synced
  away from office2 (verified 2026-07-21). office2 will not re-join that vault.
- Transformation *handles* (public-facing goal/outcome names) are not sensitive; only the
  psychological work behind them is — and that work is what moved out. Felix may continue to hold
  public handles ("structure without content").
- Removing the workspace-validator privacy invariants does not weaken any *other* invariant the
  validator enforces (output-discipline, staleness, byte budgets, etc. are untouched).

## Out of Scope

- Building the new `_private`-not-present *ingest-time* runtime check for the graph pipeline —
  that pipeline does not exist yet; this mission reframes the *design/model* to "verify not
  present", and the runtime verification is implemented when the ingest pipeline is built (#696).
- Any change to the second-brain repository itself or to the separate private vault.
- Any change to the Vikunja private-project feature.
