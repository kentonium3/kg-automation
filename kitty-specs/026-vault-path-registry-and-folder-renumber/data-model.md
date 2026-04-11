# Phase 1 Data Model: Vault Path Registry and Folder Renumber

**Mission:** `026-vault-path-registry-and-folder-renumber`
**Date:** 2026-04-11

This mission does not introduce new business entities — it is a refactor of how existing entities are referenced. The "data model" for planning purposes is the set of schemas, file contracts, and invariants the work packages consume and produce.

---

## Entity: Vault Path Registry

**File:** `scripts/vault/paths.json`
**Consumers:** `scripts/vault/resolver.py` (Python API), `scripts/vault/paths.sh` (shell API), `scripts/vault/deploy.py` (build-time substitution)

### Schema (unchanged from mission 024)

```json
{
  "version": 1,
  "updated": "YYYY-MM-DD",
  "paths": {
    "<logical_name>": "/absolute/physical/path"
  }
}
```

### State at mission 026 start

```json
{
  "version": 1,
  "updated": "2026-04-10",
  "paths": {
    "inbox": "/home/kgale/second-brain/notes/00-Inbox"
  }
}
```

### State after WP01 (registry extension — folders not yet renamed)

```json
{
  "version": 1,
  "updated": "2026-04-11",
  "paths": {
    "system":           "/home/kgale/second-brain/notes/00-System",
    "inbox":            "/home/kgale/second-brain/notes/00-Inbox",
    "inbox_processed":  "/home/kgale/second-brain/notes/02-Inbox-Processed",
    "constitution":     "/home/kgale/second-brain/notes/01-Constitution",
    "growth":           "/home/kgale/second-brain/notes/02-Growth",
    "health":           "/home/kgale/second-brain/notes/03-Health",
    "business":         "/home/kgale/second-brain/notes/04-Business",
    "finance":          "/home/kgale/second-brain/notes/05-Finance",
    "journal":          "/home/kgale/second-brain/notes/06-Journal",
    "resources":        "/home/kgale/second-brain/notes/07-Resources"
  }
}
```

**Note:** `inbox_processed` points at the target folder path even though the physical folder is not created until WP05. The registry entry exists throughout the pre-rename phase so that consumers can resolve the marker; any consumer that actually dereferences the path before WP05 would fail — but no consumer does, because `inbox_processed` has no live consumer until the #149 follow-on mission ships.

### State after WP05 (post-rename)

```json
{
  "version": 1,
  "updated": "2026-04-11",
  "paths": {
    "system":           "/home/kgale/second-brain/notes/00-System",
    "inbox":            "/home/kgale/second-brain/notes/01-Inbox",
    "inbox_processed":  "/home/kgale/second-brain/notes/02-Inbox-Processed",
    "constitution":     "/home/kgale/second-brain/notes/03-Constitution",
    "growth":           "/home/kgale/second-brain/notes/04-Growth",
    "health":           "/home/kgale/second-brain/notes/05-Health",
    "business":         "/home/kgale/second-brain/notes/06-Business",
    "finance":          "/home/kgale/second-brain/notes/07-Finance",
    "journal":          "/home/kgale/second-brain/notes/08-Journal",
    "resources":        "/home/kgale/second-brain/notes/09-Resources"
  }
}
```

### Invariants

1. **`_private` is never a logical name in this registry.** Attempting to resolve it must raise `UnknownPathError`. C-002 enforces this at the registry level; the resolver already enforces it by virtue of the path simply not being declared.
2. **Every logical name is lowercase, underscore-separated.** Convention from mission 024 README.
3. **Every path is absolute, no trailing slash.** Convention from mission 024 README.
4. **The `version` field is 1.** Schema evolution is out of scope for this mission.
5. **Marker naming:** `{{VAULT_<UPPER_CASE_OF_LOGICAL_NAME>}}`. For `inbox_processed`, the marker is `{{VAULT_INBOX_PROCESSED}}`.

---

## Entity: Target Manifest

**File:** `scripts/vault/targets.json`
**Consumers:** `scripts/vault/deploy.py`

### Schema (unchanged from mission 024)

```json
{
  "version": 1,
  "targets": [
    {
      "template": "<relative-path-to-.tmpl-source>",
      "output":   "<relative-path-to-resolved-file>",
      "office2_path": "<absolute-path-on-office2-optional>"
    }
  ]
}
```

### State at mission 026 start

```json
{
  "version": 1,
  "targets": [
    {
      "template": "scripts/openclaw/agents/felix-admin-capture/AGENTS.md.tmpl",
      "output":   "scripts/openclaw/agents/felix-admin-capture/AGENTS.md",
      "office2_path": "/data/services/openclaw/inbox-agent/AGENTS.md"
    }
  ]
}
```

### State after WP01 (expected — precise list assembled during WP01 after full audit)

The target count grows to approximately 20–30 entries. Categories:

- **OpenClaw agent files** (4 agents × up to 4 files each): AGENTS.md, TOOLS.md, SOUL.md, USER.md per agent, where the file contains vault path literals. Not every file in every agent contains literals — WP01 audit determines the exact set.
- **Main/main-patches support files:** SOUL.md, USER.md, inbox-delegation.md where literals are present.
- **Claude instructions:** `ai-agents/claude-instructions.md`, `ai-agents/claude-code-instructions.md`.
- **Top-level project config:** `CLAUDE.md`.
- **Scripts:** any script under `scripts/` that references vault paths (grep during WP01).

Each target has:
- `template`: relative path to the `.tmpl` source file (the authored source)
- `output`: relative path to the resolved file (what consumers actually read)
- `office2_path`: absolute path on office2 where `deploy.py` syncs the resolved file (only for files that need to be deployed to office2 — agent workspace files and main/main-patches)

Documentation files (under `docs/`) are generally NOT in `targets.json` — they are direct-edited in WP03 rather than template-driven. The rationale: doc markdown is narrative and referenced by humans; template substitution there creates a maintenance burden (every doc change requires editing the `.tmpl` and re-deploying) with no runtime benefit. The exception is if WP03 discovers a doc file that is *consumed* by a script or agent (which would make it functional, not narrative) — in which case it becomes a template.

### Invariants

1. **Every entry in `targets.json` has a corresponding `.tmpl` file in the repo.** `deploy.py` must detect a missing source and fail cleanly.
2. **Every entry produces a resolved output file at the specified path.** No entry is "source only" with no output.
3. **`office2_path` is optional.** Targets without it stay repo-local (example: `ai-agents/` files, which are Claude instructions read from the Mac).
4. **Output paths do NOT overlap with template paths.** A `.tmpl` and its resolved output never occupy the same path.

---

## Entity: Template File (`.tmpl` source)

**Structure:** A `.tmpl` file is a plain text file (typically markdown) containing zero or more `{{VAULT_<NAME>}}` placeholders. The deploy script substitutes each placeholder with the resolved path from the registry.

### Marker rules

- Markers are enclosed in double curly braces with no internal whitespace: `{{VAULT_INBOX}}`, not `{{ VAULT_INBOX }}`.
- Marker names are uppercase, underscore-separated, and exactly match the uppercased logical name from `paths.json`.
- A marker must correspond to a logical name that exists in `paths.json` at the time `deploy.py` runs. An unknown marker is a hard error — `deploy.py` fails and reports the unknown marker.

### Content rules

- A `.tmpl` file has the same extension + `.tmpl`. Example: `AGENTS.md` → `AGENTS.md.tmpl`.
- The resolved output has the original extension (without `.tmpl`).
- The `.tmpl` file should be committed to git. The resolved output may or may not be committed depending on whether it is consumed directly (agent workspace files are consumed by OpenClaw from the resolved location, so they must be committed).
- Comments inside `.tmpl` files are allowed (standard markdown), but a developer reviewing a `.tmpl` should understand that the file is not the runtime truth — the resolved output is.

### Backwards-compatibility constraint (WP02)

For every file that WP02 converts to a `.tmpl`:
- The resolved output (after `deploy.py --apply`) must be byte-identical to the original file (before conversion), except for the specific `{{VAULT_*}}` substitutions.
- This invariant is the basis for NFR-001 (refactor fidelity) and the WP04 test-first checkpoint.

---

## Entity: Deploy Wrapper (`deploy-f026.sh`)

**File:** `scripts/deploy/deploy-f026.sh`
**Consumers:** the operator
**Internal dependency:** `scripts/vault/deploy.py`

See `contracts/deploy-wrapper-contract.md` for the full interface.

### High-level responsibilities

1. Accept flags controlling verification depth and pause/resume behavior
2. Pause the `felix-admin-capture` cron on office2 (optional, flag-gated)
3. Invoke `python3 scripts/vault/deploy.py --apply` with appropriate arguments
4. Run verification checks: repo-wide grep for stale literals, deployed-file grep for unreplaced markers
5. Run smoke tests: invoke `felix-admin-capture` and `felix-admin-tasker` end-to-end
6. Re-enable the `felix-admin-capture` cron on office2 (if paused)
7. Emit clear pass/fail status with exit code

### Invariants

1. **Never skips verification.** Every invocation runs the verification checks. A `--skip-verify` flag exists only for debugging and must print a loud warning.
2. **Never leaves the cron paused on a failure path without explicit operator acknowledgment.** If the script crashes or fails mid-execution, it must emit a loud message stating "cron is still paused — manual re-enable required" before exiting.
3. **Idempotent re-runs.** Running the wrapper twice with the same inputs produces the same result. No state is leaked between runs.
4. **Non-zero exit on any verification failure.** The operator must see the failure and act on it, not have it buried in logs.

---

## Entity: Vault Folder

**Physical representation:** Directories on the operator's filesystem, synced via Obsidian Sync to office2.

### State transitions during this mission

| Folder | Pre-mission | Post-WP05 |
|---|---|---|
| `00-System` | exists | exists (no change) |
| `00-Inbox` | exists | renamed to `01-Inbox` |
| `01-Constitution` | exists | renamed to `03-Constitution` |
| `02-Growth` | exists | renamed to `04-Growth` |
| `03-Health` | exists | renamed to `05-Health` |
| `04-Business` | exists | renamed to `06-Business` |
| `05-Finance` | exists | renamed to `07-Finance` |
| `06-Journal` | exists | renamed to `08-Journal` |
| `07-Resources` | exists | renamed to `09-Resources` |
| `02-Inbox-Processed` | does not exist | created new in WP05 |

### Invariants

1. **Every rename is performed via the Obsidian UI**, not via `mv` or filesystem commands. This ensures Obsidian's internal link index auto-updates. (C-006)
2. **Renames are one folder at a time**, with wikilink integrity verified between each rename.
3. **`02-Inbox-Processed/` is created directly at its target name**, not renamed into place. It does not participate in the rename sequence.
4. **`_private/` inside `04-Growth/` is never read, written, enumerated, or referenced during this mission.** (C-001)

---

## Entity: Privacy Boundary Reference (`_private/`)

**Special handling.** The `_private/` path is referenced exactly once in production code, in CLAUDE.md, as a hardcoded absolute path:

> `~/second-brain/notes/02-Growth/_private/` (pre-mission — this will break after the rename because `02-Growth` becomes `04-Growth`)

### WP02 handling

CLAUDE.md migration must update the `_private/` boundary reference to use the new folder name `04-Growth`. Specifically:

- Before: `~/second-brain/notes/02-Growth/_private/`
- After: `~/second-brain/notes/04-Growth/_private/`

This is still a hardcoded absolute path — it does NOT become a template marker. The privacy boundary stays hardcoded per C-001 and C-002. But the hardcoded path itself must point at the renamed folder, otherwise the boundary rule references a folder that no longer exists.

This is the ONE place where a hardcoded vault-path literal exists in production code after the mission completes.

### Invariants

1. **`_private/` is never a logical name in `paths.json`.**
2. **The CLAUDE.md `_private/` boundary line is the only hardcoded vault-folder reference in production code post-mission.**
3. **WP02 must update this line even though it is hardcoded**, because the folder it references gets renamed.

---

## Relationships

```
paths.json ──referenced-by──→ resolver.py ──read-by──→ deploy.py
paths.json ──referenced-by──→ paths.sh ──sourced-by──→ shell scripts
targets.json ──read-by──→ deploy.py
deploy.py ──substitutes──→ .tmpl files ──produces──→ resolved files
resolved files ──synced-to──→ office2 (by deploy.py)
deploy-f026.sh ──wraps──→ deploy.py
deploy-f026.sh ──invokes──→ felix-admin-capture (smoke test)
deploy-f026.sh ──invokes──→ felix-admin-tasker (smoke test)
```

---

## What this mission does NOT model

- No new database schemas.
- No new API contracts in the REST/GraphQL sense — the "contracts" in `contracts/` are file-level interface contracts.
- No new user-facing data entities.
- No state machine beyond the folder pre/post rename states above.

This is an infrastructure refactor. The data model is the file-contract model.
