# Feature Specification: Author felix-admin-habits workspace

**Mission**: author-habits-workspace-01KXX9JZ
**Source issue**: #582 (child of epic #167)
**Mission type**: software-dev
**Status**: Draft

## Intent Summary

- **Primary actor**: the maintainer authoring OpenClaw agent workspaces (Kent / Felix operator).
- **Trigger**: `felix-admin-habits`'s workspace files, while passing all four #587 shared invariants, are cross-contaminated at the content-ownership level and carry stale text — SOUL duplicates the role, the weekly-report scope boundary, and the full enforceable privacy rule; USER carries operational date mechanics plus a now-false claim that the agent reports on patterns; TOOLS inlines volatile Vikunja habit task IDs.
- **Desired outcome**: each workspace content block lives in its #587-canonical owner file; `SOUL.md` is voice+stance only; `USER.md` is a filtered person-view whose scope description is accurate; `TOOLS.md` documents the real surface without inlining volatile IDs and receives the date-handling — with **no change to the agent's runtime behavior** (behavior-preserving clean-separation refactor).
- **Invariant that must hold**: `validate_workspace.py` continues to report `felix-admin-habits` `ok: true` (privacy enforceable rule stays in AGENTS/TOOLS; Output Discipline block stays in AGENTS).
- **Boundary / scope**: behavior-preserving refactor plus one stale-text correction (the USER "reports on patterns" claim) and de-inlining of volatile IDs. No feature/behavior additions. #409's weekly-report ownership question is already resolved (owned by the `felix-habits-weekly` deterministic timer, #723; dedicated LLM agent declined, #796) — this mission confirms the resolution is coherently expressed, it does not reopen it.

## User Scenarios & Testing

### Primary scenario (happy path)

1. The maintainer re-homes habits' content: SOUL's `## Purpose` role → already owned by AGENTS (`## Authority`/`## Scope`); SOUL's `## Weekly report — out of scope` block → already owned by AGENTS (`## Weekly report — out of scope`), so the SOUL duplicate is removed; SOUL's full `## Privacy boundary` → one-line stance (enforceable copy already in AGENTS + TOOLS); the "Kent has ADD…" justification is trimmed off the "Structured and chunked" style bullet while the style rule itself is kept.
2. The maintainer corrects USER: the `## Date handling` section moves to TOOLS; the `## Context` claim that the agent "report[s] on patterns over time" is corrected to the true scope (deliver daily check-ins + record completions) since weekly reporting moved off this agent to the `felix-habits-weekly` timer (#723).
3. The maintainer cleans TOOLS: the inlined volatile Vikunja IDs (`Habits` project `id=13` parenthetical and the `Habit task IDs: 14-20` line) are removed in favor of name-based resolution at runtime; TOOLS receives the date-handling content; the completion-comment storage contract is retained.
4. `validate_workspace.py` still reports habits `ok: true`; a content-conservation check confirms nothing substantive was dropped (only re-homed, reduced to a stance whose enforceable copy lives elsewhere, or a deliberate stale-text/ID removal).
5. The change merges to `main`; agent-prompt-sync deploys the updated habits files to office2; repo ↔ office2 md5 parity is verified at the correct destination directory.
6. A live smoke test confirms habits' morning check-in behavior is unchanged.

### Exception / edge cases

- **Invariant regression**: if reducing SOUL's privacy block accidentally removes the enforceable rule from its home, Invariant A would fail — the validator must still pass, so the enforceable copy in AGENTS/TOOLS must remain intact.
- **Silent content drop**: a moved block that lands in neither the source nor the destination is a conservation failure — the conservation check must catch it.
- **Scope creep**: AGENTS.md and IDENTITY.md are not edited except for a narrow truthfulness correction to AGENTS if (and only if) it references SOUL as a privacy-enforcement home. The diff must stay within the NFR-002 file set.
- **De-inline safety (FR-008)**: removing the inlined habit task IDs from TOOLS must not change behavior — the morning-list and completion helpers resolve the Habits project and tasks by name at runtime, so the IDs in TOOLS are documentation, not runtime config. If any runtime path actually depended on those literal IDs, de-inlining would be a behavior change and must be revisited.
- **Weekly-report coherence (FR-003)**: after removing SOUL's weekly-out-of-scope duplicate, the single authoritative statement must remain in AGENTS — the agent must still treat weekly reports as out of scope. Removing both copies would be a regression.

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | `SOUL.md` retains only voice/stance content: the `## Voice — write as Kent` section (principles, words/phrases to avoid, words/phrases that are Kent) is kept; the "Kent has ADD and processes best…" justification is trimmed off the "Structured and chunked" bullet while the style rule itself is kept. | Draft |
| FR-002 | `SOUL.md` `## Purpose` operational role block is removed. The operational role remains owned by `AGENTS.md` (`## Authority`/`## Scope`); no role text remains in SOUL. | Draft |
| FR-003 | `SOUL.md` `## Weekly report — out of scope` block is removed as a duplicate; the authoritative weekly-report-out-of-scope statement remains owned by `AGENTS.md` (`## Weekly report — out of scope`). This is the #409 incorporation: the SOUL-vs-AGENTS weekly-report conflict is resolved by keeping the single coherent statement in AGENTS. | Draft |
| FR-004 | `SOUL.md` `## Privacy boundary` is reduced to a one-line behavioral stance (e.g. "I work only where I'm invited"); the enforceable rule text, the filesystem path, and the mission-026/#152 changelog parenthetical are removed from `SOUL.md`. The enforceable copy remains present in `AGENTS.md` and `TOOLS.md`. | Draft |
| FR-005 | `USER.md` retains only the filtered person-view: name / what-to-call / timezone / notes (including "ADD (managed)" as a neutral fact) and a corrected `## Context` block. The `## Date handling` section is removed from `USER.md`. | Draft |
| FR-006 | `USER.md` `## Context` is corrected: the claim that the agent "report[s] on patterns over time" is removed; the block accurately describes the agent's scope (deliver daily habit check-ins via WhatsApp and record completions in Vikunja). Weekly pattern reporting is owned by the `felix-habits-weekly` timer (#723), not this agent. | Draft |
| FR-007 | `TOOLS.md` receives the date-handling content (timezone resolution in America/New_York, ET offset, no-Z-suffix rule) removed from `USER.md`, preserved in substance. | Draft |
| FR-008 | `TOOLS.md` no longer inlines volatile Vikunja IDs: the `Habits` project `(id=13)` parenthetical and the `Habit task IDs: 14-20 (…)` line are removed; TOOLS instructs name-based resolution of the Habits project and its habit tasks at runtime via the `vikunja_api` skill. The completion-comment storage contract (one task per habit; idempotent daily completion comment; comment format) is retained. | Draft |
| FR-009 | `IDENTITY.md` is not edited. `AGENTS.md` receives **only** a narrow truthfulness correction if it references `SOUL.md` as a privacy-enforcement home (mirroring the #585 FR-012 precedent); if AGENTS carries no such reference, AGENTS is left untouched. No other AGENTS content changes. | Draft |
| FR-010 | The updated habits workspace files deploy to office2 via agent-prompt-sync on merge to `main` (no `deploys/queued/` manifest); repo ↔ office2 md5 parity is verified post-deploy at the correct destination directory (agent slug ≠ deploy dir — the directory is confirmed at deploy time, not assumed). | Draft |
| FR-011 | #409 (SOUL-vs-AGENTS weekly-report standing-orders conflict) is confirmed resolved and incorporated: after FR-003 there is a single authoritative weekly-report-out-of-scope statement (in AGENTS), no contradiction remains, and #409 stays closed with a pointer to this mission. | Draft |

### Non-Functional Requirements

| ID | Requirement | Threshold / Measure | Status |
|----|-------------|---------------------|--------|
| NFR-001 | Invariant preservation | A habits-SCOPED assertion (parse `validate_workspace.py --json`, assert the `felix-admin-habits` object has `ok: true`) passes. Whole-fleet exit code is NOT used (calendar/#635 fails Invariant B, out of scope). | Draft |
| NFR-002 | Scope discipline | The mission diff touches only: habits `SOUL.md`/`USER.md`/`TOOLS.md` (and `AGENTS.md` narrowly, FR-009 only, if warranted) plus mission artifacts — no other agent, no IDENTITY.md, no unrelated file. | Draft |
| NFR-003 | Content conservation | A row-by-row conservation checklist (derived from the data-model move-table) passes: every "keep"/"move" block is present in its destination; the enforceable privacy token is in BOTH AGENTS.md and TOOLS.md AND absent from SOUL.md; the weekly-out-of-scope statement is present in AGENTS.md AND absent from SOUL.md; every "delete" is a deliberate stale-text/ID removal. | Draft |
| NFR-004 | Behavior preservation | Deterministic evidence: before/after output of the morning-list helper (the tick workflow's Step 1 helper) for the same input/date is identical. Plus a post-deploy live smoke producing the correct check-in message shape. | Draft |
| NFR-005 | Deploy parity | Every deployed habits file's md5 on office2 matches the repo copy at the merged commit. | Draft |

### Constraints

| ID | Constraint | Status |
|----|-----------|--------|
| C-001 | Written against the #587 authoring standard (`docs/design/openclaw-workspace-authoring-standard.md`, on main). Mission branches from current `main` so the standard + validator are in-lane (avoids the #584 mid-mission dependency-merge trap). | Active |
| C-002 | Agent prompt files deploy via agent-prompt-sync on merge-to-main; no `deploys/queued/` manifest is authored (the #636 boundary). | Active |
| C-003 | Rebaseline is expected "not required" — agent prompt files are not hashed by `audit.sh` (#621 gap). The merge commit records the rebaseline decision. | Active |
| C-004 | Behavior-preserving refactor + narrow correctness/hygiene fixes only (FR-006 stale-claim correction, FR-008 volatile-ID de-inline, FR-009 AGENTS truthfulness if warranted) — NO feature/behavior additions. AGENTS.md size (~15KB, no hard cap applies to a sub-agent) is left as-is. | Active |
| C-005 | The `_private` privacy path is already canonical across habits' files (validator `privacy_path_canonical: ok`); it is left byte-unchanged. | Active |
| C-006 | Post-merge acceptance criteria (deploy parity, live smoke) are operator-owned and documented in the mission quickstart — they are excluded from the acceptance matrix (the gate rejects post-merge "pending" rows). | Active |
| C-007 | habits is a per-dispatch sub-agent, not the main WhatsApp DM lane — no session rotation or `openclaw gateway restart` is required at deploy (unlike the #583 main SOP). | Active |
| C-008 | Single-branch topology (mission created without `--pr-bound` off a pre-cut `feat/` branch) to avoid the #2533 coordination-split fault; the feature branch merges to `main` at the end. | Active |

## Success Criteria

1. All three edited workspace files (SOUL/USER/TOOLS) are re-homed to #587 ownership; SOUL is voice+stance only; USER's scope text is accurate; TOOLS inlines no volatile Vikunja IDs.
2. `validate_workspace.py` reports habits `ok: true` (all four invariants pass).
3. A content-conservation check confirms no substantive instruction was silently dropped (weekly-out-of-scope and enforceable privacy both survive in AGENTS).
4. The change is deployed to office2 via agent-prompt-sync with repo ↔ office2 parity confirmed.
5. A live smoke test confirms habits' morning check-in behavior is unchanged.
6. #409 is confirmed resolved/incorporated (single coherent weekly-report statement; no conflict remains).

## Key Entities

- **felix-admin-habits workspace** — the five OpenClaw bootstrap files at `scripts/openclaw/agents/felix-admin-habits/` (SOUL / USER / TOOLS / IDENTITY / AGENTS.md). SOUL, USER, TOOLS are edited; IDENTITY is not; AGENTS is edited only if a narrow truthfulness correction is warranted.
- **#587 ownership model** — the concern→file mapping: SOUL = voice/stance; USER = filtered person-view; TOOLS = environment/setup; AGENTS = operating rules/role; IDENTITY = identity card.
- **felix-habits-weekly timer** — the deterministic systemd timer (`scripts.habits.weekly_report_driver`, #723) that owns weekly habit pattern reporting; the reason the habits LLM agent's weekly-report scope is "out of scope" and why USER's "reports on patterns" claim is stale.
- **agent-prompt-sync** — the office2 pull pipeline (`deploy_agent_prompts.py`, #567/#136/#636) that deploys agent prompt files on merge-to-main.

## Assumptions

- The agent-prompt-sync timer is live on office2 and will deploy the habits files on the next tick after merge (no manifest required).
- habits currently passes all four #587 invariants (verified at design time via `validate_workspace.py`).
- The date-handling content in USER.md is habits-relevant operational material whose canonical home under #587 is TOOLS (the exact precedent set by #584 capture and #585 escalation).
- The morning-list and completion helpers (`scripts.habits.*`) resolve the Habits project and habit tasks by name at runtime, so removing the inlined IDs from TOOLS.md (a prompt/doc file) does not change behavior — validated in plan phase before de-inlining.
- "ADD (managed)" in USER notes is retained as a neutral person-fact (the #583 main precedent), while the SOUL "Kent has ADD…" *justification* is trimmed (the #584 capture / #585 escalation precedent) — the precedents are consistent, not conflicting.
- #409 is already closed (2026-07-19) with weekly-report ownership settled on the deterministic timer; this mission confirms coherence rather than making an ownership decision.
