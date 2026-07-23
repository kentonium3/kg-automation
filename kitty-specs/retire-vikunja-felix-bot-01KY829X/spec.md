# Retire Vikunja felix-bot: single kent-token model

**Mission**: retire-vikunja-felix-bot-01KY829X
**Source issue**: kentonium3/kg-automation#860 (Epic #531)
**Mission type**: software-dev

## Purpose

**TL;DR** — Retire the Vikunja `felix-bot` token and route **all** Felix→Vikunja
access through the single **kent** token (`vikunja-api-kent`), so Felix operates on
Kent's complete task store instead of a partial, felix-bot-visible slice.

The runtime `VikunjaClient()` default is the felix-bot `vikunja-api` token, which
cannot see the topic-projects #717 created as `kent` (projects 16–20, ~30+ tasks) and
never shared to felix-bot. Scans, the #751 dedup precheck, and label-attach all
operate on that partial view (and 403 on kent-owned labels — #750). The
agent-vs-human write-attribution felix-bot provided (#304 / ADR-0002) is not worth the
per-user-scoping cost. This mission drops the two-token model, collapses the registry
and validator to one token, records the decision in ADR-0003, and retires the felix-bot
credential from the manifest — **leaving the actual token valid (rollback-safe) and the
felix-bot user dormant**.

## User Scenarios & Testing

**Primary actor**: the Felix runtime (all `VikunjaClient` consumers on office2).
**Secondary actors**: the operator (Kent), and the #748 drift validator.

### Primary scenario (the cutover)

1. Every runtime `VikunjaClient()` consumer resolves the **kent** token by default (via
   the single client default), not felix-bot.
2. A live scan/read through the deployed runtime returns tasks from projects **16–20**
   that were previously invisible.
3. The dedup precheck and label-attach operate on the full task store; no kent-label 403.
4. Existing felix-bot-attributed tasks keep their attribution (the felix-bot user is
   left dormant, not deleted).

### Exception / edge scenarios

- **A consumer we missed** still needs Vikunja access → because the felix-bot token is
  left valid (not revoked), a revert of the runtime change restores prior behavior; no
  hard breakage.
- **Registry ↔ runtime divergence recurs** → the collapsed validator, now exercising the
  runtime token view, fails loudly instead of silently passing under a privileged view.

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | All runtime `VikunjaClient()` consumers with no explicit token MUST resolve the **kent** token by default. The 9 known no-token call sites (inbox route_and_finalize ×2, route_someday, habits weekly_report_driver + query_active_habits_weekly, vikunja create_task, intake scan_inbox, trust assertion_verifier, escalation enumerate_candidates) MUST all use the kent token; the full set MUST be re-confirmed by grep during implementation. | Required |
| FR-002 | The felix-bot fail-soft branches made moot by the single-token model (e.g. `route_someday` label-attach 403 handling) MUST be removed. Resolves the #750 code residue. | Required |
| FR-003 | `scripts/openclaw/skills/vikunja-api/SKILL.md` token guidance MUST point to the kent token, and the stale `v0.24.6`→`v2.4.0` header + health-check example MUST be corrected. Resolves #831. | Required |
| FR-004 | The #748 registry (`scripts/common/vikunja_refs.json`) + validator MUST collapse to a single-token model, and the validator MUST exercise the **runtime token view** (not a privileged kent-only default) so declaration and access can no longer silently diverge. | Required |
| FR-005 | A new **ADR-0003** MUST supersede ADR-0002, recording the dropped-attribution decision; `identity-model.md`, `credentials-and-secrets.md`, and remaining two-token references MUST be reconciled to the single-token model. | Required |
| FR-006 | The credential manifest MUST retire the `vikunja-api` (felix-bot) credential; the kent token becomes the sole Vikunja credential. This is an audited surface — the rebaseline obligation applies. | Required |
| FR-007 | The felix-bot `vikunja-api` token MUST be left **valid** in Vikunja (rollback-safe) and the felix-bot user left **dormant**. Actual token revocation and full user deprovision are explicitly deferred to a later cleanup. | Required |
| FR-008 | The runtime token change MUST deploy to office2 through the `deploys/queued/` manifest pipeline, with connectivity of all Felix→Vikunja consumers verified **before and after**, and a live read confirming projects 16–20 are now covered. | Required |

### Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-001 | Post-cutover the runtime MUST cover Kent's full task store. | Projects 16–20 (~30+ previously-invisible tasks) return in a live runtime read; count > 0 where it was 0. | Required |
| NFR-002 | The cutover MUST be reversible without data or attribution loss. | Reverting the runtime commit + redeploy restores prior behavior; the felix-bot token remains valid and its attributed tasks intact for the duration of this mission. | Required |
| NFR-003 | No Felix→Vikunja consumer regresses on the cutover. | Every consumer enumerated in FR-001 verified connected (read/write as applicable) after deploy; zero new auth failures vs. the pre-cutover baseline. | Required |

### Constraints

| ID | Constraint | Status |
|----|-----------|--------|
| C-001 | The GitHub `kg-felix-bot` identity (PRs/commits) is **out of scope** and unchanged. | Required |
| C-002 | Full deprovision/deletion of the felix-bot Vikunja **user** + reassignment of its Inbox(14) is **out of scope** (deferred; user left dormant). | Required |
| C-003 | The token default MUST live in a single place (the shared `VikunjaClient` default); consumers inherit it — no per-site token hardcoding. Single source of truth. | Required |
| C-004 | This is a **Tier-1/2** change: confirm a recent Restic snapshot before modifying service/credential state, and verify dependent-service connectivity before and after per the pre-flight/post-change runbooks. | Required |

## Success Criteria

| ID | Criterion |
|----|-----------|
| SC-001 | Every `VikunjaClient()` no-token consumer resolves to the kent token (grep-verified; no felix-bot default remains in the runtime path). |
| SC-002 | A live read through the **deployed** runtime returns tasks from projects 16–20 (previously 0). |
| SC-003 | The collapsed validator, run under the runtime token, passes — and would fail if the registry diverged from the runtime view (the guardrail now exercises the real view). |
| SC-004 | #831 and #750 are resolvable and closed as part of the mission. |
| SC-005 | The credential-manifest change records `Rebaseline: completed` (or `not required — <reason>`). |

## Key Entities

- **kent token** (`vikunja-api-kent`, `/data/services/openclaw/secrets/vikunja-api-kent`) — becomes the sole Vikunja API credential.
- **felix-bot token** (`vikunja-api`) — retired from manifest + runtime; left valid in Vikunja for rollback; the felix-bot **user** stays dormant.
- **#748 registry** (`scripts/common/vikunja_refs.json`) + **validator** (`scripts/vikunja/validate_refs.py`) — collapse to one token; validator exercises the runtime view.
- **Projects 16–20** — the topic-projects created as kent (#717) that felix-bot could not see; the coverage gap this mission closes.

## Assumptions

- **Mechanism**: the cutover is a single central-default change — `VikunjaClient`'s
  `DEFAULT_TOKEN_PATH` (`scripts/common/vikunja_client.py`) moves from `…/vikunja-api`
  to `…/vikunja-api-kent` — which inherently collapses to the single-token model and
  flips all 9 no-token consumers at once. Any explicit-token plumbing for felix-bot is
  removed. (Confirmed at plan; grep re-run at implement.)
- The kent token file already exists on office2 (provisioned by #715). To be verified
  live during plan (per the design-time environment-probe directive).
- "Retire the token" = remove from the credential manifest + runtime; **not** a
  Vikunja-side revocation (deferred, per the rollback-safe decision).

## Out of Scope

- The GitHub `kg-felix-bot` identity.
- Vikunja-side revocation of the felix-bot token and full deprovision of the felix-bot
  user + Inbox(14) reassignment (a later cleanup).
- Any change to what the topic-projects contain or their ids.
