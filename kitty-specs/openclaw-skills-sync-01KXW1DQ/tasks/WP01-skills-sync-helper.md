---
work_package_id: WP01
title: Skills sync helper (foundation)
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-007
- FR-010
- FR-011
- FR-015
- FR-016
- NFR-001
- NFR-002
- NFR-004
- NFR-005
- NFR-006
tracker_refs: []
planning_base_branch: feat/openclaw-skills-sync
merge_target_branch: feat/openclaw-skills-sync
branch_strategy: Planning artifacts for this mission were generated on feat/openclaw-skills-sync. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/openclaw-skills-sync unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
agent: "claude"
shell_pid: "84204"
shell_pid_created_at: "1784428902.119846"
history:
- '2026-07-19: authored by /spec-kitty.tasks'
agent_profile: python-pedro
authoritative_surface: scripts/openclaw/deploy/deploy_agent_skills.py
create_intent:
- scripts/openclaw/deploy/deploy_agent_skills.py
- tests/openclaw/deploy/test_deploy_agent_skills.py
execution_mode: code_change
owned_files:
- scripts/openclaw/deploy/deploy_agent_skills.py
- tests/openclaw/deploy/test_deploy_agent_skills.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned profile:

```
/ad-hoc-profile-load python-pedro
```

Adopt its identity, boundaries, and TDD discipline for the whole WP.

## Objective

Build `scripts/openclaw/deploy/deploy_agent_skills.py` — the deterministic sync that keeps the six
OpenClaw skills faithful from repo → office2. It mirrors the proven `deploy_agent_prompts.py`
(read it first: `scripts/openclaw/deploy/deploy_agent_prompts.py`) but for the **skills** scope
model. Reuse the shared primitives; do **not** modify `deploy_agent_prompts.py`.

**Read before coding**: `deploy_agent_prompts.py` (the reference), `scripts/deploy/lib/gitsync.py`,
`deploylock.py`, `health.py`, `scripts/common/alert_bus/{__init__,model}.py`, and this mission's
`data-model.md` (record shapes + exit contract + invariants) and `research.md` (D-1, D-3, D-6).

## Key facts (from research/probing — do not re-derive)

- **Source**: `<repo_root>/scripts/openclaw/skills/<skill>/SKILL.md`. **Dest**:
  `/home/claude/.openclaw/skills/<skill>/SKILL.md`. Six skills today, one `SKILL.md` each.
- **Reuse as-is** (import): `scripts.deploy.lib.gitsync.advance_checkout`,
  `scripts.deploy.lib.deploylock.deploylock` / `LockUnavailable`, `scripts.deploy.lib.health.record`.
- **Duplicate locally** (two call sites is within the rule-of-three; do NOT refactor the prompt
  module): `compute_md5`, `atomic_copy` — copy their bodies from `deploy_agent_prompts.py`.
- **Alert bus**: `scripts.common.alert_bus.emit(Alert(...)) -> AlertResult`. `AlertResult` exposes
  **`.ok`** (NOT `.delivered` — using `.delivered` raises AttributeError, is swallowed by
  `health.record`, and silently never alerts). `Alert` requires `source, severity, title,
  description` (+ optional `action`, `details`).
- **Constants**: audit `AUDIT_PATH = /data/services/openclaw/deploy/agent-skill-sync.jsonl`;
  health state `/data/services/openclaw/deploy/agent-skill-sync-git-health.json` (+ sibling
  `agent-skill-sync-copy-health.json`); freshness `/data/services/openclaw/deploy/skills-last-tick.json`;
  skills base `/home/claude/.openclaw/skills`; repo root default `/home/claude/kg-automation`.
- **Invocation form**: `python3 -m scripts.openclaw.deploy.deploy_agent_skills` (the `-m` form — the
  module imports `scripts.*` siblings; script-path invocation fails ModuleNotFoundError, #668).

### Subtask T001 — `compute_md5` + `atomic_copy`

**Purpose**: The two generic file primitives, copied from `deploy_agent_prompts.py`.

- `compute_md5(path) -> str`: 64KB chunked hex MD5 (verbatim from the reference).
- `atomic_copy(src, dst)`: temp-write + `fsync` + preserve dst mode if it existed + `os.replace`;
  unlink temp + re-raise on exception (verbatim from the reference).
- **FR-016**: before the copy, the caller creates `dst.parent` (`mkdir(parents=True, exist_ok=True)`)
  — mirror `sync_agent`'s `agent.workspace.mkdir(...)`. Put the mkdir in `sync_skill` (T003), not in
  `atomic_copy`, to match the reference's separation.

### Subtask T002 — Skill scope enumerator

**Purpose**: Derive scope from the repo skills dir (FR-011) — no service-inventory dependency.

- `iter_skills(repo_root, skill_filter=None) -> Iterator[SkillSyncUnit]` where
  `SkillSyncUnit = (skill, source: Path, dest: Path)`.
- Iterate `sorted((repo_root/'scripts/openclaw/skills').iterdir())`; for each directory:
  - If it contains `SKILL.md` → emit a unit (`dest = SKILLS_BASE/<skill>/SKILL.md`).
  - **Multi-file guard (FR-015)**: if the dir contains any file besides `SKILL.md`, still emit the
    unit for `SKILL.md` but flag it so `sync_skill`/caller writes a `warning` audit record naming the
    extra file(s). (Return the extra-files info on the unit or via a companion signal.)
  - If it contains **no** `SKILL.md` → do not emit; the caller writes a `warning` audit record.
- `--skill <name>` restricts to one; an unknown name is a validation error (exit 3, see T004).
- Ignore `*.backup*` when assessing "other files" (a `SKILL.md.backup` is not a multi-file trigger).

### Subtask T003 — `sync_skill`

**Purpose**: Sync one unit — the copy-only, backup-ignoring, audited core.

- Compute `src_md5`; `dst_md5_before` if dest exists (else None → treated as drift/`absent`).
- If drift and not dry-run: `dst.parent.mkdir(parents=True, exist_ok=True)` (FR-016) → `atomic_copy`
  → append a `copy` audit record (`skill, filename, src_md5, dst_md5_before, dst_path`). On `OSError`
  → `error` record + count errored.
- If no drift and not dry-run: `skip` audit record.
- If dry-run: append `DRIFT <skill> SKILL.md src_md5=… dst_md5=<…|absent>` to the dry-run sink; no
  writes, no audit.
- **Copy-only (FR-004)**: never delete anything on dest. **Backup-ignore (FR-010)**: `*.backup*` is
  never a source or dest target.
- Emit the multi-file `warning` (FR-015) from here or the caller, once per skill.
- Return per-skill counts `(copied, skipped, errored, warned)`.

### Subtask T004 — `run_tick` orchestration + CLI

**Purpose**: One tick end-to-end, mirroring the reference's locked-tick structure and exit codes.

- `parse_args`: `--dry-run`, `--skill SLUG`.
- `_validate(repo_root, skill_filter)`: missing `.git/` or missing `scripts/openclaw/skills/` →
  exit-3 error string to stderr; unknown `--skill` → exit 3.
- **Dry-run path**: read-only, no lock; enumerate + `sync_skill(dry_run=True)`; print DRIFT lines;
  return 0.
- **Real tick**: hold `deploylock()` across `advance_checkout` (via a `git_pull`-style wrapper like
  the reference) **and** the per-skill copy loop. On `LockUnavailable` → `git_pull_skipped` audit +
  return 0 (benign defer). On git advance failure → `git_pull_failed` audit + `tick_summary(exit=2)`
  + return 2. Else iterate skills, write `tick_summary` (`skills_processed, files_copied,
  files_skipped, files_errored, git_head_after_pull, exit_code, duration_ms`), return 1 if any
  errored else 0.
- **Freshness (NFR)**: in a `finally`, `write_last_tick(AUDIT_PATH.parent, status=…)` with
  `exit_code=0` always (timer-liveness pointer; `completed_at_utc`), mirroring the reference. Filename
  `skills-last-tick.json`.
- Exit codes: 0 success/no-op/defer/dry-run · 1 partial copy failure · 2 git advance failed · 3
  validation. `main()` runs one tick from `Path.cwd()`.

### Subtask T005 — Health watermarks (streak-dedup alerts)

**Purpose**: A persistent git-advance OR copy failure fires exactly one ntfy alert per streak.

- Notifier seam: `def _health_notifier(title, body) -> bool: return alert_bus.emit(Alert(
  source="agent-skill-sync", severity=Severity.<WARNING/ERROR>, title=title, description=body)).ok`
  — **`.ok`, never `.delivered`**. Import `emit, Alert, Severity` from `scripts.common.alert_bus`.
- Git-advance watermark: `health.record("agent-skill-sync", advance_result, state_path=GIT_HEALTH,
  notifier=_health_notifier)` inside the locked tick (mirror the reference), failure-contained
  (never crash the tick; a `health_record_error` audit on exception).
- Copy-failure watermark: adapt the copy outcome onto an `AdvanceResult` (`ok=not errored`,
  `reason="copy_failed"` when errored) and `health.record("agent-skill-sync-copy", …,
  state_path=COPY_HEALTH, notifier=_health_notifier, confirmed_reasons={"copy_failed"},
  render=_copy_render)`. `_copy_render` returns skills-accurate `(title, body)` (a deployed skill is
  silently not updating — the #563 class).

### Subtask T006 — Tests (test-first)

**Purpose**: Prove every path. Write these FIRST (DIRECTIVE_034), watch them fail, then implement.

- **Unit**: `compute_md5`; `atomic_copy` (mode-preserve, temp-cleanup on failure); `iter_skills`
  (derivation, missing SKILL.md → warning, multi-file → warning, `*.backup*` not a multi-file
  trigger, `--skill` filter, unknown skill → exit 3); drift predicate; exit-code mapping;
  `write_last_tick` shape (`exit_code=0`, `completed_at_utc`).
- **Integration** (temp repo + temp deployed dir): induce drift → converges + `copy` audit;
  idempotent no-op → 0 writes / `skip` records; **FR-016** missing dest dir is created; induced copy
  failure (e.g. read-only dest) → exit 1 + copy-health streak alert (inject a mock notifier;
  assert delivered vs undelivered handling); `*.backup*` ignored; `--dry-run` prints DRIFT + writes
  nothing; deploylock contention → clean defer (exit 0, no copy).
- Use a **normalizing** deployed-side fixture (store bytes as they land) so an echo-only mock can't
  hide a divergence (banked #757 lesson).
- Mock `advance_checkout` / `deploylock` at the seams; do not hit a real network/office2.

## Branch Strategy

Planning artifacts were generated on `feat/openclaw-skills-sync`; the final merge target is
`feat/openclaw-skills-sync`. Execution worktrees are allocated per computed lane from `lanes.json`.

## Definition of Done

- [ ] All six subtasks complete; `deploy_agent_skills.py` importable + `-m` runnable.
- [ ] `pytest tests/openclaw/deploy/test_deploy_agent_skills.py` green; tests written first.
- [ ] Copy-only, backup-ignore, dest-dir-create, multi-file warning, exit-code contract all covered.
- [ ] Notifier uses `.ok`; both health watermarks wired; failure-contained.
- [ ] No modification to `deploy_agent_prompts.py`; no third-party imports.

## Risks / reviewer guidance

- **Notifier field**: confirm `.ok` (grep `AlertResult` in `model.py`) — the #1 silent-alert bug.
- **Lock discipline**: the copy loop MUST be inside `deploylock()` so it never races felix-deployer /
  prompt-sync on the shared checkout; dry-run takes no lock.
- **Freshness pointer** stays `exit_code=0` (timer-liveness, not deploy outcome).
- Reviewer: verify the normalizing fixture actually stores landed bytes (not an echo) and that the
  copy-failure streak test asserts one alert per streak, not per tick.

## Activity Log

- 2026-07-19T02:35:39Z – claude – shell_pid=82059 – Assigned agent via action command
- 2026-07-19T02:41:04Z – claude – shell_pid=82059 – Skills sync helper + 33 tests; dry-run smoke green
- 2026-07-19T02:41:52Z – claude – shell_pid=84204 – Started review via action command
