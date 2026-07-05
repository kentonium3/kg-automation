# Tooling Friction Log

> Log every place the tooling fought you so it can feed the tooling-gap backlog.

**Prompting questions**
- What tooling or command did you have to work around?
- What blocked you unexpectedly, and how long did it take to unblock?
- Was this a known issue or something discovered fresh?

**Entry format:** `[YYYY-MM-DD][phase] SYMPTOM — anchor — disposition`

---

## Seed context (2026-07-05)

Tooling this mission touches: spec-kitty 3.2.5 (@ main `78bc2307`) full mission
workflow; the existing kg-automation **Test CI** (pytest) that the guard rides;
`scripts/openclaw/agents/validate_workspace.py` (the #587 workspace validator);
the `deploys/queued/` felix-deployer manifest pipeline; `codex -p spec-kitty-review`
for the two mandatory checkpoints; git worktrees (coord topology). The narrative
superset record is `docs/diagnostics/658-runtime-env-assumptions-dogfood-journal.md`.

## Entries

- `[2026-07-05][pre-flight]` Orphan coordination worktrees — `.worktrees/*-coord` for
  two COMPLETED missions (#656 closed, #659 merged) still present at start with metadata
  drift — `spec-kitty merge` should remove coord worktrees at close but didn't — operator
  removed them manually (`git worktree remove --force` + `git branch -D`); candidate
  spec-kitty gap.
- `[2026-07-05][pre-flight]` Workspace-context cruft — `.kittify/workspaces/` holds ~180
  stale per-lane `*.json` files back to mission 003 — `merge` isn't pruning per-lane
  workspace context across the mission history — left as-is (workflow-managed dir, never
  hand-edited); candidate spec-kitty gap: prune both coord worktree AND its
  `workspaces/*.json` at merge.
- `[2026-07-05][pre-flight]` Version-string non-granularity (F1, carried) — `upgrade
  --agent-check` reports `installed=3.2.5, latest=3.2.4(pypi), action=none` — the string
  can't express WHICH main build is installed — mitigation: pin by commit (`78bc2307`),
  not version.
- `[2026-07-05][implement]` record-analysis dirty-tree preflight (#2102 class) — `record-analysis`
  refused on a tree dirty only with spec-kitty's OWN uncommitted state (meta.json + decisions/) —
  had to `spec-commit` the workflow's own state first — candidate gap: preflight should ignore
  workflow-owned uncommitted state.
- `[2026-07-05][implement]` spec-commit dir-vs-files backstop — `spec-commit <dir>` fails
  ("staging area contains unexpected paths") when a directory is passed; must pass explicit file
  paths — minor UX friction, cleared by listing files.
- `[2026-07-05][implement]` approve-gate chain (#2115/#1817 coord-split family) — for_review
  preflight wants status artifacts committed; approved gate wants issue-matrix.md verdicts filled
  (auto-scaffolded `unknown` rows for every issue referenced in spec.md). Both cleared by
  populate + spec-commit — the recurring coord/primary read-write-split tax, one gate at a time.
- `[2026-07-05][pre-flight]` Tracer scaffolding still agent-driven (F2, carried/evolved) —
  #2203 shipped the tracer lifecycle as doctrine (procedure + 3 templates) but there is
  still NO CLI scaffolder at `mission create` — operator hand-copied the templates into
  `traces/` — candidate: auto-scaffold `traces/` at create. Also watch: doctrine template
  names (`tooling-friction.md` etc.) differ from the prior `*-trace.md` convention the
  retrospective ingestor was built against — verify bucketing at close.
