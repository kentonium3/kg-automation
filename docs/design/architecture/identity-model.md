---
title: Identity Model
doc_type: reference
status: approved
last_updated: '2026-07-12'
updated_by: '#715-vikunja-api-kent-config-token-audit-exception + #523-kg-felix-bot-project-sync-pat-added + #341-felix-bot-expiry-context + #304-felix-bot-rotation + #100-google-workspace-foundation + #227'
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

Felix agents act under dedicated service-account identities, distinct from Kent's personal accounts on each surface. Splitting human and agent identities keeps every audit timeline unambiguously attributable: a commit, issue comment, label change, PR action, Vikunja task creation, or task comment performed by an agent is visible under the agent's service account and cannot be confused with a Kent-driven action. Today Felix has two service accounts — one for GitHub, one for Vikunja — paired with the corresponding surface.

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

### `felix-bot` — Vikunja

The shared Vikunja service account for all Felix sub-agents performing API writes (`felix-admin-habits`, `felix-admin-escalation`, `felix-admin-capture`, `felix-admin-tasker`). Provisioned during ADR-0002 Phase 1 (issue #304); see [`docs/runbooks/felix-bot-vikunja-provisioning.md`](<../../runbooks/felix-bot-vikunja-provisioning.md>) for the rotation procedure.

| Field | Value |
|---|---|
| Surface | Vikunja v0.24.6 on office2 (`https://office2.tail0f5f56.ts.net/`) |
| Username | `felix-bot` |
| Scope | All Felix sub-agent API writes; read/write on the 12 real Vikunja projects (IDs 1, 2, 4-13). Not admin (per ADR-0002 Q3 / spec C-004). |
| Currently used by | `felix-admin-habits`, `felix-admin-escalation`, `felix-admin-capture`, `felix-admin-tasker` (via the shared `vikunja-api` OpenClaw skill) |
| Email | `kentgale+felix-bot@gmail.com` (routes to `kentgale@gmail.com`) |
| Password storage | 1Password (entry `felix-bot (Vikunja)`) — no on-disk copy on office2 |
| TOTP / 2FA | Not enabled (per ADR-0002 Q5c / spec C-010 — API-only identity, Tailscale gate constrains attack surface) |
| Credential | `vikunja-api` — see [`credential-manifest.json`](<./data/credential-manifest.json>) |
| Token created | 2026-05-17 (#304 Phase 1) |
| Token expires | 2029-05-17 — `expiry_policy: rotate-before-expiry`. Vikunja v0.24.6 UI requires an explicit expiry at token creation (no non-expiring option); 3 years was chosen at operator discretion. `credential-health-check.service` is configured to alert ~30 days before expiry (~2029-04-17). Plan rotation per [felix-bot-vikunja-provisioning.md](<../../runbooks/felix-bot-vikunja-provisioning.md>). |
| Created by | #304 / ADR-0002 Phase 1 |

Note: `kg-felix-bot` (GitHub) and `felix-bot` (Vikunja) are two distinct accounts on two distinct surfaces. They share an email alias (`kentgale+felix-bot@gmail.com`) for routing convenience, but the credentials, password stores, and audit timelines are independent. `felix-doc-auditor` uses `kg-felix-bot` and does NOT use the Vikunja API.

### `kent` — Vikunja config/system token (the audit-separation exception, #715)

The `felix-bot`/`kent` separation above holds for **task writes** but has a
**deliberate exception for Vikunja configuration**. Vikunja scopes some objects
(labels, saved filters) **per user**: a label created by `felix-bot` is
invisible in Kent's `kent` UI, and `felix-bot` cannot attach a `kent`-owned
label to a task (HTTP 403). So configuration Kent must see and manage — the
label taxonomy, saved filters, projects — has to be created **as `kent`**.

Felix therefore also holds an all-permissions **`kent`** Vikunja API token
(`vikunja-api-kent`, #715) used only for these config/system changes and for
label-attach. The consequence, accepted knowingly: **Vikunja config changes
attribute to `kent`, not `felix-bot`** — the agent-vs-UI audit separation is
kept for task writes (`vikunja-api`) but given up for config, because Vikunja
offers no delegation model that would let an agent make user-visible config
changes under a distinct identity. Verified 2026-07-12: `felix-bot` **can**
read/filter `kent`-owned labels on shared tasks (Felix's label-based queries
work) but **cannot** attach them. Full detail and the credential entry live in
[`credentials-and-secrets.md` §3](<./credentials-and-secrets.md>).

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
