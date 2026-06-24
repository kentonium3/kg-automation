# Dogfood journal — mission for #325 on spec-kitty **3.2.2 (official PyPI release)**

Third attempt at a spec-kitty mission for issue #325
(`scripts/inbox/finalize_inbox_file.py`). History:

- **Attempt 1** (2026-06-20, **3.2.1**): PAUSED — `create→plan` split-authority
  topology (#1716 write-side + #2046 read-side). Journal:
  `finalize-inbox-file-01KVKG4S-dogfood-journal.md`.
- **Attempt 2** (2026-06-24, **3.2.2 from-`main` SOURCE build `aeb8dfc3`**): PAUSED
  one phase later — `finalize-tasks` primary-vs-coord split (#2087/#2090/#2101).
  Journal: `finalize-inbox-file-325-v322-dogfood-journal.md`.
- **Attempt 3 (this run)** (2026-06-24, **3.2.2 OFFICIAL PyPI RELEASE**): the
  #2090/#2106 placement fix shipped in the release. This run re-validates the
  full planning arc end-to-end.

Purpose: ground-truth timeline of our *actual* experience driving the release,
to cross-check against `/spec-kitty.analyze` on this mission and against
`spec-kitty-analyzer`.

- **Issue**: kentonium3/kg-automation#325 (P1-feature, `spec: ready`)
- **Spec-kitty**: 3.2.2 official PyPI release — `pipx install --force "spec-kitty-cli==3.2.2"`
- **Release identity**: tag `v3.2.2` = commit `f853934b6` (== `upstream/main` HEAD;
  `v3.2.2..main` empty). Prior daily-driver build `8ae2027e` is an ancestor of the
  tag (`git merge-base --is-ancestor 8ae2027e v3.2.2` = YES). The #2090/#2106
  placement commits are in the tag.
- **Mission handle**: `finalize-inbox-file-01KVXNDC` (mid8 `01KVXNDC`,
  id `01KVXNDCT9GB32JJ6M67B7PS5F`)
- **Branch topology**: target/planning `feat/finalize-inbox-file`; coordination
  branch `kitty/mission-finalize-inbox-file-01KVXNDC`; `meta.json topology: coord`.
- **Posture**: drive clean, no hand-cranking; STOP + capture on any anomaly.

---

## Pre-run: upgrade to the official release

- Started session on the from-`main` build `8ae2027e` (reports `3.2.2`). Official
  3.2.2 dropped on PyPI ~10 min before kickoff; Kent directed: upgrade binary +
  all repos first.
- **Verified the release contains the #325 fix BEFORE swapping** (so we wouldn't
  regress): `v3.2.2` tag includes `8ae2027e`; placement commits #2090/#2087/#2101
  present.
- CLI: `pipx install --force "spec-kitty-cli==3.2.2"` → source now `spec-kitty-cli==3.2.2`.
- Per-repo `spec-kitty upgrade --project --yes` on all 7 initialized repos
  (kg-automation, bake-planner, bake-tracker, intentional, metalbox,
  spec-kitty-analyzer-harness, vikunja-harness): all reported "already up to
  date" at `metadata.yaml version 3.2.2` — **no-ops because the version STRING is
  identical between the from-main build and the release.**
- **Verified the no-op masked no drift**: diffed the entire 3.2.2 source range
  (`7c78da512..v3.2.2`) for repo-facing surfaces — only CLI code, tests, and 2
  doctrine files changed; doctrine/skills live in the CLI install
  (`~/.claude/skills/`), not per-repo, and the installed copy matches the release.
  So per-repo `.kittify` had nothing to refresh.

---

## Timeline

### specify — CLEAN
- `branch-context`: `current_is_primary: true` on `main` → mandatory branching
  decision. Kent chose a dedicated `feat/finalize-inbox-file` (matches prior runs;
  reproduces the coord topology the #2106 fix targets).
- `mission create … --pr-bound --branch-strategy already-confirmed --start-branch
  feat/finalize-inbox-file`: success. Coordination branch created.
- Authored substantive `spec.md` (10 FR, 4 NFR, 5 C; 8 acceptance scenarios) +
  quality checklist (all items pass first validation). Issue body used as input,
  requirements extracted/structured (not copied verbatim).
- `spec-commit` → committed **directly to `feat/finalize-inbox-file`** (`254967c7`).
  No coord-worktree materialized (unprotected feature branch → direct commit).
  **Contrast: attempt 2 cohered spec/plan on the coord branch.**

### plan — CLEAN
- `charter context --action plan`: compact; directives 001/003/010/024/031/033/034.
- `context resolve --action plan` + `setup-plan`: entry gate passed (spec committed
  + substantive); exit gate initially blocked (plan not substantive) → expected.
- Authored `plan.md` (Technical Context with real values, Charter Check, IC map:
  IC-01 helper / IC-02 tests / IC-03 cutover+deploy) + `research.md` (D-01…D-07),
  `data-model.md`, `contracts/finalize_inbox_file.cli.md`, `quickstart.md`.
  Grounded in the existing `scripts/inbox/` family (prescan patterns; reuse
  `mark_processed.py`/`routing_log.py`).
- `decision verify`: clean (0 markers, 0 deferred). `setup-plan` re-run:
  `phase_complete: true`, auto-committed `plan.md` (`8c6f83c3`).
- Phase-1 artifacts + meta/event-log committed via `spec-commit` (`8c0722f4`).

### tasks — CLEAN (the phase that blocked both prior attempts)
- **THE key coherence check**: `context resolve --action tasks` and
  `check-prerequisites` both returned the **same primary `feature_dir`** (repo-root
  checkout) with `branch_matches_target: true`. **In both prior attempts these
  diverged** (authoring CLIs → coord worktree; prereq/finalize → primary). The
  #2106 placement fix holds.
- Authored `tasks.md` + 3 WP prompts (WP01 helper / WP02 tests / WP03
  cutover+deploy; 15 subtasks; non-overlapping `owned_files`; deps WP02→WP01,
  WP03→WP01).
- `map-requirements --batch`: **all 10 functional requirements mapped,
  `unmapped_functional: []`.** **This is exactly the call that reported "all 14
  FRs unmapped" in attempt 2** — now coherent.
- `finalize-tasks --validate-only`: first run ERRORed on ownership — `owned_files`
  named planned-new files that match zero files in the repo. **Legitimate guardrail,
  not a bug**; the error names the fix (`create_intent:`). Populated `create_intent`
  in each WP → re-run `validation_passed` (3 WPs, lanes a/b/c).
- `finalize-tasks` (mutating): **SUCCESS — `commit_created: true`, `commit_hash
  37113bab`, 3 WPs.** Tree clean; `lanes.json` present.

### Commit chain (on `feat/finalize-inbox-file`)
```
37113bab Add tasks for feature finalize-inbox-file-01KVXNDC
8c0722f4 Add plan artifacts (research, data-model, contracts, quickstart)
8c6f83c3 Add plan for feature finalize-inbox-file-01KVXNDC
254967c7 Add spec for finalize-inbox-file
2b2522e5 Add meta for feature finalize-inbox-file-01KVXNDC
5eb4553c (main) docs(diagnostics): #325 3.2.2 verification … stand down
```

---

## VERDICT — #2106 VALIDATED END-TO-END (through planning)

The coordination-topology tasks phase that hard-blocked attempts 1 and 2 now
**completes cleanly** on the official 3.2.2 release. specify → plan → tasks all
drove without hand-cranking; no workarounds; no STOP-and-capture anomalies.
Remaining: implement → review → merge (not yet run).

## Observations on working with the 3.2.2 release

1. **Placement coherence holds.** All planning artifacts landed on the
   feature/target branch; authoring and finalize CLIs agree on the primary
   feature_dir. No coord-worktree scatter for planning; no split-authority.
2. **No coord worktree materialized for planning** on an unprotected feature
   branch — `spec-commit` committed directly. (A protected-`main` "stay" topology
   would exercise the coord worktree differently; not tested this run.)
3. **`spec-commit` wants explicit file paths, not directories.** Passing
   `contracts/` (a dir) tripped the safe-commit backstop ("unexpected paths
   staged"); passing `contracts/finalize_inbox_file.cli.md` worked. Minor learning,
   working as designed.
4. **`finalize-tasks` ownership validation now requires `create_intent`** for
   planned-new files (good guardrail; clear, actionable error with "Did you mean"
   suggestions).
5. **`map-requirements` normalizes WP frontmatter** (alphabetizes keys; injects
   `requirement_refs`, `tracker_refs`, `create_intent`, `tags`, `create_intent`).
   Expected; harmless.
6. **Version-string-stuck caveat persists** — `upgrade --project` is a no-op when
   the string is unchanged across builds; can't distinguish from-main vs release
   by version alone. Documented in the version-history memory.

## For the `/spec-kitty.analyze` comparison

Human-driven consistency read at pause (to compare against analyze findings):
- spec↔plan↔tasks coherent; FR coverage complete (10/10 FR mapped; NFR/C also
  referenced). No `[NEEDS CLARIFICATION]` markers. Decision index clean.
- 3 WPs, 15 subtasks, non-overlapping ownership, acyclic deps (WP02→WP01,
  WP03→WP01), lanes a/b/c.
- Potential analyze flags worth watching: (a) WP01 carries 16 requirement_refs
  incl. all NFR-001..003 + C-001/003/004/005 — broad but accurate; (b) WP02 maps
  the FRs it *validates* (overlap with WP01's delivery refs) — intentional;
  (c) the helper's reuse-vs-reimplement of `mark_processed.py`/`routing_log.py`
  (D-01) is a design decision deferred to implementation, not yet resolved in
  artifacts.

## IMPLEMENT BOUNDARY — SPLIT-BRAIN, STOPPED (the new blocker)

Resumed driving the workflow into implement (Kent: "keep going"). It blocked
immediately — a genuine residual split-brain at the **planning→implement
handoff**, one boundary downstream of the attempts 1+2 blockers (which the release
DID fix).

Sequence:
- `spec-kitty agent action implement WP01 --agent claude --mission …` →
  `Error: Feature 'finalize-inbox-file-01KVXNDC' has no tasks directory at
  .worktrees/finalize-inbox-file-01KVXNDC-coord/kitty-specs/finalize-inbox-file-01KVXNDC/tasks`.
- Canonical loop driver `spec-kitty next --mission … --agent claude` →
  `[QUERY] Mission @ not_started · Next step: discovery`. The state machine the
  implement read-side consults thinks the mission never started.
- `spec-kitty agent tasks status --mission …` → same "Tasks directory not found"
  in the coord worktree.

Root cause (observed, read-only):
- **`feat/finalize-inbox-file` (target/primary)** holds ALL planning artifacts
  (meta, spec, plan, research, data-model, contracts, tasks.md, `tasks/WP0*.md`,
  lanes.json) PLUS a **lifecycle** event log `status.events.jsonl` (10 events,
  schema 5.0.0: MissionCreated…SpecCompleted…PlanCompleted…WPCreated×3…TasksCompleted).
- **`kitty/mission-…` (coord) branch + its worktree
  `.worktrees/finalize-inbox-file-01KVXNDC-coord/`** hold ONLY `status.json` +
  a **lane** event log `status.events.jsonl` (3 events: WP01/02/03 genesis→planned,
  "canonical bootstrap"). **No planning artifacts, no `tasks/` dir.**
- So there are TWO different-schema `status.events.jsonl` on the two branches, and
  `implement`/`next`/`tasks status` all read the **coord** side, which was never
  populated with the planning artifacts. `next` reads lifecycle state from a source
  that shows `not_started`.

Assessment: #2106 fixed planning-artifact **placement** (planning phases cohered on
the target branch and every step succeeded), but the planning→implement **handoff**
is still split: the implement read-side is coord-anchored, the coord worktree was
never populated with the planning artifacts, and the lifecycle progress recorded on
the target branch is not consulted by `next`. This is the **same split-brain class**
as #1716/#2046/#2087/#2090, surfacing at the **next boundary downstream** on the
official release.

Not me: every commit placement was chosen by the tooling — `spec-commit` printed
"committed to feat/finalize-inbox-file"; `setup-plan` and `finalize-tasks`
auto-committed to feat; `finalize-tasks` reported `commit_created: true`. The mission
is `topology: coord` yet its planning artifacts live on the target branch while the
coord worktree (which implement reads) stayed empty.

**STOPPED per the no-workaround posture.** Did NOT: populate the coord worktree,
merge feat→coord, advance any event log, or git-manipulate. Mission left intact as
evidence. No upstream filing (needs Kent's approval + dedup check vs #1716-reopened
and the #2010/#2040/#2046 strangler).

## State at STOP
- Planning arc COMPLETE on `feat/finalize-inbox-file`; implement BLOCKED by the
  split-brain above. Repo-root on `feat/finalize-inbox-file`; coord worktree present
  but empty of artifacts. Tree clean (no uncommitted changes).
- Commits on feat: `2b2522e5`(meta) `254967c7`(spec) `8c6f83c3`(plan)
  `8c0722f4`(plan artifacts) `37113bab`(tasks) `3dcd86a9`(journal).
- Internal tracker #606. Mission intact; nothing torn down.
- Next: Kent's call — characterize/dedup vs upstream; decide file-vs-known;
  decide mission disposition (likely teardown, as attempts 1+2). `/spec-kitty.analyze`
  deferred (can't reach implement/merge).

## Upstream dedup — EXACT MATCH, already tracked (#2115, OPEN)

The implement-boundary split-brain is a **known maintainer-tracked residual**:
- **Priivacy-ai/spec-kitty#2115** (OPEN, `bug`, 0 comments): *"Implement/review/merge
  command surface reads WP `tasks/` off coord (dir-read residual cluster, N+2)."*
  Found by the maintainer's own gate-read-surface-completion adversarial squad
  during PR #2113. Names exactly the surfaces I hit: `agent/workflow.py`
  (`implement`, `review`), `agent/tasks.py` (`status`, `finalize_tasks` dir-read
  legs), `merge.py`. Deliberately OUT of scope of the behavior-neutral
  read-completion mission; **pinned in `_DIR_READ_KNOWN_RESIDUALS`** (test-only)
  until a follow-on mission. Part of the #1716 coordination-topology cluster.
- The **3.2.2 CHANGELOG itself says remediation is "ongoing."** The coord-topology
  "WPs reached done with nothing committed" fixes it DID ship are all on the
  external **`orchestrator-api`** path (start-implementation lane allocation, etc.)
  — NOT the native `spec-kitty next` / `agent action implement` path the runbooks
  prescribe and that I drove. My finding is the **native-path twin** of an
  already-fixed api-path class.
- **Verdict: not a new issue — a confirming real-world event for #2115.** Value
  added: a disciplined operator drove the *native* workflow on the *released*
  3.2.2 artifact and was hard-blocked at exactly this surface (previously
  only test-pinned). Related: #2091 (`next` malformed coord branch — distinct),
  #1878/#1716 (cluster umbrellas).

## Analyzer comparison (spec-kitty-analyzer, mission-first)

Ran `spec-kitty-analyzer analyze finalize-inbox-file-01KVXNDC` against this
session's transcript (65 timeline events, 27 slash cmds, 35 CLI invocations,
1 mission). Report: `/tmp/skanalyzer-325-attempt3.json`. **3 failure modes
detected — 2 false positives + 1 minor-real; the actual blocker was MISSED:**
- FP **"Permission denied"** — fired on a SUCCESS line (`File created
  successfully at: …/spec.md`); it matched the word "permission" inside authored
  spec/WP *content* describing permission-denied test scenarios. = the PR #2
  `permission_denied`-precision class (still unmerged).
- FP **"Timeout"** — fired on my literal `timeout 300 go run …` command text.
- Real-but-minor **"Generic error"** — the `spec-commit` dir-vs-file abort I
  recovered from; not the blocker.
- **MISS** — no fingerprint matched the structural blocker (`no tasks directory
  at …-coord/…/tasks`; `[QUERY] Mission @ not_started` after `finalize-tasks`
  succeeded), although those strings are in the transcript and the analyzer
  advertises a `branch_worktree_confusion` failure catalog. The journal caught
  what the analyzer missed — confirming the redundancy rationale.
- **Candidate analyzer work (separate repo, contributor mode):** (a) tighten
  `permission_denied`/error fingerprints so they don't match failure-keyword
  *content* on success lines (PR #2 class); (b) add a coord/primary split-brain /
  "tasks dir read off coord" + "not_started after TasksCompleted" fingerprint with
  recovery guidance. Last comparable comparison produced analyzer PRs #2 and #5.
