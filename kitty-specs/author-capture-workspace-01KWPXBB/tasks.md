# Tasks: Author felix-admin-capture Workspace

**Mission**: author-capture-workspace-01KWPXBB
**Branch**: `feat/author-capture-workspace` (planning + merge target for WPs; feature-branch → main is the final PR)
**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md)

Pure-refactor authoring of capture's SOUL/USER/TOOLS (+ AGENTS.md label receiver) against the
#587 standard, with zero behavior change. Deploy/verify/smoke (FR-009/010/011) are operator-owned
post-merge acceptance (agent-prompt-sync fires only on merge to main) — documented in
[quickstart.md](./quickstart.md), not a separate lane.

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Author SOUL.md — voice/stance only | WP01 | |
| T002 | Author USER.md — filtered view, remove date-handling + ADD | WP01 | |
| T003 | Author TOOLS.md — tool surface + relocated date-handling + label pointer | WP01 | |
| T004 | AGENTS.md — receive Available Labels taxonomy beside Step 3 (receiver only) | WP01 | |
| T005 | Validate — `validate_workspace.py` PASS for capture (Invariants A+B) | WP01 | |
| T006 | Content-conservation check — each moved block in exactly one place | WP01 | |

---

## WP01 — Author capture workspace files

**Prompt**: [tasks/WP01-author-workspace-files.md](./tasks/WP01-author-workspace-files.md)

- **Goal**: Relocate leaked content to the correct owner file per the #587 contract, producing
  the authored SOUL/USER/TOOLS set (+ AGENTS.md label receiver), with zero behavior change.
- **Priority**: P1 (MVP — the entire in-repo deliverable).
- **Independent test**: `python3 -m scripts.openclaw.agents.validate_workspace` reports
  `felix-admin-capture` PASS, and the content-conservation greps (quickstart §3) all hold.
- **Requirements**: FR-001…FR-008 (authoring, in-lane); FR-009, FR-010, FR-011 (deploy/verify/smoke —
  operator-owned post-merge, see the WP's "Post-merge acceptance" section + quickstart.md);
  NFR-002, NFR-004 in-lane; NFR-001, NFR-003 post-merge.
- **Dependencies**: none.
- **Estimated prompt size**: ~460 lines.

Included subtasks:

- [x] T001 Author SOUL.md — remove role/purpose + changelog + ADD bullet; reduce privacy to one-line stance; keep voice (WP01)
- [x] T002 Author USER.md — remove `## Date handling` + "ADD (managed)"; keep filtered context + neutral terseness line (WP01)
- [x] T003 Author TOOLS.md — add relocated date-handling; replace Available Labels list with a pointer; keep vault/vikunja/github/privacy (WP01)
- [x] T004 AGENTS.md — add Available Labels taxonomy beside Step 3 `github_issue` route; no other change (WP01)
- [x] T005 Run `validate_workspace.py`; confirm capture PASS on Invariants A+B (WP01)
- [x] T006 Content-conservation check — grep proves each moved block in exactly one place; ADD gone; privacy rule retained in AGENTS/TOOLS (WP01)

**Implementation sketch**: Apply the move-table (research.md Decision 1) file by file; run the
validator; run the conservation greps (quickstart §2–3). Pure relocation — do not reword in a
way that changes behavior. FR-009/010/011 are executed by the operator after the feature branch
merges to main (agent-prompt-sync auto-deploys); see quickstart.md §4–9.

**Risks**: Stripping the enforceable privacy rule when reducing SOUL (FR-007 guard); scope-creep
on AGENTS.md beyond the label receiver (C-002); accidental behavioral rewording.

---

## Dependencies

- WP01 → none

## MVP

**WP01** is the MVP and the entire in-repo change. Deploy/verify/smoke acceptance (FR-009/010/011)
is operator-owned and runs post-merge per quickstart.md.
