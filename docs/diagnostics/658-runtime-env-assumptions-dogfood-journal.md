# Dogfood journal — mission for #658 on spec-kitty **3.2.5 @ git `78bc2307`**

Full spec-kitty mission for issue **kentonium3/kg-automation#658** — *"Infra:
eliminate runtime-environment assumptions in OpenClaw agent commands (cwd / HOME-~ /
checkout-path), fleet-wide"* (P2-infra, `area/felix-core`, `spec: ready`, Tier 3).

## Why this run is instrumented (research purpose)

Per Kent's direction, this mission is a deliberately **multi-objective dogfood run**.
The point is not just to complete #658 — it is to generate the richest possible
diagnostic corpus for improving spec-kitty and the spec-kitty-analyzer. Four
independent instrumentation objectives, cross-checked against each other:

1. **This narrative journal (the SUPERSET source).** Agent-written, unstructured but
   disciplined: steps taken + reasoning, hard errors, workflow failure modes, recovery
   actions + reasoning — event-by-event, phase-by-phase, with a numbered friction
   ledger. Kent's prior journals have materially influenced spec-kitty bug-fix
   priorities, dev process, testing mechanisms, and designs. It is the most robust
   record and the baseline all other outputs are compared against.
2. **#2095/#2203 mission tracer files** — three live-captured companion logs under
   `kitty-specs/<mission>/traces/` (`tooling-friction.md`, `approach.md`,
   `design-decisions.md`), copied from the shipped doctrine templates, seeded at
   planning, appended live through implement, assessed at close. In 3.2.5 these are an
   **agent-driven doctrine procedure** (`mission-tracer-files`, all steps `actor:
   agent`) — there is NO CLI scaffolder; the agent hand-authors them.
3. **spec-kitty-analyzer** — at close, run the Go timeline analyzer (Kent is the
   official maintainer) against this mission's event log; author a CX report; then
   **compare analyzer output to BOTH the journal AND the tracers** to find analyzer
   gaps (what the journal/tracers captured that the analyzer missed). Feeds the
   "incorporate tracers into the analyzer" idea.
4. **PR-landing dimension (new for kg-automation).** This mission lands via a real
   **feat→main PR**, not spec-kitty's default merge-commit-to-main — the first time we
   journal a PR-involved workflow and run the analyzer over it. (NOTE: this is
   DECOUPLED from the Stijn/#2341 maintainer-PR-landing trial, which is a separate
   track on a real spec-kitty-family PR — #658-as-PR would be a hollow #2341 trial
   because it lands our own mission output, not a contributor's fork PR.)

- **Issue:** kentonium3/kg-automation#658 (P2-infra, `area/felix-core`, `spec: ready`)
- **Spec-kitty build:** version string `3.2.5`; **actual build =
  `git+…/spec-kitty.git@78bc2307409997923d431c73478c888fec93b83c`** (upstream `main`
  tip, 2026-07-05 19:53Z, *"chore(release): open 3.2.5 development cycle"*). Re-pinned
  from the prior `3.2.4 @ c1424728` at session start to satisfy "catfood latest main".
  Verified latest via `upgrade --agent-check`: installed 3.2.5 > PyPI 3.2.4,
  `action=none, up_to_date`. **Pin by commit, not version — the string can't express
  which main build is present** (the standing F1 finding from prior runs).
- **Started:** 2026-07-05
- **Posture:** auto-drive the full arc, no hand-cranking; STOP + capture on any genuine
  tool failure (a workaround destroys the capture signal). Two mandatory Codex
  review-and-fix checkpoints: post-plan (before tasks) + post-merge (before feat→main).
- **Branch:** feature branch `feat/<slug>` (minted at create via `--start-branch`);
  mission lands there via `spec-kitty merge`, then a PR feat→main.
- **Mission handle:** _(minted at specify — recorded below)_

---

## Pre-flight state (2026-07-05, before specify)

- **Repo:** `kentonium3/kg-automation`, on `main`, working tree clean, in sync with
  `origin/main` (0/0). Root worktree only (after cleanup, below).
- **Re-pin:** `pipx install --force 'spec-kitty-cli @ git+…@78bc2307…'` → clean upgrade
  to `spec-kitty-cli 3.2.5`; tracer doctrine (templates + procedure) verified present
  in the new build.
- **Orphan-worktree cleanup (operator-approved).** Two leftover coordination worktrees
  from *completed* missions were present at start —
  `.worktrees/felix-admin-cron-path-fix-01KWQTY3-coord` (#656, closed) and
  `.worktrees/observation-digest-repoint-01KWS2E2-coord` (#659, mission merged) — each
  with only workflow-metadata drift (`.gitignore`, `.kittify/metadata.yaml`), no code
  at risk. `spec-kitty merge` normally removes coordination worktrees at close; these
  two missed it (the documented v323 post-merge-leftover pattern). Kent approved full
  cleanup; removed both worktrees + their `kitty/mission-*` branches via
  `git worktree remove --force` + `git branch -D`. Reached the v323-ideal clean
  pre-flight (root worktree only). See friction P1 below.

### Pre-flight friction observations (to transcribe into tracers post-create)

- **P1 — orphan coordination worktrees + accumulating workspace context.** Beyond the
  two removed coord worktrees, `.kittify/workspaces/` holds **~180 stale lane-context
  JSON files** going back to mission `003` — spec-kitty is not pruning per-lane
  workspace context at merge across the entire mission history. It's a workflow-managed
  directory (never hand-edited), so this is a standing observation, not a fix here. A
  candidate spec-kitty gap: `merge` should prune both the coordination worktree and its
  `.kittify/workspaces/*.json` entries; missing this leaves unbounded cruft that could
  confuse lane resolution or "is a mission active?" detection.
- **F1 (carried) — version-string non-granularity.** `upgrade --agent-check` reports
  `installed=3.2.5, latest=3.2.4 (pypi), action=none`; correct, but the string can't
  tell an operator *which* main build is installed or what fixes it carries. Pin by
  commit. (Standing finding from prior runs; re-confirmed.)
- **F2 (carried, EVOLVED) — tracer scaffolding.** In prior runs the retrospective
  ingestor consumed `traces/*.md` but nothing scaffolded/seeded them. As of #2203 the
  tracer lifecycle is now shipped **doctrine** (procedure + 3 templates), but it remains
  **agent-driven** — still no CLI scaffolder at `mission create`. The operator must hand-
  copy the templates into `kitty-specs/<mission>/traces/`. Watch at seed: the doctrine
  template names (`tooling-friction.md`/`approach.md`/`design-decisions.md`) differ from
  the prior `*-trace.md` convention; verify the retrospective ingestor's filename→bucket
  behavior still matches.
- **A1 (approach, positive).** `branch-context --json` was clean and deterministic:
  correctly flagged `current_is_primary=true` on `main`, `recommended_strategy=
  feature-branch` with a clear PR-bound reason. No git probing needed.
- **A2 (approach, positive).** `upgrade --agent-check` returned `action=none` — no
  spurious downgrade-to-PyPI prompt this run (we deliberately run ahead of PyPI on a
  main pin; the comparator handled installed>latest correctly).

---

## Timeline

### Specify

**Startup Upgrade Check** → `action=none, up_to_date` (see F1/A2). No upgrade run.

**Branch-context** (`branch-context --json`): `current_branch=main`,
`current_is_primary=true`, `target_branch=main`, `recommended_strategy=feature-branch`,
reason "PR-bound missions should start on a dedicated feature branch." Matches the
pre-decided feat→main PR plan; will create with `--pr-bound --branch-strategy
already-confirmed --start-branch feat/<slug>`.

**Charter context** (`charter context --action specify --json`): `mode=compact`,
template `software-dev-default`, paradigm `c4-incremental-detail-modeling`, directives
001/003/010/024/031/033/034. Carried pre-existing charter diagnostic: "Charter declared
additional tool(s) beyond the runtime registry: pytest, python" — the known
tool-registry vs DEFAULT_TOOL_REGISTRY mismatch (not introduced by us).

**Brief detection:** no `.kittify/mission-brief.md` / `ticket-context.md`. The #658
issue body is the input (per the "issue is input, not the spec" rule).

**Discovery — two spec-level forks resolved (Kent, live).** The #658 body is a thorough
brief, so discovery was focused gap-filling. Kent first re-scoped a false coupling
(#658 was mistakenly tied to the Stijn/#2341 PR-landing trial; decoupled — #658-as-PR
lands our own mission output, not a contributor fork PR, so it's a hollow #2341 trial;
Stijn's trial runs separately on a real spec-kitty-family PR). Then two genuine forks:

1. **Guard semantics → anchor-for-portability (NOT gateway-reliance).** Kent: "allow for
   the possibility of `-m scripts.` running outside the gateway." So a gateway-provided
   PYTHONPATH is NOT a pass; invocations must be robust regardless of launch context.
   **Trap surfaced live:** naive anchoring as `cd /home/claude/kg-automation && …` would
   HARDCODE a checkout path — itself one of the three assumptions #658 exists to kill. So
   the canonical anchor form must resolve repo-root robustly (thin wrapper / declared
   root env consumed explicitly), NOT a baked-in `cd`. Spec requirement: invocations
   resolve PYTHONPATH/cwd/checkout explicitly + robustly, work with or without the
   gateway, without hardcoding a checkout. (Exact form = plan-phase + Codex target.)
2. **Scope → all-in-one, no cruft.** Kent: "make Felix reliable, consistently
   implemented, and no cruft in this area." → convert/disposition EVERY in-scope
   invocation across all four felix-admin agents + redeploy all, not a bounded subset.

**Boundary confirmed (Kent's question):** the mission is ENTIRELY Felix-side. It touches
Felix agent prompts (`scripts/openclaw/agents/**`), Felix tooling (pytest guard +
`validate_workspace.py`), Felix CI, and Felix's own `scripts/` invocations. It alters NO
native OpenClaw element — not the core/binary/package, not `~/.openclaw/skills/` (reads
OK, out of scope), not openclaw.json, not `openclaw-gateway.service` (untouched here;
#656 already changed its PYTHONPATH). Notably, anchor-for-portability *reduces* Felix's
coupling to a native OpenClaw element (the gateway PYTHONPATH) — cleaner fence, not just
staying on our side of it.

**Mission created** — `agent-runtime-env-guardrails-01KWT3GH` (mid8 `01KWT3GH`, ULID
`01KWT3GHVB4X49DKG02FVEQYCQ`), `mission_type=software-dev`, `topology=coord`,
coordination branch `kitty/mission-agent-runtime-env-guardrails-01KWT3GH`, on
`feat/agent-runtime-env-guardrails` (created + switched via `--start-branch`,
`--pr-bound --branch-strategy already-confirmed`). Branch contract: target/base/merge all
`feat/agent-runtime-env-guardrails`; `branch_matches_target=true`. Later lands via PR
feat→main. spec.md scaffold written untracked (1 line; commit boundary = mine).

**Watch item:** topology=coord + coordination branch created. In v323 (also an unprotected
feature-branch start) `spec-commit` landed DIRECTLY on feat, sidestepping coord-worktree
materialization (the read/write-split source of the #2115 friction family). Watch whether
`spec-commit` lands direct on feat here too (unprotected primary → commit should be
direct per the Commit Boundary rule).

**Tracers seeded** at `kitty-specs/agent-runtime-env-guardrails-01KWT3GH/traces/`
(`tooling-friction.md`, `approach.md`, `design-decisions.md`) — doctrine templates copied
+ initial context filled; pre-flight friction observations (P1/F1/F2) transcribed into
`tooling-friction.md`.

### Spec authoring

**Ground-truth scan (design-phase-research discipline — probe live, don't trust the
issue body's "~30").** `grep -rc 'python3 -m scripts\.'` across `scripts/openclaw/agents/`
confirmed **exactly 30** occurrences, concentrated: capture/AGENTS.md **14**,
escalation **7**, habits **5**, tasker **2** (=28), plus **capture/AGENTS.md.tmpl 1** and
`validate_workspace.py` 1. Two sharpening findings: (a) the capture **`.tmpl`** carries an
invocation → must be fixed or a re-render regresses the live prompt (the v323 lesson,
re-confirmed as a live risk); (b) `felix-admin-calendar`, `felix-doc-auditor`, `main` have
**zero** `-m scripts.` invocations → they are **audit-only** (FR-008), not conversion
targets. This tightened FR-005 scope to the 4 agents + the capture `.tmpl`.

**Spec authored** — 9 FR / 4 NFR / 5 C / 5 SC + User Scenarios (3 + edge cases) + Domain
Language + Assumptions + Architecture Impact (change class `agent-prompt-changed` via
signal-to-doc-map; doc targets enumerated; rebaseline Yes/auto). The anchor-for-portability
decision and the no-hardcoded-checkout trap are encoded as FR-005(c) + an explicit edge
case; the exact canonical anchor mechanism is deferred to plan as a designated Codex
target (Assumptions). No `[NEEDS CLARIFICATION]` markers.

**Quality checklist** — all items pass, with two honest notes rather than false purity:
the "technology-agnostic / non-technical-stakeholder" items are inherently strained for a
Tier-3 infra/tooling mission whose subject matter IS technical (pytest, `-m scripts.`,
PYTHONPATH); requirements are still framed at the behavioral/outcome level, deferring the
guard's internal algorithm to plan (same accepted precedent as the #325 infra spec).
SC-004 keeps concrete health checks (`prescan --self-check`, cron status) on purpose —
tech-agnostic restatement would lose testability.

🎯 **Positive: `spec-commit` landed DIRECTLY on `feat/agent-runtime-env-guardrails`**
(commit `047a251`, exactly the 5 authored files) — **no coordination-worktree
materialization**, only the root worktree on feat. This reproduces the v323 headline
positive: an unprotected feature-branch start keeps `spec-commit` direct, sidestepping the
protected-`main` coord read/write split that is the #2115/#1716 friction family's root.
The watch item (topology=coord + coord branch created at `create`) did NOT translate into a
coord materialization at spec-commit. spec-kitty's own state files (`meta.json`,
`status.events.jsonl`, `tasks/`) correctly remain uncommitted (they ride the next
lane-transition auto-commit; not hand-committed).

**Phase scorecard (specify): ZERO interventions, ZERO hand-cranking, ZERO tool failures,
ZERO coord splits.** Specify complete; proceeding to plan.

### Plan

**CLI setup clean.** `charter context --action plan` (compact, same carried tool-registry
diagnostic), `context resolve --action plan --mission <handle>`, `setup-plan`. First
`setup-plan` correctly `blocked` (plan.md Technical Context not yet substantive) — entry
gate (spec committed+substantive) passed. Branch contract restated: all
`feat/agent-runtime-env-guardrails`, `branch_matches_target=true`.

**Design-phase research (probe live — the highest-value work of the phase).** A ground-truth
scan of `scripts/openclaw/agents/**` overturned the issue body's clean "~30 `-m scripts.`"
framing and reshaped the design:
- **The fleet is INCONSISTENT.** capture = **bare** `python3 -m scripts.inbox.…` (relies on
  ambient gateway PYTHONPATH); habits = **hardcoded** `cd /home/claude/kg-automation && …`
  — i.e. habits is "anchored" but via the FORBIDDEN checkout-path, which is *itself* the
  #658 assumption we're killing. escalation/tasker = bare.
- **A third invocation style the body didn't enumerate:** direct `python3
  /home/claude/kg-automation/scripts/…py` abs-path invocations (calendar, tasker, habits,
  `.tmpl`s) — hardcoded checkout on the same axis.
- **Gateway env, precisely:** `openclaw-gateway.service` sets `HOME`+`PATH`; the #656
  drop-in adds `PYTHONPATH=/home/claude/kg-automation`. No abstract root var — PYTHONPATH
  *is* the root. This unlocked the reuse-PYTHONPATH canonical form.
- **`~`/HOME WRITE sub-class already clean:** writes use absolute `/home/kgale/second-brain/…`
  (post-#659); remaining `~` refs are reads or the `_private/` prohibition. FR-006 → a
  confirm-clean audit, not a conversion.
- **Repo already has the robust idiom** (`REPO_ROOT="$(git rev-parse --show-toplevel)"` in
  install-hooks.sh) and the correct shape (`cd "$ROOT" && PYTHONPATH="$ROOT" python3 -m …`
  in the credential deploy scripts) — but git-rev-parse fails when cwd drifts OUTSIDE the
  repo (the exact #656 case), so it's not the answer for the portable form.

**Two decisions surfaced to Kent (minted via decision CLI, resolved, verify `clean`):**
- **D1 (scope) → include abs-path invocations.** The checkout-path axis manifests as both
  `-m scripts.` and abs-path; converting only the former leaves cruft. Kent: no cruft.
- **D2 (canonical form) → reuse gateway PYTHONPATH, fail-loud `${PYTHONPATH:?…}`.** No
  gateway/systemd change (preserves the "no native OpenClaw element altered" boundary).
  Surfaced a boundary nuance: the cleaner-semantics alternative (`FELIX_REPO_ROOT` var)
  would touch the gateway unit; Kent chose the minimal-blast-radius reuse. (I flagged this
  live because it revised a boundary claim I'd made.)

**Plan artifacts authored:** `plan.md` (Technical Context substantive; Charter Check PASS,
no violations; **6-item IC map** — IC-01 shared checker / IC-02 Test-CI guard / IC-03
validator fold / IC-04 conversion / IC-05 fleet audit+docs / IC-06 deploy+verify),
`research.md` (R-01..R-06 incl. the reuse-PYTHONPATH single-path trade-off flagged as a
Codex target + the prose-vs-command false-positive risk, the v323 F4 class), `data-model.md`
(Finding/ViolationKind model + canonical-form predicate + the command-recognizer),
`contracts/checker-contract.md` (checker API + both consumers + waiver mechanism),
`quickstart.md`. Second `setup-plan` → `phase_complete=True`, auto-committed plan.md
(`3189c72e`); Phase-1 artifacts via `spec-commit` (`5b31204`).

🎯 **Still landing directly on `feat` — no coord materialization through the entire plan
phase** (spec-commit "committed to feat/agent-runtime-env-guardrails"). spec-kitty state
(`meta.json`, `status.events.jsonl`, `tasks/`, `decisions/`) correctly remains uncommitted
(rides the next lane-transition auto-commit).

**Phase scorecard (specify→plan): ZERO interventions, ZERO hand-cranking, ZERO tool
failures, ZERO coord splits.** Plan hit its ⛔ MANDATORY STOP cleanly (no tasks generated).

**Next: mandatory post-plan Codex review** (review-and-fix, before `/spec-kitty.tasks`).

### Post-plan Codex review

Dispatched `codex exec --sandbox read-only` (gpt-5.5) against spec.md + plan.md + research.md
+ data-model.md + contracts/checker-contract.md, cross-checked against the real agent
prompts + validator + the #656 gateway drop-in. Read-only was the right sandbox: a post-plan
review only reads + emits findings; the `spec-kitty-review` profile's `danger-full-access`
exists solely for the implement/review loop's `.git` writes (which a review doesn't do).
Note: the profile is NOT registered in `~/.codex/config.toml` (migrated to a separate file);
`-p spec-kitty-review` would not resolve — read-only sidestepped that entirely.

🎯 **MARQUEE: Codex returned REQUEST-CHANGES with 3 HIGH + 5 MED + 1 LOW — ALL valid**, several
would have caused real implementation bugs. This is the single strongest validation of the
mandatory post-plan checkpoint on this run. Every finding was folded (commit `95d28ed`):

- **HIGH-1 (recognizer false-greens capture).** My R-03 recognizer excluded inline-backtick
  spans as "prose" — but capture's REAL commands are inline imperatives ("Invoke
  `python3 -m scripts.inbox.prescan`", lines 78/82/90/94-96/113/115/127/131/135/152/221).
  Would have false-greened ~14 invocations while SC-003 claimed all converted. → Recognizer
  rewritten: classify concrete inline-imperative commands; exclude only `<placeholder>`-bearing
  docs + HTML comments.
- **HIGH-2 (fail-loud ≠ "works without gateway").** Spec wording overpromised; `${PYTHONPATH:?}`
  fails outside the gateway unless PYTHONPATH is exported. → Reconciled spec/SC to "works
  under gateway OR with exported PYTHONPATH; fails LOUD, never silent/wrong-checkout" — which
  is Kent's actual "allow running outside gateway" intent (don't silently break).
- **HIGH-3 (non-cd form doesn't fix cwd drift).** My preferred non-cd form fixed imports but
  left cwd drifted — a helper with relative I/O still breaks (the #656 mode). → **Flipped the
  canonical form to the cd form** `cd "${PYTHONPATH:?}" && …` (fixes cwd + imports) + require
  absolute helper args + a non-repo-cwd smoke test. A genuine design reversal Codex earned.
- **MED-1** `python` (not just `python3`) abs-path lines → ViolationKind/D1 cover both.
- **MED-2** multiline/continuation commands → recognizer joins logical commands, reports start line.
- **MED-3** `CheckResult.passed` → the real dataclass field is **`ok`**; following the contract
  literally would have broken the validator. Fixed in data-model + contract.
- **MED-4** calendar converted but had no health check → added to SC-004/IC-06.
- **MED-5** doc-auditor both "audited" (FR-008) and validator-excluded → dispositioned as
  RETIRED (scripts-first, no live agent), not an unverifiable audit.
- **LOW-1** plan said Python 3.12 but Test CI runs 3.11 (C-001 forbids workflow change) →
  checker must be 3.11-compatible.

Decisions verify still `clean` (no NEEDS-CLARIFICATION markers introduced). Folded commit
landed **direct on feat** (`95d28ed`) — still no coord split.

**Phase scorecard (specify→plan→post-plan-review): ZERO tool failures, ZERO coord splits;
the ONE substantive design reversal (cd form) came from Codex, exactly as the checkpoint is
designed to produce.** Proceeding to `/spec-kitty.tasks`.

### Tasks

`context resolve` + `check-prerequisites` clean (`branch_matches_target=True`, tasks_dir
resolved). Decomposed the 6-item IC map into **6 WPs / 26 subtasks**:
- WP01 (lane-a, foundational) — shared checker `env_assumptions.py` + unit tests · FR-001/002/007
- WP02/03/04 (parallel after WP01) — convert capture / habits+escalation / tasker+calendar+main · FR-005/006/008
- WP05 (after WP02-04) — Test-CI fleet guard + `validate_workspace` fold + doc-auditor disposition · FR-003/004/008
- WP06 (after WP05) — docs (#167 + arch) + deploy manifest 0010 + verify · FR-009
Profiles pre-assigned: python-pedro (WP01/05), implementer-ivan (WP02/03/04), curator-carla
(WP06); impl agent claude / claude-sonnet-4-6 (Codex reserved for the adversarial review pass).
`owned_files` non-overlapping; all `code_change`.

`map-requirements --batch` → **9/9 FRs mapped, `unmapped_functional: None`**.

**Friction F3 — finalize ownership gate (documented gotcha, cleared by following the tool).**
First `finalize-tasks --validate-only` FAILED: *"Ownership validation failed: literal-path
owned_files entries match zero files. Fix the paths or add them to 'create_intent'."* — the
NEW files (env_assumptions.py, the two new test files, the 0010 manifest) were in `owned_files`
but not yet on disk. Added `create_intent:` for the new-file WPs (WP01/05/06) — the known 3.2.4
"create_intent + owned_files both list new files" lesson. Re-run → `validation_passed`.

🎯 **`finalize-tasks` (mutating) SUCCEEDED — commit `3bd5a66b`, 6 lanes computed
(lane-a…lane-f), `collapse_report` 0 merges** (correct — the WPs have distinct surfaces). Still
committing direct on feat, no coord materialization through the entire planning arc.

**Phase scorecard (specify→plan→post-plan-Codex→tasks): ZERO tool failures, ZERO coord splits,
ONE design reversal (all from Codex), ONE documented ownership gate cleared by following the
tool.** Tasks hit its ⛔ MANDATORY STOP. Proceeding to implement (auto-drive; the handoff
question is pre-answered by the drive-the-arc instruction).

### Implement

**Analysis gate + record-analysis.** `implement WP01` correctly gated on
`analysis_report_required` (legit, not a block). Authored the `analysis-findings/v1`
carrier (2 LOW + 1 info, verdict computed `ready`), `record-analysis`. **Friction F4 —
record-analysis dirty-tree preflight (#2102 class).** First `record-analysis` refused:
*"Refusing to record analysis report with pre-existing dirty working tree."* — dirty tree
was spec-kitty's OWN uncommitted state (`meta.json` M + `decisions/` from the plan-phase
decision CLI). Committed it via `spec-commit` (explicit file paths — spec-commit's backstop
rejects passing a bare directory) → re-record → `verdict: ready`. Candidate spec-kitty gap:
the preflight should ignore the workflow's own uncommitted state.

**WP01 — env-assumption checker (`env_assumptions.py`).** Implemented directly in the
lane-a worktree per the data-model/contract with all Codex fixes: logical-command recognizer
(joins backslash continuations, flags inline-imperative backtick commands, excludes
`<placeholder>` docs + HTML comments), cd-form compliance predicate, 4 ViolationKinds
(python+python3 abs-path), waiver parsing, `scan_agents_root` reusing the validator's real
`SUSPENDED_WORKSPACES`/`NON_WORKSPACE_DIRS` (the WP prompt's `EXCLUDED` was my approximation
— used the actual symbols). **21 unit tests green** covering every Codex-flagged edge case.

🎯 **The checker validated on REAL data — and caught a bug the grep missed.** Running it over
the unconverted fleet: **44 findings across 6 agents** (23 bare / 16 abs-path / 5 hardcoded-cd)
— vindicating the D1 scope expansion (the "~30 -m scripts." framing undercounted). Notably it
flagged a **hardcoded abs-path in `main` (line 85)** that my earlier `grep -m scripts.` reported
as 0 invocations — so `main` is a real conversion target, not audit-only. Ground-truth via the
tool beats ground-truth via grep.

**Friction F5 — approve-gate chain (documented gates, cleared by following the tool).** Moving
WP01 for_review→approved surfaced the #2115 coord/primary-split family, one gate at a time:
(a) `move-task for_review` preflight required committing accumulated status artifacts (tasks.md
`[D]` markers, analysis-report.md) — `spec-commit`ed; (b) `move-task approved` hit the
**issue-matrix gate** (#1817/#2115) — auto-scaffolded rows for the 5 issues my spec references
(#656/#659/#167/#587/#343), all dispositioned `verified-already-fixed` (each is prior/completed
work this mission BUILDS ON, not fixes) with evidence refs → `spec-commit` → **WP01 approved**.
All gates were documented + cleared by following the tool (no hand-cranking of workflow actions).

**WP01 DONE + approved.** Commits: checker `6bfaceff` (in lane-a). MVP (the prevention
mechanism) is in. Proceeding to the conversion WPs (WP02-04, parallel, verified by this checker).

**WP02/03/04 — conversions via 3 parallel implementer sub-agents (lanes b/c/d).** Each converted
its agents to the canonical form + self-verified with the WP01 checker (0 findings) before
committing. Results: capture 19 (13 AGENTS.md inline-imperative + 6 `.tmpl`, incl. prescan's
piped invocation → no-cd path form); habits+escalation 16 (all 5 habits hardcoded-`cd`
de-hardcoded + 3 abs-path; 7 escalation bare + 1 abs-path, list indentation preserved);
tasker+calendar+main 9 (calendar's piped `validate_calendar_event` correctly using the no-cd
`"${PYTHONPATH:?}/scripts/…"` form — the exact Codex MED-4 case; `python`/`python3` preserved).
Dispatching sub-agents kept orchestrator context lean; each got the canonical form + checker
self-verify loop inlined. All three approved through the gates (status-commit each; the
issue-matrix gate passed on WP02-04 without re-authoring — WP01's fill persisted).

**WP05 — Test-CI fleet guard + `validate_workspace` fold + doc-auditor disposition.**
`check_runtime_env_assumptions()` uses the real `.ok` CheckResult field (Codex MED-3) with a
**lazy import** of `scan_file` to break the import cycle (env_assumptions imports the exclusion
sets from validate_workspace). Fleet guard scans `scan_agents_root` → 0. doc-auditor
dispositioned RETIRED in the SUSPENDED_WORKSPACES comment.

🎯 **FINDING F6 — the domain checker is necessary but NOT sufficient; the FULL test suite caught
a real regression the checker couldn't.** WP05's `pytest scripts/openclaw/agents/tests/` showed
**43 pass, 2 FAIL** — `test_agents_md_size.py` (a prior mission's hard 12K cap on
`main`/`calendar` AGENTS.md). My verbose canonical guard message (`${PYTHONPATH:?PYTHONPATH not
set — run under openclaw-gateway or export the checkout root}`, ~74 bytes, em-dash = 3 bytes)
repeated per invocation pushed calendar (12167) + main past 12K. The env-assumption CHECKER was
happy (the long form is compliant) — only the independent size test caught it. **LESSON: per-WP
approval must run the whole suite, not just the domain verifier; I approved WP02-04 on
checker-clean alone and missed this.** Fix: shortened the canonical message globally to
`${PYTHONPATH:?PYTHONPATH unset}` across all converted files (calendar → 11923, main → 11949,
all owned-file scans still 0). This also serves Kent's "consistently implemented, no cruft" goal.

🐛 **FINDING F7 — stale-lane propagation gap (candidate spec-kitty issue).** The message-shorten
fix committed to the already-approved conversion lanes (b/c/d). WP05's lane-e had already merged
those lanes' OLD commits at approval time. `spec-kitty implement WP05` (the sanctioned stale-lane
refresh) merged the **mission branch** — which does NOT yet carry the lane-branch fix commits
(they reach mission only at final merge) — so lane-e stayed stale (calendar 12167, size tests
red). Resolved by a manual `git merge` of the updated conversion lane branches into lane-e
(disjoint files — validator/tests vs agent prompts — clean, no conflicts) → calendar 11923, **45
tests green**. The final `spec-kitty merge` will rebase everything correctly regardless; the
manual merge was only to verify WP05 green in its own lane before approval. Candidate gap: the
CLI stale-refresh should follow dependency **lane HEADs**, not just the mission branch, when a
dependency lane advances post-approval.

**WP05 approved.** Recurring friction (each cleared by following the tool): analysis went stale
after every WP's `mark-status` (touches tasks.md) → re-record before the next `implement`;
for_review/approved each needed a status `spec-commit`. All documented-gate taxes, no
hand-cranking of workflow actions.

**WP06 — deploy manifest + entrypoint + #167 doc (via curator-carla sub-agent).** Created
`deploys/queued/0010-agent-runtime-env-guardrails.yaml` + a self-bootstrapping entrypoint
`scripts/deploy/redeploy-agent-prompts-658.py` (shebang-run, `sys.path` bootstrap + `os.chdir`
to repo root, maps `--dry-run`/`--apply` → `deploy_agent_prompts.main`; itself free of the bug
the mission kills). Added the guardrail subsection to `docs/runbooks/openclaw-agent-setup.md`.
🎯 **Sub-agent caught a spec-vs-canonical discrepancy:** the spec's Architecture Impact said
"Rebaseline: Yes/completed", but the canonical `audited-surfaces.json` (`openclaw-agent-prompts`)
has `affected_baselines:[]`/`rebaseline_required:false` — audit.sh hashes only `openclaw.json`,
NOT deployed AGENTS.md (#621). Per "machine-readable wins", corrected the merge record to
**"Rebaseline: not required — agent prompts are an unmonitored audited surface (#621)"**. Also
noted felix-deployer.service has no PYTHONPATH (WorkingDirectory=/home/claude/kg-automation), so
verification commands export `PYTHONPATH="$(git rev-parse --show-toplevel)"` — the deployer's env
≠ the gateway's. WP06 validated: manifest schema + tier-guard pass; entrypoint dry-run from `/tmp`
exits 0 (cwd-independent). 45 tests green in lane-f. Approved.

### Accept + Merge

**Accept** — `all_done: True` but `ok: False` on the **acceptance-matrix.json** `pending` verdict
(9 FR TODO scaffold). Authored real FR-001..009 verdicts (all `pass`, evidence = the actual
tests/commits/artifacts) + `overall_verdict: pass`. **Friction F8 (v323 lesson re-confirmed):
accept reads the matrix from the COORD worktree copy, not the main checkout** — filling only the
main copy left it `pending`; had to copy the filled matrix into
`.worktrees/…-coord/…/acceptance-matrix.json` and commit on the coordination branch. Then accept
→ **"No outstanding acceptance issues"**, acceptance commit `7db58b8`.

**Merge** — `spec-kitty merge`: gate evidence/risk(0.24)/dependency all ✓. **Friction F9 (#1826
class):** merge aborted on lane-a because the coord worktree held an uncommitted `meta.json` (the
accept step wrote it) — `git reset --hard` would destroy it. Committed it on the coordination
branch → `spec-kitty merge --resume` completed cleanly: **squash merge `eb4aa5f1` → feat**, all 6
lane worktrees + branches removed, done transitions + retrospective captured. Leftover: the coord
worktree blocked the mission-branch deletion (the v323 pattern) → cleaned up manually
(`git worktree remove --force` + `git branch -D`).

**Post-merge verification on feat:** full agent suite **45 passed**; fleet checker **0 findings**;
manifest present; converted prompts under the 12K cap. Merged diff vs main = 47 files (16
substantive code/prompt/deploy + the kitty-specs artifacts + this journal).

### Post-merge Codex review

Dispatched `codex exec --sandbox read-only` against the complete merged diff (1186-line scoped
patch over the 16 substantive code/prompt/deploy files, excluding kitty-specs planning artifacts +
this journal). It read the actual merged feat state.

🎯 **Codex returned REQUEST-CHANGES with 2 MED — both valid false-NEGATIVES in the checker
itself** (the prevention mechanism, so worth fixing before feat→main even though the CURRENT
fleet exhibits neither shape):
- **MED-1 — line-level anchor over-governs.** `anchored` was computed for the whole logical line
  and suppressed EVERY `-m scripts.` finding on it, so an invocation *preceding* the `cd`
  anchor (`python3 -m scripts.bad && cd "${PYTHONPATH:?}" && python3 -m scripts.ok`) — which runs
  before the cd — was wrongly passed. Fix: the anchor must appear BEFORE the invocation
  (`_PYTHONPATH_ANCHOR_RE.search(text[:m.start()])`), not merely somewhere on the line.
- **MED-2 — quoted hardcoded abs-path missed.** `_ABS_PATH_RE` matched `python3 /abs/…py` but not
  `python3 "/home/claude/kg-automation/…py"` (Codex empirically verified the quoted form returned
  no finding). Fix: allow an optional quote before the path.

Both folded on feat (commit `c84769d9`) + 3 regression tests. 🎯 **After hardening the checker, the
fleet STILL scans 0 findings** — confirming the conversions are genuinely compliant, not merely
passing a lax check (a lesser check passing everything would have been the failure mode). 48 tests
green. Codex found NO semantic-breakage / consistency / deploy-correctness issues in the
conversions themselves — the calendar pipe form, the .tmpl lockstep, the validator fold, and the
self-bootstrapping entrypoint all passed its scrutiny.

**Both mandatory Codex checkpoints paid off:** post-plan caught a design reversal + an
implement-breaking bug before any code; post-merge caught 2 checker false-negatives before the PR
to main. Neither would have surfaced from the per-WP checker-clean signal alone.

### PR feat→main

Pushed `feat/agent-runtime-env-guardrails` to origin (was unpushed; 38 commits ahead of main —
the full mission incl. all spec-commits + WP commits + journal). Opened **PR
kentonium3/kg-automation#664** (feat → main) with a summary body (what/why, deliverables, scope
decisions, verification, rebaseline-not-required, journal pointer). Body auto-closes #658 on
merge (canonical `kentonium3/kg-automation#658` per the auto-close format rule). **This is the
first PR-landed change in kg-automation** (departure from the usual push-to-main / spec-kitty
merge-to-main) — the whole point per Kent: generate journal + analyzer data over a PR-involved
workflow. **Kent merges** (agent never `gh pr merge`s). Internal-repo PR → copy-approval
exception applies (no pre-review of the PR body).

### Post-mission analyzer gap-analysis (objective 4)

_(spec-kitty-analyzer vs journal + tracers — to be appended)_
