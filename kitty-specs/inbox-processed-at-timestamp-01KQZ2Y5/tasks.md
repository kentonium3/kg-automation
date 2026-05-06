# Tasks: Inbox Processed-At Timestamp

**Mission**: inbox-processed-at-timestamp-01KQZ2Y5
**Created**: 2026-05-06

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|-----|----------|
| T001 | Add processed_at parsing to classify_file() | WP01 | | [D] |
| T002 | Handle processed_at as both str and datetime from YAML | WP01 | | [D] |
| T003 | Graceful fallback when processed_at is malformed | WP01 | | [D] |
| T004 | Update processed-recent.md fixture with processed_at | WP02 | |
| T005 | Update processed-stale.md fixture with processed_at | WP02 | [P] |
| T006 | Add test: processed_at-based age calculation | WP02 | |
| T007 | Add test: mtime fallback when processed_at absent | WP02 | [P] |
| T008 | Add test: malformed processed_at fallback | WP02 | [P] |
| T009 | Update AGENTS.md Step 5 to instruct writing processed_at | WP03 | [P] |

## Work Packages

### WP01: Update prescan classifier to prefer processed_at

**Goal**: Modify `classify_file()` to derive staleness age from `processed_at` frontmatter field when present, falling back to mtime.
**Priority**: High (foundation for WP02)
**Dependencies**: None
**Estimated prompt size**: ~250 lines

- [x] T001 Add processed_at parsing to classify_file() (WP01)
- [x] T002 Handle processed_at as both str and datetime from YAML (WP01)
- [x] T003 Graceful fallback when processed_at is malformed (WP01)

**Prompt file**: `tasks/WP01-prescan-processed-at.md`

---

### WP02: Update test fixtures and add test cases

**Goal**: Update existing fixtures to include `processed_at` and add test coverage for the new code path plus backward compatibility.
**Priority**: High (validates WP01)
**Dependencies**: WP01
**Estimated prompt size**: ~300 lines

- [ ] T004 Update processed-recent.md fixture with processed_at (WP02)
- [ ] T005 Update processed-stale.md fixture with processed_at (WP02)
- [ ] T006 Add test: processed_at-based age calculation (WP02)
- [ ] T007 Add test: mtime fallback when processed_at absent (WP02)
- [ ] T008 Add test: malformed processed_at fallback (WP02)

**Prompt file**: `tasks/WP02-test-processed-at.md`

---

### WP03: Update agent instructions to write processed_at

**Goal**: Add instruction to felix-admin-capture AGENTS.md Step 5 to write `processed_at` alongside `status: processed`.
**Priority**: High (enables production use)
**Dependencies**: None (independent of WP01/WP02)
**Estimated prompt size**: ~200 lines

- [ ] T009 Update AGENTS.md Step 5 to instruct writing processed_at (WP03)

**Prompt file**: `tasks/WP03-agent-instructions.md`

## Parallelization

- **Lane A**: WP01 → WP02 (sequential — tests depend on code)
- **Lane B**: WP03 (independent — agent instructions are separate from Python code)
