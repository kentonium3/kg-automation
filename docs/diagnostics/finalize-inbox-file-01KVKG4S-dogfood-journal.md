# Dogfood journal — mission `finalize-inbox-file-01KVKG4S` (#325)

Running log of blockers and workarounds encountered while driving a spec-kitty
**3.2.1** mission on issue #325 as a deliberate dogfood run (Kent is now an
upstream spec-kitty contributor). Purpose: capture a ground-truth timeline of
*our actual experience* so it can later be cross-checked against what
`spec-kitty analyze` / the collated event-log timeline claims happened.

- **Mission**: `finalize-inbox-file-01KVKG4S` (mission_id `01KVKG4S56M3F7G0JN77N9K58D`)
- **Spec-kitty version**: 3.2.1 (pipx; command-version marker 3.2.1)
- **Started**: 2026-06-20
- **Posture**: drive clean, no hand-cranking; STOP + capture on any anomaly.

---

## Timeline

### T0 — Setup (clean)
- `upgrade --agent-check` → `none` (on 3.2.1, up to date).
- `branch-context` → on `main`, `current_is_primary: true`. Operator chose a
  feature branch; created with `--pr-bound --branch-strategy already-confirmed
  --start-branch feat/finalize-inbox-file`.
- `mission create` → success. Minted `coordination_branch
  kitty/mission-finalize-inbox-file-01KVKG4S` (`coordination_branch_created: true`).
  `meta.json` committed to **feat** (`ce3d7fa6`). `spec.md` scaffold left untracked.

### T1 — Specify (followed runbook; spec committed to primary checkout)
- Authored `spec.md` in **repo-root** `kitty-specs/…` (per runbook "stay in repo
  root, no worktrees").
- Per runbook #846 commit-boundary, ran `spec-kitty safe-commit
  kitty-specs/finalize-inbox-file-01KVKG4S/` → committed spec+meta+checklists to
  **feat** (`0389d887`).

### T2 — Plan (commit routed to coordination branch → SPLIT)
- Authored `plan.md` + `research.md` + `data-model.md` + `contracts/` +
  `quickstart.md` in **repo-root** `kitty-specs/…`.
- `setup-plan` (re-run after substantive Technical Context) → `phase_complete:
  true`, `PlanCompleted` event fired. BUT it committed **only `plan.md`** to the
  **coordination branch** (`f881c5b4`, parented off old `main` `46317366`),
  materializing the coord worktree `.worktrees/finalize-inbox-file-01KVKG4S-coord/`.

### BLOCKER #1 — split-authority topology (upstream Priivacy-ai/spec-kitty#1716, epic #1619; OPEN)
**Symptom (our experience):** mission artifacts split across three locations:
- `spec.md`, `meta.json`, `checklists/`, `status.events.jsonl`, `tasks/` → **feat** (`0389d887`).
- `plan.md` → **coordination branch** (`f881c5b4`); coord branch does NOT contain the spec commit.
- `research.md`, `data-model.md`, `contracts/`, `quickstart.md` → **uncommitted** (repo-root).

Three commands disagree on the canonical `feature_dir`:
- `setup-plan` / `check-prerequisites` → `.worktrees/…-coord/kitty-specs/…` (has only `plan.md`).
- specify runbook `feature_dir` (from `create --json`) → repo-root `kitty-specs/…` (spec+meta on feat).
- `tasks status` → repo-root `kitty-specs/…/tasks`.

**Match to #1716:** verbatim — "`mission create` writes `coordination_branch`
into `meta.json`, so later read/status/decision paths treat the coordination
worktree as authoritative, but spec/setup-plan/bootstrap planning paths can still
write and commit through the primary checkout … the operator has to manually
create/use `.worktrees/<mission>-<mid8>-coord/` to proceed."

**Root cause (per #1716):** code-level. `coordination_branch` is the topology
activation signal, but coord-worktree authority is deferred; planning paths carry
stale "planning happens in primary checkout" semantics. The specify runbook's own
"stay in repo root, no worktrees" model is exactly that stale semantics.

**Disposition:** already logged upstream (#1716 / epic #1619) → no new filing
(operator condition). Confirmed it is NOT self-inflicted git surgery (we stopped
rather than cascading FF/cherry-pick). Optional: fresh-repro evidence comment on
#1716 (operator approval pending). Related prior diagnostic:
`1777_specify-safe-commit-protected-main.md`.

**Decision:** Operator chose **Option B** — restart in the coordination worktree
(the #1716-prescribed workaround), eyes open, stop at next anomaly.

### BLOCKER #2 — no mission abandon/cancel/delete command
**Symptom:** to "restart cleanly" we need to retire the split mission, but
`spec-kitty agent mission` exposes only `create / check-prerequisites /
setup-plan / accept / merge / finalize-tasks` — there is **no abandon / cancel /
delete / reset**. There is no CLI-sanctioned way to tear down a half-built
mission. Clean teardown would require manual git surgery on workflow-managed dirs
(`kitty-specs/`, coord worktree, coord branch), which is prohibited by our
operating rules.

**Status:** OPEN — distinct, lower-priority issue. Deliberately **excluded from
the upstream #1716 evidence comment** (operator call, 2026-06-20): once #1716 is
fixed the need for an abandon command diminishes considerably, so it stands on
its own as a much lower-priority item, candidate for its own future filing. Not
yet confirmed against the upstream queue as a distinct issue.

---

### BLOCKER #3 — Option B (work-from-coord-worktree) is empirically NOT viable; resolution is cwd-independent and internally inconsistent
Operator approved Option B = in-place recovery from inside the existing coord
worktree (no abandon needed; coord worktree already materialized by setup-plan).
Before copying any artifacts, ran a read-only probe of how spec-kitty resolves
the mission **from inside `.worktrees/finalize-inbox-file-01KVKG4S-coord/`**:

| Resolver | Result (run from coord worktree) |
|----------|----------------------------------|
| `check-prerequisites` `FEATURE_DIR` | **coord worktree** path (SPEC_FILE='', only plan.md) |
| `tasks status` WP path | **repo-root** `kitty-specs/…/tasks` |
| `tasks status` merge target | "mission targets **'main'**" |
| `check-prerequisites` `current_branch` | **`feat/finalize-inbox-file`** |
| actual `git branch --show-current` in worktree | `kitty/mission-finalize-inbox-file-01KVKG4S` |
| `create`/`setup-plan`/`branch-context` target_branch | `feat/finalize-inbox-file` |

**Finding:** resolution does NOT follow cwd. Three commands resolve three
different feature dirs, three different branches, and two different merge targets
(`main` vs `feat/finalize-inbox-file`). Authoring `spec.md` into the coord
worktree would not make `tasks` (which reads repo-root) see it. There is **no
agent-side action** — choosing cwd, copying authoring files — that yields a
coherent mission state. The only "fixes" are prohibited workflow-state surgery
(editing `meta.json` to drop `coordination_branch`, manually relocating
`status.events.jsonl`), and even those are not guaranteed to converge.

**This strengthens the #1716 signal:** the split is not merely "operator must use
the coord worktree" — even using it, the resolvers disagree among themselves
(feature_dir vs tasks-dir vs branch vs merge-target). Worth an evidence comment
on #1716 (operator approval pending).

**Disposition:** STOP per operator's "stop at next anomaly" directive. Option B
retired as non-viable. Mission left untouched in its split state (no surgery).

---

## State at STOP (for cleanup / analyze cross-check)
- `feat/finalize-inbox-file` HEAD `0389d887`: spec.md, meta.json, checklists/, status.events.jsonl, tasks/ scaffold.
- coord branch `kitty/mission-finalize-inbox-file-01KVKG4S` `f881c5b4`: plan.md only.
- coord worktree `.worktrees/finalize-inbox-file-01KVKG4S-coord/` materialized, clean.
- repo-root uncommitted: research.md, data-model.md, contracts/, quickstart.md.
- Cleanup debt: orphan coord branch + worktree + the divergent feat/coord commits (defer per operator: "get through the mission first, clean up after; if blocked, clean when blocked" — superseded by STOP).

## Open question to operator (at STOP)
Mission machinery cannot reach a coherent state for #325 on 3.2.1 without
code-level fix (#1716) or prohibited surgery. Choose: (D) ship #325 as a normal
branch+commits outside spec-kitty; or (Pause) leave the mission as a live repro
and wait for the upstream fix.

## Operator decisions (2026-06-20)
- **#325**: PAUSED (no urgency). Not shipped.
- **BLOCKER #1 / #1716**: confirmed already logged upstream → no new filing.
  Draft an **evidence comment** on Priivacy-ai/spec-kitty#1716 (fresh 3.2.1
  repro + the cwd-independent / mutually-inconsistent-resolvers detail). Goal:
  show there is no happy path and no in-workflow workaround. Operator approves
  the comment body before posting.
- **BLOCKER #2 (no abandon)**: kept OUT of the #1716 comment; distinct + lower
  priority; possible separate future filing.
- Internal tracker: kentonium3/kg-automation#606 (rc44 path-resolution
  residuals; references upstream #1666 / #1716) — updated with this journal link.

## Reporting status — STOOD DOWN (2026-06-20)
**Decision: do not post upstream.** The blocker is already known and the fix is
actively in flight; a 3.2.1 "still broken" comment would be noise.

Upstream state checked before deciding:
- **#1716** OPEN, `priority:P0`, `launch-blocker` — write-side coord/primary
  desync (our spec→feat / plan→coord split). Write-side fixes already merged:
  PR #2020 + #2015 (2026-06-17).
- **PR #2045** closed as **superseded** (today), consolidating onto branch
  `feat/read-side-surface-resolver-adoption`, which stacks #2046.
- **#2046** OPEN — read-side residual: operator read CLIs (`agent tasks status`
  at `tasks.py ~4052`, `agent context`, `agent mission`, `decision`,
  `acceptance`) bypass the canonical resolver; bare-slug + coord-topology →
  silent **primary** read. This is exactly our resolver-inconsistency finding,
  already root-caused to source lines with a 4-cell strict-xfail matrix.

**Mapping:** our write-side split = #1716; our resolver inconsistency = #2046.
Both already captured + being fixed. Nothing additive to contribute.

**Action: none — wait for the fix to land in a release, then re-validate** before
retrying the mission. Internal record: this journal + kentonium3/kg-automation#606.
