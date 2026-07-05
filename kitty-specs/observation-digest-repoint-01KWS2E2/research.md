# Research: Observation-Digest Log Repoint & Decommission

Phase 0 output. Each decision: what was chosen, why, and the alternative rejected.

## D1 — Mechanism for the absolute `log_dir` default

- **Decision**: A module-level absolute constant in `scripts/openclaw/observation/config.py`,
  e.g. `DEFAULT_AGENT_LOGS_DIR = Path("/home/kgale/second-brain/agents/logs")`, used as the
  `log_dir` default (replacing `Path.home()/second-brain/agents/logs`).
- **Rationale**: Matches the #656 migrator convention (`DEFAULT_VAULT_LOGS_DIR` = the same
  path), so the two migrations agree on the canonical location. Keeps `scripts/vault/paths.json`
  semantically scoped to **Obsidian-synced** vault folders (all under `notes/`), whereas
  `agents/logs` is deliberately a sibling of `notes/` and NOT synced (C-005). A module constant
  is the smallest change (DIRECTIVE_024 locality) and is trivially unit-testable.
- **Alternative rejected**: add a logical name `agent_logs` to `paths.json` resolved via
  `get_vault_path()`. Rejected because it overloads the vault-path registry with a non-synced,
  non-`notes/` path, blurring the "vault registry = Obsidian vault folders" boundary. The
  existing `output_dir` uses the registry only because `00-System` genuinely IS a synced
  `notes/` folder.

## D2 — New migrator vs. extend the #656 migrator

- **Decision**: NEW `scripts/deploy/migrate-observation-logs.py`, importing/reusing helpers
  from `scripts/deploy/migrate-inbox-state-and-logs.py` and `scripts/deploy/lib/`.
- **Rationale**: FR-008 + spec. The #656 migrator is inbox-specific (dedup state + prescan
  logs) and its header explicitly defers the observation tree + full decommission to #659. A
  separate, single-purpose migrator keeps each migration independently auditable and idempotent.
- **Reuse**: union-merge for overlapping per-day JSONL, atomic copy-before-cutover, the Tier-2
  Restic snapshot gate (`scripts/deploy/lib/snapshot.py::verify_restic_recent`), the structured
  `_emit` logger.
- **Alternative rejected**: parameterize the #656 script with a `--mode observation`. Rejected —
  conflates two one-time migrations with different sources/targets and a much more destructive
  final step (whole-tree removal), raising blast radius against DIRECTIVE_024.

## D3 — Decommission safety (irreversible whole-tree removal)

- **Decision**: A three-precondition gate before `rm -rf /home/claude/second-brain` (FR-004):
  1. **Fresh Restic snapshot** ≤24h (NFR-001, reuse the lib gate).
  2. **Tracked-content recoverability**: the stray tree is a clone of `kentonium3/second-brain`;
     verify the working tree is clean and its HEAD commit exists on `origin` (nothing unpushed
     that only lives here). If unverifiable → abort (C-009).
  3. **No active writer**: confirm the repointed `log_dir` is the deployed steady state and no
     file under the stray `agents/logs` has an mtime after the repoint cutover within a full
     15-min digest cycle. If a writer is still active → abort (FR-004).
- **`_private` handling**: the removal is a bulk `rm -rf`; the migrator MUST NOT enumerate,
  read, copy, or log any `_private` path (C-008). No inventory/verbosity pass walks the vault
  subtree. `_private` is deleted with the tree but never inspected (SC-007).
- **Rationale**: the tree is a second-brain clone containing private-growth content; deletion is
  authorized only under `DM-01KWS4F986PVHTJRSHZPQACDM7` (C-010). Recoverability + snapshot make
  the deletion reversible-in-practice for everything except intentionally-discarded runtime
  cruft; `_private` privacy is preserved by never touching it.
- **Alternative rejected**: file-by-file quarantine/inventory then delete (the richer #656-style
  convergence). Rejected because inventorying would necessarily walk `_private`, violating C-008.

## D4 — Digest output path

- **Decision**: No code change to `output_dir`; correct the stale arch docs only.
- **Evidence**: `config.py:41` resolves output via `get_vault_path("system")/agent-activity`;
  `felix-core-digest.service` passes no `--output-dir` override (verified). Actual output =
  `/home/kgale/second-brain/notes/00-System/agent-activity/Agent-Logs/`. The stray tree's
  `notes/00-System/agent-activity/Agent-Logs/` is frozen ~2026-06-01 — historical, confirming
  the code moved to the vault. Arch-doc `output_path` recording the stray path is stale (FR-006).

## D5 — Rebaseline / audited surface

- **Decision**: Rebaseline obligation = **Yes**, via the `deploy-pipeline` audited surface
  (`deploys/queued/*.yaml`). No systemd-unit edit (D1 removes the `HOME` dependency), so
  `systemd-user-units` is not triggered. felix-deployer's happy-path auto-rebaseline handles it;
  merge commit records the outcome (C-007).
- **Evidence**: `docs/design/architecture/data/audited-surfaces.json` — `deploy-pipeline`
  (`rebaseline_required: true`) matches `deploys/queued/*.yaml`; the observation `*.py` are not
  an audited surface.

## D6 — What actually gets migrated vs. removed-in-place

- **Migrate** (runtime, git-ignored, unique): `agents/logs/{agent}/*.jsonl` observation logs →
  vault log dir (union-merge). Live writers observed: `felix-admin-escalation` (2026-07-05),
  `felix-admin-habits` (2026-06-29), `felix-admin-capture`, `enrichment`, `felix-admin-tasker`.
- **Remove in place** (superseded or recoverable):
  - `agents/logs/inbox-prescan-*.md` — deployed `prescan.py` `DEFAULT_LOG_DIR` = `/home/kgale`
    (verified); historical copies here are superseded.
  - `agents/state/inbox-routing.jsonl` — superseded by #656 (`/data/services/openclaw/state/`).
  - `notes/00-System/agent-activity/Agent-Logs/` — old digest output, superseded.
  - `vault/Notes/…` — tracked in the clone; recoverable from `kentonium3/second-brain` origin.
- **Open verification for implement/deploy**: confirm the Restic backup set actually covers
  `/home/claude/second-brain` (or that GitHub origin + the vault migration together cover all
  non-disposable data) BEFORE the destructive step. The migrator asserts this precondition.

## D7 — Anomaly (now a hard pre-delete check, was non-blocking)

A 250-byte `inbox-prescan-2026-07-05.md` (mtime 02:00) exists in the stray tree while the
deployed `prescan.py` writes to `/home/kgale` (which also has the 2026-07-05 file). Likely a
stale-path remnant or a snapshot-log side-write. Per the post-plan Codex review it is NO LONGER
"non-blocking": Phase 2 aborts if any top-level `agents/logs/inbox-prescan-*.md` is newer than
the #656 cutover (FR-004e). Still flagged for the #656 close review.

## Post-plan Codex review — resolved findings (spec-kitty-review, 2026-07-05)

The mandatory post-plan Codex review found real gaps; all are folded into spec/plan/contract:

- **D8 — Two-phase staged rollout (Codex Critical 2 + Major 1).** The single migrate+delete
  manifest raced the 15-min timer (check-then-`rm`) and `apply.py` runs `[entrypoint, "--apply"]`
  only. Resolved: split into Phase 1 (repoint + non-destructive migrate) and Phase 2
  (decommission) as **two entrypoints + two manifests** (FR-009). Phase 2 quiesces the
  `felix-core-digest` user timer for a bounded window and confirms no `summarize.py`/`log_action.py`
  process before deleting.
- **D9 — Backup-coverage proof, not recency (Codex Critical 1).** `verify_restic_recent` only
  proves a backup log completed, not that `/home/claude/second-brain` is in the set; "HEAD on
  origin" does not cover gitignored/untracked unique data. Resolved: FR-004a now requires an
  explicit coverage proof (restore/include-list) OR `--attest-backup-coverage`; abort if
  unprovable (never inspect `_private` to prove it).
- **D10 — Underscore importable module (Codex Major 4).** Logic lives in
  `scripts/deploy/observation_migration.py` (importable); hyphenated `.py` files are thin
  executable wrappers. Fixes the `-m` vs script-path inconsistency.
- **D11 — Atomic merge (Codex Major 3).** #656's `_union_merge_jsonl_files` appends directly;
  a live-writer append could be missed then deleted. Resolved: temp+`fsync`+`os.replace`
  (NFR-005); the final decommission-phase merge runs under quiesce.
- **D12 — `_private` enforced at impl level (Codex Major 5).** C-008 now forbids
  `rglob`/`os.walk`/`git status --ignored`/path-echoing errors; only `agents/logs/*/*.jsonl` is
  globbed; deletion is root-only; errors name only `source_root`.
- **D13 — Vault-dir permissions (Codex Major 6).** C-011 specifies exact owner/group/mode for the
  vault log hierarchy and adds a service-user append+remove writability post-check.
- **Grounding confirmed by Codex**: `output_dir` already resolves to the vault; no systemd-unit
  edit needed.
