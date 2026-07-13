# Tasks: Author main agent workspace

**Mission**: author-main-workspace-01KXE90Z (issue #583)
**Branch**: `feat/author-main-workspace` → merges to `feat/author-main-workspace`

Single coherent work package. The five `main` workspace files are tightly coupled
(content is *conserved across* SOUL/USER/AGENTS/TOOLS), so per the #584 precedent
they are authored by one agent in one worktree to avoid split-brain on the shared
workspace. Post-merge deploy/parity/session-rotation/smoke is operator acceptance
in `quickstart.md`, not a code WP.

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Author SOUL.md → voice-only + one-line privacy stance | WP01 | |
| T002 | Author USER.md → filtered Kent-context + Felix "why" | WP01 | |
| T003 | Author TOOLS.md → real surface + mechanics + enforceable privacy rule | WP01 | |
| T004 | Author IDENTITY.md → Felix identity card | WP01 | |
| T005 | Author AGENTS.md → role, adapted Output Discipline, routing matrix, consolidated red lines (under 12K cap; identity line unchanged) | WP01 | |
| T006 | Add GOVERNANCE.md roster note to the #587 standard | WP01 | |
| T007 | Validate: main ok:true (main-scoped) + 12K cap + suite + conservation self-check | WP01 | |

## WP01 — Author main workspace files

- **Goal**: Re-author `main`'s five #587 standard files (+ a one-line standard roster note) to fix both invariants, author the two factory files, clean SOUL to voice-only, rebalance AGENTS↔TOOLS under the 12K cap, and fold in the three approved improvements — with zero loss of live front-desk behavior.
- **Priority**: P1 (only WP; MVP).
- **Independent test**: `python3 -m scripts.openclaw.agents.validate_workspace --json` shows `main` `ok:true`; `test_agents_md_size.py` green; conservation self-check passes.
- **Prompt**: [tasks/WP01-author-main-workspace.md](tasks/WP01-author-main-workspace.md)
- **Estimated prompt size**: ~450 lines.
- **Dependencies**: none.

### Included subtasks

- [ ] T001 Author SOUL.md → voice-only + one-line privacy stance (WP01)
- [ ] T002 Author USER.md → filtered Kent-context + Felix "why" (WP01)
- [ ] T003 Author TOOLS.md → real surface + delegation/timelog/issue mechanics + enforceable `04-Growth/_private` rule (WP01)
- [ ] T004 Author IDENTITY.md → Felix identity card (WP01)
- [ ] T005 Author AGENTS.md → role statement, adapted Output Discipline block, six-specialist routing matrix, consolidated red lines; keep rules, push mechanics to TOOLS, drop Make-It-Yours (under 12K cap; message-identity line left unchanged) (WP01)
- [ ] T006 Add the one-line GOVERNANCE.md roster note to `docs/design/openclaw-workspace-authoring-standard.md` (WP01)
- [ ] T007 Validate: main `ok:true` (main-scoped) + `test_agents_md_size.py` + full openclaw suite + conservation self-check (WP01)

### Dependencies

None (single WP).

### Risks

- Byte cap (12K) on AGENTS.md — mitigated by the AGENTS↔TOOLS rebalance in `data-model.md`.
- Silent loss of a live AGENTS rule — mitigated by the full keep/move/drop table.
- Importing capture-specific inbox text into main's Output Discipline — author an *adapted* block.
