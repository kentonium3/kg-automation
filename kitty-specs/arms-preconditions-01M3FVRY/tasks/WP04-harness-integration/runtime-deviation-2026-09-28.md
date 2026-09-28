# WP04+ runtime lifecycle deviation — 2026-09-28

## Decision

Kent Gale selected **Option A: direct per-work-package execution** on 2026-09-28 after the confirmed `spec-kitty next` query/advance split tracked in [kg-automation#1040](https://github.com/kentonium3/kg-automation/issues/1040).

For the remainder of mission `arms-preconditions-01M3FVRY`:

- Do **not** call `spec-kitty next` in advancing mode for WP04, WP05, acceptance, merge, or any later action.
- Read-only query mode remains permitted.
- Drive WP04+ through the direct, deterministic workflow verbs.
- Preserve runtime run `21436f58be434403a2e244141e26bd8b` and its event evidence at `issued_step_id=discovery`; do not fabricate completed runtime steps or manually repair its cursor.

## Intentional audit gap

The `spec-kitty next` runtime lifecycle chain for WP04+ is intentionally absent. Direct work-package commands may record work-package lane/status events, workspace allocation, review evidence, and commits, but they will not create a correct WP04+ `NextStepIssued` / `MissionNextInvoked` / next-issuance lifecycle chain. This absence is an authorised consequence of the STOP-B decision, not missing implementation evidence.

If an acceptance or merge gate later refuses because that runtime lifecycle state is missing, treat it as the same #1040 defect surfacing downstream. Preserve the refusal, record it as downstream persistence, and do not re-diagnose or improvise a runtime repair.

## Upstream hold

The draft comment for closed upstream issue `spec-kitty/spec-kitty#961` must not be posted. Kent ruled its current-main premise stale because three `runtime_bridge.py` commits landed at 08:09Z on 2026-09-28 after the tested revision. Any future upstream claim requires a new clean reproduction on a newer identified build and fresh exact-copy approval.
