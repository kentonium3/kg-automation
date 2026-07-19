# Tasks: Author felix-admin-tasker workspace

**Mission**: author-tasker-workspace-01KXXEVB (#586) | **Branch**: feat/author-tasker-workspace
**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md) · **Move-table**: [data-model.md](./data-model.md)

Single work package — a behavior-preserving authoring refactor of one agent's three workspace files (SOUL/USER/TOOLS) is one cohesive, coupled unit. Post-merge deploy/parity/smoke (FR-011, NFR-005) are operator-owned and documented in [quickstart.md](./quickstart.md) §5–9 — they are NOT a `kitty-specs`-owning WP (the #584 lesson) and are excluded from the acceptance matrix (C-006).

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Author SOUL.md → voice-only + one-line privacy stance | WP01 | |
| T002 | Author USER.md → filtered person-view; remove privacy dup; trim role/comms | WP01 | |
| T003 | Author TOOLS.md → correct action-log format (keep Directive-3 fields); drop behavioral rule | WP01 | |
| T004 | Verify AGENTS.md + IDENTITY.md byte-unchanged; grep-confirm AGENTS owns removed concerns | WP01 | |
| T005 | Run validate_workspace — tasker `ok:true` (all four invariants) | WP01 | |
| T006 | Run content-conservation checklist (incl. action-log required-fields invariant) | WP01 | |

## Work Packages

### WP01 — Author felix-admin-tasker workspace to #587

**Goal**: Re-home tasker's SOUL/USER/TOOLS content to the #587 ownership contract (SOUL → voice-only + stance; USER → filtered person-view, no enforceable rule; TOOLS → corrected action-log format, no behavioral rule), keeping the agent's behavior unchanged and the validator green. AGENTS.md and IDENTITY.md are NOT edited.

**Priority**: P1 (the mission's only WP — MVP). **Prompt**: [tasks/WP01-author-tasker-workspace.md](./tasks/WP01-author-tasker-workspace.md) (~380 lines).

**Included subtasks**:

- [x] T001 Author SOUL.md → voice-only + one-line privacy stance (WP01)
- [x] T002 Author USER.md → filtered person-view; remove privacy dup; trim role re-statement + comms voice-line (WP01)
- [x] T003 Author TOOLS.md → correct action-log format (preserve Directive-3 required fields); remove behavioral confirmation rule; keep privacy path + token rule (WP01)
- [x] T004 Verify AGENTS.md + IDENTITY.md byte-unchanged; grep-confirm AGENTS owns role + confirmation rule + enforceable privacy (WP01)
- [x] T005 Run validate_workspace — assert felix-admin-tasker `ok:true` (WP01)
- [x] T006 Run the content-conservation checklist from data-model.md (incl. invariant #9 action-log required-fields) (WP01)

**Independent test**: `python3 -m scripts.openclaw.agents.validate_workspace --json` → tasker `ok:true`; `git diff --name-only` lists only the three files + mission artifacts; AGENTS.md/IDENTITY.md byte-identical; conservation greps pass.

**Dependencies**: none (branch already carries #587 from main).

**Risks**: enforceable privacy or confirmation rule stripped from ALL files (must survive in AGENTS/TOOLS resp. AGENTS); accidental AGENTS/IDENTITY edit; wrong FR-008 corrected format; dropping the Directive-3 required-fields line during the TOOLS correction.

**Requirements covered**: FR-001…FR-010, NFR-001…NFR-004. (FR-011, NFR-005 = post-merge operator acceptance in quickstart.md, C-006.)

**Post-merge acceptance** (operator-owned, NOT this WP): quickstart.md §5–9 — feat→main merge, agent-prompt-sync deploy, md5 parity at `/data/services/openclaw/tasker-agent/`, live smoke.
