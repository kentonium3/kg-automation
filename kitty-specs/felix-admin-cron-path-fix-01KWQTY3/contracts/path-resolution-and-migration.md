# Contract: path resolution & migration

Behavioral contract for the path constants and the one-time migration. These are
the assertions the implementation and its tests must satisfy.

## C1 — cwd-independent import (E4 / FR-001, FR-002, NFR-002)

- **Given** an agent subprocess launched by `openclaw-gateway.service`
- **When** it runs `python3 -m scripts.<domain>.<helper>` from **any** working
  directory (repo root or otherwise)
- **Then** the `scripts` package resolves and the helper runs (no
  `ModuleNotFoundError`).
- **Test**: invoke a representative helper (`scripts.inbox.prescan --self-check`
  or equivalent) with `cwd` set to (a) the repo root and (b) a non-repo dir
  (e.g. `/tmp`), with `PYTHONPATH=/home/claude/kg-automation` in the environment;
  both exit 0. Unit-level: assert resolution does not read `os.getcwd()`.

## C2 — state path resolution (E1, E2 / FR-004, FR-005)

- `routing_log.DEFAULT_ROUTING_LOG_PATH` == `/data/services/openclaw/state/inbox-routing.jsonl`.
- `handle_clarification_state.STATE_PATH_DEFAULT` == `/data/services/openclaw/state/pending-calendar-clarifications.json`.
- **Independence**: with `HOME` monkeypatched to an arbitrary value and cwd
  changed, the resolved paths are unchanged (absolute, not `~`-derived).
- **Round-trip**: writer then reader over the new path yields the written entries;
  a missing file yields an empty result (fail-safe), never an exception.

## C3 — log path resolution (E3 / FR-006, FR-007)

- `prescan.DEFAULT_LOG_DIR` == `/home/kgale/second-brain/agents/logs`.
- No agent prompt or template references `~/second-brain` or
  `/home/claude/second-brain` for logs after the change; `AGENTS.md`,
  `AGENTS.md.tmpl`, `TOOLS.md`, `TOOLS.md.tmpl` agree on the vault path.
- **Test**: grep assertion in CI/test that no in-scope agent asset contains
  `/home/claude/second-brain` or a bare `~/second-brain` write target.

## C4 — no stray-dir writer (PR-5 / FR-008, SC-5)

- Static: no module under `scripts/inbox/` resolves a write path under
  `/home/claude/second-brain`.
- Runtime: after migration + decommission, a full inbox tick and a calendar
  clarification cycle do **not** recreate `/home/claude/second-brain`.

## C5 — migration entrypoint (FR-005, FR-008, C-003)

- **Pre**: refuses to proceed unless a Restic snapshot ≤ 24h exists (or triggers
  one) — Tier-2 gate via `scripts/deploy/lib/snapshot`.
- **Action** (idempotent): copies `inbox-routing.jsonl` and
  `pending-calendar-clarifications.json` to `/data/services/openclaw/state/`
  (preserving contents); copies any `agents/logs/*.md` under
  `/home/claude/second-brain/` into `/home/kgale/second-brain/agents/logs/`
  without overwriting a same-named canonical log; then removes
  `/home/claude/second-brain/`.
- **Post**: asserts both state files exist and are non-empty at the new path and
  that `/home/claude/second-brain` no longer exists.
- **Idempotent**: re-running after success is a no-op that still passes `post`.
- **Dry-run**: `--dry-run` prints the planned operations and mutates nothing
  (tested).

## C6 — sequencing (IC-01 before IC-04)

- The prose-removal change (dropping `cd …` / "Working dir" instructions) must not
  merge/deploy before the `PYTHONPATH` guardrail is live. Enforced by task
  dependency ordering, not by runtime code.
