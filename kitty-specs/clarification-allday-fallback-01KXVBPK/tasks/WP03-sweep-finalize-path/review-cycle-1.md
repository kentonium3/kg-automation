---
affected_files: []
cycle_number: 1
mission_slug: clarification-allday-fallback-01KXVBPK
reproduction_command:
reviewed_at: '2026-07-18T22:29:31Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP03
review_artifact_override_at: "2026-07-18T22:46:16Z"
review_artifact_override_actor: "operator"
review_artifact_override_wp_id: "WP03"
review_artifact_override_reason: "Arbiter override: cycle-2 reviewer-renata APPROVE (mutation-verified) supersedes cycle-1 REJECT; fix 64cbede2. Override required by review-artifact gate (#574/#1817 class, approve-gate variant on 3.2.6)."
---

# WP03 review feedback — cycle 1/3 (reviewer-renata, REJECT)

All primary guarantees, tests, and DoD checks hold **except one genuine FR-007 (MUST) gap** on the create-log-succeed / mark-fail → reconcile interleaving (the sharpest-risk ladder).

## Required change

**Close the FR-007 marker-loss on the "create+log succeed, `mark_processed` fails, later tick reconciles" interleaving.**

The failure sequence:
1. tick-1: `_run_finalize` creates the event AND writes the `calendar` routing-log row, but `_invoke_mark_processed` fails (e.g. `MARK_PROCESSED_TIMEOUT`) → transaction returns `status: "error"` → `finalize_record` returns `"retained"` (correct for create-once) — **but the `calendar_all_day_fallback` marker was never emitted** (it's only emitted on the fresh-`finalized` branch).
2. tick-2: the block is already logged → `skipped` → `status: finalized` → `_block_was_skipped` is True → returns `"reconciled"`, which suppresses the marker.
3. Net: event created exactly once (INV-1 holds), note processed, record removed — **but the distinct FR-007 `calendar_all_day_fallback` marker is permanently lost**; only the generic `calendar` row remains → operator cannot distinguish the fallback from a normal timed create (breaks SC-004 for that record).

**Fix**: make the `calendar_all_day_fallback` marker **idempotent and reconcile-aware** so it is emitted exactly once whenever the fallback event exists — including the mark-fail→reconcile path. Concretely:
- Before emitting, check (via `RoutingLogReader`) whether a `calendar_all_day_fallback` row **already exists for the note**.
- Emit it on **both** the fresh-`finalized` branch **and** the `reconciled` branch **when absent**.
- On the reconcile branch the skipped block result carries no `artifact` (`_artifact_of` returns `""`), so source the event id (`destination`) from the **existing `calendar` routing-log row** for the note, not from the skipped block result.
- This preserves "no re-emit" for the canonical FR-009 case (marker already present → do not re-emit) while guaranteeing FR-007's durable marker under the mark-fail interleaving.

**Add a regression test** for this exact sequence: force `_invoke_mark_processed` to return non-zero on the first `finalize_record` call after the `calendar` block is logged, then re-run `sweep_finalize`; assert the record is removed as `reconciled` AND that **exactly one** `calendar_all_day_fallback` row exists in the routing log.

## Repro (reviewer-provided)
Force `_invoke_mark_processed` to return a non-zero result on the first `finalize_record` after the `calendar` block is logged, then re-run `sweep_finalize` → observe record removed as `reconciled` with **no** `calendar_all_day_fallback` entry.

## Everything else verified clean
Eligibility gate (FR-005) empirically correct incl. datetime-string rejection; canonical path (INV-7) single-key; determinism (NFR-001); 8h window (C-006, no other aging in the flip band); marker extends KNOWN_KINDS (C-007); reconcile cases (a)/(b)/(c) correct; `test_routing_log.py` out-of-map edit minimal + justified. `pytest tests/inbox/ -q` → 478 passed.

## Note for WP04 (integration tests)
The reconciliation ladder ships with zero coverage in WP03 (DoD defers to WP04). **WP04 must explicitly cover the mark-fail→reconcile marker case** (this regression), not just the happy reconcile path.
