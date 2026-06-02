# Research: Remove escalation v1 comment-write parity

**Mission**: `remove-escalation-v1-parity-01KT4VTD`
**Date**: 2026-06-02

## Open Decisions

### OD-1: Shape of the comment-write removal

**Question**: Two candidate shapes for removing the v1 `[Felix-Escalation]` comment write — (A) delete the parity scaffolding entirely now, OR (B) flip the framing from "transitional parity" to "permanent audit-trail mirror" and keep the dual-write as a feature.

**Decision**: A — delete entirely.

**Rationale**:
- The original mission #309 explicitly framed the dual-write as soak-window safety to enable a single-config-flip rollback. The soak is over (declared retroactively complete on #309 today). The rollback option is no longer needed; the JSONL substrate is proven by 12 days of clean operation.
- Path B (keep as permanent feature) would require re-justifying the second Vikunja API call per event against the value of a feature no one actually uses (no runtime reader of the new comments would exist post-cleanup, since the phantom-subscription detector reads pre-cutover historical comments only — see OD-2).
- Kent's directly-stated preference on 2026-06-02: "I really despise dev actions that leave this kind of debt behind. Clean it up."

### OD-2: Disposition of the phantom-subscription reader

**Question**: `scripts/escalation/reconcile_completions.py` reads `[Felix-Escalation]` comments at runtime via `_COMMENT_MARKER` and `_count_escalation_comments` to power a phantom-subscription detector. After the comment write is gone, this reader continues to read frozen historical comments from pre-cutover. Three candidate dispositions:

- (A) Keep the reader as historical-record drift detection (limit reads to pre-cutover comments)
- (B) Delete the reader entirely as part of this mission
- (C) Defer disposition until #507 (Felix↔Vikunja bi-directional sync foundation) ships and subsumes it

**Decision**: B — delete now.

**Rationale**:
- The detector has fired ZERO times in 12 days of post-cutover operation. Verified by:
  - `gh issue list --repo kentonium3/kg-automation --search "phantom_subscription"` returns no hard-fail bugs filed.
  - `ssh office2-claude 'grep phantom_subscription /data/services/openclaw/state/escalation/*.jsonl /tmp/openclaw/*.log'` returns nothing.
- The catchable set is empty: if the backfill at #309 cutover had missed any tasks, the daily reconcile would have flagged them within the first 24h. None were flagged.
- The detector is structurally a substrate-specific cross-system drift check that #507 will replace with a proper general mechanism. Keeping it now means carrying a transitional-purpose code path until #507 ships, which violates the no-vestiges principle Kent is codifying at #514.
- Option C (defer until #507) would leave the reader running on a frozen substrate of historical comments for an unknown duration — exactly the drift pattern this mission exists to eliminate.
- If a phantom situation arises in the interim, the reconcile module's preserved subscribed-sweep path will catch tasks Felix knows about; tasks Felix doesn't know about would surface through operator notice or, eventually, #507.

**Confirmed via**: explicit user direction on 2026-06-02 during the /specify phase: "yes update the spec and proceed" with the deletion in scope.

## Closed Items (no further research needed)

- **JSONL schema invariance**: existing schema is untouched; new code writes the same JSONL records as today, minus the parallel comment write. No data migration step.
- **Pre-cutover comments stay in Vikunja**: explicit out-of-scope per spec C-001 and issue #376 body. The cleanup removes Felix's writer and reader, not the historical record on Vikunja's side.
- **Habits/enrichment domain unaffected**: out-of-scope per spec and issue body. Habits has its own parity period story (separate cleanup).

## Decisions

| ID | Decision | Rationale |
|---|---|---|
| D-001 | Delete the comment-PUT step from `_vikunja_side_effects` and the `_format_v1_comment`/`_COMMENT_PREFIX` helpers | Path A from OD-1 |
| D-002 | Delete `_COMMENT_MARKER`, `_count_escalation_comments`, and the phantom-subscription detection walk from `reconcile_completions.py` | Path B from OD-2 |
| D-003 | Delete the `phantom_subscription` reason code path from `hard_fail.py` along with its templating that references `[Felix-Escalation]` comment_count | Producer is being deleted (D-002), so the reason code becomes unreachable |
| D-004 | Delete `scripts/escalation/backfill_jsonl_from_comments.py` and `tests/escalation/test_backfill.py` | The substrate to backfill from will be frozen; tool has no future use |
| D-005 | Preserve the reconcile module's subscribed-sweep path unchanged | Primary drift detector; works on JSONL as canonical |
| D-006 | Group code+tests into WP01 and prompts+runbook+arch-data into WP02 | Sequencing rationale: prompts depend on the code/test behavior being settled. Two WPs of ~5 subtasks each fits the spec-kitty size guidance. |
