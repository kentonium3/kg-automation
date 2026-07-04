# Data Model: Author felix-admin-capture Workspace

This mission has no runtime data model. The "entities" are the workspace files and the
content blocks moving between them. This document models that relocation as the design
contract the implementation and review verify against.

## Entity: Workspace file

| File | Role (owner concern) | In scope | Mutation |
|---|---|---|---|
| `SOUL.md` | Voice / stance | Authored | Remove role + full privacy block + changelog + ADD bullet; keep voice; add one-line privacy stance |
| `USER.md` | Filtered person-view | Authored | Remove `## Date handling`, remove ADD fragment; keep filtered context + neutral terseness line |
| `TOOLS.md` | Environment / tool surface | Authored | Add relocated date-handling; replace label list with a pointer |
| `AGENTS.md` | Operating rules / SOP | Receiver only | Add `Available Labels` taxonomy beside Step 3; no other change |
| `IDENTITY.md` | Display card | Untouched | — |

## Entity: Content block (the moving units)

Each block has a single owner before and after. Conservation rule: **every relocated block
appears in exactly one destination file and is absent from its source file** (NFR-002).

| Block | Source | Destination | Conservation check |
|---|---|---|---|
| Role / Purpose | SOUL.md | AGENTS.md `## Authority` (already present) | Absent from SOUL; present in AGENTS (pre-existing) — net: deleted from SOUL |
| Privacy (enforceable rule) | SOUL.md | AGENTS.md + TOOLS.md (already present) | Absent from SOUL as a full block; one-line stance remains in SOUL; enforceable rule present in AGENTS/TOOLS |
| Date handling | USER.md | TOOLS.md | Absent from USER; present in TOOLS |
| Available Labels taxonomy | TOOLS.md | AGENTS.md (beside Step 3) | List absent from TOOLS (pointer remains); present in AGENTS |
| ADD references | SOUL.md, USER.md | — (deleted) | Absent everywhere |
| Voice ("write as Kent") | SOUL.md | SOUL.md (stays) | Present in SOUL |

## Invariants (validated)

1. **INV-privacy (Invariant A)**: `04-Growth/_private/` enforceable rule present in AGENTS.md
   or TOOLS.md after the refactor. Checked by `validate_workspace.py`. FR-007.
2. **INV-output-discipline (Invariant B)**: Output Discipline block present in capture's
   AGENTS.md (unchanged). Checked by `validate_workspace.py`.
3. **INV-single-owner**: no relocated block appears in two files with conflicting authority
   (NFR-002). Checked by content-conservation review + grep.
4. **INV-behavior**: capture's routing decisions on the same inputs are unchanged pre/post
   deploy (NFR-001). Checked by the inbox smoke test.
5. **INV-parity**: repo copies == office2 copies after sync (NFR-003). Checked via the
   agent-prompt-sync audit log + direct file comparison.

## State transition (the mission lifecycle)

```
authored (repo, feature branch)
  → validated (validate_workspace.py PASS for capture)
  → merged to main (via PR)
  → deployed (agent-prompt-sync copies to office2 within 5 min; audit log records it)
  → verified (parity check + smoke test PASS)
  → [rollback path: revert workspace files + re-merge → sync re-copies prior version]
```

There is no partial/intermediate persisted state: the files are either the pre- or
post-refactor version on each side, and the sync is atomic per file.
