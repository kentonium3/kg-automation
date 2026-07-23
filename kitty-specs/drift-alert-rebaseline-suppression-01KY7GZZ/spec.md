# Suppress expected drift alerts during rebaseline

**Mission**: drift-alert-rebaseline-suppression-01KY7GZZ
**Source issue**: kentonium3/kg-automation#862
**Mission type**: software-dev

## Purpose

**TL;DR** — Stop the security-monitor drift audit from paging on deploy drift
that felix-deployer has already flagged as expected and is actively rebaselining.

When an audited-surface deploy lands within seconds of a security-monitor audit
tick, the audit sees the (expected) drift and fires a false `error` page **before**
felix-deployer's deferred-confirm rebaseline stamps the new baseline. The page is
noise for drift the system already knows about and is reconciling. This mission
makes the audit consult felix-deployer's pending-rebaseline token so it withholds
the push **only** for the exact baselines with expected in-flight drift, bounded by
the pending window — while still paging immediately on any genuinely unexpected
drift, so the channel that must stay credible for real unauthorized-change
detection keeps its credibility.

## User Scenarios & Testing

**Primary actor**: the security-monitor audit run (automated; daily cron plus
on-demand rebaseline audits).
**Secondary actors**: felix-deployer (writes the pending-rebaseline token during a
deploy), and the operator (Kent), who receives the push pages.

### Primary scenario (happy path)

1. felix-deployer applies an audited-surface manifest; the audited surface drifts
   on disk (e.g. a new `EnvironmentFile=` line in a systemd user unit).
2. felix-deployer writes/updates the pending-rebaseline token naming the exact
   baselines with expected in-flight drift (`expected_baselines`) and when the
   window opened (`pending_since_utc`).
3. A security-monitor audit tick runs in the window before felix-deployer confirms
   and stamps the new baseline. It detects drift on baseline `X`.
4. The audit finds `X` in the active pending token's `expected_baselines` and the
   token is within its bounded window → it **withholds the push** for `X` while
   still recording the drift locally.
5. Seconds later felix-deployer reconciles and stamps the new baseline; subsequent
   audits read clean. **The operator is never paged for the expected drift.**

### Exception / edge scenarios

- **Unexpected drift** — the audit detects drift on baseline `Y` that is *not* in
  any active pending token → it pages normally (real, unauthorized-change signal).
- **Mixed run** — drift on both expected `X` and unexpected `Y` in one audit run →
  the audit withholds the push for `X` only and **still pages for `Y`**. Never a
  blanket mute of the run.
- **No / unreadable token** — the token is absent, unreadable, or malformed → the
  audit pages normally (ambiguity resolves toward alerting).
- **Stale token** — the token exists but is older than the bounded window
  (a stuck/failed reconcile) → the audit does **not** suppress; it pages so the
  genuinely-stuck expected drift surfaces.

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | When the audit detects drift on a baseline, it MUST determine whether that specific baseline is named in felix-deployer's active pending-rebaseline token before deciding whether to raise a push alert for it. | Required |
| FR-002 | The audit MUST withhold the **push notification** for a drifted baseline **only when all** of the following hold: (a) an active pending-rebaseline token exists and is readable; (b) the baseline name is in the token's `expected_baselines`; (c) the token is within the bounded suppression window (see FR-005). In every other case it MUST push exactly as it does today. Suppression gates only the *push* — never drift *detection* (see FR-008). | Required |
| FR-003 | Suppression MUST be scoped per baseline. In a single audit run mixing expected and unexpected drifted baselines, the audit MUST withhold the push only for the expected baselines and MUST still push for every unexpected drifted baseline and every non-baseline IOC alert. | Required |
| FR-004 | If the pending token is absent, unreadable, or malformed, the audit MUST fall back to current behavior (push the alert). Ambiguity always resolves toward alerting. | Required |
| FR-005 | The suppression window MUST be a dedicated **short** bound (a small multiple of the felix-deployer deploy tick — target ~15 minutes), **not** felix-deployer's 24-hour stale-token threshold. If the token's `pending_since_utc` is older than this window, the audit MUST NOT suppress; it MUST push, so a stuck/lingering (or maliciously planted) token can never mute the security channel for longer than the short window. | Required |
| FR-006 | A suppressed drift MUST still be recorded locally — the audit log and the `drift-events.jsonl` doc-audit signal MUST be written exactly as for an un-suppressed drift. Only the push notification is withheld; the local audit trail and downstream signals are unchanged. | Required |
| FR-007 | The change MUST update the affected architecture/observability documentation (security posture and observability-and-alerting narratives, plus any affected machine-readable data) to describe the read-only audit↔felix-deployer coupling and its fail-safe rules. | Required |
| FR-008 | The change MUST NOT alter the audit's drift-**detection** contract that felix-deployer's reconcile depends on: every drifted baseline (expected or not) MUST still emit its `[ALERT] <name> changed since baseline:` line to stdout and the audit MUST still exit `1` on any drift, so felix-deployer continues to detect the expected drift and stamp the new baseline. Only the human push is gated. | Required |

### Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-001 | Consulting the pending token MUST add negligible latency to an audit run. | ≤ 100 ms added per audit run (a single small-JSON local file read; no network). | Required |
| NFR-002 | A missing, locked, or errored felix-deployer state directory/file MUST NOT cause the audit to fail — it continues and defaults to alerting. | Audit exit-code contract preserved: `0` = all clear, `1` = drift; no new non-zero exits introduced by the token read. | Required |
| NFR-003 | For any drift not provably expected (per FR-002), alerting behavior MUST be identical to today. | Zero reduction in true-positive push alerts; measured by parity of alert output on non-expected drift versus pre-change. | Required |

### Constraints

| ID | Constraint | Status |
|----|-----------|--------|
| C-001 | The coupling MUST be one-directional and read-only: the audit reads felix-deployer's pending-token state and MUST NOT write to or mutate any felix-deployer state. | Required |
| C-002 | The suppression logic MUST reuse felix-deployer's existing token schema and reader (`read_token`, `expected_baselines`, `pending_since_utc`) as the single source of truth for **what** drift is expected — it MUST NOT redefine or reparse the token. The audit applies its own dedicated **short** suppression window (FR-005) for **how long** it honors the token; this is intentionally distinct from felix-deployer's 24 h `MAX_AGE_SECONDS` stale threshold and is not a second definition of "expected." | Required |
| C-003 | The deterministic decision `(baseline_name, token_state) → suppress \| alert` MUST be implemented as an independently tested helper per the repo's helper-script conventions, not as ad-hoc inline shell logic. | Required |
| C-004 | The change deploys to office2 through the `deploys/queued/<name>.yaml` manifest discipline; if `audit.sh` (or any touched file) is an audited surface, the deploy must carry the rebaseline obligation. | Required |

## Success Criteria

| ID | Criterion |
|----|-----------|
| SC-001 | An audited-surface deploy that lands within the audit window produces **zero** false push pages for its expected baselines. |
| SC-002 | A drift on a baseline not named in any pending token produces a push page **100%** of the time (no true-positive suppressed). |
| SC-003 | With a stale/expired pending token, an expected-but-unreconciled drift produces a push page within one audit cycle. |
| SC-004 | Across a one-week observation window containing at least one audited-surface deploy, the operator receives no expected-drift false page. |

## Key Entities

- **Pending-rebaseline token** — felix-deployer state
  (`rebaseline-pending.json`) naming the baselines with expected in-flight drift
  (`expected_baselines`) and the window-open timestamp (`pending_since_utc`);
  normally cleared within ~10 s of the deploy by felix-deployer's reconcile.
- **Baseline** — a named security snapshot (e.g. `systemd-user-unit-contents.txt`)
  the audit diffs against its stored copy.
- **Drift page / alert** — the push notification the audit sends via the
  felix-alert bus (#701) when a baseline differs from its snapshot.

## Domain Language

- **expected drift** — a baseline change felix-deployer has recorded in its pending
  token as an in-flight, sanctioned rebaseline.
- **page / alert** — a push notification via the felix-alert bus (#701). Preferred
  over "notification."
- **suppress / withhold** — withhold the *push* while retaining the full local
  record. It never means deleting or hiding the drift itself.

## Assumptions

- **Resolution of the issue's "suppress or downgrade" fork**: the default chosen
  here is **withhold the push and retain the full local record** (audit log +
  `drift-events.jsonl` unchanged). Rationale: the drift is already durably recorded
  locally, so the only noise is the push; a low-priority "confirmation" push was
  considered and rejected as re-introducing the noise the mission removes. This is
  the one product choice the operator may wish to revisit; it is called out for
  review rather than silently assumed.
- The bounded suppression window is a dedicated **short** window (~15 min, a small
  multiple of the felix-deployer deploy tick), **not** felix-deployer's 24 h stale
  threshold (revised per post-plan Codex Finding 3). In practice the token clears
  within ~10 s, so real suppression lasts seconds; the ~15 min bound only covers a
  slow reconcile and hard-caps how long a lingering or maliciously planted token can
  mute the security push.
- **Threat-model boundary**: the token is `0600 claude`-owned. An actor with `claude`
  write access could already trigger felix-deployer's auto-rebaseline of a planted
  change (a pre-existing felix-deployer vector, independent of this mission). This
  mission adds only a short-window *push* suppression on top of that; it grants no new
  capability, and the short window bounds the mute. Full token-provenance validation
  was considered and deferred as disproportionate to that pre-existing exposure.
- felix-deployer and security-monitor both run on office2 and the audit (running as
  the `claude` user via `sg docker -c`) can read felix-deployer's `0600` token —
  **verified live on office2** during plan (per DIR-015).
- The suppression gates the **push** at the end-of-run emit step; drift detection
  (the per-baseline `[ALERT]` line + exit code) is untouched so felix-deployer's
  reconcile is unaffected (FR-008).

## Out of Scope

- Redesigning felix-deployer's rebaseline lifecycle or the token schema.
- Changing what counts as an audited surface, or the set of baselines.
- Any change to ntfy push-delivery ordering (the out-of-order-on-phone symptom is a
  downstream consequence of the false page; removing the false page removes it).
