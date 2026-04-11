# Contract: Target Manifest Schema

**File:** `scripts/vault/targets.json`
**Inherited from:** Mission 024 (MVP)
**Modified by:** Mission 026 (extension to all migration targets)

## Schema

```json
{
  "version": 1,
  "targets": [
    {
      "template": "<path-to-.tmpl-source>",
      "output": "<path-to-resolved-output>",
      "office2_path": "<absolute-path-on-office2-optional>"
    }
  ]
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `version` | integer | yes | Schema version. Currently 1. |
| `targets` | array | yes | List of target entries. |
| `targets[].template` | string | yes | Relative path from repo root to the `.tmpl` source file. |
| `targets[].output` | string | yes | Relative path from repo root to the resolved output file. |
| `targets[].office2_path` | string | no | Absolute path on office2 where the resolved file is synced. Omit for repo-local targets. |

## Rules

1. **Relative paths are from the repository root**, not from the current working directory.
2. **`template` and `output` must not be the same path.** The template is the source; the output is the product.
3. **Every `template` path must end in `.tmpl`.** Convention.
4. **The `output` path is usually `template` with `.tmpl` stripped.** Example: `AGENTS.md.tmpl` → `AGENTS.md`.
5. **`office2_path` is absolute and includes the filename.** Not just the target directory.
6. **Omitting `office2_path` means the file stays in the repo only.** Used for files like `ai-agents/claude-instructions.md` that are consumed by Claude Code on the Mac, not deployed to office2.

## Target categories for mission 026

### Category A: OpenClaw agent workspace files (with office2_path)

Every file under `scripts/openclaw/agents/<agent>/` that contains vault path literals becomes a target. The `office2_path` points at the corresponding location under `/data/services/openclaw/` on office2.

**Example:**
```json
{
  "template": "scripts/openclaw/agents/felix-admin-tasker/AGENTS.md.tmpl",
  "output":   "scripts/openclaw/agents/felix-admin-tasker/AGENTS.md",
  "office2_path": "/data/services/openclaw/tasker-agent/AGENTS.md"
}
```

The exact `office2_path` values for each agent are determined by the existing OpenClaw deployment pattern and confirmed in WP01. Reference: the mission-024 entry for `felix-admin-capture` shows the convention (`/data/services/openclaw/inbox-agent/AGENTS.md`).

### Category B: Claude instruction files (no office2_path)

Files under `ai-agents/` are consumed by Claude Code on the operator's Mac, not deployed anywhere else.

**Example:**
```json
{
  "template": "ai-agents/claude-instructions.md.tmpl",
  "output":   "ai-agents/claude-instructions.md"
}
```

### Category C: Top-level project config (no office2_path)

`CLAUDE.md` is consumed by Claude Code from the repo root.

```json
{
  "template": "CLAUDE.md.tmpl",
  "output":   "CLAUDE.md"
}
```

### Category D: Scripts referencing vault paths (case-by-case)

If a script hardcodes a vault path, the preferred fix is to have it call `get_vault_path(name)` at runtime rather than to convert the script to a `.tmpl`. Scripts are code; templating them adds complexity.

- **If the script is cheap to modify to use the resolver:** do that, no target entry.
- **If the script is a static config file with path literals:** convert to `.tmpl` and add a target entry.

WP01 audit decides per file.

### Category E: Documentation (NOT in targets.json — direct-edited in WP03)

Files under `docs/` are narrative and human-read. They are direct-edited in WP03 rather than templated. The exception: any `docs/` file that is *consumed by a script or agent* (making it functional rather than narrative), in which case it becomes a template and gets a target entry.

## Deploy script contract (`scripts/vault/deploy.py`)

- **Input:** `targets.json` and `paths.json`
- **Action:** For each target, read the `.tmpl` source, substitute every `{{VAULT_*}}` marker with the resolved path from `paths.json`, write the result to `output`. If `office2_path` is set, sync the resolved file to office2 via the existing sync mechanism.
- **Output:** Resolved files in the repo (and on office2 where specified)
- **Exit code:** Non-zero on any unresolved marker, missing template, or sync failure.

## Invariants

1. Every `template` path exists in the repo.
2. Every `output` path is writable.
3. Every `.tmpl` file contains only markers that correspond to keys in `paths.json`.
4. Running `deploy.py` twice with no changes produces no diffs (idempotence).

## Test-first acceptance checks (WP01 exit criteria)

- [ ] `targets.json` parses as valid JSON
- [ ] Every `template` path in `targets.json` exists on disk
- [ ] `python3 scripts/vault/deploy.py` (dry-run) reports zero errors
- [ ] Dry-run output includes a line for every target entry
- [ ] No target entry references a missing logical name (dry-run would catch this)
