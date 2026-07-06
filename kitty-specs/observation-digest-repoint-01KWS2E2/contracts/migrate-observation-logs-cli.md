# Contract: two-phase migrate + decommission entrypoints + deploy manifests

No REST/GraphQL surface. Contracts = (1) an importable logic module, (2) two thin executable
entrypoints (Phase 1 migrate, Phase 2 decommission), and (3) two deploy manifests. This shape is
required because `scripts/deploy/lib/apply.py` invokes an entrypoint as `[entrypoint, "--apply"]`
only (no extra args), so staged behavior MUST be expressed as separate entrypoints — not flags.

## Importable module (fixes hyphen/underscore inconsistency — Codex Major 4)

`scripts/deploy/observation_migration.py` — underscore name, importable as
`scripts.deploy.observation_migration`. Holds all logic (union-merge, precondition checks,
quiesce, delete). Unit-tested directly via `import`. The two hyphenated `.py` files below are
**thin executable wrappers** (shebang + `+x` + `sys.path` shim) that call into this module.

## Phase 1 entrypoint — migrate only (non-destructive)

`scripts/deploy/migrate-observation-logs.py`

| Flag | Default | Meaning |
|---|---|---|
| `--dry-run` | **on** | Print JSON plan; no mutation; exit 0. |
| `--apply` | — | Union-merge `agents/logs/{agent}/*.jsonl` (source → vault). **Never deletes.** |
| `--source-root` | `/home/claude/second-brain` | Stray-tree root. |
| `--vault-logs-dir` | `/home/kgale/second-brain/agents/logs` | Migration target. |

- Union-merge is **atomic**: write merged file to a temp path, `fsync`, `os.replace` onto the
  destination (NFR-005). Idempotent; convergent re-run = no-op.
- Globs ONLY `source_root/agents/logs/*/*.jsonl`. No `rglob`/`os.walk`/`git status --ignored` (C-008).
- Post-check: vault dir writable by service user `claude` (append+remove a temp JSONL) (C-011).

## Phase 2 entrypoint — decommission (destructive, separate deploy)

`scripts/deploy/decommission-observation-stray-tree.py`

| Flag | Default | Meaning |
|---|---|---|
| `--dry-run` | **on** | Print JSON plan + precondition results; no mutation; exit 0. |
| `--apply` | — | Run precondition gate → quiesce → final merge → root-only delete → restart. |
| `--source-root` | `/home/claude/second-brain` | Tree to remove. |
| `--vault-logs-dir` | `/home/kgale/second-brain/agents/logs` | Final-merge target. |
| `--attest-backup-coverage` | off | Operator attestation accepted in lieu of an automated Restic include-list proof (FR-004a). |

### Precondition gate (ALL must pass, else exit non-zero, nothing destructive) — FR-004

1. **Snapshot + coverage**: fresh Restic snapshot AND proof `/home/claude/second-brain` is in the
   backup set (restore-list/include check) OR `--attest-backup-coverage`. Recency alone fails.
2. **Origin recoverability**: the clone's HEAD commit is present on `origin`
   (`kentonium3/second-brain`).
3. **Quiesce**: stop the `felix-core-digest` user timer; confirm no `summarize.py`/`log_action.py`
   process running (bounded wait); if a writer is active → abort.
4. **inbox-prescan mtime**: no top-level `agents/logs/inbox-prescan-*.md` newer than the #656
   cutover; else abort / require operator disposition (Codex Minor).

### Destructive sequence (only after gate passes)

1. Final union-merge of any remaining `agents/logs/{agent}/*.jsonl` (atomic; under quiesce).
2. **Root-only** `rm -rf <source-root>` — a single root-level operation. MUST NOT enumerate,
   walk, `git status --ignored`, or emit any descendant path. Errors may name only `<source-root>`.
3. Restart the `felix-core-digest` timer; post-check `test ! -e <source-root>`.

## Exit codes (both entrypoints)

| Code | Meaning |
|---|---|
| 0 | Success (dry-run, applied, or convergent no-op) |
| non-zero | Precondition failed / error / abort-before-delete (nothing destructive ran) |

## stdout / stderr

- stdout: one JSON object (plan in dry-run; result summary in apply). Never a `_private` or any
  descendant path.
- stderr: structured `_emit` progress + errors; error strings name only `source_root`.

## Deploy manifests (two, staged — FR-009)

- Phase 1: `deploys/queued/NNNN-migrate-observation-logs.yaml` — `tier: 2`; `pre` Restic snapshot
  gate; `apply` runs `migrate-observation-logs.py --apply`; `post` vault writability; audited
  surface (deploy-pipeline) → auto-rebaseline. **No deletion.**
- Phase 2: `deploys/queued/MMMM-decommission-observation-stray-tree.yaml` — queued only AFTER
  Phase 1 is verified over ≥1 clean cycle; `tier: 2`; `pre` snapshot gate; `apply` runs
  `decommission-observation-stray-tree.py --apply`; `post` `test ! -e /home/claude/second-brain`.

## Regression test contract (NFR-004 / C-008)

For BOTH executable entrypoints:
- file mode has the executable bit; `sys.path` shim present;
- script-path `--dry-run` via subprocess exits 0 and mutates nothing;
- the JSON plan/output contains no `_private` and no descendant path (only `source_root`);
- (module test) union-merge uses temp+`os.replace` and preserves the union of source+dest lines.
