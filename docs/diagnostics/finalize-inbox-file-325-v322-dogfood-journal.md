# Dogfood journal — mission for #325 on spec-kitty **3.2.2**

Second attempt at a spec-kitty mission for issue #325
(`scripts/inbox/finalize_inbox_file.py`). The first attempt (2026-06-20, on
**3.2.1**) was PAUSED — blocked by the create→plan split-authority topology
(upstream Priivacy-ai/spec-kitty #1716 write-side + #2046 read-side). See the
companion journal `finalize-inbox-file-01KVKG4S-dogfood-journal.md` for that run.

3.2.2 is meant to carry the fixes for those blockers. This run re-validates.
Purpose (same as before): capture a ground-truth timeline of *our actual
experience* so it can be cross-checked against `spec-kitty-analyzer` (still v0.x,
hence the journal gives redundancy) and the collated event-log timeline.

- **Issue**: kentonium3/kg-automation#325 (P1-feature, `spec: ready`)
- **Spec-kitty version**: 3.2.2 (pipx; `spec-kitty-cli version 3.2.2`)
- **Started**: 2026-06-24
- **Posture**: drive clean, no hand-cranking; STOP + capture on any anomaly.
- **Mission handle**: _(minted at specify — recorded below)_

---

## Pre-flight state (2026-06-24, before specify)
- Working tree clean; `.worktrees/` empty.
- No `finalize` branches anywhere (local/remote) — prior 3.2.1 split-mission
  cleanup debt (orphan coord branch/worktree/feat) is fully resolved.
- #325 OPEN, `spec: ready` → spec gate passes.
- main was 5 commits ahead of origin/main (3.2.2 upgrade artifacts + 3.2.1
  stand-down journal). **Pushed** to origin/main (`46317366..0ff80950`) so the
  mission branches off current main; pre-push suite green (3781 passed).
- Command-file shapes confirmed (3.2.2): specify/plan/tasks = runbooks
  (690/384/714 lines); implement/review/merge/accept = shims (9 lines).

---

## Timeline

### T0 — Specify setup (clean)
- Startup upgrade check → `action: none` (installed 3.2.2, up to date).
- `branch-context --json` → `current_branch=main`, `current_is_primary=true`,
  `recommended_strategy=feature-branch`, `merge_target_branch=main`,
  `branch_matches_target=true`.
- `charter context --action specify` → compact mode, loaded OK. Known
  tool-registry diagnostic noise (pytest/python beyond runtime registry) present,
  non-blocking.
- Brief detection → no `.kittify/mission-brief.md`, no ticket-context → normal
  discovery gate.
- **Branch-strategy decision (mandatory, current_is_primary=true)**: operator
  chose **feature branch `feat/finalize-inbox-file`** (same topology that split on
  3.2.1 → most faithful re-validation of the #1716/#2046 fix).
- **Scope decision**: operator chose **Full — helper + tests + in-repo AGENTS.md
  cutover (`scripts/openclaw/agents/felix-admin-capture/AGENTS.md`) + a
  `deploys/queued/<name>.yaml` manifest** (felix-deployer applies post-merge).
  Grounding: sibling helpers exist (prescan/append_routing/mark_processed),
  `tests/inbox/` established, agent prompt has in-repo source, `deploys/queued/`
  empty. Helper + prompt land together at merge → no cross-mission split needed.
- Not a bulk edit (new helper + single-file prompt edit).

### T1 — mission create (success)
- `mission create "finalize-inbox-file" --pr-bound --branch-strategy
  already-confirmed --start-branch feat/finalize-inbox-file` → success.
  - mission_slug `finalize-inbox-file-01KVVYH9`, mid8 `01KVVYH9`,
    mission_id `01KVVYH9EWJ4JKMVZVEVR0C7A1`.
  - `coordination_branch kitty/mission-finalize-inbox-file-01KVVYH9`
    (`coordination_branch_created: true`).
  - switched onto `feat/finalize-inbox-file`; **branch contract now internally
    consistent**: target/base/merge_target all = `feat/finalize-inbox-file`
    (mission merges into the feature branch; feat→main is the later PR step).
  - `spec.md` left **untracked** per #846 commit boundary; `plan_guard:
    SPEC_NOT_SUBSTANTIVE_OR_UNCOMMITTED` as expected.
  - _Contrast w/ 3.2.1 run: there the contract was self-inconsistent (feat vs
    main vs coord across resolvers). Here it is coherent. Watching plan step for
    the #1716 split next._

### T2 — Specify authoring + spec-commit (routed to coord, coherent)
- Authored substantive `spec.md` (14 FR / 5 NFR / 4 C / 5 SC), `checklists/
  requirements.md` (all items pass). No `[NEEDS CLARIFICATION]` markers, so no
  Decision-Moment markers needed.
- `spec-commit --mission finalize-inbox-file-01KVVYH9 spec.md meta.json
  checklists/requirements.md` → `committed: true`,
  **`placement_ref: kitty/mission-finalize-inbox-file-01KVVYH9`** (the
  coordination branch), commit `9c2c778f`. Materialize-then-retry materialized
  the coord worktree `.worktrees/finalize-inbox-file-01KVVYH9-coord`.
- **Topology after spec-commit (KEY 3.2.2 vs 3.2.1 difference):**
  - feat HEAD `0300baba`: meta.json only (create commit).
  - coord HEAD `9c2c778f`: meta.json + spec.md + checklists/ — **self-complete**.
  - repo-root (feat) shows spec.md/checklists/status.events.jsonl/tasks as
    untracked + meta.json modified — these are working-tree copies; the canonical
    committed versions are on coord. NOT cleaned (per never-git-clean-kitty-specs
    / don't-over-clean discipline).
  - On 3.2.1 this same point produced the split (spec→feat, plan→coord, resolvers
    disagreed). On 3.2.2 the coord branch is the single coherent home so far.
  - Did NOT manually touch coord branch/worktree or repo-root untracked files.

### T3 — Plan setup + resolver consistency check (#1716/#2046 validation)
- `charter context --action plan` → compact; full directive set (DIR-001..015 +
  builtin DIRECTIVE_*).
- **Resolver cross-check (the #2046 test):**
  | Resolver | feature_dir |
  |----------|-------------|
  | `context resolve --action plan` | **coord worktree** |
  | `tasks status` | **coord worktree** (errors: no tasks dir yet — expected) |
  | `agent mission setup-plan` | **coord worktree** (plan_file/spec_file/feature_dir all coord) |
  | `check-prerequisites --paths-only` | **repo-root** (reads the untracked repo-root spec.md copy) |
  - **3.2.2 verdict so far: COHERENT for driving.** The three *action/authority*
    paths (context-resolve, tasks-status, setup-plan) all agree on the coord
    worktree. Only `check-prerequisites --paths-only` still reads the primary
    checkout — the residual #2046 read-side class — but it is not on the
    progress path, so it does not block. Sharp contrast with the 3.2.1 run, where
    setup-plan↔tasks disagreed and there was *no* coherent feature_dir at all.
- `setup-plan` created `plan.md` scaffold **in the coord worktree** and returned
  `result: blocked, plan_substantive: false` (exit-gate: needs real Technical
  Context Language/Version) — expected, not a failure. Authoring will happen at
  the CLI-designated coord-worktree feature_dir (NOT hand-cranking; that is where
  setup-plan placed the scaffold). branch contract consistent: all
  feat/finalize-inbox-file.
- Planning interrogation: feature is comprehensively specified in #325 + has
  established sibling-helper conventions → proceeding with a documented
  Engineering Alignment (no blocking questions), consistent with auto-drive.

### T4 — Plan authoring + commit (coherent, no split)
- Mapped the reuse surface (Explore subagent): reuse `mark_processed.mark_processed()`
  (frontmatter + atomic write + idempotence + private-refusal), `prescan.resolve_registry()`
  (vault paths, `PRESCAN_REGISTRY_PATH` test override), prescan JSON-stdout convention.
  Move = atomic `os.rename` (reject cross-FS EXDEV → exit 2). Daily log per #325
  contract. Invocation `python3 -m scripts.inbox.finalize_inbox_file`.
- Authored in the **coord worktree** feature_dir (where setup-plan placed the
  scaffold): plan.md (real Technical Context, Charter Check on 7 directives,
  3-IC map: helper+tests / cutover+manifest / stranded-note reconcile),
  research.md (7 decisions), data-model.md, contracts/finalize-cli-contract.md,
  quickstart.md. No `[NEEDS CLARIFICATION]` markers → no Decision-Moment markers.
- Re-ran `setup-plan` → `result: success, phase_complete: true,
  plan_substantive: true`; plan.md **auto-committed to coord**.
- `spec-commit` Phase-1 artifacts → coord, commit `2c70c830`
  (`placement_ref: kitty/mission-finalize-inbox-file-01KVVYH9`).
- **#1716/#2046 VERDICT: the create→plan split is FIXED on 3.2.2.** All spec +
  plan + Phase-1 artifacts live coherently on the single coordination branch;
  every authority resolver (context-resolve, setup-plan, tasks-status) agreed on
  the coord worktree throughout. Only residual: `check-prerequisites
  --paths-only` reads the primary checkout (untracked copies) — cosmetic, never
  on the progress path. On 3.2.1 this exact sequence had no coherent state and
  was PAUSED; on 3.2.2 it drove clean through plan.
- No hand-cranking used anywhere (no manual git on kitty-specs/coord, no cleanup
  of repo-root untracked copies).
- Reached the plan runbook's ⛔ MANDATORY STOP POINT → checkpoint with operator
  before `/spec-kitty.tasks`. Operator: **auto-drive to merge**.

### T5 — Tasks phase → BLOCKER: tasks-phase resolver split (#2046 residual, STILL PRESENT on 3.2.2)
- `context resolve --action tasks` → feature_dir = **coord worktree** (consistent
  with plan). Authored `tasks.md` + `tasks/WP01-finalize-helper.md` +
  `tasks/WP02-cutover-deploy.md` there (the `tasks/` placeholder from `create`
  was stranded untracked in repo-root and never committed to coord — minor
  topology note; I authored the real WP files in the resolver-designated coord
  dir, Write tool created `tasks/`).
- `map-requirements --batch` → success, **coverage 14/14**; the CLI normalized
  WP frontmatter and wrote `requirement_refs` into the **coord** WP files
  (verified present).
- `finalize-tasks --validate-only` → **`error: Requirement mapping validation
  failed`, ALL 14 FRs `unmapped_functional_requirements`** — i.e. it saw ZERO
  mappings, directly contradicting map-requirements.
- **Root cause (read-only diagnosis, no surgery):** WP files + tasks.md exist
  ONLY in the coord worktree; repo-root `kitty-specs/.../tasks/` has just the
  `.gitkeep` + create README. `finalize-tasks` resolves to **repo-root** (sees no
  tasks.md, no WP files → 0 mappings → all 14 unmapped). `finalize-tasks --help`
  exposes no `--feature-dir`/worktree flag.
- **Tasks-phase resolver matrix (the split):**
  | Command | feature_dir |
  |---------|-------------|
  | `context resolve --action tasks` | coord worktree |
  | `map-requirements` | coord worktree (wrote refs there) |
  | `agent tasks status` | coord worktree |
  | `setup-plan` (plan phase) | coord worktree |
  | `check-prerequisites --paths-only` | **repo-root** |
  | `finalize-tasks [--validate-only]` | **repo-root** |
- **Verdict:** 3.2.2 fixed the create→plan write-side split (#1716) — spec+plan
  cohered on coord and drove clean. But the **read-side residual (#2046) is STILL
  present at the plan→tasks boundary**: the tasks authoring/mapping CLIs resolve
  to the coord worktree while `finalize-tasks`/`check-prerequisites` resolve to
  the primary checkout. No single authoring location satisfies the whole tasks
  toolchain; converging by hand would require moving/removing files inside the
  workflow-managed coord worktree (prohibited by operating rules — and not
  guaranteed to converge given map-requirements re-binds to coord).
- **Action: STOPPED per workflow rules** (no file moves, no forced convergence,
  no hand-cranking). Mission left intact: spec+plan committed on coord
  (`9c2c778f`, `2c70c830`); tasks artifacts authored but UNCOMMITTED in the coord
  worktree; `finalize-tasks` never run in mutating mode. Escalating to operator.
- **Maps to:** upstream Priivacy-ai/spec-kitty **#2046** (read-side surface
  resolver adoption; was in flight on `feat/read-side-surface-resolver-adoption`
  per the 3.2.1 journal). This is a fresh 3.2.2 repro at the tasks phase. Internal
  tracker: kentonium3/kg-automation#606.

---

## Operator decision (2026-06-24) + stand-down

- **#325**: PAUSED again (no urgency), now blocked one phase later than 3.2.1 —
  at plan→tasks `finalize-tasks` instead of create→plan. Not shipped.
- **Posture**: stand down as a clean 3.2.2 repro of the read-side resolver split
  (#2046). Leave the mission intact for re-validation once the read-side fix
  RELEASES (not just merges) — same gating rule as the 3.2.1 stand-down.
- **Upstream**: do NOT post yet. Draft an evidence note for #2046 (fresh 3.2.2
  tasks-phase repro + the resolver matrix above) for operator approval first.
- **Internal**: update kentonium3/kg-automation#606 with this journal link + the
  3.2.2 result (write-side #1716 fixed; read-side #2046 still splits at tasks).

### State at STOP (for cleanup / re-validation cross-check)
- Mission `finalize-inbox-file-01KVVYH9`, branch `feat/finalize-inbox-file`,
  coord branch `kitty/mission-finalize-inbox-file-01KVVYH9`, coord worktree
  `.worktrees/finalize-inbox-file-01KVVYH9-coord/`.
- coord HEAD `2c70c830`: spec.md, meta.json, checklists/, plan.md, research.md,
  data-model.md, contracts/, quickstart.md — all coherent on coord.
- **Uncommitted in coord worktree** (the repro surface): tasks.md,
  tasks/WP01-finalize-helper.md, tasks/WP02-cutover-deploy.md (WP frontmatter
  carries the map-requirements `requirement_refs`), status.events.jsonl.
- feat HEAD `0300baba`: meta.json (create commit). repo-root checkout otherwise
  carries stale untracked working copies of the spec/plan artifacts (canonical
  copies are on coord) + the empty `tasks/` placeholder.
- `finalize-tasks` never run in mutating mode. No git surgery, no file moves, no
  hand-cranking anywhere in the run.
- Cleanup debt (defer to post-fix re-validation): paused mission's feat + coord
  branches/worktree, uncommitted coord tasks artifacts. Plus pre-existing
  unrelated stale remotes (`origin/feat/architecture-data-validator`,
  `origin/fix/felix-exec-host-gateway-directive`,
  `origin/kitty/mission-trustworthy-weekly-habit-report-*`).

### Net dogfood result
3.2.2 is a real step forward: the #1716 write-side split that hard-blocked at
create→plan on 3.2.1 is FIXED, and specify+plan now drive cleanly on the
coordination topology. The #2046 read-side residual remains and now surfaces one
phase later, blocking `finalize-tasks`. Re-run the mission after the read-side
resolver fix ships in a release.

---

## Post-stop verification (2026-06-24) — fix-in-build + upstream search → STAND DOWN, no post

Operator asked to (a) verify whether the fix is actually in our build, and (b)
search up/down-stream from #2046 for a more specific tracking issue. Both done.

### Fix-in-build (definitive)
- Our 3.2.2 = source build of `git+https://github.com/Priivacy-ai/spec-kitty.git@main`,
  commit **`aeb8dfc31a88d2ae779e7b32f5340e90159733e6`** (pipx install 2026-06-23,
  AFTER the strangler merged).
- Strangler **PR #2065** (`1f42e94e`, closes #2010/#2040/#2046) **IS in our build**
  (compare `1f42e94e...aeb8dfc` → behind_by 0). Residual persists regardless.
- Installed-code confirmation (`specify_cli/cli/commands/agent/mission.py`):
  `finalize_tasks` resolves feature_dir via `_resolve_mission_dir_name_primary_anchored`
  (primary checkout); `check_prerequisites` via `_primary_anchored_feature_dir`
  (the PR #2089 point-fix). Neither uses the coord-aware surface resolver, while
  `context resolve` / `map-requirements` / `setup-plan` do → the tasks-phase split.
  This is **primary-anchoring by design** in finalize/check-prereq, contradicting
  the coord-pointing authoring/mapping CLIs — an internal inconsistency, not a
  stale build.

### Upstream search — the bug is ALREADY filed, with maximal precision (all OPEN, 2026-06-24)
Operator's recollection ("represented in a different issue somewhere") was correct.
- **#2087** (P1 bug) — "check-prerequisites and finalize-tasks resolve a
  coord-topology mission's planning surface to DIFFERENT checkouts (authoring/read
  split)" — exact mechanism match.
- **#2101** (P1 bug) — "Coordination-worktree missions: planning/tasks commands
  resolve different feature_dir (tasks phase deadlocks; not fixed by #2070)" —
  cites our **exact** build commit `aeb8dfc3`, `pr_bound`/`topology: coord`.
- **#2090** (P0 enh) — "Unify all planning-lifecycle commands onto ONE
  topology-aware surface authority" — the structural cure; explicitly lists
  `map-requirements` + `finalize-tasks` among commands still to unify. PR #2089
  was a point-fix only.
- **#1716** — **reopened** (P0 launch-blocker), updated today.

### Disposition: STAND DOWN — no upstream post
The blocker is already captured down to our exact commit, today, by the
maintainers, with a P0 structural fix (#2090) scoped. A confirming comment would
be noise — same call as the 3.2.1 stand-down. The drafted #2046 evidence note is
therefore moot; do NOT reopen #2046 (it's correctly closed — the residual lives in
the OPEN #2087/#2090/#2101 + reopened #1716). **Re-run #325 after the
planning-lifecycle unification (#2090) ships in a release**, then re-validate the
full specify→merge arc. Internal record: #606 (updated with these cross-refs).
