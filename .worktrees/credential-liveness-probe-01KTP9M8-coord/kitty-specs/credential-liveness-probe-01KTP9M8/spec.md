# Specification: Credential Liveness Probe

**Mission**: `credential-liveness-probe-01KTP9M8`
**Mission ID**: `01KTP9M86VF89TQM5SX7JVA83Z`
**Target branch**: `main`
**Mission type**: `software-dev`
**Issue**: kentonium3/kg-automation#572 (closes)
**Created**: 2026-06-09

## Purpose (Stakeholder Summary)

`credential-health-check` currently verifies file presence/ownership/mode for `gog`-managed OAuth credentials but does NOT probe whether the refresh token still works. The OAuth app is configured `External` + `Testing` (per `docs/runbooks/google-workspace-ops.md` §2.4), so Google issues refresh tokens with a hard **7-day expiration**. This means every Felix Google integration (calendar, gmail, drive, sheets, contacts, docs) silently dies once per week. Today, the operator only discovers the death when something user-facing fails (the NETECH calendar event that surfaced #572 was missed for ~7 days).

This mission adds a **liveness probe** for `oauth2`-typed credentials: a cheap read against the credential is issued on a frequent cadence; failure converts to a deduped GitHub issue (existing channel) that carries the concrete recovery command. The probe makes the 7-day cycle visible within ≤6 hours of expiration instead of waiting for user-facing failure.

Per operator decision (Option C — live with the weekly cycle + automate around it; see `reference_gog_credential_health_gap.md`), this probe is **load-bearing** for the chosen path: it is the visibility layer that prevents silent integration failure.

**Closes #572.**

## User Scenarios & Testing

### Primary scenario: healthy credential

1. Liveness probe runs (separate timer from the daily expiry/staleness check).
2. For each `oauth2`-typed credential in the manifest with `monitor_liveness: true`, the probe issues a cheap read using the credential.
3. All probes succeed (HTTP 200, no `invalid_grant`).
4. Per-credential signal: `credential_alive` (logged INFO, no GitHub issue, no Vikunja task).
5. No operator interruption.

### Scenario: Testing-app 7-day expiration cycle (DOMINANT cause)

1. Token was last refreshed 7 days ago. Google has now expired it.
2. Liveness probe runs (within 6h of expiration per cadence).
3. `gog calendar list -j --max-results 1` returns `invalid_grant — Token has been expired or revoked.`
4. Probe classifies the failure: keyring file mtime + 7d is within ±24h of NOW → `classification: "routine-7day-cycle"`.
5. Failure reason includes the concrete recovery command: `ssh -t office2-claude /home/claude/kg-automation/scripts/security/gog-reauth.sh`.
6. Orchestrator dedups by GitHub issue title prefix; if no existing open issue, files one labeled `P1-bug`, `area/infrastructure`. Title prefix includes the credential name + cycle classification.
7. Operator sees the issue (whether via GitHub UI, digest, or downstream WhatsApp escalation — out of scope here) and runs `gog-reauth.sh`.
8. On next probe cycle after recovery: probe succeeds. The dedup check still finds the existing issue. The orchestrator auto-closes-or-comments the issue (TBD per FR-009 below — operator-visible recovery).

### Scenario: unexpected revocation (e.g., password change, manual revoke)

1. Operator changed Google account password OR revoked the app at myaccount.google.com/permissions.
2. Token dies at non-cycle time (more than 24h before next expected expiration).
3. Liveness probe detects `invalid_grant` like above.
4. Probe classifies: keyring mtime + 7d is NOT within ±24h of NOW → `classification: "unexpected-revocation"`.
5. Failure reason includes both the recovery command AND a brief diagnostic prompt: "If you didn't change passwords or revoke access, investigate at https://myaccount.google.com/permissions before re-auth."
6. Orchestrator files a separate GitHub issue with a different title prefix (`credential-liveness-unexpected`) so it doesn't dedup against routine-cycle issues.

### Scenario: dedup prevents repeat issues during the same outage

1. Probe runs at 06:00 → files issue X.
2. Probe runs at 12:00 → still failing. Dedup finds open issue X with the same title prefix → no new issue. Logged as `alert_deduped`.
3. Probe runs at 18:00 → operator hasn't acted. Dedup still finds X. No new issue.

### Scenario: probe error vs probe failure (distinguish)

1. Probe runs but the gog CLI itself errors out (e.g., disk full, gog binary missing). This is NOT an `invalid_grant`.
2. Probe returns a different signal: `credential_probe_error` with the raw error text.
3. The orchestrator logs this as a per-credential error (existing pattern, like signal-reader-raised) but does NOT file a `credential_dead` issue (the credential might be fine; the probe is broken).

### Scenario: dry-run

1. Operator runs `python3 -m credential_health_check --dry-run --liveness-only` from any shell.
2. Probe issues real liveness reads against the credentials.
3. On detected failure: logs `alert_would_file` instead of filing.
4. Useful for testing the probe logic against current state without filing noise.

### Scenario: ad-hoc list

1. Operator runs `python3 -m credential_health_check --list --liveness`.
2. Output is a terminal table showing each `oauth2` credential, when it was last successfully probed, current classification (`alive` / `dead-routine-7day` / `dead-unexpected` / `probe-error`), and the recovery command if applicable.
3. Read-only: no probes are issued; the table reflects the last probe result from the journal.

## Domain Language

| Term | Definition |
|---|---|
| **Liveness probe** | A cheap, read-only operation issued against a credential to verify the credential can authenticate. For `gog`-managed OAuth: `gog --account <email> calendar list -j --max-results 1` with a short timeout. The HTTP status / OAuth grant outcome is the answer. |
| **Probe failure** | A liveness probe that completes but returns `invalid_grant` (or equivalent expired/revoked-token signal). Credential is unauthenticated. |
| **Probe error** | A liveness probe that fails to complete due to a non-credential cause: gog binary missing, env-var unset, disk full, network down. Credential's authentication status is unknown; do not file a credential-dead issue. |
| **Routine-7day-cycle** | A probe failure where `mtime(keyring-file) + 7d` is within ±24h of now. Matches the External+Testing OAuth app's 7-day refresh-token TTL. |
| **Unexpected-revocation** | A probe failure where the 7-day expiration math doesn't match. Cause is operator action (password change, manual revoke) or a Google security review. Warrants investigation before re-auth. |
| **Recovery command** | The exact shell command an operator runs to fix the failure, embedded in the GitHub issue body. For gog: `ssh -t office2-claude /home/claude/kg-automation/scripts/security/gog-reauth.sh`. |
| **Probe cadence** | The frequency at which liveness probes run for all monitored credentials. This mission targets 6 hours (per #572 update). Implemented as a separate systemd timer from the existing daily `credential-health-check.timer`. |

## Functional Requirements

| ID | Description | Status |
|---|---|---|
| FR-001 | A new function `probe_oauth_liveness(credential: Credential) -> Optional[LivenessResult]` exists in `scripts/security/credential_health_check/liveness.py`. Returns `None` when alive; returns a populated `LivenessResult` when dead, classified, or errored. | Specified |
| FR-002 | `LivenessResult` is a dataclass with fields: `credential_name: str`, `classification: Literal["dead-routine-7day", "dead-unexpected", "probe-error"]`, `reason: str` (human-readable), `recovery_command: Optional[str]`, `probed_at: datetime` (UTC). | Specified |
| FR-003 | For credentials of `type: oauth2` with `liveness_probe.gog_account` set in the manifest, the probe shells out to `gog --account <account> calendar list -j --max-results 1`. Other oauth2-typed credentials without `liveness_probe.gog_account` are skipped (logged INFO `liveness_skipped`). | Specified |
| FR-004 | The probe shell call has a 15s timeout. Timeout → classification `probe-error` with reason `"liveness probe exceeded 15s timeout"`. | Specified |
| FR-005 | The probe parses the gog stderr for the substring `invalid_grant` to detect token death. Any other non-zero exit is classified `probe-error`. Exit 0 = alive. | Specified |
| FR-006 | Cycle classification: when classification would be `dead-*`, the probe reads the gog keyring file mtime. If `mtime + 7d` is within ±24h of probe time, classification is `dead-routine-7day`; otherwise `dead-unexpected`. The keyring file path is per credential — for the gog default account: `/home/claude/.config/gogcli/keyring/_gogcli_key_v1_<base64>`. | Specified |
| FR-007 | The `recovery_command` field is populated from the manifest: each oauth2 credential has a `liveness_probe.recovery_command` field. For the gog default account: `ssh -t office2-claude /home/claude/kg-automation/scripts/security/gog-reauth.sh`. | Specified |
| FR-008 | Orchestrator integration: a new `_process_liveness_alert(cred, today, cycle_id, result, logger, dry_run)` function in `orchestrator.py` is invoked for each credential with `monitor_liveness: true`. It calls `probe_oauth_liveness()`, dedups by GitHub issue title prefix, and files an issue on failure. | Specified |
| FR-009 | Dedup behavior: the title prefix encodes the classification (`credential-liveness-routine-7day:` vs `credential-liveness-unexpected:`) so the two failure modes do NOT dedup against each other. If a routine issue is open and an unexpected-revocation probe later fires, a separate issue is filed. | Specified |
| FR-010 | When a previously-failing probe now succeeds, the orchestrator does NOT auto-close existing open issues. The operator closes manually after running the recovery command (existing pattern; matches cadence + staleness alerts). Auto-close-on-recovery is deferred to a follow-up mission once weekly re-auth becomes routine and operator-closure friction outweighs the audit-trail clarity of manual close (see Future Work). | Specified |
| FR-011 | A new CLI flag `--liveness-only` runs only the liveness pass and skips cadence/staleness/manifest-quality. Useful for ad-hoc probing and faster cycle times. | Specified |
| FR-012 | A new CLI flag `--list --liveness` extends `--list` to add a per-oauth2-credential row showing: `name`, `last_probed_at_iso`, `last_classification`, `recovery_command_if_failing`. Read-only; no probes issued. | Specified |
| FR-013 | The credential manifest gains a new optional per-credential block `liveness_probe`: `{enabled: bool, gog_account: Optional[str], keyring_file: Optional[str], recovery_command: str}`. Credentials without this block are skipped from liveness (logged INFO once per cycle). | Specified |
| FR-014 | The `gog-credentials-keyring` credential record in `docs/design/architecture/data/credential-manifest.json` is updated to set `liveness_probe.enabled: true` with the gog default account + keyring file path + recovery command. No new credential record is added. | Specified |
| FR-015 | A new systemd timer `credential-liveness-probe.timer` runs every 6 hours (`OnCalendar=*-*-* 00,06,12,18:00:00`), invoking `/usr/bin/python3 -m credential_health_check --liveness-only`. Persistent=true so missed firings catch up. | Specified |
| FR-016 | A new systemd service `credential-liveness-probe.service` runs as a one-shot, owned by the claude user, with `Environment=HOME=/home/claude` and the same `PYTHONPATH` + `WorkingDirectory` as the existing `credential-health-check.service`. | Specified |
| FR-017 | The existing `credential-health-check.timer` cadence (daily at 13:00 UTC) and existing signals are UNCHANGED. The new timer is additive. | Specified |
| FR-018 | The `tailscale-auth` and `whatsapp-session` activity signals (existing) are NOT touched by this mission. They remain in the daily cycle. | Specified |
| FR-019 | Probe output is structured-logged at INFO with the following fields per call: `cycle_id`, `credential_name`, `classification`, `probed_at`, `duration_ms`. On failure: + `reason`, `recovery_command`. On error: + `error_detail`. | Specified |
| FR-020 | Dry-run mode (`--dry-run --liveness-only`) still issues the real probe (so the operator sees real classification), but logs `alert_would_file` instead of filing a GitHub issue. | Specified |
| FR-021 | Phone-based recovery: `scripts/security/gog-reauth.sh` (the recovery command referenced from FR-007) MUST work end-to-end via Termius + Tailscale on the operator's phone with the same UX as a Mac terminal — interactive TTY, redirect-URL paste prompt, and post-auth liveness probe verification. If the existing script needs UX tweaks to be phone-friendly (e.g., URL output formatting, clearer paste prompts), those tweaks are in scope for this mission. | Specified |

## Non-Functional Requirements

| ID | Description | Status |
|---|---|---|
| NFR-001 | A single probe call completes in ≤15s (timeout-enforced per FR-004). A full liveness cycle for all monitored credentials completes in ≤60s wall-clock. | Specified |
| NFR-002 | Token cost: zero LLM tokens consumed (deterministic helper; no LLM in the probe path). Per Felix Constitution Directive 6. | Specified |
| NFR-003 | Stdlib + existing-deps only — no new third-party packages. Reuses `subprocess`, `dataclasses`, `datetime`, the existing `Credential` dataclass, the existing `github_writer.dedup_check`/`file_alert` functions. | Specified |
| NFR-004 | Per-module coverage gate: ≥90% line / ≥85% branch on `scripts/security/credential_health_check/liveness.py` via `pytest --cov=scripts.security.credential_health_check.liveness --cov-branch --cov-fail-under=90`. | Specified |
| NFR-005 | Tests use the existing pytest + `tmp_path` + monkeypatch patterns under `tests/security/credential_health_check/test_liveness.py`. Subprocess calls are mocked; no real gog calls during pytest. | Specified |
| NFR-006 | Manifest schema change (adding `liveness_probe` block) is BACKWARD-COMPATIBLE: credentials without the block are simply skipped from liveness. Existing manifest readers (cadence, staleness, manifest-quality) are unaffected. | Specified |
| NFR-007 | The liveness probe MUST NOT trigger Google account lockout. Cadence × per-call quota cost is well below documented rate limits (Google Calendar API: 1M reads/day per project; 6h cadence × 1 credential ≈ 4 calls/day, four orders of magnitude under the limit). | Specified |

## Constraints

| ID | Description | Status |
|---|---|---|
| C-001 | Per CLAUDE.md, `~/second-brain/notes/04-Growth/_private/` is never read, written, referenced, or logged. The probe operates on credential state only; no vault paths involved. The C-001 invariant is structurally satisfied. | Specified |
| C-002 | Per CLAUDE.md change-control: Tier 3 (Logic/Workflow) — new Python helper + systemd units. No Tier 0/1/2 surfaces touched. Dry-run capability per FR-020. | Specified |
| C-003 | Per Felix Constitution Directive 6: deterministic work goes in a helper script the agent invokes; reserve LLM for judgment/classification. The probe is 100% deterministic. No agent prompts are added or modified. | Specified |
| C-004 | Per `[[feedback_helper_m_invocation_form]]`: the CLI is invoked via `python3 -m credential_health_check --liveness-only` form (existing module). No script-path form. | Specified |
| C-005 | Per `[[feedback_no_workarounds_for_expediency]]`: the new systemd units are installed via the standard deploy path (`scripts/office2/<unit-file>` mirrored to `~/.config/systemd/user/`). No ad-hoc manual installation. | Specified |
| C-006 | Per `[[feedback_migration_no_vestiges]]`: no transitional parity-write code. The probe is purely additive; nothing replaces an existing surface. | Specified |
| C-007 | Recovery command embedded in GitHub issues MUST exactly match the deployed `gog-reauth.sh` invocation path. If the script path changes in the future, the manifest's `liveness_probe.recovery_command` is updated as part of that change (per architecture docs). | Specified |
| C-008 | No autonomous account-lockout-recovery logic enters this mission. Operator action is required to fix a dead token. Probes only observe. | Specified |

## Success Criteria

1. `python3 -c "from scripts.security.credential_health_check.liveness import probe_oauth_liveness, LivenessResult; print('ok')"` imports cleanly.
2. `pytest tests/security/credential_health_check/ --cov=scripts.security.credential_health_check.liveness --cov-branch --cov-fail-under=90 -v` passes with ≥90% line / ≥85% branch coverage on `liveness.py`.
3. Existing tests in `tests/security/credential_health_check/` STAY passing (regression sanity).
4. A synthetic test invocation with a mocked `subprocess.run` returning `invalid_grant` produces `classification: "dead-routine-7day"` when the mocked keyring mtime is 6.9 days old, and `classification: "dead-unexpected"` when it's 3 days old.
5. A synthetic test invocation with a mocked `subprocess.run` returning success produces `None` (alive).
6. A synthetic test invocation with `subprocess.run` raising `TimeoutExpired` produces `classification: "probe-error"` with reason mentioning the 15s timeout.
7. Manifest schema validation: `credential-manifest.json` after FR-014 still parses cleanly; existing consumers (`listing`, `manifest`, `cadence`) are unaffected.
8. Dry-run validation: `python3 -m credential_health_check --dry-run --liveness-only` against a state where the gog token is dead logs `alert_would_file` and does NOT file a GitHub issue.
9. End-to-end on office2 (post-deploy): `systemctl --user start credential-liveness-probe.service` against current state (alive gog token) logs `credential_alive` per credential and files no issue.
10. The new systemd unit files (`credential-liveness-probe.{service,timer}`) appear under `scripts/office2/` and the deployed copies under `~/.config/systemd/user/` match byte-for-byte.
11. **Phone-based recovery end-to-end test**: operator (Kent) runs `gog-reauth.sh` via Termius + Tailscale from his phone against a state where the token has just expired. The flow completes successfully: URL is openable from phone browser, redirect URL is pasteable into the Termius prompt, post-auth liveness probe confirms `credential_alive`, and the previously-filed GitHub issue is closeable. Friction observed during this test (if any) is captured in a follow-up commit within the same mission. Until this test passes, the mission is not done.

## Key Entities

| Entity | Role |
|---|---|
| `LivenessResult` (new dataclass) | The per-probe-call return value. None = alive; populated = dead or errored. |
| `probe_oauth_liveness()` (new function) | The probe implementation. Pure-ish: depends on subprocess + filesystem; both mockable for tests. |
| `_process_liveness_alert()` (new orchestrator function) | The integration point: iterates credentials with `liveness_probe.enabled`, probes each, dedups + files on failure. |
| `Credential.liveness_probe` (new attribute) | The per-credential config block. Optional; absent = skip. |
| `credential-liveness-probe.timer` (new systemd unit) | 6h cadence. Separate from the daily check. |
| `credential-liveness-probe.service` (new systemd unit) | One-shot service that invokes `python3 -m credential_health_check --liveness-only`. |
| `gog-credentials-keyring` (existing manifest record) | Gains the `liveness_probe` block; otherwise unchanged. |
| `github_writer.dedup_check` / `file_alert` (existing helpers) | Reused as-is for issue filing. |

## Out of Scope

- Multi-account probing (only the gog default account is monitored initially; the schema allows future expansion).
- Auto-recovery (probe never attempts to re-mint a token; operator action required).
- WhatsApp push notification *directly* from the probe — the GitHub issue is the surface; downstream digest/escalation picks it up by existing mechanisms.
- Generalizing beyond gog (the design accommodates other oauth2 credentials, but only gog is wired in this mission).
- Probing non-OAuth credentials (tailscale-auth, whatsapp-session, etc. — they have their own existing signals).
- Predictive expiration warnings (e.g., "token expires in 24h") — out of scope; the probe is reactive.
- Per-scope probing (the probe uses one cheap calendar read as a single-call proof; verifying every scope is overkill).
- Re-architecting the existing `credential-health-check` cycle. The new cadence is a separate timer; existing cadence is untouched.

## Future Work (deliberately deferred)

### Auto-close GitHub issues on recovery

Once weekly re-auth becomes routine (multiple cycles complete without surprise), the manual-close step in FR-010 will become friction. The eventual target state is:

- When a previously-failing probe now succeeds AND there is an open `credential-liveness-routine-7day:` issue for that credential, the orchestrator auto-closes the issue with a comment: `"Auto-closed: probe at <ts> confirmed token alive. If you didn't recently re-auth, this is unexpected — investigate at https://myaccount.google.com/permissions."`
- Unexpected-revocation issues (`credential-liveness-unexpected:`) are NOT auto-closed (the diagnostic step Kent took matters; manual close preserves the audit trail).
- This requires a new `_close_alert(issue_number, comment)` helper in `github_writer.py` and orchestrator wiring to call it when a probe transitions from `dead-*` to `alive` while a matching open issue exists.

Operator trigger to schedule this follow-up mission: when manual-close friction is noticeable (Kent's judgment call, no metric set). File a new issue then; do not pre-file now.

### Multi-account probing

The schema supports `liveness_probe.gog_account` per credential. If a second Google account (e.g., a Workspace migration per the long-term Option A path in `reference_gog_credential_health_gap.md`) is added, the manifest gains a second credential record with its own `liveness_probe` block. No code changes needed in this mission's scope; the probe iteration already handles N credentials. Mention here so the future-Kent doesn't waste time wondering if expansion is supported.

## Architecture Impact

This mission touches deployed services + credential surfaces, so per CLAUDE.md "Discovery aid for spec/plan agents", `docs/design/architecture/data/signal-to-doc-map.json` was consulted. Affected change classes:

- **`credential-added-or-modified`**: existing `gog-credentials-keyring` record gains a `liveness_probe` block. Update `credential-manifest.json` + the credential's narrative doc if any.
- **`systemd-unit-added-or-modified`**: two new units (`credential-liveness-probe.{service,timer}`). Update the relevant systemd-units doc if one exists for credential-health-check.
- **`service-added-or-modified`**: a new logical service (the 6h liveness probe). Update `service-inventory.json` + narrative.
- **`runbook-modified`**: `docs/runbooks/google-workspace-ops.md` §Common Issues should reference the new automatic surface ("you'll see a GitHub issue in 0–6h instead of discovering via outage").

Doc targets enumerated by `signal-to-doc-map.json` per change class will be honored in the merge commit.
