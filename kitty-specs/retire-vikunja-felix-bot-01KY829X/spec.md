# Retire Vikunja felix-bot: single client, single kent identity

**Mission**: retire-vikunja-felix-bot-01KY829X
**Source issue**: kentonium3/kg-automation#860 (Epic #531 — Shared Vikunja Client and Configuration Boundary)
**Mission type**: software-dev

## Purpose

**TL;DR** — Route **all** Felix→Vikunja access through the single shared `VikunjaClient`
under the single **kent** identity, and eliminate felix-bot's Vikunja view entirely.

Two problems compound today: (1) ~6 runtime domains (sync, escalation, enrichment,
habits, credential-health) bypass the shared `VikunjaClient` and talk to Vikunja with
hand-loaded tokens + **raw HTTP** — a design inconsistency and a second, un-consolidated
token-loading path; and (2) the runtime default token is felix-bot, which cannot see the
kent-owned topic-projects #717 created (16–20, ~30+ tasks). The felix-bot Vikunja user
existed only for write-attribution (#304 / ADR-0002); once Vikunja's per-user visibility
fences were discovered, that rationale evaporated — there is no purpose for felix-bot in
Vikunja. This mission **consolidates every consumer onto `VikunjaClient`** (the Epic #531
boundary; the de-facto task-service seam of EA-architecture §11), **flips the single
source to the kent token**, and **eliminates felix-bot's Vikunja view** (kent-centric).

**Architecture boundary (§11 discipline)**: `VikunjaClient` *is* the seam between Felix's
logic and Vikunja. This mission establishes that seam by consolidation; it explicitly does
**not** build an abstract `TaskService` port / adapter registry — that formal port is
deferred until a second task backend (Todoist/Asana) justifies it ("seam now, formal port
when a second implementation justifies it").

## User Scenarios & Testing

**Primary actor**: the Felix runtime (every Vikunja consumer on office2).
**Secondary actors**: the operator (Kent), the #748 drift validator.

### Primary scenario

1. Every runtime Vikunja operation flows through `VikunjaClient`; no runtime path
   hand-loads a token or issues raw HTTP to Vikunja.
2. The single `VikunjaClient` default is the **kent** token, so all reads/writes see
   Kent's full task store, including projects 16–20.
3. felix-bot's Vikunja view is gone; any live felix-bot-owned data has been migrated to
   kent or confirmed empty.

### Exception / edge scenarios

- **A consumer we missed / a client gap**: because the felix-bot token is left valid
  (not revoked) during this mission, a revert restores prior behavior; a client that
  lacks an operation a consumer needs is a gap to close in `VikunjaClient`, not a reason
  to keep a raw path.
- **felix-bot-owned data stranded**: the inverse probe surfaces anything only felix-bot
  can see (its Inbox 14, tasks, labels, filters); it is migrated to kent or confirmed
  abandoned before the view is dropped.

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | **All Felix→Vikunja runtime access MUST go through the shared `VikunjaClient`.** The raw-HTTP / direct-token consumers MUST be migrated onto it: `scripts/sync/cycle.py`, `scripts/escalation/{record_completion,reconcile_completions}.py`, `scripts/enrichment/{record_completion,reconcile_completions}.py`, `scripts/habits/{sweeper,set_due_dates,record_completion,exclude_completed,identify_workout_task,migrate_schedule,backfill_jsonl_from_comments}.py`, `scripts/security/credential_health_check/vikunja_writer.py`. No runtime path may hand-load the token or issue raw HTTP to Vikunja. The full set MUST be re-confirmed by grep during implementation. | Required |
| FR-002 | `VikunjaClient` MUST be extended as needed to cover every operation the migrated consumers require (comments, completions, label ops, etc.) so consolidation loses no capability. New client methods follow the existing client contract + error model. | Required |
| FR-003 | The single `VikunjaClient` default token MUST be the **kent** token (`vikunja-api-kent`); the felix-bot default MUST be removed. Once FR-001 lands, this is the one place identity is set (single source of truth). | Required |
| FR-004 | The felix-bot fail-soft branches made moot (e.g. `route_someday` label-attach 403 handling) MUST be removed. Resolves the #750 code residue. | Required |
| FR-005 | An **inverse probe** MUST enumerate what felix-bot owns/sees that kent does not (its Inbox 14, tasks, labels, filters); any live felix-bot-owned data MUST be migrated to kent or explicitly confirmed abandoned. felix-bot's Vikunja view is eliminated. | Required |
| FR-006 | The #748 registry + validator MUST collapse to a single-token model and draw the token from the **shared `VikunjaClient` default** (not a parallel constant), so declaration and access can never silently diverge again. | Required |
| FR-007 | Token references in agent/skill/unit surfaces MUST be updated to the kent/single-token model: `scripts/openclaw/skills/vikunja-api/SKILL.md` (+ stale `v0.24.6`→`v2.4.0` header + health-check → resolves #831), `scripts/openclaw/skills/escalation/SKILL.md`, `scripts/openclaw/agents/felix-admin-tasker/TOOLS.md`, `scripts/sync/systemd/felix-vikunja-sync.service`. | Required |
| FR-008 | **ADR-0004** MUST supersede ADR-0002 (dropped-attribution / single-client-single-identity); `identity-model.md` and `credentials-and-secrets.md` MUST be reconciled. (ADR-0003 is already taken.) | Required |
| FR-009 | The credential manifest MUST retire the `vikunja-api` (felix-bot) credential (kent token sole). The felix-bot token MUST be left **valid** in Vikunja (rollback-safe) and its user left **dormant**; Vikunja-side revocation + full deprovision are a later cleanup. | Required |
| FR-010 | The cutover MUST deploy to office2 through the manifest/self-pull path with connectivity of **every migrated consumer** verified **before and after**, and a live read confirming projects 16–20 are covered. | Required |

### Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-001 | Post-cutover the runtime MUST cover Kent's full task store with **no split-brain**. | Every migrated consumer reads/writes the kent view; projects 16–20 (~30+ tasks) return; zero consumers left on the felix-bot view. | Required |
| NFR-002 | The cutover MUST be reversible without data or attribution loss. | Reverting the mission commit + redeploy restores prior behavior; the felix-bot token stays valid and its attributed tasks intact during the mission. | Required |
| NFR-003 | Consolidation MUST preserve behavior per consumer. | Each migrated consumer's observable Vikunja effects (the tasks/comments/labels it reads or writes) are unchanged except for the widened kent visibility; covered by per-consumer tests. | Required |

### Constraints

| ID | Constraint | Status |
|----|-----------|--------|
| C-001 | The GitHub `kg-felix-bot` identity is **out of scope** and unchanged (felix-bot may still serve non-Vikunja Felix functions). | Required |
| C-002 | Full deprovision/deletion of the felix-bot Vikunja **user** is **out of scope** (left dormant); this mission eliminates its *use/view*, not the account. | Required |
| C-003 | Single source of truth + single boundary: exactly one client (`VikunjaClient`) mediates Vikunja, and its default sets the one identity. No per-site token or raw HTTP. | Required |
| C-004 | **No abstract `TaskService` port / adapter layer** is built in this mission (§11 discipline — seam via `VikunjaClient`; formal port deferred to a second-backend justification). | Required |
| C-005 | **Tier-1/2**: confirm a recent Restic snapshot before modifying service/credential state; verify dependent-service connectivity before and after (attended). | Required |

## Success Criteria

| ID | Criterion |
|----|-----------|
| SC-001 | `grep -rnE "secrets/vikunja-api([^-]|$)" scripts/` shows **no runtime** consumer hand-loading the felix-bot token or issuing raw HTTP to Vikunja; every runtime Vikunja op goes through `VikunjaClient`. |
| SC-002 | A live read through the deployed runtime returns tasks from projects 16–20 (previously 0), from a migrated consumer path. |
| SC-003 | The collapsed validator, drawing the shared default, passes — and fails on a deliberately diverged registry entry. |
| SC-004 | The inverse probe result is recorded: felix-bot-only data is either migrated to kent or confirmed abandoned; nothing live is stranded. |
| SC-005 | #831 and #750 are resolved and closed. |
| SC-006 | The credential-manifest change records the verified `Rebaseline:` outcome. |

## Key Entities

- **`VikunjaClient`** (`scripts/common/vikunja_client.py`) — the single Vikunja access
  boundary (the #531 boundary / §11 task seam); its default sets the identity.
- **kent token** (`vikunja-api-kent`) — the sole Vikunja API credential post-mission.
- **felix-bot token** (`vikunja-api`) + **felix-bot user** — Vikunja view eliminated;
  token left valid (rollback), user dormant; retired from the manifest.
- **Raw-HTTP consumers** — sync/escalation/enrichment/habits/credential-health modules
  migrated onto `VikunjaClient`.
- **Projects 16–20** + **felix-bot Inbox(14)** — the visibility gap closed (16–20) and
  the inverse-probe target (14).

## Assumptions

- `VikunjaClient` is a sufficient/extensible boundary for every consumer's operations;
  where it lacks a method, the mission adds it (FR-002) rather than keeping a raw path.
- The kent token file exists + is non-empty on office2 (verified 2026-07-23); it is a
  superset-or-equal of what Felix needs (the inverse probe confirms and closes any gap).
- Admin/one-shot scripts that deliberately target a specific token
  (`provision_felix_bot.py`, `validate_felix_bot.py`, `swap_vikunja_secrets.py`,
  `reconcile_projects.py`, `create_saved_filters.py`, `migrate_tasks.py`) are **not**
  runtime consumers; those tied to felix-bot become obsolete and are archived/retired,
  not migrated.

## Out of Scope

- The GitHub `kg-felix-bot` identity.
- Vikunja-side revocation of the felix-bot token + full deprovision of the felix-bot user.
- Any abstract task-service port/adapter interface (deferred; C-004).
