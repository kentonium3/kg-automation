---
work_package_id: WP01
title: 'Author felix-admin-tasker workspace to #587'
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-007
- FR-008
- FR-009
- FR-010
- FR-011
tracker_refs: []
planning_base_branch: feat/author-tasker-workspace
merge_target_branch: feat/author-tasker-workspace
branch_strategy: Planning artifacts for this mission were generated on feat/author-tasker-workspace. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/author-tasker-workspace unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
phase: Phase 1 - Author
assignee: ''
agent: claude
history:
- at: '2026-07-19T15:20:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: curator-carla
authoritative_surface: scripts/openclaw/agents/felix-admin-tasker/
create_intent: []
execution_mode: code_change
model: claude-sonnet-5
owned_files:
- scripts/openclaw/agents/felix-admin-tasker/SOUL.md
- scripts/openclaw/agents/felix-admin-tasker/USER.md
- scripts/openclaw/agents/felix-admin-tasker/TOOLS.md
role: implementer
tags: []
task_type: implement
---

# Work Package Prompt: WP01 – Author felix-admin-tasker workspace to #587

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned profile:

```
/ad-hoc-profile-load curator-carla
```

You are **curator-carla** (knowledge-base / doctrine maintenance) acting as implementer for a
**behavior-preserving** workspace authoring refactor. This is content curation on a LIVE task-intelligence
agent — precision and conservation matter more than cleverness. Do NOT fold in behavior changes.

## Objective

Re-home `felix-admin-tasker`'s three workspace files (SOUL/USER/TOOLS) to their #587-canonical owner
file and correct one stale doc (the TOOLS action-log format), proving the set stays invariant-green and
behavior-preserving. The authoritative design is the move-table in
`kitty-specs/author-tasker-workspace-01KXXEVB/data-model.md` — **follow it exactly, row by row.**
`AGENTS.md` and `IDENTITY.md` are NOT edited.

## Context you must read first

1. `kitty-specs/author-tasker-workspace-01KXXEVB/spec.md` — FRs + NFRs + constraints.
2. `kitty-specs/author-tasker-workspace-01KXXEVB/data-model.md` — the row-by-row move-table + the 10 conservation invariants (source of truth).
3. `kitty-specs/author-tasker-workspace-01KXXEVB/research.md` — the 7 decisions + rationale.
4. `kitty-specs/author-tasker-workspace-01KXXEVB/quickstart.md` — the validation + conservation-grep steps.
5. `docs/design/openclaw-workspace-authoring-standard.md` — the #587 concern→file ownership contract.
6. The current files: `scripts/openclaw/agents/felix-admin-tasker/{SOUL,USER,TOOLS,AGENTS,IDENTITY}.md`.
7. `scripts/openclaw/observation/log_action.py` + `config.py` — the authority for the FR-008 action-log format.

## Hard rules

- **Behavior-preserving.** No new instructions, no changed workflows, no "improvements" beyond the named
  corrections. `AGENTS.md` and `IDENTITY.md` MUST stay byte-identical (do not touch them).
- **Conservation.** Every block is keep / trim / reduce-to-stance / delete per the move-table. Nothing
  substantive may be silently dropped. A DELETE is safe ONLY because the canonical copy already lives in
  the named owner — verify that before removing.
- **Scoped edits only.** Touch only the 3 `owned_files` (SOUL/USER/TOOLS). Do NOT edit AGENTS.md or IDENTITY.md.
- **Do NOT fold the noted-but-out-of-scope items** (the AGENTS `:sonnet` vs `<model>` inconsistency; IDENTITY trim). They are deliberately deferred (spec C-004).

## Subtasks

### T001 — Author SOUL.md → voice-only + one-line privacy stance (FR-001, FR-002, FR-003, FR-004)

**Purpose**: Reduce SOUL to the Voice section plus a single behavioral privacy stance line.

**Steps** (per data-model.md SOUL rows):
1. **Delete `## Purpose`** (the role block "You are felix-admin-tasker. Your sole purpose is task intelligence…" including the embedded confirmation sentence). Role is owned by `AGENTS.md` `## Authority`/`## Scope`; the confirmation clause is owned by `AGENTS.md` `## Operating Mode`. (FR-002)
2. **Keep `## Voice — write as Kent` verbatim** — Principles, "Words and phrases to avoid", "Words and phrases that are Kent". Do not alter it (including the "Structured and chunked … Kent has ADD" style bullet — it stays). (FR-001)
3. **Delete `## Behavioral principles`** entirely. Every item is owned elsewhere: never-create-without-confirmation → AGENTS `## Operating Mode`; minimize-questions → AGENTS enrich_task Step 1 (≥90%/<90% thresholds); one-question-at-a-time → AGENTS enrich_task Step 3 ("send ONE focused question"); batch-concise → AGENTS retroactive_enrichment; propose-confidently → SOUL `## Voice` ("Confident but honest"). (FR-003)
4. **Reduce `## Privacy boundary`** to a single one-line behavioral stance, e.g.:
   `## Privacy stance` / `I work only where I'm invited.`
   Remove the full never-touch policy body, the filesystem path, AND the mission-026/#152 changelog parenthetical. The enforceable rule stays in AGENTS + TOOLS. (FR-004)

**Result**: SOUL.md contains the title, `## Voice — write as Kent` (unchanged), and a one-line privacy stance — nothing else.

### T002 — Author USER.md → filtered person-view (FR-005, FR-006, FR-007)

**Steps** (per data-model.md USER rows):
1. **Keep** the person block (Name / What to call / Timezone / Notes incl. "ADD (managed)") and `## Identities` (personal / intentional / metalcasework) unchanged.
2. **Trim `## Context`**: remove the embedded role re-statement sentence ("Your job is to take raw or incomplete task descriptions and structure them into fully enriched Vikunja entries — with the right project, labels, priority, due date, and description."). Keep the genuine Kent-context: "Kent is a solo entrepreneur managing multiple business and personal initiatives. Tasks arrive from several sources: Obsidian inbox (voice captures via Wispr Flow and typed notes), direct Vikunja creation, and agent actions." (FR-006)
3. **Trim `## Communication preferences`**: remove the "Concise, direct. No pleasantries or filler." line (a voice rule owned by SOUL `## Voice`). Keep the genuine interaction preferences: prefers proposals over open-ended questions; "Yes/no" confirmations preferred; batch proposals when multiple tasks need structuring. (FR-007)
4. **Delete `## Privacy boundary`** entirely (the enforceable rule + path + changelog parenthetical). The enforceable copy stays in AGENTS + TOOLS. USER carries NO enforceable privacy rule after this. (FR-005)

**Result**: USER.md = person block + `## Identities` + trimmed `## Context` + trimmed `## Communication preferences`. No privacy rule, no role statement.

### T003 — Author TOOLS.md → correct action-log format; drop behavioral rule (FR-008, FR-009)

**Steps** (per data-model.md TOOLS rows):
1. **Keep** `## Skills`, `### WhatsApp`, `### Vikunja API` unchanged (correct env surface; no volatile IDs to touch).
2. **Correct `### Action log`** (FR-008 — the one stale-text fix). Current text says:
   - `Central logging to /home/kgale/second-brain/agents/logs/.` and `**Format**: task-intelligence-YYYY-MM-DD.md`.
   Replace with the shape `log_action.py` actually writes (verify against `scripts/openclaw/observation/log_action.py::_write_entry` + `config.py DEFAULT_AGENT_LOGS_DIR`):
   - Path: `/home/kgale/second-brain/agents/logs/felix-admin-tasker/YYYY-MM-DD.jsonl` (a **per-agent subdirectory**, `.jsonl` — one file per day, JSON-Lines).
   - **PRESERVE the Directive-3 required-fields substance** — the block must still state that every action is logged with: agent name, action type, target, outcome, timestamp, and autonomy level. Do NOT drop that enumeration (conservation invariant #9). Correct only the filename/path shape.
3. **`## Restrictions`**: **Delete** the line "NEVER create tasks without Kent's confirmation (while at Assisted level)" (behavioral operating rule owned by AGENTS `## Operating Mode`). **Keep** "NEVER read, write, or reference `/home/kgale/second-brain/notes/04-Growth/_private/` …" (Invariant A env home — leave byte-unchanged, C-005) and "NEVER log API tokens or credentials". (FR-009)

**Result**: TOOLS.md = Skills + WhatsApp + Vikunja API + a corrected Action-log block (correct path, `.jsonl`, required-fields preserved) + Restrictions (privacy path + token rule only).

### T004 — Verify AGENTS.md + IDENTITY.md untouched; confirm AGENTS ownership (FR-010, NFR-002, NFR-004a)

**Steps**:
1. Do NOT edit AGENTS.md or IDENTITY.md. Confirm both are byte-identical:
   `git diff --quiet -- scripts/openclaw/agents/felix-admin-tasker/AGENTS.md scripts/openclaw/agents/felix-admin-tasker/IDENTITY.md && echo unchanged`
2. Grep-confirm AGENTS already owns every removed concern (so the DELETEs are safe):
   - Role: `grep -n "## Authority\|## Scope" .../AGENTS.md`
   - Confirmation rule: `grep -ni "explicit confirmation\|Operating Mode" .../AGENTS.md`
   - Enforceable privacy: `grep -n "04-Growth/_private" .../AGENTS.md` (present) and in TOOLS.md (present).
   - Confirm AGENTS does NOT reference SOUL as a privacy home (so no truthfulness fix is warranted): `grep -ni "SOUL" .../AGENTS.md` → expect no privacy-home reference.
3. If any removed concern is NOT actually present in AGENTS, STOP — the DELETE would be a behavior change; report it (do not improvise).

### T005 — Validate invariants (NFR-001)

```bash
python3 -m scripts.openclaw.agents.validate_workspace --json
```
Parse the output and assert the `felix-admin-tasker` object has `ok: true` with all four checks (`privacy_boundary`, `privacy_path_canonical`, `output_discipline`, `runtime_env_assumptions`) `ok`. Use the tasker-scoped object, not the whole-fleet exit code (calendar/#635 fails Invariant B, out of scope). If tasker is not `ok:true`, fix per the move-table (most likely the enforceable privacy rule was over-stripped) — the enforceable copy must remain in AGENTS + TOOLS.

### T006 — Content-conservation checklist (NFR-003)

Run the 10 conservation invariants from `data-model.md` §"Conservation invariants" as greps (see quickstart.md §3). All must hold, in particular:
- Enforceable privacy present in AGENTS + TOOLS; ABSENT from SOUL + USER.
- Confirmation rule present in AGENTS; ABSENT from SOUL + TOOLS.
- Role present in AGENTS; ABSENT from SOUL + USER.
- Voice in SOUL only; Identities in USER only; Output Discipline in AGENTS (unchanged).
- Action-log format matches `log_action.py`; no `task-intelligence-*.md` string remains; **the Directive-3 required-fields enumeration still present in TOOLS** (invariant #9).
- Scope: `git diff --name-only` lists only the three files + mission artifacts; AGENTS.md/IDENTITY.md byte-identical.

## Branch Strategy

Planning artifacts were generated on `feat/author-tasker-workspace`. Completed changes merge back into
`feat/author-tasker-workspace` (single_branch topology; no coordination branch). Execution worktrees are
allocated per computed lane from `lanes.json`. The final `feat/author-tasker-workspace` → `main` merge is
the operator-owned deploy trigger (quickstart.md §5), AFTER the post-merge Codex review.

## Definition of Done

- [ ] SOUL/USER/TOOLS edited exactly per the move-table; AGENTS.md and IDENTITY.md byte-unchanged.
- [ ] `validate_workspace` reports tasker `ok:true` (all four invariants).
- [ ] All 10 conservation invariants pass (incl. #9 action-log required-fields).
- [ ] `git diff --name-only` shows only the three files + mission artifacts.
- [ ] The commit is scoped (`git add` only the three files) with a conventional message referencing #586.

## Risks / reviewer guidance

- **Over-stripping privacy** → Invariant A regression. The enforceable rule MUST survive in AGENTS + TOOLS.
- **Dropping the confirmation rule everywhere** → the guarantee weakens. It must survive in AGENTS.
- **FR-008 format wrong** → the doc stays wrong. It must match `log_action.py` (`…/felix-admin-tasker/YYYY-MM-DD.jsonl`), and the required-fields line must survive.
- **Accidental AGENTS/IDENTITY edit** → NFR-002/NFR-004a violation. Keep them byte-identical.
- Reviewer: check the diff against the move-table row by row; run the conservation greps yourself.

## Post-merge acceptance (operator-owned — NOT this WP)

FR-011 + NFR-005 (feat→main merge, agent-prompt-sync deploy, md5 parity at
`/data/services/openclaw/tasker-agent/`, live smoke) are documented in quickstart.md §5–9 and excluded from
the acceptance matrix (C-006). Do not attempt them from the lane worktree.
