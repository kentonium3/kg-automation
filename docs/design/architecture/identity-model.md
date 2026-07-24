---
title: Identity Model
doc_type: reference
status: approved
last_updated: '2026-07-23'
updated_by: 'vikunja-token-seam-kent-cutover-01KY8XQ0 (#860 phase 2, ADR-0007 — Vikunja felix-bot retired to dormant; kent is the sole runtime Vikunja identity) + #715-vikunja-api-kent-config-token-audit-exception + #523-kg-felix-bot-project-sync-pat-added + #341-felix-bot-expiry-context + #304-felix-bot-rotation + #100-google-workspace-foundation + #227'
---

# Identity Model

## Dual Google Identity

Kent operates with two Google identities:

| Identity | Scope | Vikunja Label | Calendar | Status |
|----------|-------|---------------|----------|--------|
| Personal | Personal life, health, growth | `personal` (blue, #2196f3) | Personal Google Calendar | Label exists (F001); calendar integration planned (F012) |
| Intentional LLC | Business, consultancy | `intentional` (green, #4caf50) | Intentional Workspace | Label exists (F001); routing deferred to Phase 3 |

## How Identity Routing Works

1. Tasks in Vikunja are tagged with `personal` or `intentional` labels
2. When calendar integration arrives (F012), the label determines which Google identity receives the calendar event
3. When WhatsApp integration arrives (F003-F006), the intent parser will infer identity from context and apply the label

## Current State (Post-F001)

- Both labels exist in Vikunja and are selectable on any task
- No automated routing yet — labels are applied manually
- Full routing is a Phase 3 capability

## Vikunja Project Structure

```
Everyday
├── Inbox           (default landing zone)
└── Someday         (deferred tasks)

Personal Growth & Transformation    (Area)
Business Acquisition                (Area)
└── CT-90day                        (subproject)
Health & Conditioning               (Area)
Intentional LLC                     (Area)
Metal Casework                      (Area)
```

Areas are organizational parent projects — convention is to place tasks in subprojects, not directly in Area projects.

## Agent Service Accounts

Felix agents act under service-account identities per surface. On **GitHub**, that is a dedicated `kg-felix-bot` account distinct from Kent's personal `kentonium3` — the split keeps every GitHub audit timeline (commit, issue comment, label change, PR action) unambiguously attributable to agent vs. human.

On **Vikunja**, the picture changed with [ADR-0007](<./adr/0007-retire-vikunja-felix-bot.md>) (#860 phase 2, 2026-07-23): Felix **no longer uses a dedicated Vikunja service account for runtime work.** All runtime Felix→Vikunja access — task reads and writes, completion writes, inbox scan/apply, sync, escalation/enrichment, and config/label work — now authenticates as the **`kent`** Vikunja user via the single `vikunja-api-kent` token. The former dedicated `felix-bot` Vikunja account and its `vikunja-api` token are **retired to dormant** (see below). The agent-vs-human attribution distinction was deliberately dropped on the Vikunja surface because Vikunja's per-user object scoping (#715/#717) made it expensive and actively caused incomplete reads (#860) — the correctness and reliability gains outweigh the lost distinction, and the `[Felix]` comment-text convention remains the in-Vikunja marker of agent authorship. **GitHub `kg-felix-bot` is unaffected** — the two surfaces are independent.

### `kg-felix-bot` — GitHub

The shared GitHub service account for all Felix agents (currently `felix-doc-auditor-driver`). This separation is load-bearing for the driver's Level-1 gate (the `_get_decision_actor` helper in [`scripts/doc_audit/run.py`](<../../../scripts/doc_audit/run.py>), implementing the actor-verification check from [`scripts/openclaw/skills/doc-audit/SKILL.md` §8.6](<../../../scripts/openclaw/skills/doc-audit/SKILL.md>)), where the driver must verify that an approval label was applied by a human and not by itself. The agent-AGENTS.md path referenced in pre-#343 docs no longer exists; the SKILL.md remains as the canonical specification of the actor-verification rule.

| Field | Value |
|---|---|
| Surface | GitHub (`github.com/kentonium3/kg-automation`) |
| Username | `kg-felix-bot` |
| Repo role | Collaborator on `kentonium3/kg-automation` |
| Currently used by | `felix-doc-auditor-driver` (post-#343), `felix-core-digest-signals` (post-#490 deterministic signal filer in `tick.py` → `felix-file-issue.py`), `spec-lifecycle.yml priority-field-sync` (#523, project-scope PAT only) |
| Email | `kentgale+felix-bot@gmail.com` (routes to `kentgale@gmail.com`) |
| TOTP / 2FA | Enabled |
| Credentials | `kg-felix-bot-pat` (classic PAT, scopes `repo, read:org, workflow`, held in gh CLI auth store on office2) and `kg-felix-bot-project-sync-pat` (classic PAT, scope `project` only, held as `PROJECT_SYNC_PAT` GitHub Actions secret on `kentonium3/kg-automation`) — see [`credential-manifest.json`](<./data/credential-manifest.json>) for full details. Two separate tokens, same identity: the project-sync PAT is intentionally narrower to keep blast radius low for the auto-sync workflow. |
| Created by | #215 (identity), #523 (project-sync PAT added) |

### `kent` — Vikunja (the sole runtime Vikunja identity, ADR-0007)

As of [ADR-0007](<./adr/0007-retire-vikunja-felix-bot.md>) (#860 phase 2), **all** runtime Felix→Vikunja access authenticates as the **`kent`** Vikunja user through the single `vikunja-api-kent` all-permissions API token. Runtime consumers resolve this token through one point — `scripts/common/vikunja_config.get_vikunja_token_path()` (directly or via the shared `VikunjaClient` default) — so the runtime identity lives in exactly one place.

| Field | Value |
|---|---|
| Surface | Vikunja v2.4.0 on office2 (`https://office2.tail0f5f56.ts.net/`) |
| Username | `kent` |
| Scope | **All runtime Felix→Vikunja access** — task reads/writes, completion writes, inbox scan/apply, sync full-poll, escalation/enrichment, plus config/label work (labels, saved filters, projects, label attachment). All-permissions token. |
| Runtime consumers | habits, escalation, enrichment, sync, inbox scan/apply, credential-health writer, `vikunja/create_task`, `trust/assertion_verifier`, `create_taxonomy_labels`, and the #748 `validate_refs` drift validator — all via the shared token seam |
| Credential | `vikunja-api-kent` — see [`credential-manifest.json`](<./data/credential-manifest.json>) |
| Token created | 2026-07-12 (#715); promoted to sole runtime credential 2026-07-23 (ADR-0007) |
| Token expires | 2027-07-12 — `expiry_policy: rotate-before-expiry`. `credential-health-check.service` alerts ~30 days before (~2027-06-12). Now the sole runtime Vikunja credential — rotate before expiry to maintain **all** Felix Vikunja capability. |
| Created by | #715; promoted by ADR-0007 (#860 phase 2) |

**Why a human account and not a bot?** Vikunja scopes objects (projects, labels, saved filters, label attachment) **per user**: a `felix-bot` account was blind to projects it was never shared into (topic projects 16–20, the #860 blind-read) and could not attach `kent`-owned labels (HTTP 403, #750). Consolidating on `kent` closes both — runtime and the #748 validator now share the same view and cannot silently diverge. The accepted cost: runtime writes attribute to `kent`, so `created_by` no longer distinguishes agent from human on Vikunja (the `[Felix]` comment-text convention remains that marker). See [ADR-0007](<./adr/0007-retire-vikunja-felix-bot.md>) for the full rationale and [`credentials-and-secrets.md` §3](<./credentials-and-secrets.md>) for the credential entry.

### `felix-bot` — Vikunja (retired to dormant, ADR-0007)

The dedicated `felix-bot` Vikunja service account was provisioned during ADR-0002 Phase 1 (issue #304) as the agent write identity, and served that role until [ADR-0007](<./adr/0007-retire-vikunja-felix-bot.md>) (#860 phase 2, 2026-07-23) **retired it from the runtime path**. It is **dormant, not deprovisioned**: the `felix-bot` Vikunja user still exists, its `created_by: felix-bot` attribution on existing tasks/comments is preserved, and it still owns its private Inbox project (14). Its `vikunja-api` token is marked **retired / dormant (non-runtime)** in [`credential-manifest.json`](<./data/credential-manifest.json>) — the secret file remains on office2 but no runtime consumer resolves it. Full deprovision of the user and reassignment of Inbox(14) are **out of scope** (deferred cleanup; spec C-002). Historical provisioning/rotation detail lives in [`docs/runbooks/felix-bot-vikunja-provisioning.md`](<../../runbooks/felix-bot-vikunja-provisioning.md>).

Note: `kg-felix-bot` (GitHub) and `felix-bot` (Vikunja) were always two distinct accounts on two distinct surfaces. They share an email alias (`kentgale+felix-bot@gmail.com`) for routing convenience, but the credentials, password stores, and audit timelines are independent. **GitHub `kg-felix-bot` is unaffected by ADR-0007** — only the Vikunja `felix-bot` user is retired from the runtime path. `felix-doc-auditor` uses `kg-felix-bot` and does NOT use the Vikunja API.

Canonical registry: [`AGENT-REGISTRY.md` §Service Accounts](<../../constitution/AGENT-REGISTRY.md#service-accounts>).

Future Felix agents may share these accounts or get their own dedicated service accounts per surface, depending on whether per-agent audit-trail separation becomes useful (per C-009: deliberately not split per sub-agent today).

## Google Workspace Accounts

Felix integrates with Google Workspace via the `gog` CLI (see [ADR-0001](<./adr/0001-google-workspace-via-gog.md>) and [`docs/runbooks/google-workspace-ops.md`](<../../runbooks/google-workspace-ops.md>)). Each Google account is a distinct OAuth identity registered with gog. Refresh tokens are stored in gog's encrypted keyring at `/home/claude/.config/gogcli/credentials.json` on office2.

### Personal account — kentgale@gmail.com (active 2026-05-13)

- **gog client alias**: `default`
- **Scopes granted**: Gmail, Calendar, Drive, Contacts (People API), Sheets, Docs
- **Google Cloud project**: `felix-openclaw-gog` (project ID 44082398134)
- **OAuth Client ID**: Desktop application type, named `felix-openclaw-gog` in Cloud Console
- **Authorized via**: `gog auth add kentgale@gmail.com --services gmail,calendar,drive,contacts,docs,sheets --remote` (see runbook for full procedure)

### Intentional business account — TBD (stub)

A future Google Cloud project for the Intentional consulting business will have its own OAuth Client and refresh-token bucket. Procedure: identical Cloud Console setup steps against the Intentional account, then `gog auth credentials --client intentional <path>` + `gog auth add intentional@example.com --client intentional --services ... --remote`. After registration, `gog auth list` will show both accounts. Per-command account selection via `-a <email>` or `--client <alias>` flags.

This stub is intentional placeholder. Update when the second project is set up.
