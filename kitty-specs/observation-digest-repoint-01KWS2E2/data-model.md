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
| Snapshot freshness | Restic snapshot ≤24h (`lib/snapshot.py`) | NFR-001 |
| Tracked-content recoverability | stray tree working dir clean AND HEAD present on `origin` (`kentonium3/second-brain`) | C-009 |
| Repoint deployed | resolved `log_dir` == vault path; no stray-tree write after cutover within one 15-min cycle | FR-004 |

### Decommission target

- `/home/claude/second-brain` — git clone of `kentonium3/second-brain` (12M).
- Removal: wholesale `rm -rf`, no traversal/logging of `_private` (C-008).
- Post-state: path absent (`test ! -e`), not recreated within a full digest cycle (SC-003).

## State transitions (migrator)

```
DRY-RUN (default)  ── report planned actions, no mutation, exit 0
      │  --apply
      ▼
MIGRATE LOGS  ── union-merge agents/logs/{agent}/*.jsonl → vault (copy-before-cutover)
      │
      ▼
VERIFY PRECONDITIONS ── snapshot ✓  recoverability ✓  no-writer ✓   (any ✗ → ABORT, non-zero)
      │
      ▼
DECOMMISSION  ── rm -rf /home/claude/second-brain  (no _private traversal)
      │
      ▼
POST-CHECK  ── stray absent; vault ownership/mode correct  → exit 0
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
