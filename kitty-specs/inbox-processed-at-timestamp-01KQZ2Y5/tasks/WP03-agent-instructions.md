---
work_package_id: WP03
title: Update agent instructions to write processed_at
dependencies:
- WP01
- WP02
requirement_refs:
- FR-01
- FR-02
- FR-03
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T009
history:
- date: '2026-05-06'
  event: created
  agent: claude-opus
authoritative_surface: scripts/openclaw/agents/felix-admin-capture/
execution_mode: code_change
owned_files:
- scripts/openclaw/agents/felix-admin-capture/AGENTS.md
tags: []
---

# WP03: Update agent instructions to write processed_at

## Objective

Update the felix-admin-capture agent's AGENTS.md to instruct the agent to write
a `processed_at` frontmatter field alongside `status: processed` when processing
inbox files.

## Context

- **File**: `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`
- **Section**: Step 5 ("Mark as processed"), currently at lines 146-154
- **Current behavior**: Agent writes `status: processed` or `status: needs-review`
- **Target behavior**: When writing `status: processed`, also write `processed_at`
  with current timestamp in agent's local timezone, ISO 8601 format

This is an agent prompt change only — no code execution is involved. The agent
(an LLM running in OpenClaw) reads these instructions and follows them when
processing inbox files.

## Implementation Guide

### T009: Update AGENTS.md Step 5 to instruct writing processed_at

**Purpose**: Add clear instruction for the agent to write the `processed_at`
field at processing time.

**Current Step 5 text** (lines 146-154):
```markdown
### Step 5: Mark as processed

After successfully processing all content blocks from an inbox file:
- Update frontmatter: `status: processed`
- Do NOT delete the original file — preserve it as a record

If any content block could not be classified:
- Set `status: needs-review` instead
- Add a note in the processing log explaining what was unclear
```

**Updated Step 5 text**:
```markdown
### Step 5: Mark as processed

After successfully processing all content blocks from an inbox file:
- Update frontmatter: `status: processed`
- Update frontmatter: `processed_at: "<current timestamp>"` using your local
  timezone in ISO 8601 format (e.g. `processed_at: "2026-05-06T12:30:00-04:00"`)
- Do NOT delete the original file — preserve it as a record

If any content block could not be classified:
- Set `status: needs-review` instead (do NOT write `processed_at`)
- Add a note in the processing log explaining what was unclear
```

**Key points**:
- The timestamp must use the agent's local timezone (not UTC) for human readability in Obsidian
- Quote the value in the YAML frontmatter to prevent YAML auto-parsing issues
- `processed_at` is NOT written for `needs-review` status — only for successful processing
- The timestamp is written once and not updated on subsequent file touches

**Files**: `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`

## Definition of Done

- [ ] Step 5 in AGENTS.md includes `processed_at` instruction
- [ ] Instruction specifies ISO 8601 format with local timezone
- [ ] Instruction specifies quoting the value in frontmatter
- [ ] `needs-review` path explicitly excludes `processed_at`
- [ ] No other sections of AGENTS.md are modified

## Risks

- **Agent compliance**: LLM agents may not perfectly follow formatting instructions.
  The prescan fallback (WP01) handles this — malformed timestamps fall back to mtime.

## Reviewer Guidance

- Verify the instruction is clear and unambiguous
- Verify the example timestamp format matches ISO 8601 with timezone offset
- Verify no other AGENTS.md sections were inadvertently modified
- Verify the `needs-review` exclusion is explicit
