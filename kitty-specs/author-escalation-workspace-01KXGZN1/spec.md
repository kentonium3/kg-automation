# Feature Specification: Author felix-admin-escalation workspace

**Mission**: author-escalation-workspace-01KXGZN1
**Source issue**: #585 (child of epic #167; absorbs #724)
**Mission type**: software-dev
**Status**: Draft

## Intent Summary

- **Primary actor**: the maintainer authoring OpenClaw agent workspaces (Kent / Felix operator).
- **Trigger**: `felix-admin-escalation`'s workspace files, while passing both #587 shared invariants, are cross-contaminated at the content-ownership level and carry stale references to the deleted Goals project (11).
- **Desired outcome**: each workspace content block lives in its #587-canonical owner file; `SOUL.md` is voice+stance only; `USER.md` is a filtered person-view; operational date-handling and the Goals(11) references are gone from where they don't belong — with **no change to the agent's runtime behavior** (pure clean-separation refactor).
- **Invariant that must hold**: `validate_workspace.py` continues to report `felix-admin-escalation` `ok: true` (privacy enforceable rule stays in AGENTS/TOOLS; Output Discipline block stays in AGENTS).
- **Boundary / scope**: pure refactor — no behavior or content improvements folded in; AGENTS.md size and the fleet-wide `_private` path inconsistency are explicitly out of scope (path deferred to #732).

## User Scenarios & Testing

### Primary scenario (happy path)

1. The maintainer re-homes escalation's content: SOUL's operational `## Purpose` role → already owned by AGENTS; SOUL's full privacy rule → one-line stance (enforceable copy already in AGENTS + TOOLS); USER's `## Date handling` → TOOLS; the SOUL "Kent has ADD…" justification is trimmed off the style bullet.
2. The maintainer absorbs #724: removes the deleted Goals project (11) from TOOLS.md's overdue-query filter and exclusion table, and from the dormant `scripts/vikunja/setup_vikunja.py` saved-filter definitions.
3. `validate_workspace.py` still reports escalation `ok: true`; a content-conservation check confirms nothing substantive was dropped (only re-homed or reduced to a stance whose enforceable copy lives elsewhere).
4. The change merges to `main`; agent-prompt-sync deploys the updated escalation files to office2; repo ↔ office2 md5 parity is verified.
5. A live smoke test confirms escalation's tick behavior is unchanged.

### Exception / edge cases

- **Invariant regression**: if reducing SOUL's privacy block accidentally removes the enforceable rule from its home, Invariant A would fail — the validator must still pass, so the enforceable copy in AGENTS/TOOLS must remain intact.
- **Silent content drop**: a moved block that lands in neither the source nor the destination is a conservation failure — the conservation check must catch it.
- **Scope creep**: touching AGENTS.md content, IDENTITY.md, other agents, or the `_private` path is out of scope; the diff must stay within escalation's SOUL/USER/TOOLS.md + `setup_vikunja.py` + mission artifacts.

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | `SOUL.md` retains only voice/stance content: the `## Voice — write as Kent` section (principles, escalation tone, words/phrases to avoid) is kept; the "Kent has ADD…" justification is trimmed off the "Structured and chunked" bullet while the style rule itself is kept. | Draft |
| FR-002 | `SOUL.md` `## Purpose` operational role block is removed; the "insistence is a feature" idea is preserved as a one-line behavioral stance in `SOUL.md`. The operational role remains owned by `AGENTS.md` (`## Authority`/`## Scope`). | Draft |
| FR-003 | `SOUL.md` `## Privacy boundary` is reduced to a one-line behavioral stance; the enforceable rule text, the filesystem path, and the mission-026 changelog parenthetical are removed from `SOUL.md`. The enforceable copy remains present in `AGENTS.md` and `TOOLS.md`. | Draft |
| FR-004 | `USER.md` retains only the filtered person-view: name / what-to-call / timezone / notes (including "ADD (managed)" as a neutral fact) and the `## Context` block. The `## Date handling` section is removed from `USER.md`. | Draft |
| FR-005 | `TOOLS.md` receives the date-handling content (timezone resolution in America/New_York, ET offset, no-Z-suffix rule) removed from `USER.md`, preserved in substance. | Draft |
| FR-006 | `TOOLS.md` no longer references the deleted Goals project (11): the overdue-query in-agent filter changes from `project_id NOT IN (11, 13)` to `NOT IN (13)`, and the `11 | Goals` row is removed from the project-exclusions table. The `_private` privacy-path line is left unchanged. | Draft |
| FR-007 | `scripts/vikunja/setup_vikunja.py` no longer defines the stale "Goals" saved filter (`project = 11 && done = false`); its other saved-filter definitions are unchanged. | Draft |
| FR-008 | `AGENTS.md` and `IDENTITY.md` are not edited by this mission (they already own the role/authority and are already authored). | Draft |
| FR-009 | The updated escalation workspace files deploy to office2 via agent-prompt-sync on merge to `main` (no `deploys/queued/` manifest); repo ↔ office2 md5 parity is verified post-deploy. | Draft |

### Non-Functional Requirements

| ID | Requirement | Threshold / Measure | Status |
|----|-------------|---------------------|--------|
| NFR-001 | Invariant preservation | `validate_workspace.py` reports `felix-admin-escalation` `ok: true` (both invariants pass) after authoring. | Draft |
| NFR-002 | Scope discipline | The mission diff touches only escalation's `SOUL.md`, `USER.md`, `TOOLS.md`, and `scripts/vikunja/setup_vikunja.py` (plus mission artifacts) — no other agent workspace, no unrelated file. | Draft |
| NFR-003 | Content conservation | 100% of substantive pre-refactor instructions are present post-refactor in their canonical home (verified by a grep/diff conservation check over the moved blocks). | Draft |
| NFR-004 | Behavior preservation | escalation's live tick behavior is unchanged (pure refactor), verified by a post-deploy smoke test producing the correct message shape. | Draft |
| NFR-005 | Deploy parity | Every deployed escalation file's md5 on office2 matches the repo copy at the merged commit. | Draft |

### Constraints

| ID | Constraint | Status |
|----|-----------|--------|
| C-001 | Written against the #587 authoring standard (`docs/design/openclaw-workspace-authoring-standard.md`, on main). Mission branches from current `main` so the standard + validator are in-lane (avoids the #584 mid-mission dependency-merge trap). | Active |
| C-002 | Agent prompt files deploy via agent-prompt-sync on merge-to-main; no `deploys/queued/` manifest is authored (the #636 boundary). | Active |
| C-003 | Rebaseline is expected "not required" — agent prompt files are not hashed by `audit.sh` (#621 gap). The merge commit records the rebaseline decision. | Active |
| C-004 | Pure refactor — no behavior or content improvements are folded in (operator scope call). AGENTS.md size (15KB, no hard cap applies) is left as-is. | Active |
| C-005 | The fleet-wide `_private` privacy-path representation inconsistency is out of scope; it is deferred to #732. escalation's path line is left byte-unchanged. | Active |
| C-006 | Post-merge acceptance criteria (deploy parity, live smoke) are operator-owned and documented in the mission quickstart — they are excluded from the acceptance matrix (the gate rejects post-merge "pending" rows). | Active |
| C-007 | If session rotation is used at deploy, it must be paired with `openclaw gateway restart` per the #583 SOP (rotation can wedge the live WhatsApp DM lane). | Active |

## Success Criteria

1. All three edited workspace files (SOUL/USER/TOOLS) are re-homed to #587 ownership, and every Goals(11) reference is gone from TOOLS.md and `setup_vikunja.py`.
2. `validate_workspace.py` reports escalation `ok: true` (both invariants pass).
3. A content-conservation check confirms no substantive instruction was silently dropped.
4. The change is deployed to office2 via agent-prompt-sync with repo ↔ office2 parity confirmed.
5. A live smoke test confirms escalation's behavior is unchanged.

## Key Entities

- **felix-admin-escalation workspace** — the five OpenClaw bootstrap files at `scripts/openclaw/agents/felix-admin-escalation/` (SOUL / USER / TOOLS / IDENTITY / AGENTS.md). SOUL, USER, TOOLS are edited; AGENTS, IDENTITY are not.
- **#587 ownership model** — the concern→file mapping: SOUL = voice/stance; USER = filtered person-view; TOOLS = environment/setup; AGENTS = operating rules/role; IDENTITY = identity card.
- **Goals project (11)** — a Vikunja project deleted in #717; residual references in escalation TOOLS.md and the dormant `setup_vikunja.py` are the #724 cleanup.
- **agent-prompt-sync** — the office2 pull pipeline (`deploy_agent_prompts.py`, #567/#136/#636) that deploys agent prompt files on merge-to-main.

## Assumptions

- The agent-prompt-sync timer is live on office2 and will deploy the escalation files on the next tick after merge (no manifest required).
- escalation currently passes both #587 invariants (verified at design time via `validate_workspace.py`).
- The date-handling content in USER.md is escalation-relevant operational material whose canonical home under #587 is TOOLS (the exact precedent set by #584 capture).
- "ADD (managed)" in USER notes is retained as a neutral person-fact (the #583 main precedent), while the SOUL "Kent has ADD…" *justification* is trimmed (the #584 capture precedent) — the two precedents are consistent, not conflicting.
