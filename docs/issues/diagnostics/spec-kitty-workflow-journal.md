---
title: Spec-Kitty Workflow Journal
doc_type: diagnostic
status: active
---

# Spec-Kitty Workflow Journal

**Purpose**: Chronological log of suspected or actual spec-kitty workflow errors, unexpected behaviors, and edge cases encountered during feature development. Each entry captures enough evidence (commands run, JSON outputs, git state, file contents) to retrace steps and diagnose root causes if downstream errors occur.

**Standing directive**: When a spec-kitty workflow produces unexpected behavior — even if not a hard error — append an entry here before attempting any compensating action. Do not use git or other tools to simulate what spec-kitty should have done.

**Related**:
- `docs/issues/diagnostics/spec-kitty-feedback/` — individual incident reports intended for upstream reporting to spec-kitty-cli
- This file is a running internal log; individual entries may graduate to standalone reports under `spec-kitty-feedback/` if they warrant upstream attention

---

## Entry Template

```markdown
## YYYY-MM-DD — {short title}

**Feature**: {NNN-slug}
**Spec-kitty version**: {x.y.z}
**Workflow step**: {specify | plan | tasks | implement | review | accept | merge}
**Severity**: {observation | soft-error | hard-error}

**What I expected**: ...

**What actually happened**: ...

**Evidence**:
- Commands run: ...
- JSON / output excerpts: ...
- Git state: ...

**Hypothesis**: ...

**Resolution**: {pending | user-decision | bug-filed | resolved-in-vX.Y.Z | won't-fix}

**Downstream impact**: ...
```

---

## 2026-04-04 — auto_commit did not capture LLM-authored spec edits during /spec-kitty.specify

**Feature**: 015-documentation-architecture-rationalization
**Spec-kitty version**: 3.0.3
**Workflow step**: specify
**Severity**: observation (behavior unclear, no hard error)

**What I expected**:
With `.kittify/config.yaml` setting `auto_commit: true`, I expected the artifacts produced during `/spec-kitty.specify` (populated `spec.md`, updated `meta.json`, new `checklists/requirements.md`) to be auto-committed on the target branch, matching the commit pattern of prior features (e.g., F014) where `spec.md` content landed in commits titled "Add spec for feature ###-slug".

**What actually happened**:
`spec-kitty agent feature create-feature …` created the feature directory scaffold and committed two empty/template files to `main`:
- `6c35834 Add spec for feature 015-documentation-architecture-rationalization`
- `d574abb Add meta for feature 015-documentation-architecture-rationalization`

Subsequent LLM edits via the Write tool — setting `mission: documentation` in `meta.json`, writing the full spec body to `spec.md`, and creating `checklists/requirements.md` — were NOT auto-committed. The status `tasks/` directory and `status.events.jsonl` file (scaffolded by `create-feature`) also remained untracked.

**Evidence**:
- Config: `/Users/kentgale/repos/kg-automation/.kittify/config.yaml` contains `auto_commit: true` at top level (not nested under `agents`).
- `create-feature` JSON output (excerpt): `"write_mode": "update_existing_files", "next_step": "Read then update spec_file/meta_file; do not recreate with blind write."`
- `git status --short` after LLM edits:

  ```text
   M kitty-specs/015-documentation-architecture-rationalization/meta.json
   M kitty-specs/015-documentation-architecture-rationalization/spec.md
  ?? kitty-specs/015-documentation-architecture-rationalization/checklists/
  ?? kitty-specs/015-documentation-architecture-rationalization/status.events.jsonl
  ?? kitty-specs/015-documentation-architecture-rationalization/tasks/
  ```

- `git log --oneline -3`:

  ```text
  d574abb Add meta for feature 015-documentation-architecture-rationalization
  6c35834 Add spec for feature 015-documentation-architecture-rationalization
  c5a47d5 refactor: consolidate diagnostics and postmortems under docs/issues
  ```

**Hypothesis**:
spec-kitty's `auto_commit` mechanism only fires inside its own Python CLI code paths when spec-kitty itself writes a file. LLM-authored edits via the Claude Code Write tool bypass those hooks. It's unclear whether:
- The slash-command author expects the LLM to commit artifacts manually at the end of `/spec-kitty.specify`, or
- A later step (e.g., `/spec-kitty.plan`) detects and commits the staged edits, or
- auto_commit is meant to catch these and a regression / config-parsing issue is preventing that.

F014's git history shows its spec body DID land in a commit, so there's a path by which this normally works — just not visible from my seat.

**Resolution**: user-decision — Kent directed: "start journal, then proceed with C (let workflow run without manual compensation) to see what happens naturally." Proceeding to `/spec-kitty.plan` next.

**Downstream impact**:
- If `/spec-kitty.plan` runs `check-prerequisites`, it may fail or warn about dirty working tree.
- If plan silently commits the accumulated changes, that confirms the intended pattern.
- If plan does neither (proceeds and leaves both specify + plan outputs uncommitted), the dirty-state will compound and future workflow steps may hit harder errors.
- Ultimate risk: merge-time conflicts or spec-kitty state-machine confusion because identity files were updated out-of-band.

---
