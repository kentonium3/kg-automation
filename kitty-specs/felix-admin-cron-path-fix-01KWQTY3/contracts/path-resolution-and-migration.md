# Contract: path resolution & migration

Behavioral contract for the path constants and the one-time migration. These are
the assertions the implementation and its tests must satisfy.

## C1 — cwd-independent import (E4 / FR-001, FR-002, NFR-002, SC-10)

- **Given** an agent subprocess launched by `openclaw-gateway.service` (with the
  `pythonpath.conf` drop-in active)
- **When** it runs `python3 -m scripts.<domain>.<helper>` from **any** working
  directory (repo root or otherwise)
- **Then** the `scripts` package resolves and the helper runs (no
  `ModuleNotFoundError`).
- **Authoritative acceptance (Codex #1 C1)**: `PYTHONPATH` is confirmed present
  inside a **real OpenClaw agent/cron subprocess** (payload prints
  `os.environ["PYTHONPATH"]` from a non-repo cwd) — an SSH login shell is NOT an
  acceptable proxy. This gate must pass before the cwd prose (C6) is removed.
- **Test**: unit-level, assert resolution does not read `os.getcwd()`; deploy-level,
  the in-agent env check above.

## C2 — state path resolution (E1, E2 / FR-004, FR-005, FR-010)

- `routing_log.DEFAULT_ROUTING_LOG_PATH` == `/data/services/openclaw/state/inbox-routing.jsonl`.
- `handle_clarification_state.STATE_PATH_DEFAULT` == `/data/services/openclaw/state/pending-calendar-clarifications.json`.
- The **calendar agent's inline `.jsonl` writer** (`felix-admin-calendar/AGENTS.md`,
  `main/AGENTS.md`, calendar `TOOLS.md`) resolves
  `/data/services/openclaw/state/pending-calendar-clarifications.jsonl` — path
  repoint only; the `.json`/`.jsonl` format duality is unchanged here (follow-up).
- **Independence**: with `HOME` monkeypatched to an arbitrary value and cwd
  changed, the resolved paths are unchanged (absolute, not `~`-derived).
- **Round-trip**: writer then reader over the new path yields the written entries;
  a missing file yields an empty result (fail-safe), never an exception.

## C2b — dedup import correctness (FR-011 / SC-8)

- `prescan.py` imports the routing-log reader via the **package-absolute** path
  (`from scripts.inbox.routing_log import RoutingLogReader`).
- **Test**: a full prescan run from a non-repo cwd (e.g. `/tmp`) with the guardrail
  active does **not** emit the "dedup-disabled mode" warning and consults the ledger.

## C2c — state dir ownership/modes (FR-012 / SC-9)

- `/data/services/openclaw/state/` exists as `claude:secondbrain`, mode `0750`.
- Migrated state files are `claude:secondbrain`, mode `0640`.
- Helper parent-dir creation MUST NOT set a more restrictive mode than the
  convention (fix `routing_log.py` `0700`; set explicit mode in
  `handle_clarification_state.py`).

## C3 — log path resolution (E3 / FR-006, FR-007)

- `prescan.DEFAULT_LOG_DIR` == `/home/kgale/second-brain/agents/logs`.
- No agent prompt or template references `~/second-brain` or
  `/home/claude/second-brain` for logs after the change; `AGENTS.md`,
  `AGENTS.md.tmpl`, `TOOLS.md`, `TOOLS.md.tmpl` agree on the vault path.
- **Test**: grep assertion in CI/test that no in-scope agent asset contains
  `/home/claude/second-brain` or a bare `~/second-brain` write target.

## C4 — no stray-dir writer (PR-5 / FR-008, FR-010, SC-5)

- Static: no module under `scripts/inbox/` **and no felix-admin agent prompt**
  (`AGENTS.md*`/`TOOLS.md*`, incl. the calendar inline `.jsonl` writer) resolves a
  write path under `/home/claude/second-brain` or a bare `~/second-brain` (the
  `_private/` boundary references are read-prohibitions, not writers, and are
  exempt).
- Runtime: after migration + decommission, a full inbox tick **and** a calendar
  clarification cycle do **not** recreate `/home/claude/second-brain`.

## C5 — migration entrypoint (FR-005, FR-008, FR-012, C-003)

- **Pre**: refuses to proceed unless a Restic snapshot ≤ 24h exists (or triggers
  one) — Tier-2 gate via `scripts/deploy/lib/snapshot`.
- **Action** (idempotent, atomic-before-cutover per H1):
  - Ensures `/data/services/openclaw/state/` exists as `claude:secondbrain` `0750`.
  - Copies present state file(s) (currently `inbox-routing.jsonl`; also any
    `pending-calendar-clarifications.*` if present) to the new path, **before**
    the repointed readers rely on it, and sets `claude:secondbrain` `0640`.
  - **Recursively** copies the stray `agents/logs/` tree (per-agent subdirs incl.)
    into `/home/kgale/second-brain/agents/logs/` without overwriting same-named
    canonical logs.
  - **Inventories** the entire stray tree and classifies every path; if any path is
    unclassified/uncopied, it **refuses** to remove the tree.
  - **Quarantine-renames** `/home/claude/second-brain` →
    `/home/claude/second-brain.quarantine-<ts>`; final delete only after the `post`
    checks pass (or is left for a later verified window).
- **Post**: asserts state file(s) exist non-empty at the new path with correct
  owner/group/mode; historical logs present in the vault; original stray path gone
  (or quarantined); nothing unclassified was dropped (size/count parity).
- **Idempotent**: re-running after success is a no-op that still passes `post`.
- **Dry-run**: `--dry-run` prints planned operations and mutates nothing (tested).

## C6 — sequencing (IC-01 before IC-04)

- The prose-removal change (dropping `cd …` / "Working dir" instructions) must not
  merge/deploy before the `PYTHONPATH` guardrail is live. Enforced by task
  dependency ordering, not by runtime code.
