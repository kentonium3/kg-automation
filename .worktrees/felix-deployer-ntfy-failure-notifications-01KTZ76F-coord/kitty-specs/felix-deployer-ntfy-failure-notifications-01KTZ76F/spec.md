# Specification: Felix-deployer ntfy Failure Notifications

**Mission**: `felix-deployer-ntfy-failure-notifications-01KTZ76F`
**Mission type**: software-dev
**Source issue**: kentonium3/kg-automation#595

---

## Intent Summary

Replace the felix-deployer applier's broken openclaw-cron WhatsApp DM dispatch with a direct ntfy.sh push, so failed deploys reliably reach the operator's phone independent of openclaw/WhatsApp availability.

- **Primary actor**: the felix-deployer applier ticking on office2.
- **Trigger**: a manifest in `deploys/queued/` fails apply (any phase: tier guard, verification_pre, entrypoint, verification_post).
- **Success outcome**: within seconds of the failure being recorded to `deploys/failed/`, the operator receives an ntfy push on their phone showing the manifest name, failed phase, tier, head SHA prefix, failed-at timestamp, and a redacted error summary. The operator decides to fix-forward or roll back.
- **Rule that must always hold**: a notification dispatch failure (ntfy.sh down, network blip, bad topic, HTTP 5xx) NEVER crashes the applier tick. The on-disk failure record in `deploys/failed/` remains the source of truth; the push is escalation, not the record.
- **Most common exception**: office2 has no outbound internet, or ntfy.sh is unreachable. The applier tick continues, the failure is recorded to disk, and the notify call logs a non-fatal warning. The operator discovers the failure later by polling `deploys/failed/` — same fallback the existing security-monitor uses.

---

## Domain Language

Use these canonical terms throughout planning and implementation:

- **notification** — the rendered title+body that ntfy.sh receives via HTTP POST. Not "DM", not "alert", not "message".
- **notification contract** — the schema describing how `(manifest, phase, error_summary, head_sha, failed_at)` is rendered to title+body. Versioned as `ntfy-notification-v1`.
- **topic** — the private ntfy.sh path segment identifying where notifications route. Stored in a systemd `EnvironmentFile=`, never committed.
- **failure record** — the existing on-disk artifact in `deploys/failed/<manifest>/`. The source of truth for what happened; unchanged by this mission.
- **substrate** — the transport mechanism for the notification. This mission's choice is **ntfy.sh** (HTTPS POST), chosen for failure-mode independence from openclaw and WhatsApp.

---

## User Scenarios & Testing

### Primary scenario — Failed deploy notifies operator

A queued manifest fails at the `entrypoint` phase (the deploy script exits non-zero). The applier tick:
1. Records the failure to `deploys/failed/<manifest>/` per existing behavior.
2. Calls `notify.dispatch_failure_notification(manifest, phase, error_summary, head_sha, failed_at)`.
3. notify.py redacts secrets from `error_summary`, truncates to ≤500 chars, renders title+body per the `ntfy-notification-v1` contract, and POSTs to `https://ntfy.sh/$FELIX_DEPLOYER_NTFY_TOPIC` via `curl`.
4. The operator's phone (ntfy app subscribed to the topic) shows the alert within a few seconds.
5. Tick continues and exits normally; the next tick runs on schedule.

### Exception scenario — ntfy.sh unreachable

office2 has no outbound internet, or ntfy.sh returns 5xx, or curl times out. The applier:
1. Records the failure to disk (unchanged).
2. notify.py's curl invocation fails. notify.py returns `LibResult(ok=False, summary=..., details={"error_code": "NTFY_UNREACHABLE", ...})`.
3. The tick logs the dispatch failure as a non-fatal warning and continues.
4. The manifest stays in `deploys/failed/` for operator discovery via direct polling.

### Bootstrap scenario — Redeploying the fixed applier

Post-merge, the operator runs `scripts/deploy/deploy-felix-deployer-bootstrap.sh --rollback` (stops + removes the broken applier's units) and then `--apply` (re-deploys the fixed applier). The new `--apply` MUST succeed end-to-end — including the previously-broken step 5 area — because step 5 is removed entirely; no openclaw cron registration is attempted. The applier's systemd service file picks up `EnvironmentFile=` so `FELIX_DEPLOYER_NTFY_TOPIC` is in the service environment.

### Edge cases

- **`FELIX_DEPLOYER_NTFY_TOPIC` is unset or empty**: notify.py logs a non-fatal warning ("ntfy: skipped (topic not configured)") and returns `LibResult(ok=False)`. The tick continues. This mirrors the security-monitor behavior.
- **`error_summary` is empty**: notification still dispatches; the body shows "(no error summary)" rather than an empty section.
- **`error_summary` contains a secret**: the redactor strips known patterns BEFORE truncation. Any post-redaction text that exceeds 500 chars is truncated.
- **Repeated failures for the same manifest**: each tick that re-attempts the manifest produces a fresh notification. No dedup; volume is operator-tolerable (≤5/day expected) and silencing would mask the same underlying issue worsening.
- **Concurrent ticks**: the existing applier is single-instance (systemd `Type=oneshot` timer-driven); no concurrent dispatch concern.

---

## Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | The applier dispatches a push notification via ntfy.sh whenever a manifest's apply fails (any phase). | required |
| FR-002 | A notification dispatch failure (network error, HTTP 5xx, missing topic, missing curl binary) does NOT crash the applier tick; the tick continues and the next manifest is processed. | required |
| FR-003 | The notification body's error summary is redacted of known secret patterns before being truncated to ≤500 characters. | required |
| FR-004 | The notification carries: manifest name, tier, failed phase, head SHA prefix (first 8 chars), failed-at timestamp (ISO-8601 UTC), and a redacted error summary. | required |
| FR-005 | The bootstrap deploy script (`scripts/deploy/deploy-felix-deployer-bootstrap.sh`) does NOT attempt to register any openclaw cron for failure alerts. Step 5 of the previous bootstrap (the broken `openclaw cron edit … --payload-template` call) is removed. | required |
| FR-006 | The bootstrap deploy script's `--apply` mode succeeds end-to-end on an office2 host that has the previously-broken partial-applied state, after a preceding `--rollback`. The combined `--rollback` then `--apply` sequence is idempotent. | required |
| FR-007 | The ntfy topic is read from environment variable `FELIX_DEPLOYER_NTFY_TOPIC`, supplied to the applier via a systemd `EnvironmentFile=` directive. The topic value is NEVER committed to the repository. | required |
| FR-008 | The existing `kitty-specs/pull-based-deploy-pipeline-01KTYQQS/contracts/dm-payload-v1.md` is superseded by a new contract `contracts/ntfy-notification-v1.md` (in this mission's feature dir) describing the rendered title+body shape and the redact-then-truncate invariant. | required |
| FR-009 | `scripts/deploy/felix-deployer/notify.py` exposes a single public function `dispatch_failure_notification(manifest, phase, error_summary, head_sha, failed_at)` returning `LibResult`. Callers (notably `_tick.py`) invoke only this function. | required |
| FR-010 | `_tick.py` is updated so its dispatch call uses the new `dispatch_failure_notification` API instead of `dispatch_failure_dm`. The `PHASE_TO_DM_PHASE` collapse from the 7-phase to 4-phase set is preserved (renamed to `PHASE_TO_NOTIFY_PHASE`). | required |
| FR-011 | Architecture impact docs are updated: `data-flows.json` and `data-flows.md` gain an entry for the new outbound HTTP flow (`felix-deployer → ntfy.sh`); `service-inventory.json` reflects the felix-deployer service's new env-file dependency. | required |
| FR-012 | A sample environment file template at `scripts/deploy/felix-deployer/env.sample` shows `FELIX_DEPLOYER_NTFY_TOPIC=` with a comment explaining how to mint a private topic and that the real value lives only on office2 outside the repo. | required |
| FR-013 | Test coverage exists for: payload rendering (deterministic title+body for given inputs); secret redaction before truncation; truncation at 500 chars; dispatch-success LibResult shape; dispatch-failure LibResult shape for each error class (NTFY_UNREACHABLE, NTFY_HTTP_ERROR, NTFY_MISSING_TOPIC, NTFY_CURL_MISSING). | required |
| FR-014 | The retired `dispatch_failure_dm` function, the `CRON_NAME = "felix-deployer-alert"` constant, and the `--payload-file` / `openclaw cron run` invocation are removed from notify.py (no dead code, no compatibility shim). | required |
| FR-015 | A `Rebaseline: completed at <ts>` line is recorded in the merge commit per the audited-surface protocol (this mission modifies scripts/deploy/deploy-felix-deployer-bootstrap.sh and scripts/deploy/felix-deployer/*). | required |

## Non-Functional Requirements

| ID | Requirement | Status | Threshold |
|---|---|---|---|
| NFR-001 | ntfy dispatch curl invocation completes (success or fail) within a bounded timeout that does not delay the applier tick beyond operator tolerance. | required | curl `--max-time` ≤ 10 seconds; tick total time ≤ existing tick budget + 10 s. |
| NFR-002 | The full deploy/notify test suite (everything under `tests/deploy/test_*notify*` and `test_deployer.py`) runs in under 5 seconds wall-clock. | required | ≤ 5 s wall clock on a developer Mac. |
| NFR-003 | Importing `scripts.deploy.felix_deployer.notify` has zero outbound network side effects. | required | No HTTP requests, no DNS lookups, no subprocess spawns at import time. |
| NFR-004 | Branch test coverage for `scripts/deploy/felix-deployer/notify.py` stays at or above the repo's existing `--cov-branch` threshold for the deploy package. | required | Branch coverage ≥ existing threshold (per project pytest config). |

## Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | ntfy.sh (`https://ntfy.sh/<topic>`) is the substrate. No alternative push services (Pushover, Apprise, custom WebSocket, etc.) are introduced. | binding |
| C-002 | No openclaw cron registration for the failure-alert path. The `felix-deployer-alert` cron name is retired; it is NOT replaced by a renamed cron. | binding |
| C-003 | The existing applier failure-handling invariants are preserved: on-disk record is source of truth; tick is best-effort about notification; tick exits 0 even if notification fails. | binding |
| C-004 | Acceptance is code-only. The mission ships when code merges to main, CI is green, and the rebaseline obligation is recorded in the merge commit. Operator-driven post-merge `--rollback` + `--apply` and the deliberate-failure smoke test are tracked outside this mission. | binding |
| C-005 | The notification HTTP POST uses `curl` invoked via subprocess, mirroring the existing security-monitor precedent. No new Python HTTP dependency is added (no `requests`, no `httpx`). | binding |
| C-006 | `FELIX_DEPLOYER_NTFY_TOPIC` is never committed. The env.sample template is committed; the real value is created on office2 outside the repo. | binding |
| C-007 | The retired `kitty-specs/pull-based-deploy-pipeline-01KTYQQS/contracts/dm-payload-v1.md` stays in place as the mission's historical record (do not modify or delete a finished mission's artifacts). The new contract lives in this mission's feature dir. | binding |
| C-008 | The existing `deploys/applied/0001-bootstrap-felix-deployer.yaml` and its partial-apply notes stay as the historical record. Whether the post-merge re-bootstrap overwrites `0001` or writes a fresh `0002` is a plan-phase decision. | binding |

---

## Success Criteria

Measurable, technology-agnostic outcomes that determine mission success at acceptance and post-merge review.

- **SC-001** — Unit tests pass: given a manifest, phase, error_summary, head_sha, and failed_at, `dispatch_failure_notification` renders title+body matching the `ntfy-notification-v1` contract exactly (byte-for-byte for the title; structural-with-redaction for the body).
- **SC-002** — Unit tests pass: a `error_summary` containing canonical secret patterns (per `scripts.deploy.lib.verify.redact_secrets`) is redacted BEFORE being truncated; truncation at exactly 500 chars holds; the result never contains a secret pattern.
- **SC-003** — Unit tests pass: each simulated failure mode (network unreachable, HTTP 5xx, missing topic, missing curl binary) returns `LibResult(ok=False)` with a documented `error_code`. No mode raises an exception.
- **SC-004** — `validate_docs` accepts the new `ntfy-notification-v1.md` contract file with valid YAML frontmatter.
- **SC-005** — The `deploy-manifest-validate` CI check remains green on the merge commit (no schema regressions in the existing manifests in `deploys/applied/`).
- **SC-006** — Architecture data files reflect the change: `data-flows.json` contains an outbound entry for felix-deployer → ntfy.sh; `service-inventory.json` shows felix-deployer's new EnvironmentFile dependency; both files validate against their respective schemas.
- **SC-007** — `scripts/deploy/deploy-felix-deployer-bootstrap.sh --dry-run` output contains no reference to `openclaw cron edit`, `openclaw cron run`, `--payload-template`, `--payload-file`, or the `felix-deployer-alert` cron name.
- **SC-008** — A grep across the repository finds zero post-merge occurrences of `CRON_NAME = "felix-deployer-alert"`, `dispatch_failure_dm`, or `--payload-file` outside historical mission artifacts (kitty-specs/pull-based-deploy-pipeline-01KTYQQS/ is allowed to retain them).

---

## Key Entities

- **Notification** — The HTTP POST payload sent to ntfy.sh: title (short, one-line, identifies the failed manifest), body (multi-line, carries the structured failure detail), priority and tag headers. Ephemeral; not persisted.
- **Notification Contract (`ntfy-notification-v1`)** — The schema describing how (manifest, phase, error_summary, head_sha, failed_at) renders into title+body, including the redact-then-truncate invariant and the priority/tag header conventions.
- **Topic** — A private ntfy.sh path segment (e.g. `felix-deployer-<random-suffix>`) identifying the push channel. Subscribed in the operator's ntfy phone app. Stored in `FELIX_DEPLOYER_NTFY_TOPIC` env var on office2; never in the repository.
- **Failure Record** — The existing on-disk artifact in `deploys/failed/<manifest>/`. Unchanged by this mission. Source of truth for "what failed and when."
- **Bootstrap Wrapper** — `scripts/deploy/deploy-felix-deployer-bootstrap.sh`. Modified by this mission: step 5 (openclaw cron registration) removed; remaining 6 steps preserved.

---

## Architecture Impact

Per the change-class lookup in `docs/design/architecture/data/signal-to-doc-map.json`, this mission touches the following classes — each must update the listed `doc_targets`:

- **service-added-or-modified** (felix-deployer's outbound dependencies change): `docs/design/architecture/data/service-inventory.json`, `docs/design/architecture/service-inventory.md`, `docs/design/architecture/service-dependencies.view.md`, `docs/design/felix-capability-roadmap.md`.
- **credential-added-or-modified** (new `FELIX_DEPLOYER_NTFY_TOPIC` env credential): `docs/design/architecture/data/credential-manifest.json`, `docs/design/architecture/credentials-and-secrets.md`, `docs/design/architecture/identity-model.md`.
- **data-flow-added-or-modified** (new outbound HTTPS POST flow): `docs/design/architecture/data/data-flows.json`, `docs/design/architecture/data-flows.md`, `docs/design/architecture/data-flows.view.md`.
- **systemd-unit-added-or-modified** (`felix-deployer.service` gains `EnvironmentFile=`): `docs/design/architecture/data/service-inventory.json`, `docs/design/architecture/service-inventory.md`, `docs/design/architecture/data/audited-surfaces.json`.

Plan-phase responsibility: enumerate exactly which JSON entries / markdown sections change in each file; the spec records only the affected file set.

---

## Risk Tier

**Tier 3 — Logic/workflow.** Modifies Python scripts (`notify.py`, `_tick.py`), a bash wrapper (`deploy-felix-deployer-bootstrap.sh`), contract documentation, and architecture data. The new `EnvironmentFile=` directive on `felix-deployer.service` is a service env-file modification (a Tier 2 dimension), but the env file is mint-on-office2 with a non-secret topic (best-effort failure path), not a database or application secret. Net classification: Tier 3, consistent with the source issue.

This mission touches an audited surface (`scripts/deploy/deploy-felix-deployer-bootstrap.sh`, `scripts/deploy/felix-deployer/*`); the rebaseline obligation applies (#557) and is captured in FR-015.

---

## Assumptions

- ntfy.sh's free public hosted service is operationally reliable enough for best-effort operator alerts (the existing security-monitor relies on it in production).
- `curl` is installed and on PATH on office2 (verified — it is, per the existing security-monitor pattern).
- The operator subscribes their ntfy phone app to the new `FELIX_DEPLOYER_NTFY_TOPIC` value once during initial setup; this is an out-of-band operator action, not a mission deliverable.
- The existing `dm-payload-v1.md` contract has no external consumers beyond felix-deployer (verified by grep over the repository before this mission concluded).
- The repository's existing `--cov-branch` configuration extends transparently to the rewritten `notify.py`.
- The `scripts.deploy.lib.verify.redact_secrets` function already handles the secret patterns of concern (HTTP basic-auth strings, API keys, JWTs, SSH key fragments). No new redaction patterns are needed for this mission.
- Reusing `curl` via subprocess is acceptable per the existing security-monitor precedent; adding `requests` to the repo's pinned deps for one POST is not required.
- The decisive reason ntfy.sh was chosen over openclaw cron Design A (the issue's proposed remediation) is failure-mode independence: the failure-notification path must not share substrates with the deploys that might fail. This rationale is captured here so future readers don't reopen the design decision.

---

## Out of Scope

- WhatsApp DM as a failure-notification substrate (deprecated for this path; failure-mode-coupled to openclaw).
- A shared "ntfy adapter" library extracted from security-monitor + felix-deployer. Each subsystem keeps its own inline curl call for now; consolidation is a separate concern if a third caller appears.
- Retroactive notification of failures that occurred while the broken DM path was active (none exist — the live applier has had an empty queue since deploy).
- Multi-recipient / fan-out notification routing.
- Notification deduplication, batching, or rate-limiting.
- A live ntfy.sh integration test in CI (no NTFY_TOPIC in CI; coverage is via subprocess mock plus operator-driven post-merge smoke test).
- Operator-side ntfy phone app installation, configuration, or topic subscription (out-of-band).
- Re-deployment of felix-deployer on office2 (`--rollback` + `--apply`). Operator-driven after merge; tracked outside this mission.
- The deliberate-failure end-to-end smoke test on the live applier (operator-driven after redeploy).
- Migration of security-monitor's ntfy usage to a shared library.
- Switching `scripts/deploy/lib/verify.redact_secrets` to a richer redaction set; that's a Felix-wide concern, not specific to this notification path.

---

## Notes

- The chosen substrate (ntfy.sh) is reinforced by the `ntfy_notification_pattern` memory entry (canonical push-notify substrate, security-monitor precedent).
- The decisive `(B) ntfy.sh` choice over `(A) openclaw cron throwaway one-shot` was made in discovery on failure-mode-independence grounds: a deploy failure that breaks openclaw or WhatsApp would also break Design A. ntfy.sh is independent of both.
- The existing `deploys/applied/0001-bootstrap-felix-deployer.yaml` has notes describing the partial-apply state. Whether the post-merge bootstrap re-run overwrites `0001` in place or writes a new `0002-bootstrap-felix-deployer-v2.yaml` is a plan-phase decision; this spec deliberately does not pre-decide it.
- The new `contracts/ntfy-notification-v1.md` file lives in THIS mission's `kitty-specs/<slug>/contracts/` dir; the retired `dm-payload-v1.md` stays in the source mission's dir as historical record.
