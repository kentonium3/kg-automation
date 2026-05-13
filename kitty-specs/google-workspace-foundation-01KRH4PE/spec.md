# Spec: Google Workspace foundation — runbook, inventory, legacy cleanup

**Mission**: `google-workspace-foundation-01KRH4PE`
**Source issue**: [#100](https://github.com/kentonium3/kg-automation/issues/100) (closes); materially closes [#120](https://github.com/kentonium3/kg-automation/issues/120); unblocks epics [#164](https://github.com/kentonium3/kg-automation/issues/164), [#165](https://github.com/kentonium3/kg-automation/issues/165)
**Mission type**: `software-dev`
**Status**: draft
**Target branch**: `main`

## Summary

ADR-0001 (committed in `a0a7660`) selected `gog` CLI via Linuxbrew as the Google Workspace integration substrate. The live setup work — Linuxbrew install, `brew install steipete/tap/gogcli`, OAuth project/client creation in Google Cloud Console, scope grant for all six target services (Gmail, Calendar, Drive, Contacts, Sheets, Docs), and refresh-token mint for the personal account — completed 2026-05-13. End-to-end auth verified by live API calls against Calendar, Gmail, Drive, and Contacts.

This mission delivers the documentation and architecture-state artifacts that complete the integration as a long-lived, operable foundation:

1. An operator runbook capturing the full setup procedure (including the non-obvious failure modes the live setup surfaced — Calendar MCP API trap, D-Bus SecretService failure on headless, brew PATH per-user).
2. Service-inventory entries for the new integration.
3. Credential-manifest update covering the new shared OAuth client and refresh token; deprecation marker for the legacy Calendar-only credentials.
4. Identity-model entry covering the personal Google account; stub for the future Intentional business account.
5. Legacy cleanup of `scripts/google/authorize-calendar.py` (deprecated in favor of `gog auth`).
6. Post-merge verification recipe for any operator (you, future you) re-running this on a new machine.

No new code is being written. No Python wrapper or Felix-side skill. The runbook + architecture docs are the deliverable.

## User Scenarios & Testing

### Primary scenario — operator references the runbook to add the Intentional business account

**As** Kent (or any future operator),
**when** I need to add a second Google account (e.g., the Intentional business workspace) to the same gog install,
**then** the runbook in `docs/runbooks/google-workspace-ops.md` walks me through every step — Google Cloud Console project setup, OAuth consent, Client ID creation, scp of client_secret.json, `gog auth credentials`, `gog auth add --remote` two-step flow, common pitfalls — without re-deriving any of the findings from the 2026-05-13 personal-account setup.

**Acceptance**:
- The runbook covers all steps in sequence.
- The runbook explicitly calls out the three non-obvious failure modes that bit us during the personal-account setup: (a) Calendar MCP API masking the real Google Calendar API in the API library search, (b) D-Bus SecretService failure on headless servers requiring file backend, (c) brew PATH being per-user — claude's bashrc needs the brew shellenv line too.

### Secondary scenario — fresh operator audits the integration

**As** a future agent (or human),
**when** I want to understand what `gog` is, what credentials it consumes, and how it fits into the system,
**then** `docs/design/architecture/service-inventory.md` and `data/service-inventory.json` show `gog` as a deployed integration; `credentials-and-secrets.md` and `data/credential-manifest.json` reflect the shared OAuth client and refresh-token state, with deprecated markers on the obsolete Calendar-only credentials; `identity-model.md` notes the kentgale@gmail.com personal account.

**Acceptance**:
- Service inventory adds an entry for "Google Workspace via gog" with paths to the deployed binary, SKILL.md, credential locations, and the maintainer/source.
- Credential manifest records the new `google-workspace-client.json` (path, owner, mode, purpose) and the gog keyring at `/home/claude/.config/gogcli/credentials.json` (managed by gog).
- Calendar-only credentials at `/data/services/openclaw/secrets/google-calendar-{client-id,client-secret,refresh-token}` are marked `status: deprecated`, `deprecated_at: 2026-05-13`, with reason and replacement reference.
- Identity model has a personal-account section with a stub for the future Intentional account.

### Tertiary scenario — legacy script deprecation

**As** a future maintainer,
**when** I look at `scripts/google/authorize-calendar.py`,
**then** I either find it in `docs/archive/` (frozen historical) or with a deprecation banner pointing at the gog auth flow,
**so that** I don't waste time wondering if it's load-bearing.

**Acceptance**:
- The legacy `scripts/google/authorize-calendar.py` is moved to `docs/archive/` with a brief one-line note explaining the deprecation, OR left in place with a top-of-file docstring banner pointing at `gog auth credentials` + `gog auth add`. Implementer's call per quickstart.

### Edge cases

- **Brew is on PATH for kgale but not claude**: surfaced 2026-05-13. The runbook must document that `~/.bashrc` for claude needs `eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"` separately (already added live; runbook captures the rationale so future systemd-launched agents don't trip on missing brew PATH).
- **OpenClaw cron-launched agents inherit a non-interactive shell**: the gog env vars need to be available in that context. If `~/.bashrc` is sourced only by interactive shells, agents may not see `GOG_KEYRING_PASSWORD`. Runbook documents the test (run a sample `gog calendar colors` via `systemd-run --user` to verify), and the alternative of an EnvironmentFile in the relevant systemd unit if bashrc isn't picked up.
- **Adding a second Google account (Intentional)**: out of scope for this mission, but the runbook documents the procedure so it's a follow-up runbook reference, not a new spec phase.

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | Add `docs/runbooks/google-workspace-ops.md` covering install, auth, common commands, the three known pitfalls, and the future-account expansion path. | proposed |
| FR-002 | Update `docs/design/architecture/service-inventory.md` and `docs/design/architecture/data/service-inventory.json` with a new entry for the Google Workspace integration via gog. | proposed |
| FR-003 | Update `docs/design/architecture/credentials-and-secrets.md` and `docs/design/architecture/data/credential-manifest.json` to register the new `google-workspace-client.json` + the gog-managed refresh token; mark the legacy `google-calendar-*` credentials as deprecated. | proposed |
| FR-004 | Update `docs/design/architecture/identity-model.md` with a personal Google account section and a stub for the future Intentional account. | proposed |
| FR-005 | Move `scripts/google/authorize-calendar.py` to `docs/archive/scripts/authorize-calendar.py` (per the repo's archive convention) OR add a top-of-file deprecation banner pointing at the gog auth flow — implementer's call. | proposed |
| FR-006 | Update `docs/INDEX.md` and `docs/design/architecture/data/doc-domain-map.json` to reflect the new runbook + any documentation moves (per the change-control protocol). | proposed |
| FR-007 | Validate via `python3 tooling/scripts/validate_docs.py` — all docs pass. | proposed |

### Non-Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| NFR-001 | Runbook is self-contained — a future operator setting this up on a new machine can complete the process without referring to the original GitHub issues or chat history. | proposed |
| NFR-002 | Runbook captures the three known pitfalls (Calendar MCP, headless keyring, per-user brew PATH) explicitly enough that an operator can recognize the symptom and apply the fix without re-deriving the diagnosis. | proposed |
| NFR-003 | No new code is added or deleted; the mission is pure doc/architecture work. Implementer must not modify `gog` itself or any agent prompts. | proposed |

### Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | The mission does NOT update any Felix agent's AGENTS.md to actually use gog. Per #100's design, agent-side integration belongs to downstream user-story missions (#164 epic morning-briefing, #165 epic email triage, etc.). | accepted |
| C-002 | The mission does NOT set up the Intentional business account. That's a follow-up procedure documented by the runbook but executed separately. | accepted |
| C-003 | Legacy `google-calendar-*` credential files at `/data/services/openclaw/secrets/` are marked deprecated in the credential manifest but NOT deleted from disk in this mission. Deletion is operator-discretion post-merge once they confirm no orphaned consumer references them. | accepted |
| C-004 | The OpenClaw cron-launched agent context (non-interactive shell) is documented in the runbook; if testing reveals the bashrc env vars aren't inherited there, the mission's verification step captures that finding for a follow-up mission rather than fixing it here. | accepted |

## Success Criteria

- **SC-001**: After merge, `docs/runbooks/google-workspace-ops.md` exists and is a self-contained reference (NFR-001).
- **SC-002**: After merge, `openclaw skills info gog` on office2 reports ✓ Ready (already true; this is a regression guard).
- **SC-003**: After merge, `gog calendar colors`, `gog gmail search 'newer_than:1d' --max 1`, `gog drive search "x" --max 1`, and `gog contacts list --max 1` all execute successfully on office2 as the claude user (already verified live 2026-05-13; regression guard).
- **SC-004**: After merge, `python3 tooling/scripts/validate_docs.py` reports OK.
- **SC-005**: Issues #100 and #120 close on merge.

## Assumptions

- `gog` v0.16.0 (current) is stable for the documented commands.
- Google Cloud Console UI does not change in ways that invalidate the runbook procedure within the next 6 months. (If it does, runbook becomes a doc-debt update item rather than a re-spec.)
- The Felix-managed personal Google account (kentgale@gmail.com) remains the auth identity for this phase. The Intentional business account is a separate Google Cloud project / OAuth client / refresh-token bucket, registered with gog later via `--client intentional` (or similar alias).

## Dependencies

- Builds on ADR-0001 (committed `a0a7660`).
- Builds on the live setup work (2026-05-13): Linuxbrew + gog installed; OAuth project + client + refresh token in place; auth chain verified.
- No dependency on other open missions.

## Out of Scope

- Updating any Felix agent's AGENTS.md to actually invoke gog (per C-001). Downstream user-story missions handle that.
- Intentional business account setup (per C-002). Documented as a future procedure.
- Deleting the legacy `google-calendar-*` credential files from disk (per C-003). Marked deprecated, deletion deferred.
- Fixing the systemd-non-interactive-shell env-var inheritance (if it's an issue) — captured for follow-up per C-004.
- Adding new gog commands or modifying gog itself (NFR-003).
