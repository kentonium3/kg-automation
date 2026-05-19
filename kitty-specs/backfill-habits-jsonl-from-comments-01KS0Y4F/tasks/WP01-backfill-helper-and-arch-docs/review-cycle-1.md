---
affected_files: []
cycle_number: 1
mission_slug: backfill-habits-jsonl-from-comments-01KS0Y4F
reproduction_command:
reviewed_at: '2026-05-19T20:58:53Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP01
---

# WP01 Review Feedback — Cycle 1/3 (Phase 4)

**Reviewer**: codex:gpt-5:python-reviewer (orchestrator running move-task on behalf — sandbox blocked the in-repo feedback-file write).

**Verdict**: Changes requested.

## Blocking finding 1 — `.pre-phase4-backfill.bak` overwrites on every live run

**Location**: `scripts/habits/backfill_jsonl_from_comments.py:286` (in `_snapshot_jsonl` or its caller).

**Bug**: every invocation of the live (non-dry-run) backfill performs `shutil.copy2(source, source + ".pre-phase4-backfill.bak")` unconditionally. After the first successful live run, the JSONL log contains the backfilled records. A second live invocation (which is supposed to be idempotent and harmless) overwrites the existing `.pre-phase4-backfill.bak` with the **post-backfill** content. The true pre-backfill rollback substrate is silently lost.

**Why this violates the contract**:
- FR-008: "Before the first JSONL write in a live run, the helper creates a snapshot copy ... Skipped if the JSONL log file does not yet exist." The "first" qualifier implies the snapshot represents the pre-backfill state — by definition, the state before ANY backfill records were appended. Overwriting it on re-runs destroys that invariant.
- Rollback contract (spec § Rollback plan and quickstart.md): operator restores from `.bak` to undo the backfill. If `.bak` has been overwritten with post-backfill content, the restore is a no-op (or worse, restores a partially-corrupted JSONL).

**Required fix**:
- If the `.bak` file already exists, do NOT overwrite. Either:
  - (Preferred) Skip the snapshot step and log to the summary report's `snapshot` section: "Pre-backfill snapshot already exists at <path>; preserved." This makes re-runs trivially safe.
  - OR rename the new snapshot with a timestamp suffix (e.g., `.pre-phase4-backfill-2026-05-19T20:30Z.bak`) — preserves multiple snapshots but makes rollback ambiguous.

Recommend the first approach: check `if not bak_path.exists()` before `shutil.copy2`. Add a test that asserts the .bak is NOT overwritten on a second live invocation.

---

## Blocking finding 2 — Malformed comment snippets missing from summary report

**Location**: `scripts/habits/backfill_jsonl_from_comments.py:419` (counter increment) and `scripts/habits/backfill_jsonl_from_comments.py:561` (summary formatter).

**Bug**: the helper increments a `records_skipped_malformed` counter when a comment fails to match `FELIX_COMMENT_PATTERN`, but the summary report only prints the count (`Comments skipped as malformed: N`). The malformed comment text snippets are not captured or displayed.

**Why this violates the contract**:
- FR-009: "Output a summary report ... including: records-by-task, records-by-state, **comments-skipped-as-malformed (count + snippets)**, unmapped-state-values (count + original state + snippets per occurrence), and any anomalies." The count + snippets requirement is explicit and parallels the unmapped-state-values section, which DOES include snippets.
- Operator value: without snippets, the operator can't audit what's being skipped or distinguish legitimate non-Felix comments from bugs in the regex / parser.

**Required fix**:
- Capture each malformed comment's snippet (task_id + first ~80 chars of the comment text) into a list during the backfill loop.
- Include the list in the summary report under the existing "Comments skipped as malformed" section, formatted similarly to the `unmapped-state-values` section: one line per occurrence with task_id and snippet.
- Add a test in TestBackfillDryRun (or a new TestMalformedReporting group) that mocks 2-3 malformed comments and asserts both the count AND the snippets appear in the formatted report.

---

## Non-blocking notes (explicit reviewer verdicts)

- **Larger helper size** (~575 effective lines vs my ~220 estimate): **acceptable**. Behavior matches the contracts; size growth comes from legitimate features (`_SnapshotError` discriminator, per-task bucketing, summary formatter).
- **Unmapped-state snippet trimming to first line / 80 chars**: **acceptable**. Reasonable readability default; matches data-model.md examples closely enough.
- **C-001 vs C-004 terminology in the WP prompt**: editorial cleanup for future WP prompts; non-blocking.

## Non-blocking validations (passed)

- All 307 habits tests pass.
- New module coverage: 92%.
- `python3 -m scripts.habits.backfill_jsonl_from_comments --help` exits 0.
- C-004 honored: `git diff main -- scripts/habits/exclude_completed.py` returns empty.
- No Vikunja write methods (only GET).
- `python3 tooling/scripts/validate_docs.py` passes.
- Both JSON docs parse.

## Cycle tracking

Cycle 1/3. Re-implementer should:
1. Fix the `.bak` overwrite (skip if .bak already exists).
2. Capture + display malformed-comment snippets in the summary report.
3. Add regression tests for both fixes.
4. Re-run the full test suite to confirm no regressions.
