# Implementation Plan: Suppress expected drift alerts during rebaseline

**Branch**: `fix/862-drift-alert-rebaseline-suppression` | **Date**: 2026-07-23 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/drift-alert-rebaseline-suppression-01KY7GZZ/spec.md`
**Source issue**: kentonium3/kg-automation#862

## Summary

The security-monitor audit (`scripts/office2/security-monitor/audit.sh`) pages on
any baseline drift with zero awareness of felix-deployer's deferred-confirm
rebaseline. When an audited-surface deploy lands within the audit window, the audit
fires a false `error` page for drift felix-deployer has already recorded as expected.

**Approach** (revised after post-plan Codex review — see "Codex findings folded"):
add a small, tested Python helper that reads felix-deployer's pending-rebaseline
token (`rebaseline-pending.json`) and, reusing felix-deployer's own `read_token`,
returns the set of baselines with **fresh, expected** in-flight drift — where "fresh"
uses a dedicated **short** suppression window (~15 min), not felix-deployer's 24 h
stale threshold. `audit.sh` leaves its drift-detection path **completely unchanged**
(every drift still emits `[ALERT] <name>` to stdout and the run still exits `1`, so
felix-deployer's reconcile still detects the drift and stamps the new baseline). The
**only** change is at the end-of-run **push emit**: `audit.sh` calls the helper once
(only when drift exists) and filters the expected-baseline lines out of the push
summary — pushing only unexpected drift and IOC alerts, or nothing if all drift is
expected. The coupling is one-directional and read-only. Fail-safe by construction:
any error, missing/stale token, or unreadable state yields an **empty** set → the
audit pushes exactly as it does today.

## Technical Context

**Language/Version**: Python 3 (office2 is python3-only — no `python` binary) for the
helper; Bash for the `audit.sh` integration.
**Primary Dependencies**: Reuses `scripts/deploy/felix-deployer/rebaseline.py`
(`read_token`, token schema) as the single source of truth for the token. Defines a
dedicated short suppression window `AUDIT_SUPPRESS_WINDOW_SECONDS` (≈900 s), NOT
`MAX_AGE_SECONDS`. Standard library only (`json`, `datetime`, `pathlib`, `os`).
**Storage**: Reads (never writes) `/data/services/felix-deployer/state/rebaseline-pending.json`.
**Testing**: `pytest` unit tests for the helper (token present/fresh/stale/absent/
malformed; membership; empty-on-error). Bash integration verified by a live office2
round-trip during deploy (SC-001/002/003).
**Target Platform**: office2 (Ubuntu 24.04). Helper lives in the checkout at
`/home/claude/kg-automation/...`; `audit.sh` invokes it by absolute path, matching the
existing pattern where `audit.sh` already sources
`/home/claude/kg-automation/scripts/common/alert_bus.sh`.
**Project Type**: single (scripts + tests in the kg-automation repo).
**Performance Goals**: One Python subprocess per audit run (NFR-001: ≤100 ms added).
NOT per baseline — the helper returns the whole expected set in one call.
**Constraints**: read-only cross-subsystem coupling (C-001); reuse felix-deployer's
token schema + staleness (C-002); deterministic decision as a tested helper (C-003);
deploy via manifest, `audited_surface: false` (audit.sh matches no audited pattern).
**Scale/Scope**: ~15 baselines per audit run; token normally clears within ~10 s.

### Environment probe results (DIR-015 — verified live on office2, 2026-07-23)

- `/data/services/felix-deployer/state/` is `claude:claude`, mode `drwxrwxr-x`
  (traversable + readable by the `claude` user). The audit runs via `sg docker -c`
  as the **claude user** (group changes to docker; user stays claude), so it can
  read the `0600 claude`-owned token. **No permission barrier.**
- Checkout present at `/home/claude/kg-automation/scripts/deploy/felix-deployer/rebaseline.py`.
- Deployed audit copy at `/data/services/security-monitor/scripts/audit.sh`
  (`claude:claude`, executable) — re-synced via the canonical
  `scripts/deploy/deploy-security-monitor-audit.py` (precedent: applied manifest
  `0022-systemd-unit-content-baseline.yaml`).
- `audit.sh` is **not** an audited surface (`scripts/office2/security-monitor/*.sh`
  matches no pattern in `audited-surfaces.json`) → **rebaseline not required**.

## Charter Check

*GATE: passed (compact charter context; no blocking directives surfaced).*

- **DIR-006 (deterministic-where-possible)**: the suppress/alert decision is fully
  deterministic → routed into a tested Python helper, not agent judgment. ✅
- **DIR-014 (documentation-synchronization)**: FR-007 requires updating the security
  posture / observability-and-alerting narratives and any affected machine-readable
  data describing the coupling. ✅ (covered in IC-03)
- **DIR-015 (probe real environment during design)**: office2 probe completed above. ✅
- **Engineering principle — single source of truth**: the helper reuses
  felix-deployer's `read_token` + `MAX_AGE_SECONDS` rather than reparsing/redefining
  "expected" or "stale" (C-002). ✅
- **Guardrail preference / fail-safe**: ambiguity resolves toward alerting; the
  security-detection channel never loses a true positive (NFR-003). ✅

## Project Structure

### Documentation (this mission)

```
kitty-specs/drift-alert-rebaseline-suppression-01KY7GZZ/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # /spec-kitty.tasks output (NOT created here)
```

### Source Code (repository root)

```
scripts/
  deploy/
    felix-deployer/
      rebaseline.py            # EXISTING — reused (read_token, MAX_AGE_SECONDS)
      expected_drift.py        # NEW — the query helper (reads token → fresh expected set)
  office2/
    security-monitor/
      audit.sh                 # MODIFIED — one helper call per run + per-baseline suppress
tests/
  deploy/ (or scripts/deploy/felix-deployer/tests/)
      test_expected_drift.py   # NEW — unit tests for the helper
deploys/
  queued/
    drift-alert-rebaseline-suppression.yaml   # NEW — Tier-3 manifest, audited_surface: false
docs/design/architecture/
  security-posture… / observability-and-alerting…  # MODIFIED per FR-007 (+ any data/*.json)
```

**Structure Decision**: Single-project layout. The new helper is co-located with
`rebaseline.py` under `scripts/deploy/felix-deployer/` so it can `import rebaseline`
directly (same directory → no cross-package path gymnastics) and reuse its token
reader + staleness constant. `audit.sh` (the consumer) invokes the helper by absolute
checkout path, consistent with how it already sources `alert_bus.sh`.

## Implementation Concern Map

### IC-01 — Expected-drift query helper (deterministic core)

- **Purpose**: Given the live felix-deployer state, return the set of baseline names
  with fresh, expected in-flight drift — the single deterministic decision point.
- **Relevant requirements**: FR-001, FR-002, FR-004, FR-005; NFR-001, NFR-002;
  C-001, C-002, C-003.
- **Affected surfaces**: `scripts/deploy/felix-deployer/expected_drift.py` (new);
  imports `rebaseline.read_token` (reuses the schema + reader). Defines its own
  `AUDIT_SUPPRESS_WINDOW_SECONDS` (≈900 s / 15 min) — deliberately NOT
  `rebaseline.MAX_AGE_SECONDS` (Codex F3).
- **Sequencing/depends-on**: none.
- **Behavior contract**: `--list` prints the newline-delimited expected-baseline set
  to stdout — a baseline is included only when the token is present, the name is in
  `expected_baselines`, and `now − pending_since_utc ≤ AUDIT_SUPPRESS_WINDOW_SECONDS`.
  Empty output when: no token / unreadable / malformed / stale / unparseable timestamp.
  **Exit 0 always** (never fails the caller). **Read-only.** Honors an
  `EXPECTED_DRIFT_TOKEN_PATH` env override for tests/live-verify (Codex F4); defaults
  to `rebaseline.DEFAULT_TOKEN_PATH`.
- **Risks**: importing `rebaseline` pulls its `audited_surfaces` import — wrap the
  import AND the read in try/except so any failure degrades to an empty set
  (fail-safe), never raises (Codex F5: membership is done in Python, so no shell
  pattern-matching hazard).

### IC-02 — audit.sh integration (gate the PUSH, never the detection)

- **Purpose**: Filter expected-baseline drift out of the human push while leaving the
  drift-detection contract felix-deployer depends on completely unchanged.
- **Relevant requirements**: FR-003, FR-006, FR-008; NFR-003.
- **Affected surfaces**: `scripts/office2/security-monitor/audit.sh` — **no change**
  to `check_baseline()` or `alert()`: every drift still emits `[ALERT] <name>`, sets
  `ALERT=1`, and the run still exits `1` (FR-008). The change is confined to the
  end-of-run summary/emit block (lines ~283–319): when `ALERT=1`, call the helper once
  (`EXPECTED_DRIFT=$(python3 <helper> --list 2>/dev/null || true)`), build the push
  set from `$ALERT_FILE` by dropping lines matching
  `^\[ALERT\] <name> changed since baseline:` whose `<name>` is in `$EXPECTED_DRIFT`
  (exact match via `grep -Fxq`), and emit the push **only if** the push set is
  non-empty. `stdout` (`cat "$ALERT_FILE"`) and `exit 1` are unchanged.
- **Sequencing/depends-on**: IC-01.
- **Risks**: (a) the line-parse must extract `<name>` only from baseline-drift lines —
  IOC alert lines (`[ALERT] IOC: …`, `[ALERT] /etc/hosts modified…`) never match the
  `changed since baseline:` pattern, so they are always pushed (FR-003). (b) the single
  helper read happens at push time = freshest possible (resolves Codex F2 stale-snapshot
  race — no read-at-start/decide-later gap). (c) helper failure → empty var → today's
  push behavior.

### IC-03 — Deploy + documentation sync

- **Purpose**: Ship the audit.sh change to office2 through the manifest discipline and
  record the new coupling in architecture docs.
- **Relevant requirements**: FR-007; C-004.
- **Affected surfaces**: `deploys/queued/drift-alert-rebaseline-suppression.yaml`
  (entrypoint `scripts/deploy/deploy-security-monitor-audit.py`, tier 3,
  `audited_surface: false`, mirroring `0022`); the new helper deploys via
  felix-deployer's self-pull (checkout-resident, no separate copy);
  `docs/design/architecture/` security-posture + observability-and-alerting narratives
  (+ any affected `data/*.json`) describing the read-only audit↔felix-deployer coupling
  and its fail-safe rules.
- **Sequencing/depends-on**: IC-01, IC-02.
- **Risks**: live-verify (SC-001/002/003) must NOT write a synthetic token into the
  live felix-deployer state dir (the running timer would race/consume it — Codex F4).
  Instead point the helper at a temp token via `EXPECTED_DRIFT_TOKEN_PATH` and run the
  audit with that env set; felix-deployer's real state is never touched (INV-1).

## Codex findings folded (post-plan review, 2026-07-23)

The mandatory post-plan Codex pass caught one HIGH design flaw and four refinements;
all are folded into this plan and the spec before task decomposition:

- **F1 (HIGH)** — the original "skip `alert()`" idea would have made felix-deployer's
  reconcile see "All clear" and never stamp the baseline. **Fix**: gate only the push;
  leave the `[ALERT]`/exit-1 detection path unchanged (FR-008, IC-02).
- **F2 (MED)** — single-read-at-start stale-snapshot race. **Fix**: the one helper read
  moves to push time (freshest possible; no cache-then-decide gap).
- **F3 (MED)** — 24 h stale threshold could mute the security channel for a day.
  **Fix**: dedicated ~15 min `AUDIT_SUPPRESS_WINDOW_SECONDS` (FR-005, C-002).
- **F4 (MED)** — live synthetic token races the deployer. **Fix**:
  `EXPECTED_DRIFT_TOKEN_PATH` override for verification (IC-03).
- **F5 (LOW)** — shell pattern-match hazard. **Fix**: membership in Python + exact
  `grep -Fxq` (IC-01/IC-02).
```
