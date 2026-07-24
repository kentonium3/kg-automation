# Vikunja token seam + kent cutover (phase 2 of #860)

**Mission**: vikunja-token-seam-kent-cutover-01KY8XQ0
**Source issue**: kentonium3/kg-automation#860 (Epic #531 — Shared Vikunja Client and Configuration Boundary)
**Mission type**: software-dev

## Purpose

**TL;DR** — Collapse Felix→Vikunja token *resolution* to a **single point**, then perform the
atomic identity flip felix-bot → kent and retire the felix-bot token from the runtime path.

Phase 1 (`retire-vikunja-felix-bot-01KY829X`) routed every runtime consumer through the shared
`VikunjaClient` for HTTP, but left **token resolution split three ways**: some consumers use bare
`VikunjaClient()` (client default), the habits scripts each hardcode their own `DEFAULT_TOKEN_PATH`
felix-bot literal, and `sync` resolves `config.secrets_dir / "vikunja-api"`. So the flip Phase 1
promised as "a one-liner" would in fact reach only ~half the consumers. This mission first
**finishes the seam** — a single `get_vikunja_token_path()` resolution point that every runtime
consumer routes through (behavior-preserving, still felix-bot) — and *then* flips that one point to
the kent token, retires the felix-bot runtime credential, reconciles the ADR/identity/credential
docs and agent skill/tool references, and runs the **attended Tier-2 cutover** on office2.

**Why the split matters (root cause being corrected):** the single-token-resolution property was
an implicit goal in Phase 1's narrative, enforced by no requirement and quietly relaxed at
acceptance (SC-001 was read as "no raw urllib; DEFAULT_TOKEN_PATH constants may remain"). This
mission makes that property an explicit, un-relaxable success criterion.

**Architecture boundary (§11 discipline):** the seam is `VikunjaClient` + the `get_vikunja_token_path()`
config helper. This mission does **not** introduce an abstract `TaskService` port / adapter — that
formal port is deferred until a second task backend justifies it (respecting the seam is enough).

## User Scenarios & Testing

**Primary actor**: the Felix runtime (every Vikunja consumer on office2).
**Secondary actor**: the operator (Kent), for the attended cutover.

### Primary scenario

1. Every runtime Vikunja consumer resolves its token from **one** point (`get_vikunja_token_path()`),
   directly or via `VikunjaClient`. No consumer hardcodes a token path.
2. Before the flip: the resolved token is still felix-bot (`vikunja-api`) — zero observable change.
3. After the flip: changing that single point (its default, or the `VIKUNJA_TOKEN_PATH` override) to
   `vikunja-api-kent` makes **every** runtime consumer authenticate as kent, with no per-consumer edit.
4. Post-cutover, an inverse probe confirms the kent token sees the topic-projects (16–20) and Inbox(1)
   that felix-bot could not — closing the visibility gap that motivated #860.

### Exception / edge scenarios

- **Token file missing/unreadable** → a single, clear fail-loud error from the one resolution point
  (not N divergent per-script error strings).
- **Cutover connectivity** → each Felix→Vikunja consumer is connectivity-checked before and after the
  flip; a regression in any consumer is caught at the cutover gate.
- **Split-brain avoidance** → the flip is a single atomic change to one resolution point; there is no
  window where some consumers are kent and others felix-bot.

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | **Single token-resolution point.** Add `get_vikunja_token_path()` to `scripts/common/vikunja_config.py` (mirroring `get_vikunja_base_url()`): resolution order = `VIKUNJA_TOKEN_PATH` env override → a single canonical default path. It is the **sole** source of the Vikunja token path. `VikunjaClient`'s default-token loading resolves through it; every runtime consumer that today hardcodes a `DEFAULT_TOKEN_PATH` felix-bot literal (habits `sweeper`, `record_completion`, `exclude_completed`, `set_due_dates`, `identify_workout_task`, `migrate_schedule`) and `sync` (`cycle.py`/`fetch.py`) routes through it. No runtime consumer defines its own felix-bot token-path literal. `--token-path` CLI overrides may remain as a testing surface but MUST default to `get_vikunja_token_path()`. | Required |
| FR-002 | **Behavior-preserving centralization first.** FR-001 is landed and verifiable with the resolved token still the felix-bot `vikunja-api` — zero observable Vikunja effect change — as a distinct, independently-reviewable step **before** the flip. | Required |
| FR-003 | **The atomic flip.** Change the single resolution point's default from `vikunja-api` (felix-bot) to `vikunja-api-kent` (kent). After this one change, every runtime consumer authenticates as the kent Vikunja user. Both secret files already exist on office2; no secret rotation is performed. | Required |
| FR-004 | **Retire felix-bot from the runtime path.** Remove the felix-bot fail-soft branches made moot by the kent identity (e.g. `route_someday` label-attach 403 handling) — **resolves #750**. In the credential-manifest, mark the `vikunja-api` (felix-bot) credential **retired / dormant (non-runtime)** — not deleted — since the dormant felix-bot user still owns Inbox(14) and attribution history; the kent token (`vikunja-api-kent`) becomes the sole **runtime** Vikunja credential. | Required |
| FR-005 | **Validator convergence.** The #748 drift validator (`scripts/vikunja/validate_refs.py`) MUST exercise the same token view the runtime uses, so registry declaration and runtime access can no longer silently diverge (the structural blindness that caused #860 — the validator ran under the kent token while the runtime ran under felix-bot). After the flip both are the kent token; confirm and lock this so a future divergence is caught. | Required |
| FR-006 | **Doc / ADR / skill reconciliation.** Author **ADR-0007** recording the dropped-attribution decision and superseding ADR-0002's rationale (ADR-0002 stays as historical record, marked superseded). Reconcile `identity-model.md`, `credentials-and-secrets.md`, `service-inventory`, and `data-flows` to the single-token model. Update the `vikunja-api` SKILL.md token guidance to the kent token, fix its stale `v0.24.6`→`v2.4.0` header and health-check example, and update the escalation SKILL + tasker TOOLS/AGENTS token references — **resolves #831**. | Required |
| FR-007 | **Attended Tier-2 cutover + verification.** Deploy via checkout self-pull. Perform a **before/after connectivity check** of every Felix→Vikunja consumer (from `service-inventory`), plus the FR-001/§Primary inverse probe (kent token sees projects 16–20 + Inbox(1)). The credential-manifest change is an **audited surface** → record the rebaseline outcome (completed, or not-required with reason). | Required |

### Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-001 | Centralization (FR-001/FR-002) is behavior-preserving up to the flip. | Each affected consumer's Vikunja effects are unchanged vs. HEAD while the resolved token is still felix-bot; proven by the existing parity/affected test surface staying green at the pre-flip step. | Required |
| NFR-002 | Single fail-loud token error. | A missing/unreadable token file produces exactly one clear error originating from `get_vikunja_token_path()`/`VikunjaClient`, not divergent per-script messages. | Required |

### Constraints

| ID | Constraint | Status |
|----|-----------|--------|
| C-001 | No abstract `TaskService` port / adapter layer (§11 — seam via `VikunjaClient` + config helper; formal port deferred). | Required |
| C-002 | The felix-bot **Vikunja user** is left **dormant**, not deprovisioned; Inbox(14) reassignment and full user deletion are deferred to a later cleanup (out of scope here). The `vikunja-api` secret file remains on office2. | Required |
| C-003 | The GitHub `kg-felix-bot` identity (PRs/commits) is **out of scope** and unchanged. | Required |

## Success Criteria

| ID | Criterion |
|----|-----------|
| SC-001 | **(Un-relaxable architectural gate — the property Phase 1's relaxed SC failed to protect.)** `grep -rnE "secrets/vikunja-api([^-]\|$)" scripts/` returns **zero** runtime-consumer matches: no runtime module defines or hand-loads a felix-bot token path. Every runtime Vikunja consumer resolves the token via `get_vikunja_token_path()` (directly or through `VikunjaClient`). The only permitted matches are the explicitly enumerated admin/one-shot scripts that deliberately target the felix-bot user (`provision_felix_bot`, `validate_felix_bot`, `swap_vikunja_secrets`) and docs describing the dormant credential. |
| SC-002 | **Single-point flip proof.** An automated test demonstrates that changing `get_vikunja_token_path()`'s resolution (via the `VIKUNJA_TOKEN_PATH` override) changes the resolved token for **every** runtime consumer path, with no per-consumer code change. |
| SC-003 | The full affected suite is green: vikunja / inbox / habits / escalation / enrichment / trust / sync **and** the architectural ratchets (`tests/architectural/`). |
| SC-004 | Post-cutover on office2: every runtime consumer authenticates as kent (spot-verified per consumer); the inverse probe confirms the kent token sees projects 16–20 + Inbox(1); the felix-bot fail-soft branches are gone (#750); the SKILL.md is on v2.4.0 with a correct health-check example (#831). |
| SC-005 | The credential-manifest (audited surface) rebaseline outcome is recorded on the merge — completed at `<ts>`, or `not required — <reason>`. |

## Key Entities

- **`get_vikunja_token_path()`** (`scripts/common/vikunja_config.py`) — NEW single token-path
  resolution point; the one place the Vikunja runtime identity lives.
- **`VikunjaClient`** (`scripts/common/vikunja_client.py`) — the Vikunja access boundary; its
  default-token loading resolves through `get_vikunja_token_path()`.
- **kent token** (`vikunja-api-kent`) — becomes the sole runtime Vikunja credential.
- **felix-bot token** (`vikunja-api`) — retired from the runtime path; marked dormant in the
  credential-manifest; file retained on office2 for the dormant user.
- **#748 registry + validator** (`scripts/common/vikunja_refs.json`, `scripts/vikunja/validate_refs.py`)
  — converged onto the runtime (kent) token view.

## Assumptions

- Both secret files (`/data/services/openclaw/secrets/vikunja-api` and `…/vikunja-api-kent`) already
  exist on office2 (verified) — the flip is a path change, not a secret rotation.
- The deployed drivers invoke habits/sync scripts with **no** token args (`python3 -m scripts.habits.sweeper`),
  and `--token-path` is a local-testing surface — so centralization is a pure code change with zero
  deployment-argument impact (verified).
- The last Restic snapshot (`2026-07-23T04:00Z`, exit 0) satisfies the Tier-2 24h backup gate; a fresh
  snapshot is taken at cutover if >24h by then.
- `intake/apply_reply.py` and the Phase-1 Group-A consumers already use bare `VikunjaClient()` — they
  inherit the flip automatically once the client default resolves through the helper.

## Out of Scope (deferred)

- Full deprovision/deletion of the felix-bot Vikunja user + reassignment of Inbox(14) (C-002).
- The GitHub `kg-felix-bot` identity (C-003).
- Any abstract task-service port/adapter interface (C-001).

## Architecture Impact

Change classes (per `signal-to-doc-map.json`, to be finalized in plan): **credential-added-or-modified**
(retire `vikunja-api` runtime credential), **architecture-doc-added** (ADR-0007). Doc targets to review
in the merge: `docs/design/architecture/data/credential-manifest.json`, `credentials-and-secrets.md`,
`identity-model.md`, `service-inventory.(md|json)`, `data-flows.(md|json)`, the new
`docs/design/architecture/adr/0007-*.md`, `docs/INDEX.md` (+ `DEVELOPER_PORTAL.md` if the ADR is
surfaced), and the agent SKILL/TOOLS/AGENTS token references. Rebaseline obligation applies
(credential-manifest is an audited surface).
