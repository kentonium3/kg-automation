# Data Model: Author main agent workspace

There is no runtime data schema — this mission authors prompt files. The
"model" here is the **content-conservation model**: which content block belongs
in which owner file, and the invariants that must hold after authoring. This
mirrors the #584 pilot's conservation approach.

## Entities

### Workspace file (owner)
The five #587 standard files under `scripts/openclaw/agents/main/`, each owning
exactly one concern:

| File | Owns (post-authoring) |
|------|------------------------|
| `IDENTITY.md` | Display card: name (Felix), creature, vibe, emoji |
| `SOUL.md` | Voice/stance only + one-line privacy stance |
| `USER.md` | Filtered view of Kent + the Felix "why" |
| `TOOLS.md` | Real tool surface, paths, mechanics, enforceable privacy path |
| `AGENTS.md` | Role/authority, SOP, delegation, enforceable policy, Output Discipline |

Out of model (unchanged): `GOVERNANCE.md`, `felix-file-issue.py`.

### Content block (moved unit)
The current-state content that must be conserved (moved, not lost) during
authoring:

| Block (current location) | Destination | Requirement |
|--------------------------|-------------|-------------|
| `## Voice` (SOUL) | stays SOUL | FR-001 |
| `## Purpose` (SOUL) | role → AGENTS; "why" → USER | FR-001, FR-002, FR-005 |
| `## Understanding Kent` (SOUL) | USER (filtered) | FR-002 |
| `## Sub-agent delegation` table (SOUL) | drop (AGENTS owns fuller SOPs) | FR-007 |
| `## Heartbeat behavior` (SOUL) | drop (AGENTS owns Heartbeats) | FR-001 |
| `## Privacy boundary` full rule (SOUL) | one-line stance in SOUL; enforceable rule → AGENTS/TOOLS | FR-006, Inv-A |
| `## Red lines` (SOUL) | consolidate → AGENTS | FR-009 |
| factory scaffold (TOOLS) | replaced by real surface | FR-003 |
| factory scaffold (IDENTITY) | replaced by Felix identity | FR-004 |
| `Communication style` (USER) vs `Voice` (SOUL) overlap | Kent-prefs → USER; agent voice → SOUL | FR-002 |
| Output Discipline block (absent) | add to AGENTS (mirror capture) | FR-006, Inv-B |
| identity line `Sent by main:sonnet` (AGENTS) | de-hardcode | FR-008 |

## Invariants (must hold after authoring)

- **INV-1 (Invariant A)**: the enforceable `04-Growth/_private/` never-touch rule
  is present in `AGENTS.md` and/or `TOOLS.md`; `SOUL.md` carries only the
  one-line stance. Validator `privacy_boundary` check → ok.
- **INV-2 (Invariant B)**: `AGENTS.md` carries the Output Discipline block.
  Validator `output_discipline` check → ok.
- **INV-3 (single owner)**: every shared concern (privacy, voice, role,
  delegation, heartbeat, red lines) appears in exactly one owner file — no
  duplication across files.
- **INV-4 (no placeholder)**: no factory-template or `[fill this in]` text
  remains in any of the five files.
- **INV-5 (delegation fidelity)**: the verbatim-passthrough and cron-vs-ask relay
  rules survive consolidation intact (no rule dropped) — the #263/#285 class stays
  covered.
- **INV-6 (deploy parity)**: after agent-prompt-sync, office2 copies match repo
  copies (md5) for all authored files.
- **INV-7 (no scope creep)**: `GOVERNANCE.md` content unchanged; no
  `deploys/queued/` manifest created; no speculative mail behavior introduced.

## State transitions

None. Prompt files have no lifecycle state; the transition is a one-shot author →
validate → deploy → verify.
