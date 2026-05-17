# Spec: Provision felix-bot Vikunja identity

**Mission**: `felix-bot-vikunja-provisioning-01KRT3N4`
**Source**: Issue [#304](https://github.com/kentonium3/kg-automation/issues/304) — Phase 1 of [ADR-0002](../../docs/design/architecture/adr/0002-felix-vikunja-task-model.md)
**Umbrella**: Issue [#311](https://github.com/kentonium3/kg-automation/issues/311)
**Target branch**: `main`
**Mission type**: software-dev
**Created**: 2026-05-17

---

## Overview

Provision a dedicated `felix-bot` Vikunja user on the office2 instance so that every API write performed by Felix sub-agents (habits, escalation, capture, tasker) attributes to that identity at the Vikunja API layer instead of to `kent`. This is the foundational phase of the ADR-0002 redesign; subsequent phases (JSONL infrastructure, habits migration, etc.) depend on the new identity being in place.

The mission also revokes Kent's existing API tokens to leave `felix-bot` as the sole API path, while preserving Kent's UI access via the existing `kent` Vikunja account.

---

## User Scenarios and Testing

### Actors

- **Operator** (Kent + Claude Code): executes the provisioning workflow and validates outcomes.
- **Felix sub-agents** (`felix-admin-habits`, `felix-admin-escalation`, `felix-admin-capture`, `felix-admin-tasker`): consume the rotated token via the existing `vikunja-api` skill after the swap.
- **Vikunja v0.24.6 instance** on `office2`: target of the user registration, project sharing, and write attribution.
- **felix-doc-auditor**: out of scope (uses the GitHub PAT, not the Vikunja token).

### Primary flow

1. Operator confirms pre-flight criteria (Restic backup recent, dependent services healthy, Kent available).
2. Operator registers a new Vikunja user `felix-bot` via `POST /api/v1/register` with the agreed email and a 1Password-generated strong password.
3. Operator generates a long-lived API token for `felix-bot` via the Vikunja UI (or token API endpoint).
4. Operator shares each of the 12 real Vikunja projects (IDs 1, 2, 4-13) with `felix-bot` at read/write permission from the `kent` account.
5. Operator runs the side-channel validation script using `felix-bot`'s new token directly (not via the secrets file). The script writes a sample comment, reads it back, and asserts `created_by.username == felix-bot`. It also probes each shared project to confirm felix-bot has read/write access.
6. If side-channel validation succeeds: operator backs up `/data/services/openclaw/secrets/vikunja-api` to a side-by-side `.kent-pre-felix-bot.bak` file (mode 600), then replaces the contents with `felix-bot`'s token.
7. Operator restarts `openclaw-gateway.service` via `systemctl --user restart openclaw-gateway` so all child agent sessions reload the new token.
8. Operator runs post-swap verification: a real Felix agent invocation writes a sample comment; operator confirms the comment's `created_by.username == felix-bot`.
9. Operator updates the architecture documentation: `data/credential-manifest.json`, `credentials-and-secrets.md`, `identity-model.md`, and `data/service-inventory.json` (if it tracks user accounts).
10. Operator revokes any remaining `kent`-attributed API tokens via the Vikunja UI.
11. 7-day soak: each Felix cron (habits-morning-checkin, escalation-daily, inbox-7am/noon/5pm/10pm) completes successfully without authentication errors for 7 consecutive days.

### Edge cases

- **Side-channel validation fails** (e.g., project not properly shared, token rejected): no production disruption occurred since the secrets file was not modified. Operator diagnoses and retries from step 4.
- **Side-channel validation succeeds but post-swap verification fails** within 30 minutes: operator executes the rollback (restore `.bak`, restart gateway, verify reverted to kent attribution).
- **A Felix agent cron tick fails mid-soak** due to an auth error: operator inspects logs, attempts to refresh the token, or executes rollback if the issue is systemic.
- **Kent creates a new Vikunja project after this mission completes**: that project is not automatically shared with felix-bot. Out of scope here; a separate sibling issue (to be filed after this spec lands) tracks an ongoing reconciliation cron.
- **Project sharing API rejects the operation** for one of the 12 projects: operator investigates per-project (could be a Vikunja permissions edge case); does not proceed to step 6 until all 12 succeed.

### Acceptance scenarios

- AS-001: felix-bot can write a comment on a task in each of the 12 real projects, and each comment's `created_by.username` equals `felix-bot`.
- AS-002: The morning habits check-in cron at the next 7:05am ET completes without authentication errors.
- AS-003: The escalation cron at the next scheduled time completes without errors.
- AS-004: Each inbox cron (7am, noon, 5pm, 10pm ET) completes its next scheduled run without errors.
- AS-005: The credential health check daemon recognizes the rotated credential and does not file a new alert at its next 13:00 UTC run.
- AS-006: Kent's existing UI login at `https://office2.tail0f5f56.ts.net/` continues to work normally after token rotation.
- AS-007: All API tokens previously attributed to `kent` are absent from Vikunja's per-user token list after the mission completes.
- AS-008: The rollback procedure restores kent attribution within 5 minutes when executed as a smoke test during pre-swap validation.

---

## Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | Register a new Vikunja user `felix-bot` with username `felix-bot`, email `kentgale+felix-bot@gmail.com`, and a strong 1Password-generated password. | proposed |
| FR-002 | Generate a long-lived API token for the `felix-bot` user. | proposed |
| FR-003 | Share each of the 12 real (non-pseudo, non-archived) Vikunja projects with `felix-bot` at read/write permission. Real projects on the instance today: IDs 1 (Inbox), 2 (Everyday), 4 (Someday), 5 (Personal Growth & Transformation), 6 (Business Acquisition), 7 (CT-90day), 8 (Health & Conditioning), 9 (Intentional LLC), 10 (Metal Casework), 11 (Goals), 12 (Research), 13 (Habits). | proposed |
| FR-004 | Run a side-channel validation script using `felix-bot`'s token directly (not via the secrets file). The script must: (a) verify the token authenticates, (b) verify read access to each of the 12 shared projects, (c) write a sample comment on a low-impact task and assert `created_by.username == felix-bot`, (d) delete or mark the sample comment so it does not pollute production data. The script must complete successfully BEFORE the production secrets file is modified. | proposed |
| FR-005 | Back up the existing `/data/services/openclaw/secrets/vikunja-api` to a side-by-side file `vikunja-api.kent-pre-felix-bot.bak` with mode 600 and ownership `claude:claude`. | proposed |
| FR-006 | Replace the contents of `/data/services/openclaw/secrets/vikunja-api` with `felix-bot`'s API token, preserving mode 600 and ownership `claude:claude`. | proposed |
| FR-007 | Restart `openclaw-gateway.service` via `systemctl --user restart openclaw-gateway` so all child agent sessions reload the new token on their next invocation. | proposed |
| FR-008 | Perform a post-swap verification write: invoke a Felix sub-agent through the gateway to write a sample Vikunja comment, then confirm the comment's `created_by.username == felix-bot` via API read. | proposed |
| FR-009 | Verify the next scheduled run of each Felix cron job (`habits-morning-checkin`, `escalation-daily`, `inbox-7am`, `inbox-noon`, `inbox-5pm`, `inbox-10pm`) completes without authentication errors against the Vikunja API. | proposed |
| FR-010 | Update `docs/design/architecture/data/credential-manifest.json` `vikunja-api` entry: bump `last_reviewed` to the rotation date, prepend `#304` to `updated_by`, and update `notes` to reflect `felix-bot` ownership of the token. | proposed |
| FR-011 | Update `docs/design/architecture/credentials-and-secrets.md` to reflect `felix-bot` ownership in the active credentials table and any narrative sections that describe the consumer of `vikunja-api`. | proposed |
| FR-012 | Update `docs/design/architecture/identity-model.md` Agent Service Accounts section to add `felix-bot` (Vikunja) alongside the existing `kg-felix-bot` (GitHub) entry. | proposed |
| FR-013 | Update `docs/design/architecture/data/service-inventory.json` if the `vikunja` service entry tracks per-user accounts; add `felix-bot` if so. | proposed |
| FR-014 | Revoke any other API tokens previously attributed to the `kent` user via the Vikunja UI, so `felix-bot` is the only API identity in active use. | proposed |
| FR-015 | Run a rollback smoke test as part of side-channel validation: temporarily revert the secrets file to the `.bak`, restart the gateway, write a sample comment, confirm attribution to `kent`, then re-apply the rotation. Verifies the rollback procedure works under timed pressure before relying on it. | proposed |

---

## Non-Functional Requirements

| ID | Requirement | Measurement | Status |
|---|---|---|---|
| NFR-001 | Side-channel validation script completes in under 5 minutes end-to-end. | Wall-clock time from script start to exit code 0. | proposed |
| NFR-002 | Total downtime window from token swap to first successful Felix cron tick is under 30 minutes. | Time from `systemctl restart openclaw-gateway` to the next scheduled cron exit code 0. | proposed |
| NFR-003 | Rollback executes within 5 minutes when triggered. | Wall-clock time from rollback trigger to verified kent-attributed write. | proposed |
| NFR-004 | Zero errors in `journalctl --user -u openclaw-gateway.service` for 30 minutes after the swap. | `grep -E 'error|ERROR|fail|FAIL' journalctl output for the window` returns no matches. | proposed |
| NFR-005 | All 12 project shares apply successfully within a single batch operation (one share per project, no retries needed). | API responses 200/201 for each of 12 share grants. | proposed |
| NFR-006 | 7-day soak: zero authentication failures on Vikunja API calls from any Felix sub-agent. | `journalctl --user -u openclaw-gateway.service --since "7 days ago" | grep -c '401\|403\|auth.*fail'` returns 0. | proposed |

---

## Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | Vikunja version on office2 is v0.24.6; all API behavior assumed conforms to that version's documented contract. Upgrades during this mission are out of scope. | accepted |
| C-002 | The secrets file path `/data/services/openclaw/secrets/vikunja-api` is canonical and must not change. Felix sub-agents reference this path via the Vikunja API skill. | accepted |
| C-003 | `data/credential-manifest.json` (JSON, authoritative) and `credentials-and-secrets.md` (narrative view) must be updated in the same commit to prevent drift. | accepted |
| C-004 | `felix-bot` receives read/write permission only on shared projects. Not admin. | accepted |
| C-005 | The `kent` Vikunja user account itself is not modified except to revoke its API tokens. Kent retains UI access. | accepted |
| C-006 | No code changes to any Felix agent are part of this mission. Only secrets file contents and documentation change. | accepted |
| C-007 | No migration or rewriting of historical tasks, comments, labels, or project ownership. All pre-existing writes remain attributed to `kent`. | accepted |
| C-008 | Tier 2 change-risk protocol applies. Restic backup must be confirmed before the secrets file is rotated, per `docs/runbooks/governance/pre-flight-checklist.md`. | accepted |
| C-009 | `felix-bot` is a Felix-wide identity. The mission does not split per sub-agent (no `felix-habits-bot` etc.) — that decision is deferred to a future date if/when it becomes valuable. | accepted |
| C-010 | TOTP / 2FA is intentionally NOT enabled on the `felix-bot` account. The account is API-only in normal operation and the Tailscale gate constrains attack surface. | accepted |

---

## Success Criteria

| ID | Criterion | Measurement |
|---|---|---|
| SC-001 | Every Felix agent comment write after cutover attributes to `felix-bot` at the API layer. | Sample 5 random comments written by Felix sub-agents during the 7-day soak; all show `created_by.username == felix-bot`. |
| SC-002 | All 12 real Vikunja projects accessible to felix-bot for read AND write. | Side-channel validation confirms reads on all 12; write probe succeeds on one per project. |
| SC-003 | Zero authentication errors in `openclaw-gateway` logs across the 7-day post-cutover soak. | `journalctl --user -u openclaw-gateway.service --since "7 days ago" | grep -ciE '401|403|auth.*fail'` returns 0. |
| SC-004 | Zero regression in Felix cron success rates across the 7-day soak window. | Per-cron exit codes during the soak match or exceed pre-cutover baseline. |
| SC-005 | Rollback procedure verified executable in under 5 minutes during the pre-swap validation phase. | Smoke test (FR-015) is recorded and confirms timing. |
| SC-006 | All four affected documentation files (`credential-manifest.json`, `credentials-and-secrets.md`, `identity-model.md`, `service-inventory.json`) updated in the same merge to `main`. | Single commit (or sequential commits in the same merge) touches all four files with consistent attribution to `felix-bot`. |
| SC-007 | Kent's existing API tokens are revoked; only `felix-bot`-attributed tokens are active on the instance after the mission completes. | Vikunja per-user token list shows no active tokens for `kent` user; one or more for `felix-bot`. |

---

## Key Entities

- **`felix-bot` Vikunja user account** — newly created on the office2 instance. Owns the rotated API token.
- **`felix-bot` API token** — long-lived bearer token stored in `/data/services/openclaw/secrets/vikunja-api` post-rotation.
- **Vikunja secrets file** at `/data/services/openclaw/secrets/vikunja-api` — mode 600, claude:claude. Single source of truth for the active API token.
- **Backup file** at `/data/services/openclaw/secrets/vikunja-api.kent-pre-felix-bot.bak` — transient, mode 600. Used for rollback only; removed after the 7-day soak passes.
- **12 Vikunja project share grants** — one per real project, granting `felix-bot` read/write permission.
- **Credential manifest entry** for `vikunja-api` in `data/credential-manifest.json` — authoritative record of the credential's ownership and metadata.
- **Validation harness** — a side-channel script (location TBD during plan phase) that exercises felix-bot's token end-to-end before the production swap.

---

## Assumptions

- A-001: Kent's UI login session continues to function after his API tokens are revoked. Vikunja sessions and API tokens are independent — a logged-in browser session does not require an API token to remain valid.
- A-002: The `vikunja.service` container on office2 remains running and accessible throughout the mission. No Vikunja-side maintenance overlaps with the rotation window.
- A-003: A recent Restic backup will exist at execution time (within the last 24 hours), per the Tier 2 pre-flight checklist.
- A-004: Felix sub-agents' Vikunja API skill reads the secrets file on each invocation rather than caching the token in agent memory. The `systemctl restart openclaw-gateway` is therefore sufficient to roll out the new token to all child agent sessions.
- A-005: Sharing a Vikunja project with felix-bot does not affect Kent's existing access (kent retains owner permissions; felix-bot is added as a collaborator).
- A-006: The Vikunja registration API requires only `username + email + password` (per the live probe on 2026-05-17). No additional fields like display name are required for registration to succeed.
- A-007: Vikunja's project sharing is one-shot — once shared, the grant persists until explicitly revoked. There is no expiration on the grants we create here.
- A-008: Pseudo-projects (IDs -5 to -1) are filter views that compose dynamically based on the requesting user's accessible projects; felix-bot will see appropriate content in these views after the 12 share grants are in place.

---

## Out of Scope

- **Vikunja-side data migration.** No tasks, comments, labels, attachments, or project ownership are rewritten. Historical writes remain attributed to `kent`.
- **Habit task `repeat_after` configuration** — that is Phase 3 (#306) of the ADR-0002 implementation.
- **JSONL state-log infrastructure** — Phase 2 (#305).
- **Historical comment backfill into JSONL** — Phase 4 (#307).
- **New-project auto-share monitor** — to be filed as a separate sibling infra issue immediately after this spec lands. Tracks "did we miss onboarding a new Vikunja project to felix-bot?" via daily cron alert. Documented here so the gap is not forgotten.
- **Code changes to Felix sub-agents.** The Vikunja API skill, agent AGENTS.md files, and helper scripts are untouched; only the secrets file contents change.
- **Vikunja webhook subscriptions.** Phase 8 deferred enhancement per ADR-0002 Q4.
- **Splitting `felix-bot` into per-sub-agent Vikunja identities** (e.g., `felix-habits-bot`, `felix-escalation-bot`). One Felix-wide identity per C-009.
- **TOTP/2FA on `felix-bot`.** Deliberately skipped per C-010.
- **Updates to felix-doc-auditor** — that agent uses the GitHub PAT (`kg-felix-bot-pat`), not the Vikunja token. Untouched.

---

## Dependencies

- ADR-0002 (parent design decision) — `docs/design/architecture/adr/0002-felix-vikunja-task-model.md`
- Issue #304 — source issue with the spec-ready body
- Issue #311 — umbrella implementation tracker
- `docs/design/research/vikunja-task-model-research.md` — capabilities research including the live-probe of project sharing endpoints
- `docs/design/architecture/data/change-risk-taxonomy.json` — Tier 2 protocol
- `docs/runbooks/governance/pre-flight-checklist.md` — Tier 2 pre-flight requirements
- Felix Constitution Directive 6 — deterministic-vs-stochastic split (validation harness and verification helpers are deterministic; live agent invocation during post-swap verification is stochastic but bounded by acceptance scenarios above)

---

## Notes

- The spec assumes execution happens in a single working session with operator presence. If interrupted between FR-005 (backup) and FR-008 (post-swap verification), the system is in a transient state that can be recovered either by completing the swap or by rolling back to the `.bak`.
- The rollback smoke test (FR-015) is intentionally part of pre-swap validation so the recovery path is proven before it is needed in anger.
