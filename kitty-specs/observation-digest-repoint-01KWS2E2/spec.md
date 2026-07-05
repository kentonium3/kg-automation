# Feature Specification: Observation-Digest Log Repoint & Decommission

**Mission**: observation-digest-repoint-01KWS2E2
**Type**: software-dev
**Source issue**: kentonium3/kg-automation#659 (fast-follow to #656)
**Status**: Draft

## Overview

Felix's **observation-digest subsystem** (`felix-core-digest`, feature F014) runs on
office2 as a systemd **user** timer (user `claude`, every 15 minutes). On each tick it
writes raw per-agent activity logs (JSONL) and produces a human-readable digest.

The raw logs currently land in a **stray tree** — `/home/claude/second-brain/agents/logs/`
— on the `claude` service account, outside Kent's real account and outside the backed-up
vault. A prior fix (#656) relocated the *inbox* subsystem's state and logs off that stray
tree but deliberately **narrowed** its decommission, because this observation writer still
targets it. This mission finishes the job: repoint the remaining writer to the backed-up
vault-account path, migrate the historical logs, and fully **decommission** the stray tree.

### Grounding facts (verified against deployed code, 2026-07-05)

- The **only** runtime path still resolving onto the stray tree is the raw **input log
  dir**: `scripts/openclaw/observation/config.py:40` defaults `log_dir` to
  `Path.home()/second-brain/agents/logs`, which resolves to `/home/claude/…` because the
  deployed unit `felix-core-digest.service` sets `Environment=HOME=/home/claude` and passes
  no `--log-dir` override.
- The **digest output** dir (`config.py:41`) already resolves through the vault registry to
  `/home/kgale/second-brain/notes/00-System/agent-activity/Agent-Logs/` — **already synced.**
  The architecture docs recording the output at `/home/claude/second-brain/notes/Agent-Logs/`
  are **stale**, not a live defect.
- No systemd unit edit is required: making the `log_dir` default an absolute, registry-resolved
  path removes the `HOME` dependency.

### What the stray tree actually contains (verified on office2, 2026-07-05)

`/home/claude/second-brain` is **not** a bare log directory. It is a **git clone of
`kentonium3/second-brain`** (origin `git@github.com:kentonium3/second-brain.git`, single
"Initial commit", created 2026-04-04; 12M total). Its contents:

| Path | Nature | Disposition |
|---|---|---|
| `agents/logs/{agent}/*.jsonl` | observation raw logs — **live** (`felix-admin-escalation` written 2026-07-05); git-ignored runtime | **migrate** to vault, then remove with tree |
| `agents/logs/inbox-prescan-*.md` | historical inbox prescan logs; deployed `prescan.py` now writes to `/home/kgale` | remove with tree (superseded) |
| `agents/state/inbox-routing.jsonl` | old inbox dedup state | remove with tree (superseded by #656 → `/data`) |
| `notes/00-System/agent-activity/Agent-Logs/` | old digest output, frozen ~2026-06-01 | remove with tree (superseded; code now writes vault) |
| `vault/Notes/…` (8.1M) | March-2026 Obsidian vault snapshot (tracked in the clone) | remove with tree; recoverable via GitHub origin |
| `vault/02-Growth/_private/` | private-growth content (per `.gitignore`) | **NEVER read/log**; removed wholesale with the tree, never inspected |

**Governance decision (recorded `DM-01KWS4F986PVHTJRSHZPQACDM7`):** deleting this tree crosses
the second-brain boundary (for the `claude` account, `/home/claude/second-brain` *is*
`~/second-brain`). Kent **explicitly authorized** the full decommission for this specific tree,
overriding the boundary here only, with the guards in FR-003/FR-004/C-008/C-009.

## Domain Language

| Canonical term | Meaning | Avoid |
|---|---|---|
| **stray tree** | `/home/claude/second-brain` — directory on the `claude` service account, not backed up, to be decommissioned | bare "second-brain" |
| **vault** | `/home/kgale/second-brain` — Kent's account; the Obsidian **vault** proper is its `notes/` subtree | bare "second-brain" |
| **vault log dir** | `/home/kgale/second-brain/agents/logs` — sibling of `notes/`; backed-up account, intentionally **not** Obsidian-synced | — |
| **raw logs** | per-action JSONL at `agents/logs/{agent}/YYYY-MM-DD.jsonl` — forensic, high-volume | "logs" (ambiguous) |
| **digest** | human-readable Markdown summary under `…/00-System/agent-activity/Agent-Logs/` — already vault-synced | — |

## User Scenarios & Testing

The "user" here is the **operator** (Kent) and the automated **felix-deployer** pipeline;
there is no human-facing UI.

### Primary scenario — repointed writer

1. The mission merges; felix-deployer pulls `main` and applies the queued migration manifest.
2. On the next 15-minute `felix-core-digest.timer` tick, `log_action.py` writes the agent's
   activity log to `/home/kgale/second-brain/agents/logs/{agent}/YYYY-MM-DD.jsonl`.
3. Nothing is written under `/home/claude/second-brain`.
4. The digest continues to be produced at the unchanged, already-synced vault output path.

### Migration scenario — two-phase (FR-009)

**Phase 1 — repoint + migrate (non-destructive):**
1. `config.py` repoint merges; felix-deployer applies the Phase-1 manifest (Tier-2 snapshot gate).
2. The migrate entrypoint union-merges runtime `agents/logs/{agent}/*.jsonl` from the stray tree
   into the vault log dir (temp+fsync+`os.replace`; no entry lost/duplicated). It does NOT delete.
3. Operator/verification confirms ≥1 clean digest cycle: new logs appear under `/home/kgale`,
   none new under `/home/claude/second-brain`.

**Phase 2 — decommission (destructive, separate deploy):**
4. The Phase-2 manifest runs the decommission entrypoint: verify FR-004 preconditions
   (snapshot + **coverage proof**, origin recoverability, inbox-prescan mtime check).
5. Quiesce: stop the `felix-core-digest` user timer for a bounded window; confirm no
   `summarize.py`/`log_action.py` running; final union-merge of any remaining source JSONL.
6. Root-only `rm -rf /home/claude/second-brain` — no `_private` traversal (C-008); restart timer.
7. Post-checks confirm the stray tree is absent and the vault dir ownership/mode is correct.

### Exception & edge cases

- **Concurrent cron write during Phase-1 migrate** → harmless: Phase 1 is non-destructive; the
  repoint means new writes go to the vault, and any straggler source appends are caught by the
  next cycle and the Phase-2 final merge under quiesce.
- **Live `summarize.py`/`log_action.py` at decommission** → Phase 2 quiesces the timer and checks
  for a running process; if one is active it MUST abort before removal (fail-safe).
- **Restic snapshot missing or backup coverage of the source root unprovable** → abort; do not
  delete. Recency alone does not satisfy FR-004(a).
- **`inbox-prescan-*.md` newer than the #656 cutover** → abort / require operator disposition
  (evidence of a lingering writer into the tree).
- **Re-run after completion** → idempotent no-op (convergent).
- **Interrupted migration** → temp+`os.replace` keeps the destination consistent and the source
  intact until the copy is verified; safe to resume.

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | The observation-digest raw `log_dir` default MUST resolve to an absolute, backed-up vault-account path (`/home/kgale/second-brain/agents/logs`) independent of `HOME`, so that under the deployed service account raw logs no longer land on the stray tree. | Draft |
| FR-002 | Existing historical raw logs under the stray tree MUST be migrated to the vault log dir with no entry lost or duplicated (union-merge of overlapping per-day JSONL files). | Draft |
| FR-003 | Decommission removes the entire stray tree (`/home/claude/second-brain`) via a **root-only** `rm -rf` of the source root. The implementation MUST NOT enumerate, walk (`rglob`/`os.walk`), `git status --ignored`, read, copy, or log any descendant path — in particular any `_private` path. Only runtime observation logs are migrated first (FR-002); all other content is removed in place without inspection. | Draft |
| FR-004 | Decommission MUST be preceded by ALL of, else ABORT before any destructive action: (a) a fresh Restic snapshot AND proof that `/home/claude/second-brain` is actually **covered** by the backup (include-list/restore-list check) OR an explicit operator attestation accepted by the migrator — recency alone is insufficient; (b) verification that the clone's tracked content is present on origin (`kentonium3/second-brain`); (c) the repointed `log_dir` is the deployed steady state, the `felix-core-digest` user timer is **quiesced** (stopped) for a bounded window, and no `summarize.py`/`log_action.py` process is running; (d) a final union-merge of any remaining source `agents/logs/{agent}/*.jsonl` is performed under quiesce; (e) no top-level `agents/logs/inbox-prescan-*.md` has an mtime newer than the #656 cutover (else abort / require operator disposition). | Draft |
| FR-009 | Delivery MUST be a **two-phase staged rollout**: Phase 1 deploys the `config.py` repoint + a non-destructive log migration and is verified over ≥1 clean digest cycle (logs land only under `/home/kgale`); Phase 2 is a **separate** decommission deploy (quiesce → final merge → coverage-gated root-only delete → restart timer). The two phases MUST be independent manifests/entrypoints so Phase 2 runs only after Phase 1 is confirmed. | Draft |
| FR-005 | The migration + decommission MUST be idempotent and convergent (safe to re-run; completed state re-runs as a no-op). | Draft |
| FR-006 | Architecture docs MUST be corrected: `service-inventory.json` (`felix-core-digest`) and `data-flows.json` (`observation-digest`) repoint the log path, remove the `#659` `path_retention_note`s, correct the stale `output_path`, and correct the `exec_start` `repos/` discrepancy; markdown views regenerated to match. `updated_by` set to `659`. | Draft |
| FR-007 | Docstrings referencing `~/second-brain/agents/logs/` in `config.py`, `log_action.py`, and `summarize.py` MUST be updated to the canonical path. | Draft |
| FR-008 | Deployment MUST be expressed as a `deploys/queued/NNNN-*.yaml` manifest consumed by felix-deployer, reusing the shared deploy library and the #656 migrator machinery. | Draft |

### Non-Functional Requirements

| ID | Requirement | Threshold / Measure | Status |
|---|---|---|---|
| NFR-001 | Any destructive migration step MUST be gated on a recent Restic backup. | Snapshot age ≤ 24h at gate time (Tier-2). | Draft |
| NFR-002 | The digest subsystem MUST keep running on its existing schedule with no downtime introduced. | No missed 15-minute timer cycle; `felix-core-digest.timer` active post-deploy. | Draft |
| NFR-003 | Zero raw-log data loss during migration. | Post-migration union entry count ≥ union(source, target) pre-migration; verified by count/dedup check. | Draft |
| NFR-004 | Each migrator/decommission deploy entrypoint MUST survive felix-deployer's shebang/dry-run invocation. | Regression test asserts `+x` bit, `sys.path` shim present, and `--dry-run` exits 0 with no side effects, for BOTH entrypoints. | Draft |
| NFR-005 | JSONL union-merge MUST be crash- and writer-safe. | Merge writes to a temp file, `fsync`s, then `os.replace` onto the destination (atomic); the final decommission-phase merge runs under timer quiesce so no concurrent append can be missed. | Draft |

### Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | No change to `felix-core-digest.service` / `.timer` unit files or the 15-minute schedule. | Draft |
| C-002 | The digest **output** directory (already vault-synced at `…/00-System/agent-activity/Agent-Logs/`) MUST remain unchanged. | Draft |
| C-003 | The #490 `tick.py` signal-extraction path and its `/data/services/openclaw/felix-core-digest-signals/` state MUST remain unchanged. | Draft |
| C-004 | Inbox writers/state relocated in #656 MUST remain unchanged. | Draft |
| C-005 | Raw JSONL logs MUST NOT be placed inside the Obsidian-synced `notes/` tree; they stay at `agents/logs` (forensic, high-volume). | Draft |
| C-006 | All office2 changes MUST flow through the `deploys/queued` manifest pipeline; no out-of-band changes on office2. | Draft |
| C-007 | The #557 rebaseline obligation is triggered by the `deploy-pipeline` audited surface; the merge commit MUST record the rebaseline outcome per `security-baseline-ops.md`. | Draft |
| C-008 | No agent or script in this mission may read, copy, reference, or log any `_private` path. Implementation-level constraints (enforced, not just intent): the decommission MUST glob ONLY `source_root/agents/logs/*/*.jsonl` for migration; MUST NOT `rglob`/`os.walk`/inventory the tree, MUST NOT run `git status --ignored`, MUST NOT use per-file delete callbacks that echo child paths; deletion is a single root-level operation; any emitted error may name only `source_root`, never a descendant. | Draft |
| C-011 | The vault log dir hierarchy under `/home/kgale/second-brain/agents/logs/` MUST be writable by the deploying service user (`claude`): exact owner/group/mode specified for `agents/`, `agents/logs/`, per-agent subdirs, and JSONL files; a post-check MUST confirm the service user can append and remove a temp JSONL under the target. | Draft |
| C-009 | The decommission is authorized only because the tracked content is a clone of `kentonium3/second-brain` recoverable from origin, and the runtime observation logs are migrated first. If either recoverability precondition cannot be verified, the destructive step MUST NOT run (abort and surface). | Draft |
| C-010 | The full tree deletion crosses the second-brain boundary and proceeds ONLY under Kent's explicit authorization recorded in `DM-01KWS4F986PVHTJRSHZPQACDM7`; it is not a generalizable pattern. | Draft |

## Success Criteria

| ID | Criterion (measurable, outcome-focused) |
|---|---|
| SC-001 | After one post-deploy timer cycle, new raw JSONL exists under `/home/kgale/second-brain/agents/logs/{agent}/` and **zero** new files appear under `/home/claude/second-brain`. |
| SC-002 | All historical raw logs are preserved (union-merge invariant holds; no entry lost). |
| SC-003 | `/home/claude/second-brain` does not exist on office2 and is not recreated within a full 15-minute cycle (`test ! -e`). |
| SC-004 | #656 SC-5's invariant — "no writer targets `/home/claude/second-brain`" — is fully satisfied across both the inbox and observation subsystems. |
| SC-005 | `service-inventory.json`, `data-flows.json`, and their markdown views reflect reality: vault log path, no `#659` retention notes, corrected `output_path` and `exec_start`. |
| SC-006 | Rebaseline recorded on merge; post-change verification passes; no felix-deployer failure ntfy alert. |
| SC-007 | The decommission touched no `_private` path (no descendant path appears in any migrator output, log, or emitted record); ALL preconditions (snapshot **+ coverage proof**, origin recoverability, timer quiesce + no live process, inbox-prescan mtime check) were verified before deletion. |
| SC-008 | Phase 1 ran and was verified over ≥1 clean digest cycle BEFORE Phase 2 executed; the two phases were independent deploys. If Phase 1 verification had failed, Phase 2 would not have run. |

## Key Entities

- **felix-core-digest (F014)** — systemd user timer + oneshot service (user `claude`, office2); runs `summarize.py` then `tick.py` every 15 min.
- **Raw agent-activity logs** — per-agent JSONL at `agents/logs/{agent}/YYYY-MM-DD.jsonl`; written by `log_action.py`, read by `summarize.py`.
- **Stray tree** — `/home/claude/second-brain`: a stale **git clone of `kentonium3/second-brain`** (March vault snapshot + old digest/state + live observation logs + `_private`); to be decommissioned wholesale after runtime-log migration.
- **Vault log dir** — `/home/kgale/second-brain/agents/logs` (backed-up account; sibling of `notes/`).
- **Vault path registry** — `scripts/vault/paths.json` + `scripts/vault/resolver.py`.
- **One-time migrator** — new deploy helper under `scripts/deploy/` (sibling of `migrate-inbox-state-and-logs.py`), reusing its union-merge / snapshot-gate / atomic-copy machinery.
- **Deploy manifest** — `deploys/queued/NNNN-*.yaml` consumed by felix-deployer.

## Assumptions

- The digest output already resolves to the synced vault (`config.py:41`); the arch-doc `output_path` is stale and is corrected here, not a live bug.
- felix-deployer's happy-path auto-rebaseline satisfies the #557 obligation for the `deploy-pipeline` surface; the merge commit records the outcome.
- No systemd unit edit is needed — making the `log_dir` default absolute/registry-resolved removes the `HOME=/home/claude` dependency (keeps the audited-surface footprint to the manifest only).
- The migrator's SOURCE root (`/home/claude/second-brain`) is intentionally hardcoded/parameterized as the stray tree; only the default is repointed in `config.py`.
- The stray tree is a git clone of `kentonium3/second-brain`; its **tracked** content (incl. the March vault snapshot) is recoverable from origin, so wholesale deletion is safe once runtime logs are migrated and the snapshot gate passes.
- Full deletion is authorized by Kent per `DM-01KWS4F986PVHTJRSHZPQACDM7` (second-brain boundary overridden for this tree only). `_private` content is deleted with the tree but never read, copied, or logged (C-008).

## Out of Scope

- The inbox state/log relocation and inbox-writer fixes (delivered in #656).
- Making raw JSONL logs Obsidian-synced (intentionally not done — forensic, high-volume).
- The broader #658 fleet-wide runtime-environment-assumption audit (this mission is the concrete observation-digest instance of that class).

## Dependencies

- #656 merged to `main` (merge `c0ffcbb8`) — prerequisite (done).
- Shared deploy library `scripts/deploy/lib/` and the felix-deployer pipeline.
- Reusable #656 migrator `scripts/deploy/migrate-inbox-state-and-logs.py`.
