# Data Model: Observation-Digest Log Repoint & Decommission

This is a filesystem/config change, not a database feature. The "entities" are the config
object, the log artifacts, and the migrator's inputs/preconditions/outputs.

## Entities

### ObservationConfig (`scripts/openclaw/observation/config.py`)

| Field | Type | Before | After |
|---|---|---|---|
| `log_dir` (default) | `Path` | `Path.home()/second-brain/agents/logs` (→ `/home/claude/…` under `HOME=/home/claude`) | `DEFAULT_AGENT_LOGS_DIR = /home/kgale/second-brain/agents/logs` (absolute; `HOME`-independent) |
| `output_dir` (default) | `Path` | `get_vault_path("system")/agent-activity` | **unchanged** (already vault-synced) |
| Overrides | ctor args / CLI `--log-dir`,`--output-dir` | preserved | preserved |

**Invariant**: under any `HOME`, the resolved `log_dir` is `/home/kgale/second-brain/agents/logs`
unless explicitly overridden.

### Raw log artifact

- Path: `<log_dir>/<agent-name>/<YYYY-MM-DD>.jsonl`
- Writer: `log_action.py` (append). Reader: `summarize.py`.
- Format: one JSON object per line (agent action record).
- Merge semantics: for a given `(agent, date)`, the vault file and stray file are **union-merged**
  by line identity (dedup on exact line) — no entry lost or duplicated (NFR-003).

### Migration preconditions (checked before any destructive step)

| Precondition | Check | Requirement |
|---|---|---|
| Snapshot + coverage | fresh Restic snapshot AND `/home/claude/second-brain` in the backup set (restore/include-list) OR `--attest-backup-coverage`; recency alone insufficient | FR-004a, NFR-001 |
| Origin recoverability | clone HEAD commit present on `origin` (`kentonium3/second-brain`) | FR-004b, C-009 |
| Quiesce + no live process | `felix-core-digest` user timer stopped; no `summarize.py`/`log_action.py` running | FR-004c |
| inbox-prescan mtime | no top-level `agents/logs/inbox-prescan-*.md` newer than #656 cutover | FR-004e |

### Decommission target

- `/home/claude/second-brain` — git clone of `kentonium3/second-brain` (12M).
- Removal: wholesale `rm -rf`, no traversal/logging of `_private` (C-008).
- Post-state: path absent (`test ! -e`), not recreated within a full digest cycle (SC-003).

## State transitions (two entrypoints — FR-009)

**Phase 1 — `migrate-observation-logs.py` (non-destructive):**
```
DRY-RUN (default) ── plan, no mutation, exit 0
   │ --apply
   ▼
MIGRATE LOGS ── union-merge agents/logs/{agent}/*.jsonl → vault (temp+fsync+os.replace)
   │
   ▼
POST-CHECK ── vault writable by service user (append+remove temp jsonl) → exit 0
```
Verified over ≥1 clean digest cycle before Phase 2 is staged.

**Phase 2 — `decommission-observation-stray-tree.py` (destructive, gated):**
```
DRY-RUN (default) ── plan + precondition results, no mutation, exit 0
   │ --apply
   ▼
GATE ── snapshot+coverage ✓  origin ✓  quiesce+no-live-proc ✓  inbox-prescan-mtime ✓
   │        (any ✗ → ABORT, non-zero, nothing destructive)
   ▼
FINAL MERGE ── union-merge remaining source jsonl under quiesce (atomic)
   │
   ▼
DELETE ── root-only rm -rf /home/claude/second-brain  (no descendant walk; no _private)
   │
   ▼
RESTART + POST-CHECK ── restart timer; stray absent; vault ownership/mode  → exit 0
```

Re-running after completion is a convergent no-op (FR-005): logs already merged, tree already
absent → nothing to do, exit 0.

## Architecture-doc records touched (IC-04 / FR-006)

- `docs/design/architecture/data/service-inventory.json` → `felix-core-digest`: `input_path`,
  `output_path` (stale-fix), `exec_start` (`repos/` fix), remove `path_retention_note` +
  dependency note; `updated_by: 659`.
- `docs/design/architecture/data/data-flows.json` → `observation-digest`: log paths, remove
  `path_retention_note`; `updated_by: 659`.
- Markdown views regenerated to match.
