# Data Model: Retire Vikunja felix-bot (single kent-token model)

No application data model changes. The "model" here is the credential/identity configuration
and who reads which token.

## Entities

### Vikunja API tokens (office2 secret files)

| Token | File | Before | After |
|-------|------|--------|-------|
| `vikunja-api-kent` (kent) | `/data/services/openclaw/secrets/vikunja-api-kent` | config + label-attach only | **sole runtime token** (all reads/writes) |
| `vikunja-api` (felix-bot) | `/data/services/openclaw/secrets/vikunja-api` | runtime default (reads/writes) | **retired** from manifest + runtime; file left **valid** (rollback); user **dormant** |

### Credential manifest (`credential-manifest.json`)

- Retire the `vikunja-api` entry (kent token becomes the sole Vikunja API credential).
- Unchanged: `vikunja-api-kent`, `vikunja-admin` (web UI u/p), and the two `kg-felix-bot-*`
  GitHub PATs (out of scope — GitHub identity).

### Consumer → token binding

- **Before**: `VikunjaClient()` (no token) → felix-bot default; `validate_refs.py` → kent constant.
  Divergence = the bug (felix-bot can't see kent-owned projects 16–20).
- **After**: `VikunjaClient()` (no token) → kent default; `validate_refs.py` → **same** default.
  Convergence = the fix.

## Decision / state table

| Surface | Before | After |
|---------|--------|-------|
| `VikunjaClient.DEFAULT_TOKEN_PATH` | `…/vikunja-api` | `…/vikunja-api-kent` |
| 9 no-token consumers | felix-bot view (partial) | kent view (full: projects 16–20 visible) |
| `route_someday` label-attach | fail-soft (felix-bot 403) | unconditional attach (kent can attach) |
| #748 validator token source | parallel kent constant | shared runtime default |
| felix-bot `vikunja-api` credential | in manifest, runtime default | retired from manifest; token valid, user dormant |
| ADR of record | ADR-0002 (attribution) | ADR-0004 (dropped attribution); 0002 superseded |

## Invariants

- **INV-1** (single source of truth): exactly one place defines the runtime token (the client default); the validator shares it (C-003 / FR-004).
- **INV-2** (coverage): post-cutover the runtime sees every kent-owned project, incl. 16–20 (NFR-001).
- **INV-3** (reversibility): the felix-bot token stays valid; reverting the runtime commit restores prior behavior (NFR-002).
- **INV-4** (attribution preserved): existing felix-bot-attributed tasks are untouched (user dormant, not deleted) (C-002).
- **INV-5** (scope): GitHub `kg-felix-bot` identity + full user deprovision are out of scope (C-001/C-002).
