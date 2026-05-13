# Tasks: Auto-apply audit edits

**Mission**: `auto-apply-audit-edits-01KRG1BG`
**Source**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [quickstart.md](quickstart.md)
**Source issue**: [#259](https://github.com/kentonium3/kg-automation/issues/259)

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Create `scripts/openclaw/agents/felix-doc-auditor/handle_audit_routing.py` (partition + auto-apply + gate-file + audit-summary, with in-script allowlist and #254-pattern atomic writes) | WP01 |  | [D] |
| T002 | Create `tests/openclaw/agents/felix-doc-auditor/test_handle_audit_routing.py` (7+ cases per plan.md test plan) | WP01 | [P with T001] | [D] |
| T003 | Update `scripts/openclaw/agents/felix-doc-auditor/AGENTS.md` — add Invariant statement to § 7.5; replace § 7.9 with single helper invocation; reduce § 7.10 and § 7.11 to cross-references | WP01 |  | [D] |
| T004 | Run local pytest — confirm new tests pass and full suite remains green | WP01 |  | [D] |
| T005 | (Removed during planning — felix-doc-auditor has no AGENTS.md.tmpl, unlike felix-admin-capture. Subtask ID retained to preserve frontmatter contract; the implementer's task here is to verify the absence via `ls scripts/openclaw/agents/felix-doc-auditor/` and confirm no .tmpl mirror is needed.) | WP01 |  | [D] |

## Work Package WP01 — Implement handle_audit_routing.py and collapse § 7.9/§ 7.10/§ 7.11

**Goal**: Add the orchestrator helper that does all forward-path audit decision logic in script, and update AGENTS.md (and .tmpl) so the auditor's prompt reads "if any edit proposals, run helper, done" rather than reasoning through routing+commit+gate-file logic on every cron tick.

**Priority**: P2 (per source issue #259).

**Independent test (WP01 review scope)**: New helper exists and has unit tests covering all-auto, all-gate, mixed, empty, malformed-JSON, commit-failure, atomic-write-mode-preservation. AGENTS.md § 7.5 has the invariant; § 7.9 invokes the helper; § 7.10/§ 7.11 are stub cross-references; AGENTS.md.tmpl matches.

**Included subtasks (review scope — T001–T005)**:

- [x] T001 Create `scripts/openclaw/agents/felix-doc-auditor/handle_audit_routing.py` (WP01)
- [x] T002 Create `tests/openclaw/agents/felix-doc-auditor/test_handle_audit_routing.py` (WP01) [P with T001]
- [x] T003 Update felix-doc-auditor AGENTS.md (WP01)
- [x] T004 Run local pytest suite (WP01)
- [x] T005 Verify no AGENTS.md.tmpl exists for felix-doc-auditor (no-op subtask — planning artifact; see T005 note in Subtask Index) (WP01)

**Post-merge operator verification (out of WP01 review scope)**:

- Wait for / trigger next felix-doc-auditor cron tick; confirm a known-change_type-only audit auto-applies and closes without filing pending-approval (SC-001).
- Apply `audit-approve` to #236, #249, #250 in sequence; confirm each is drained correctly by the unchanged § 3 path (SC-003).
- Compare cron-run `total_tokens` pre- vs. post-merge for a comparable `frontmatter_date`-only audit; confirm ≥ 50% reduction (SC-004).

**Why the split**: same scoping discipline as #254 / #253 — operator verification requires running against deployed code on `main` (not from an unmerged lane branch) and requires waiting for real cron cycles. Folding into WP DoD would create the same conflict the rescope discipline (commit b82aac4) addresses.

**Implementation sketch**:

1. T001 + T002 are independent files; `[P]` candidate. The handler imports stdlib only (`json`, `subprocess`, `tempfile`, `os`, `stat`, `sys`, `pathlib`). Reuse the #254 atomic-write pattern verbatim (with a comment cross-referencing `scripts/inbox/inject_parse_error_marker.py`).
2. T003 + T004 are mechanical mirror edits. Touch only § 7.5 (add invariant) and § 7.9 / § 7.10 / § 7.11 (collapse to helper invocation). Preserve every other section.
3. T005 runs `python3 -m pytest tests/ -v`. Expect 7+ new tests added (+1 regression test from existing-suite count). Failure stops the WP.

**Parallel opportunities**: T001+T002 and T003+T004 are pairwise-parallel. T005 depends on all.

**Dependencies**: None on other open work. Builds conceptually on #254 (atomic-write pattern is reused).

**Risks (review-scope)**:
- **Atomic-write regression**: this WP creates a NEW edit-application surface. The #254 fix (mode preservation) MUST be applied here too. T007 in spec ("test_atomic_write_preserves_mode") guards against this. Reviewer must confirm the mode-preservation code is present.
- **AGENTS.md prose-edit precision**: only § 7.5, § 7.9, § 7.10, § 7.11 should change. Reviewer should `git diff` and confirm no other sections touched.
- **§ 3 untouched**: scope discipline. § 3 (decision-handling for existing pending-approvals) keeps its current prose. Reviewer should confirm.
- **Subprocess error handling**: handler invokes `git commit` and `gh issue create`. Reviewer should verify both have structured error reporting (stderr identifies which leg failed) and that a commit failure doesn't half-do (commit fails → gate NOT filed; both succeed or both don't happen).

**Estimated prompt size**: ~350 lines.

## MVP Scope

WP01 is the entire mission. No phase split necessary.

## Next Steps

After WP01 merges, the post-merge operator (you) runs the verification recipe in quickstart.md §§ 4–5.
