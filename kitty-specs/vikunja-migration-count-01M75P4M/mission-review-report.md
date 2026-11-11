# Mission Review: vikunja-migration-count-01M75P4M

**Reviewer**: Claude Sonnet 5.5 (reviewer-renata), 2026-11-11. **Post-merge whole-diff review**: Codex gpt-6.1-sol, 2026-11-11, APPROVE, 0 MATERIAL. **Implementer**: Codex gpt-6.1-sol. **Orchestrator**: Claude Opus 5.5.

**Verdict: PASS WITH FOLLOW-UPS.** No MATERIAL findings. `tests/deploy`: 1885 passed. The full suite outside the sandbox: 8955 passed, 0 failed.

## Requirement trace

FR-001 to FR-007, NFR-001, NFR-002 and C-001 to C-004 are met. Every removed `!= 10` is replaced by a comparison against a reviewed input. For the builder, that is the CLI's expected count against the observed difference. For the verifier, it is the sha-bound baseline's exact set. No gate is weakened. Both history records match the real release records and their applied manifests.

## Process items and dispositions

1. **Decisions lock.** Claim and move-task refused with `WRITE_CHECKOUT_DIRTY`, naming only the untracked 0-byte `decisions/index.json.lock`. That is the same symptom as registry row 131 (spec-kitty/spec-kitty#6628, `record-analysis`). Its workaround was applied: confirm the lock is unheld, move it outside the checkout, run the command, then move it back with inode and mtime unchanged. The lock stays untracked and is never committed. This is a recurrence on two more commands, to note on #6628 with Kent's approval of the copy.
2. **Analysis A3 residual.** A zero-migration mismatch rejection at gate compare and preflight was folded into the implementer prompt on 2026-11-11, not into the WP file. It is covered by `test_zero_migration_compare_and_preflight`.
3. **FR-007 is not in the acceptance matrix.** It was added after finalize-tasks, by analysis A1, so the matrix holds only FR-001 to FR-006 (registry: a late FR cannot be recorded). Its evidence: the WP01 commit message records the doc-sync disposition (architecture JSON, markdown view, INDEX and roadmap had no affected entry; the runbook is updated). The matrix was not hand-edited.

## Follow-ups (non-blocking)

- The PR description states that the verifier's fail-closed property rests on the baseline sha being reviewed in the STAGE PR.
- The rrule.3 STAGE or ACTIVATE PR must add `services/vikunja/releases/v2.8.0-rrule.3.json`. Add a runbook note.
- Validate every history entry against its applied manifests, not only the first and current releases. Include 0035 and 0036 in the next-release fixture (post-merge review EDGE).
- `test_next_release_predecessor_refusals` could assert specific failure codes.
