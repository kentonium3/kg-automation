# Data Model: felix-bot Vikunja provisioning

**Mission**: `felix-bot-vikunja-provisioning-01KRT3N4`

This mission's "data model" is largely a set of entities that exist outside the kg-automation repository — they live in the Vikunja v0.24.6 instance on office2, in the filesystem of office2, and in the architecture documentation. There are no new in-repo database tables, no new schemas to define inside the code we write. The model below catalogs the entities the mission creates or modifies and their relationships.

---

## Entity catalog

### E-1 — `felix-bot` Vikunja user account

**Location**: Vikunja v0.24.6 PostgreSQL/SQLite store on office2 (managed by `vikunja.service`).

**Lifecycle**: Created during Phase 1 via `POST /api/v1/register`. Permanent thereafter — not deleted by this mission.

**Fields** (as represented by Vikunja's User model):

| Field | Value | Source |
|---|---|---|
| `id` | assigned by Vikunja at registration | Vikunja-internal auto-increment |
| `username` | `felix-bot` | Mission constant |
| `email` | `kentgale+felix-bot@gmail.com` | Discovery decision (Q5a) |
| `name` | `felix-bot` (or empty) | Optional |
| `created` | `2026-05-17T...` | Vikunja sets at registration |
| `password_hash` | bcrypt of 1Password-generated password | Stored by Vikunja, never read out |

**Relationships**:
- Owns 0 projects (kent retains ownership of all 12)
- Is shared into 12 projects at R/W permission (see E-3)
- Holds 1 long-lived API token (see E-2)

---

### E-2 — `felix-bot` API token

**Location**: Vikunja's token store + `/data/services/openclaw/secrets/vikunja-api` on office2 (mode 600, claude:claude).

**Lifecycle**:
- Generated during Phase 1 by the operator (via Vikunja UI logged in as felix-bot, OR via the API token endpoint if available in v0.24.6)
- Written to the secrets file by `swap_vikunja_secrets.py` during Phase 3
- Used by all Felix sub-agents through the existing `vikunja-api` skill
- Never expires unless explicitly revoked

**Fields**:

| Field | Value |
|---|---|
| `token` | opaque string issued by Vikunja |
| `owner_user_id` | felix-bot's user ID |
| `created` | Phase 1 timestamp |
| `expires` | none (long-lived) |
| `scope` | full (Vikunja v0.24.6 does not have scoped tokens) |

**Relationships**:
- Owned by felix-bot user (E-1)
- Stored exclusively in `/data/services/openclaw/secrets/vikunja-api` (one file = one active credential)
- Used by `openclaw-gateway.service` and all child agent sessions through the `vikunja-api` skill

---

### E-3 — Project share grants

**Location**: Vikunja's project-user join table (queryable via `GET /api/v1/projects/{id}/users`).

**Lifecycle**: Created during Phase 1 via `PUT /api/v1/projects/{id}/users`. Persist until explicitly revoked.

**Records** (12 total, one per real Vikunja project):

| Project ID | Project title | Grant |
|---|---|---|
| 1 | Inbox | felix-bot, R/W |
| 2 | Everyday | felix-bot, R/W |
| 4 | Someday (child of 2) | felix-bot, R/W |
| 5 | Personal Growth & Transformation | felix-bot, R/W |
| 6 | Business Acquisition | felix-bot, R/W |
| 7 | CT-90day (child of 6) | felix-bot, R/W |
| 8 | Health & Conditioning | felix-bot, R/W |
| 9 | Intentional LLC | felix-bot, R/W |
| 10 | Metal Casework | felix-bot, R/W |
| 11 | Goals | felix-bot, R/W |
| 12 | Research | felix-bot, R/W |
| 13 | Habits | felix-bot, R/W |

**Fields per record**:

| Field | Value |
|---|---|
| `project_id` | one of the 12 above |
| `user_id` | felix-bot's user ID |
| `permission` | `1` (read-write) |
| `created` | Phase 1 timestamp |

**Relationships**:
- Each grant links one Vikunja project to felix-bot (E-1)
- Pseudo-projects (-5 to -1) are NOT included — they're filter views, not shareable

---

### E-4 — Vikunja secrets file (active)

**Path**: `/data/services/openclaw/secrets/vikunja-api`

**Lifecycle**: Already exists at mission start (holding kent-attributed token). Rotated during Phase 3 to hold felix-bot's token.

**Fields**:

| Attribute | Pre-mission | Post-mission |
|---|---|---|
| Path | `/data/services/openclaw/secrets/vikunja-api` | same |
| Mode | `600` | `600` |
| Owner | `claude:claude` | `claude:claude` |
| Contents | kent's API token | felix-bot's API token |
| Size | one line, token value + newline | one line, token value + newline |

**Relationships**:
- Read by all Felix sub-agents via the `vikunja-api` skill on each invocation
- Replaces the kent-attributed token with felix-bot's (the token rotation IS the swap)

---

### E-5 — Vikunja secrets backup file (transient)

**Path**: `/data/services/openclaw/secrets/vikunja-api.kent-pre-felix-bot.bak`

**Lifecycle**: Created during Phase 3 (right before secrets-file rotation). Deleted during Phase 6 (after 7-day soak passes).

**Fields**:

| Attribute | Value |
|---|---|
| Path | `/data/services/openclaw/secrets/vikunja-api.kent-pre-felix-bot.bak` |
| Mode | `600` |
| Owner | `claude:claude` |
| Contents | kent's pre-rotation API token (verbatim copy of pre-swap `vikunja-api`) |

**Relationships**:
- Used by `swap_vikunja_secrets.py`'s rollback path: if post-swap verification fails, contents are written back to `/data/services/openclaw/secrets/vikunja-api`
- Removed only after the 7-day soak passes (per R-009)

---

### E-6 — `credential-manifest.json` `vikunja-api` entry

**Path**: `docs/design/architecture/data/credential-manifest.json`

**Lifecycle**: Existing entry, modified during Phase 4 (doc updates) to reflect new ownership.

**Field changes**:

| Field | Before | After |
|---|---|---|
| `last_reviewed` | (varies) | 2026-05-17 (rotation date) |
| `updated_by` | existing string | prepend `#304-felix-bot-rotation` |
| `notes` | references kent-attributed token | revised to reference felix-bot ownership and the rotation date |
| `created_by` | (kent user info) | unchanged — this is the file authorship attribution, not the credential ownership |

Other fields (name, type, storage, expiry_policy, review_cadence, host) remain unchanged.

---

### E-7 — `credentials-and-secrets.md` narrative

**Path**: `docs/design/architecture/credentials-and-secrets.md`

**Lifecycle**: Existing file, modified during Phase 4 to reflect new ownership.

**Sections to update**:

| Section | Change |
|---|---|
| Frontmatter `last_updated` | Bump to 2026-05-17 |
| Frontmatter `updated_by` | Prepend `#304-felix-bot-rotation` |
| Active Credentials table (`vikunja-api` row) | Update "Used By" or "Notes" column to mention felix-bot ownership |
| Section 3 "Scoped plaintext files (mode 600)" narrative | Confirm references describe felix-bot as the API identity now |

---

### E-8 — `identity-model.md` Agent Service Accounts

**Path**: `docs/design/architecture/identity-model.md`

**Lifecycle**: Existing file, modified during Phase 4. Adds a new entry alongside the existing `kg-felix-bot` (GitHub) entry.

**New row**:

| Identity | Surface | Scope | Created by |
|---|---|---|---|
| `felix-bot` | Vikunja v0.24.6 on office2 | All Felix sub-agent API writes; R/W on 12 projects | #304 / ADR-0002 Phase 1 |

---

### E-9 — `service-inventory.json` (conditional)

**Path**: `docs/design/architecture/data/service-inventory.json`

**Lifecycle**: Existing file, modified during Phase 4 IF the `vikunja` service entry tracks per-user accounts. If it does not track that today, this update is a no-op and skipped.

**Field changes** (if applicable):

| Field | Before | After |
|---|---|---|
| `vikunja.users` (if present) | `["kent"]` | `["kent", "felix-bot"]` |

---

## Relationship diagram

```
+----------------------+
|  felix-bot (E-1)     |  Vikunja user account on office2
|  username, email     |
+----------+-----------+
           |
           | owns
           v
+----------------------+
|  API token (E-2)     |  long-lived; stored in:
+----------+-----------+
           |
           | stored in
           v
+----------------------+
|  vikunja-api (E-4)   |  /data/services/openclaw/secrets/vikunja-api
+----------------------+
           ^
           | rotation backed up to
           |
+----------------------+
|  .bak file (E-5)     |  vikunja-api.kent-pre-felix-bot.bak (transient)
+----------------------+

felix-bot ────shared via grants (E-3)────> 12 Vikunja projects (IDs 1, 2, 4-13)
                                              R/W permission

Architecture documentation reflects state:
  credential-manifest.json (E-6) ───┐
  credentials-and-secrets.md (E-7) ─┼─── single commit per Constraint C-003
  identity-model.md (E-8) ──────────┤
  service-inventory.json (E-9) ─────┘
```

---

## Validation rules

| Rule | Where enforced |
|---|---|
| `felix-bot` username is unique on the Vikunja instance | Vikunja-side; `POST /api/v1/register` returns conflict if duplicate |
| API token is non-empty before being written to the secrets file | `swap_vikunja_secrets.py` input validation |
| Mode 600 + claude:claude ownership on all secrets files | `swap_vikunja_secrets.py` explicit `chmod` and `chown` (or `os.chmod`) |
| All 12 share grants must succeed before validation phase begins | `provision_felix_bot.py` exits nonzero if any share fails; operator does not advance |
| Validation comment must be deleted before validation script exits | `validate_felix_bot.py` cleanup step |
| Post-swap verification must confirm `created_by.username == felix-bot` | `swap_vikunja_secrets.py` halts and rolls back if attribution check fails |

---

## State transitions

**Secrets file `vikunja-api`**:

```
[kent token (pre-mission)]
        |
        | swap_vikunja_secrets.py
        v
[felix-bot token (post-rotation)]  ← terminal state
```

**Backup file `vikunja-api.kent-pre-felix-bot.bak`**:

```
[absent]
   |
   | swap_vikunja_secrets.py phase 3.1 (backup)
   v
[exists, contains pre-rotation kent token]
   |
   | (held throughout 7-day soak)
   v
[removed by revoke_kent_tokens.py after soak passes]
```

**kent user's Vikunja API tokens**:

```
[1+ active token(s) attributed to kent]
        |
        | revoke_kent_tokens.py during Phase 6
        v
[0 active tokens attributed to kent]  ← terminal state
```

**felix-bot's project access (per-project)**:

```
[no access]
   |
   | PUT /api/v1/projects/{id}/users (provision_felix_bot.py)
   v
[R/W shared] ← terminal state
```

---

## Notes

- No new in-repo schemas are introduced by this mission. All new "data" is in Vikunja's existing user/project/token tables or on the office2 filesystem under existing paths.
- Vikunja-side state is the authoritative record for E-1, E-2, E-3. Filesystem state is the authoritative record for E-4, E-5. Documentation files are the narrative view (E-6, E-7, E-8, E-9).
- All Vikunja entity fields named above (`id`, `username`, `permission`, etc.) reflect the v0.24.6 API contract observed during the 2026-05-17 live probe (see `docs/design/research/vikunja-task-model-research.md`).
