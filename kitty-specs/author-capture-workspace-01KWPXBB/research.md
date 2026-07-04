# Research: Author felix-admin-capture Workspace

Phase 0 research consolidating the decisions that ground the plan. Most design was
locked with Kent pre-spec (2026-06-28 and 2026-07-03 sessions); this file records the
resolved decisions and the one new finding surfaced during planning.

## Decision 1 — The content move-table (locked with Kent)

**Decision**: Relocate exactly these blocks; everything else stays put. Pure relocation,
no behavioral rewording.

| Content block | From → To | Rationale |
|---|---|---|
| `## Purpose` / role statement | SOUL → **delete** | AGENTS.md `## Authority` already owns the role (verified). SOUL excludes role per #587. |
| `## Privacy boundary` (full block) | SOUL → **one-line stance** | SOUL carries only "I work only where I'm invited"; enforceable rule already lives in AGENTS.md + TOOLS.md (FR-007). |
| `## Date handling` (TZ/ET-offset/no-Z) | USER → **TOOLS** | Operational mechanics belong in TOOLS, not the person-view. |
| `### Available Labels` taxonomy | TOOLS → **AGENTS** (beside Step 3 `github_issue`) | Routing-time policy belongs beside the routing step; TOOLS keeps a pointer only (staleness-trap rule). |
| Voice ("write as Kent") | **stays in SOUL** | The keeper — SOUL's proper content. |
| ADD references | **removed everywhere** | See Decision 2. |

**Rationale**: Grounded in the OpenClaw templates (docs.openclaw.ai concepts/soul,
reference/templates/{USER,TOOLS}) and the #587 ownership contract. Verified against the
live files: SOUL.md currently carries `## Purpose`, the full `## Privacy boundary`, and a
changelog parenthetical; USER.md carries `## Date handling`; TOOLS.md carries the full
`### Available Labels` list. AGENTS.md already owns the role (`## Authority`), the
enforceable privacy rule (`## Privacy — absolute rule`), and Step 3's `github_issue` route.

**Alternatives considered**: (a) EA-scope behavioral redesign in the same mission —
rejected; Kent chose Path 1 (pure refactor), all routing-intelligence deferred to #651.
(b) Keeping the label list in TOOLS with a "keep in sync" note — rejected as a staleness
trap the #587 standard explicitly bans.

## Decision 2 — Remove all ADD references

**Decision**: Remove the SOUL "structured and chunked / Kent has ADD" bullet and the USER
`Notes` "ADD (managed)" fragment. Keep a neutral USER line attributing terseness to the
capture *method* ("captures tend to be terse/fragmentary — voice or quick-note"), not to Kent.

**Rationale (Kent, 2026-07-03)**: ADD references bias the agent's responses. Terseness is a
property of quick-capture, not a personal attribute to encode into the agent's model of Kent.

## Decision 3 — USER.md is a filtered view, not a profile

**Decision**: USER.md keeps only the Kent context relevant to interpreting inbox captures
(who, address, timezone, and a scoped `Context`), not a replicated global profile.

**Rationale**: #587 Principle 4 and the OpenClaw USER template ("not a full dossier"). capture's
view differs legitimately from other agents' views.

## Decision 4 (NEW — planning finding) — Deploy path is agent-prompt-sync, not a manifest

**Decision**: The authored files deploy via the existing **agent-prompt-sync** pull pipeline
(`deploy_agent_prompts.py`, mission #567/#136) — a systemd user timer on office2 that every
5 min runs `git pull --ff-only origin main`, MD5-compares each in-scope prompt file against
the deployed copy under `/data/services/openclaw/inbox-agent/`, and atomically copies drift.
**No `deploys/queued/` manifest is authored.**

**Rationale**: The spec (FR-9/C-003, following issue #584's Architecture Impact) assumed the
felix-deployer manifest path. Reading `scripts/openclaw/deploy/deploy_agent_prompts.py` and
`docs/runbooks/agent-prompt-sync-ops.md` established that agent-prompt files (`AGENTS/IDENTITY/
SOUL/TOOLS/USER`) are **out of felix-deployer's scope** and flow through this separate
pull-based pipeline — the pull-vs-felix-deployer boundary tracked as #636. felix-deployer
manifests are for crons, helpers, systemd units, and config. Spec FR-9 and C-003 were amended
in-plan to match (with Kent's approval, 2026-07-04); this decision documents the deviation per
DIRECTIVE_010.

**Alternatives considered**: Authoring a `deploys/queued/` manifest anyway — rejected; it
would invoke the wrong pipeline and duplicate/contradict the automatic sync.

**Consequence for tasks**: no manifest deliverable. FR-9 becomes "confirm the agent-prompt-sync
timer is live, then verify it recorded the copy of each changed file in
`/data/services/openclaw/deploy/agent-prompt-sync.jsonl` after merge to main."

## Decision 5 — Shared-invariant homing after the refactor

**Decision**: After relocation, capture must still pass `validate_workspace.py`:
- **Invariant A (privacy)**: enforceable `04-Growth/_private/` rule remains in AGENTS.md (and
  TOOLS.md carries the path). SOUL's one-line stance does NOT satisfy the checker on its own —
  which is correct, because the enforceable rule stays in AGENTS.md/TOOLS.md (FR-007).
- **Invariant B (Output Discipline)**: unchanged — the canonical block stays in capture's
  AGENTS.md. capture is the canonical source; this mission does not touch it.

**Verification (baseline, 2026-07-04)**: capture already reports PASS on both invariants
(`python3 -m scripts.openclaw.agents.validate_workspace`). The refactor must keep it PASS —
the risk is FR-007 (don't strip the enforceable privacy rule when reducing SOUL).

## Decision 6 — Rebaseline expectation (#557/#621)

**Decision**: Rebaseline is expected to be **"not required — agent prompt files are not
currently hashed by the monitor (#621 gap)."** `audit.sh` hashes only `openclaw.json`, not the
per-agent SOUL/USER/TOOLS files, so no security baseline covers this change. Confirmed at merge.

**Rationale**: Documented in CLAUDE.md's rebaseline section and the #621 memory. Agent-prompt
changes are an audited surface *in principle* but are not yet hashed, so there is nothing to
reset.

## Open items carried to implementation

- Verify the agent-prompt-sync timer is live on office2 before relying on auto-deploy
  (`systemctl --user list-timers | grep agent-prompt-sync`). Read-only check.
- Capture a pre-deploy smoke baseline (capture's current routing decisions) to compare against
  post-deploy (NFR-001).
