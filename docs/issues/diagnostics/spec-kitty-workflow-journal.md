---
title: Spec-Kitty Workflow Journal
doc_type: diagnostic
status: active
---

# Spec-Kitty Workflow Journal

**Purpose**: Chronological log of suspected or actual spec-kitty workflow errors, unexpected behaviors, and edge cases encountered during feature development. Each entry captures enough evidence (commands run, JSON outputs, git state, file contents) to retrace steps and diagnose root causes if downstream errors occur.

**Standing directive**: When a spec-kitty workflow produces unexpected behavior — even if not a hard error — append an entry here before attempting any compensating action. Do not use git or other tools to simulate what spec-kitty should have done.

**Related**:
- `docs/issues/diagnostics/spec-kitty-feedback/` — individual incident reports intended for upstream reporting to spec-kitty-cli
- This file is a running internal log; individual entries may graduate to standalone reports under `spec-kitty-feedback/` if they warrant upstream attention

---

## Entry Template

```markdown
## YYYY-MM-DD — {short title}

**Feature**: {NNN-slug}
**Spec-kitty version**: {x.y.z}
**Workflow step**: {specify | plan | tasks | implement | review | accept | merge}
**Severity**: {observation | soft-error | hard-error}

**What I expected**: ...

**What actually happened**: ...

**Evidence**:
- Commands run: ...
- JSON / output excerpts: ...
- Git state: ...

**Hypothesis**: ...

**Resolution**: {pending | user-decision | bug-filed | resolved-in-vX.Y.Z | won't-fix}

**Downstream impact**: ...
```

---

## 2026-04-04 — auto_commit did not capture LLM-authored spec edits during /spec-kitty.specify

**Feature**: 015-documentation-architecture-rationalization
**Spec-kitty version**: 3.0.3
**Workflow step**: specify
**Severity**: observation (behavior unclear, no hard error)

**What I expected**:
With `.kittify/config.yaml` setting `auto_commit: true`, I expected the artifacts produced during `/spec-kitty.specify` (populated `spec.md`, updated `meta.json`, new `checklists/requirements.md`) to be auto-committed on the target branch, matching the commit pattern of prior features (e.g., F014) where `spec.md` content landed in commits titled "Add spec for feature ###-slug".

**What actually happened**:
`spec-kitty agent feature create-feature …` created the feature directory scaffold and committed two empty/template files to `main`:
- `6c35834 Add spec for feature 015-documentation-architecture-rationalization`
- `d574abb Add meta for feature 015-documentation-architecture-rationalization`

Subsequent LLM edits via the Write tool — setting `mission: documentation` in `meta.json`, writing the full spec body to `spec.md`, and creating `checklists/requirements.md` — were NOT auto-committed. The status `tasks/` directory and `status.events.jsonl` file (scaffolded by `create-feature`) also remained untracked.

**Evidence**:
- Config: `/Users/kentgale/repos/kg-automation/.kittify/config.yaml` contains `auto_commit: true` at top level (not nested under `agents`).
- `create-feature` JSON output (excerpt): `"write_mode": "update_existing_files", "next_step": "Read then update spec_file/meta_file; do not recreate with blind write."`
- `git status --short` after LLM edits:

  ```text
   M kitty-specs/015-documentation-architecture-rationalization/meta.json
   M kitty-specs/015-documentation-architecture-rationalization/spec.md
  ?? kitty-specs/015-documentation-architecture-rationalization/checklists/
  ?? kitty-specs/015-documentation-architecture-rationalization/status.events.jsonl
  ?? kitty-specs/015-documentation-architecture-rationalization/tasks/
  ```

- `git log --oneline -3`:

  ```text
  d574abb Add meta for feature 015-documentation-architecture-rationalization
  6c35834 Add spec for feature 015-documentation-architecture-rationalization
  c5a47d5 refactor: consolidate diagnostics and postmortems under docs/issues
  ```

**Hypothesis**:
spec-kitty's `auto_commit` mechanism only fires inside its own Python CLI code paths when spec-kitty itself writes a file. LLM-authored edits via the Claude Code Write tool bypass those hooks. It's unclear whether:
- The slash-command author expects the LLM to commit artifacts manually at the end of `/spec-kitty.specify`, or
- A later step (e.g., `/spec-kitty.plan`) detects and commits the staged edits, or
- auto_commit is meant to catch these and a regression / config-parsing issue is preventing that.

F014's git history shows its spec body DID land in a commit, so there's a path by which this normally works — just not visible from my seat.

**Resolution**: behavior clarified during `/spec-kitty.plan` on 2026-04-04. See Update below.

**Update (2026-04-04, after /spec-kitty.plan setup-plan)**:
`spec-kitty agent feature setup-plan` rewrote `meta.json` (to add `documentation_state`) and in doing so picked up the LLM-authored changes that were sitting in the working tree, committing them together. So auto_commit DOES catch LLM-edited files — but only when spec-kitty itself next writes to that file. `spec.md` remained uncommitted because no spec-kitty command writes to `spec.md` after `create-feature`.

**Revised hypothesis**: auto_commit creates one commit per spec-kitty-authored file write, and the staged working-tree state of that file is included in the diff. Files that spec-kitty never writes to (like the LLM-authored `spec.md` body) remain uncommitted indefinitely unless a later workflow step touches them.

**Downstream impact**: If `spec.md` is never written-to by spec-kitty again (likely), the LLM-authored spec body will remain uncommitted through tasks/implement/review. This may cause merge or accept to fail if those steps verify clean working tree.

---

## 2026-04-04 — False-positive documentation-generator detection during setup-plan

**Feature**: 015-documentation-architecture-rationalization
**Spec-kitty version**: 3.0.3
**Workflow step**: plan (setup-plan)
**Severity**: soft-error (incorrect data persisted to meta.json)

**What I expected**:
Documentation mission's `setup-plan` should only report generators it can verify are actually configured for the project (e.g., a `docs/conf.py` for Sphinx, a `jsdoc.json` for JSDoc).

**What actually happened**:
`setup-plan` output reported `generators_detected: [{jsdoc}, {sphinx}]` and wrote the same entries to `meta.json` under `documentation_state.generators_configured`, with empty `config_path` strings for both. Neither generator is actually configured in this repo — there is no `jsdoc.json`, no `conf.py`, no Sphinx doctree, no package.json jsdoc dependency. This is a false positive.

**Evidence**:
- `setup-plan --json` output: `"generators_detected": [{"name": "jsdoc", "language": "javascript", "config_path": ""}, {"name": "sphinx", "language": "python", "config_path": ""}]`
- meta.json commit `fbd28f5 Update generator config for feature 015-...` shows both generators persisted with empty config paths.
- Repo file search: no `jsdoc.json`, no `conf.py`, no `sphinx` config anywhere in the project.

**Hypothesis**: The documentation-mission scanner is heuristic-based (detects presence of Python/JavaScript source files and assumes the associated generators apply) rather than config-file-based. Empty `config_path` is the telltale — there's no config file backing either assertion.

**Resolution**: bug-filed-candidate — recommend filing upstream: "documentation-mission setup-plan should only report generators whose config files are actually present; empty config_path indicates a false positive".

**Downstream impact**: The plan template will reference these non-existent generators. If tasks/WPs are scaffolded from this data, work packages like "configure JSDoc" or "configure Sphinx" may be generated for generators that shouldn't be part of this feature. For F015, the feature isn't about code-doc generation at all — it's about human-authored markdown curation. Mitigating by flagging as N/A in plan.md.

---

## 2026-04-04 — Wrong mission template scaffolded for documentation-mission feature

**Feature**: 015-documentation-architecture-rationalization
**Spec-kitty version**: 3.0.3
**Workflow step**: plan (setup-plan)
**Severity**: soft-error (scaffolded artifact from wrong template)

**What I expected**:
With `mission: documentation` in `meta.json`, `setup-plan` should scaffold `plan.md` from the documentation-mission's plan template (`specify_cli/missions/documentation/templates/plan-template.md`), which has doc-appropriate fields (Divio types, generator setup, accessibility, WTD principles, Phase 0 = doc audit).

**What actually happened**:
`setup-plan` scaffolded `plan.md` using the software-dev default template. The resulting file has software-dev-oriented fields: `Language/Version`, `Primary Dependencies`, `Testing`, `Target Platform`, `Performance Goals`, `Source Code (repository root)` with `src/models/`, `src/services/`, `tests/contract/` layout — none of which apply to a documentation curation feature.

**Evidence**:
- Constitution context (`spec-kitty constitution context --action plan --json`): `"Template set: software-dev-default", "Paradigms: test-first", "Directives: TEST_FIRST"`
- The documentation mission IS installed: `specify_cli/missions/documentation/` contains `plan-template.md`, `spec-template.md`, `tasks-template.md`.
- Scaffolded `plan.md` (committed as `616bef5`) starts with `# Implementation Plan: [FEATURE]` and references `src/specify_cli/missions/software-dev/command-templates/plan.md`.

**Hypothesis**: The constitution template set (`software-dev-default`) overrides per-feature mission selection when scaffolding planning artifacts. `meta.json.mission: "documentation"` is recorded but not honored by `setup-plan`'s template selection.

OR: `setup-plan` looks at the constitution template set rather than the feature's mission to pick templates. If so, the docs for how mission selection interacts with constitution templates needs clarification.

**Resolution**: bug-filed-candidate — recommend filing upstream: "setup-plan should scaffold plan.md from the feature's mission-specific template (per meta.json.mission), not from the constitution's global template set".

**Downstream impact**: Plan must be hand-adapted from the software-dev template to fit a documentation curation feature. Downstream `/spec-kitty.tasks` may also scaffold from the software-dev tasks template, producing WP structures that don't fit doc curation work.

---

## 2026-04-04 — finalize-tasks overwrote LLM-authored dependency frontmatter (internal workflow inconsistency)

**Feature**: 015-documentation-architecture-rationalization
**Spec-kitty version**: 3.0.3
**Workflow step**: tasks (finalize-tasks, final step of /spec-kitty.tasks)
**Severity**: soft-error (execution DAG corrupted; downstream impact on /spec-kitty.implement)

**What I expected**:
The `/spec-kitty.tasks` slash-command prompt explicitly instructs the LLM to parse dependencies from tasks.md and write them to each WP's frontmatter, with this exemplar:

```yaml
---
work_package_id: "WP02"
title: "Build API"
dependencies: ["WP01"]  # Generated from tasks.md
---
```

I followed this instruction: for all 11 WPs, I parsed the tasks.md Dependencies sections and wrote the corresponding `dependencies` array to each WP's frontmatter before the finalization step.

I expected `finalize-tasks` to either (a) honor the LLM-authored `dependencies` frontmatter, or (b) re-parse tasks.md and match what the LLM wrote.

**What actually happened**:
`finalize-tasks` re-parsed tasks.md itself and OVERWROTE the LLM-authored frontmatter in 10 of 11 WPs. The `updated_wp_count: 0` field in its JSON output was misleading — the commit it created (`5dd07155`) shows `dependencies: [WP01, WP02]` → `dependencies: []` diffs on multiple WP files.

**Dependency outcomes**:

| WP | LLM-authored (in frontmatter + in tasks.md) | Post-finalize frontmatter |
|---|---|---|
| WP01 | `[]` | `[]` ✓ |
| WP02 | `[]` | `[]` ✓ |
| WP03 | `[WP01, WP02]` | `[]` ❌ |
| WP04 | `[WP02]` | `[]` ❌ |
| WP05 | `[]` | `[]` ✓ |
| WP06 | `[WP01]` | `[]` ❌ |
| WP07 | `[WP01, WP02, WP03, WP04, WP05, WP06]` | `[]` ❌ |
| WP08 | `[WP07]` | `[]` ❌ |
| WP09 | `[WP07]` | `[]` ❌ |
| WP10 | `[]` | `[]` ✓ |
| WP11 | `[WP02, WP07]` | `[WP01, WP02, WP07]` ⚠️ |

Only WP11's dependencies survived parsing, AND the parser spuriously added `WP01` that was not declared in tasks.md's WP11 Dependencies section.

**Evidence**:
- `finalize-tasks` JSON output: `"updated_wp_count": 0` (claim), but `git show 5dd07155` shows 10 WP files with `dependencies: []` overwriting LLM-authored arrays.
- tasks.md's WP03 section explicitly lists "- WP01 (cite Divio standard)" and "- WP02 (new path for office2-backup-and-security.md must exist)" under `### Dependencies` — parser did not pick these up.
- tasks.md's WP11 section at line 387 has "WP11 (depends on WP07 + WP02)" — the "depends on" keyword is the only WP entry using that wording, and it's the only one that survived.

**Hypothesis**: The dependency parser in `finalize-tasks` uses a regex pattern that requires "depends on WP##" or "Dependencies: WP##" explicit phrases, NOT the bulleted `- WP## (reason)` format that the slash-command prompt tells the LLM to generate. When the parser finds no match, it writes `dependencies: []` to the frontmatter, silently destroying the LLM's work.

**Supporting observation**: The slash-command prompt (v3.0.3) tells the LLM:
> "Parse dependencies from tasks.md for dependency relationships:
> - Explicit phrases: 'Depends on WP##', 'Dependencies: WP##'
> - Phase grouping: Phase 2 WPs typically depend on Phase 1
> - Default to empty if unclear"

The LLM did follow this — multiple phrase forms were used in tasks.md. But the Python parser in `finalize-tasks` appears to implement a narrower recognition strategy, creating a round-trip mismatch: LLM generates → Python discards.

**Decision-making**:
- This is NOT manual compensation on my part — I was following documented slash-command instructions.
- Manual `git` reverts or commit rewrites would be workarounds and violate the "no workflow workarounds" directive.
- Two spec-kitty-native options: (a) edit tasks.md wording to use "depends on" phrasing, then re-run finalize-tasks; (b) accept the stripped state.
- User decision: **manually patch the WP frontmatter to restore the dependency DAG** (option 2 from the reported options). Rationale: restoring the expected functional state is necessary for downstream `/spec-kitty.implement` to honor the dependency DAG. This is a post-workflow-error repair, not a pre-emptive workaround.

**Resolution**: bug-filed-candidate — recommend filing upstream:
> "finalize-tasks destroys LLM-authored dependencies frontmatter when parser fails to match bullet-format `### Dependencies` sections in tasks.md. Parser and slash-command-prompt guidance are inconsistent: the slash-command tells the LLM to parse bullet lists and write them to frontmatter; finalize-tasks then parses tasks.md again with a narrower regex and zeros out whatever the LLM wrote."

**Downstream impact**:
- **Critical**: With empty `dependencies` in WP frontmatter, `/spec-kitty.implement` cannot correctly determine `--base` flags. All 11 WPs would look parallel-startable, breaking the DAG:
  - WP03 could start before WP01's Divio standards doc exists (would need to cite it).
  - WP07 could start before all frontmatter fixes (WP01-06) are done.
  - WP08 could start before INDEX.md (WP07) exists.
- **Already fixed**: Manual frontmatter patch committed to restore the DAG (see journal entry below, following this one).

**Process lesson**:
- The slash-command should be internally consistent: either the LLM OR the Python parser should own dependency extraction, not both.
- When `finalize-tasks` overrides LLM output, it should either (a) warn when doing so, or (b) set `updated_wp_count` to reflect the actual mutations.
- This sequence would be hard to detect without careful inspection — the workflow succeeded (exit code 0), the success message was clear, and only commit-diff inspection revealed the dependency loss.

---

## 2026-04-04 — Manual frontmatter patch to restore F015 WP dependencies (workflow error repair)

**Feature**: 015-documentation-architecture-rationalization
**Spec-kitty version**: 3.0.3
**Workflow step**: post-tasks (manual repair after finalize-tasks workflow error)
**Severity**: N/A — user-directed repair of the preceding workflow error

**What happened**:
Per user directive, manually patched the `dependencies` frontmatter field on 7 WP prompt files to restore the execution DAG that finalize-tasks had destroyed. Used the Edit tool to set each WP's `dependencies` array to its designed value as documented in tasks.md's `### Dependencies` sections.

**Files patched**:

- WP03: `dependencies: []` → `[WP01, WP02]`
- WP04: `dependencies: []` → `[WP02]`
- WP06: `dependencies: []` → `[WP01]`
- WP07: `dependencies: []` → `[WP01, WP02, WP03, WP04, WP05, WP06]`
- WP08: `dependencies: []` → `[WP07]`
- WP09: `dependencies: []` → `[WP07]`
- WP11: `dependencies: [WP01, WP02, WP07]` → `[WP02, WP07]` (removed spurious WP01)

**Rationale for the manual patch**:
- finalize-tasks produced an invalid execution DAG that would cause `/spec-kitty.implement` to authorize incorrect WP parallelism.
- Restoring the LLM-authored dependency state matches what tasks.md declares and what the slash-command prompt directed the LLM to produce.
- This is post-error repair, not pre-emptive workaround: the workflow tool ran, completed, and produced incorrect output; the user explicitly directed this repair.

**Process boundary preserved**:
- Did NOT manually re-run or bypass finalize-tasks.
- Did NOT force-push or revert the finalize-tasks commit.
- Did NOT invent new dependencies beyond what tasks.md already declared.

**Committed in**: (commit hash recorded in next commit after this journal entry)

**Follow-up action recommended**: When filing the finalize-tasks parser bug upstream, include this manual-repair workflow as context to show the actual user impact.

---

## 2026-04-04 — finalize-tasks --validate-only is NOT actually read-only (mutates frontmatter)

**Feature**: 015-documentation-architecture-rationalization
**Spec-kitty version**: 3.0.3
**Workflow step**: tasks (finalize-tasks --validate-only)
**Severity**: soft-error (surprise mutation; undermines manual repair attempts)

**What I expected**:
`finalize-tasks --validate-only` should be a dry-run flag that validates the current state without modifying any files. The slash-command prompt calls it out for "ownership validation before committing" and the `--validate-only` convention across CLI tooling universally means "read-only, no mutations".

**What actually happened**:
After manually patching the 7 WP prompt files to restore stripped dependencies, I ran `spec-kitty agent feature finalize-tasks --validate-only --json` to verify that the patched DAG validated. The command returned `validation_passed` and reported no errors. But when I inspected the files afterward, ALL SEVEN MANUAL PATCHES HAD BEEN REVERTED — `dependencies: []` once again on WP03, WP04, WP06, WP07, WP08, WP09, and `dependencies: [WP01, WP02, WP07]` on WP11 (with the spurious WP01 back).

**Evidence**:
- JSON output: `"result": "validation_passed", "bootstrap": {"total_wps": 11, "newly_seeded": 0, "already_initialized": 11}` — note the bootstrap section is included even under `--validate-only`.
- `git status kitty-specs/015-documentation-architecture-rationalization/tasks/` showed NO changes (files matched HEAD), meaning the patches had been silently reverted to match the last commit which was the stripped version from `finalize-tasks`.
- Directly grepping the WP03 file confirmed `dependencies: []` instead of the `[WP01, WP02]` I had just written.

**Hypothesis**: The bootstrap step inside `finalize-tasks` runs unconditionally, before the validate/commit fork, and it re-parses `tasks.md` and rewrites WP frontmatter based on the parser's (buggy) output. The `--validate-only` flag only suppresses the final "commit" step — it does NOT skip the mutation-inducing bootstrap step. The combination is: bootstrap writes stripped values, validator validates the stripped (trivially-acyclic) state, command returns success, writes-to-disk are uncommitted but persisted.

Since the file write happens on disk (not just in memory), any subsequent `git add` / `git commit` could capture the stripped state as authoritative. This is a silent data-loss pattern.

**Why this is a bigger deal than it seems**:
- It means manual repair is unstable. Every subsequent spec-kitty command that includes a bootstrap step will re-strip the manually-patched dependencies.
- The user has no way to say "leave my frontmatter alone" — bootstrap always runs.
- Even `--validate-only`, which should be the safest possible flag, is destructive.
- Documentation / mental models for `--validate-only` lead users to expect a safe dry-run. This violates that contract.

**Resolution**: bug-filed-candidate — recommend filing upstream:
> "finalize-tasks --validate-only is not actually read-only. The bootstrap step inside finalize-tasks runs unconditionally and rewrites WP frontmatter even when --validate-only is set. Either (a) bootstrap should be skipped under --validate-only, or (b) bootstrap should be idempotent (read current frontmatter, preserve if non-empty), or (c) the flag should be renamed to reflect that it's not read-only."

**Mitigation applied**: After discovering the revert, re-applied the 7 patches with the Edit tool and immediately committed them via git. Committed in commit `64c0632` on main. Verified post-commit that the stored frontmatter contains the correct dependency DAG (confirmed via grep against all 11 WP files).

**Ongoing risk**: If `/spec-kitty.implement` or any other spec-kitty command triggers bootstrap on this feature, the dependencies will likely be stripped again. Monitor closely during implement phase. If seen again, journal as a recurring hit on this bug pattern.

---

## 2026-04-04 — No supported post-analyze refinement path (workflow design gap)

**Feature**: 015-documentation-architecture-rationalization
**Spec-kitty version**: 3.0.3
**Workflow step**: analyze (post-output remediation)
**Severity**: design-gap (not a bug; missing tool for a common need)

**What the analyze prompt says**:
The `/spec-kitty.analyze` slash-command's "Next Actions" section instructs the LLM to suggest:
> "Provide explicit command suggestions: e.g., 'Run /spec-kitty.specify with refinement', 'Run /plan to adjust architecture', 'Manually edit tasks.md to add coverage for performance-metrics'"

**What actually works in spec-kitty 3.0.3**:
- `/spec-kitty.specify` calls `spec-kitty agent feature create-feature`, which **always allocates the next ordinal number** (e.g., 016, 017). It is designed for NEW features, not refinement of existing ones. There is no "refinement mode".
- `/spec-kitty.plan` calls `setup-plan`, which scaffolds plan.md from the mission template. Re-running on an existing feature risks overwriting hand-authored content.
- `/spec-kitty.tasks` regenerates `tasks.md` + scaffolds new WP files. Re-running destroys existing WP prompts unless the LLM carefully preserves them.
- `spec-kitty agent feature` has NO refine/update-spec command.

**The workflow gap**:
After `/spec-kitty.analyze` produces findings that point to spec/plan/tasks drift, there is no supported command path for refining the spec. The user must either:
- **Manually edit** the relevant artifact(s) and accept that no spec-kitty command orchestrates the fix, OR
- **Abandon the feature** and start a new one with the corrected spec (wasteful; loses planning work).

**Impact**:
- Users following the analyze prompt's guidance literally will try to run `/spec-kitty.specify` and either get confused when it creates a new feature ordinal, or inadvertently duplicate the feature.
- Kent correctly caught this on F015 and refused to run `/spec-kitty.specify`, preferring to understand the intended workflow first.

**Resolution path chosen for F015**:
Manually applied 9 edits to spec.md via the Edit tool to resolve /analyze findings I1, C1, I3. Did NOT re-run /plan or /tasks (to preserve hand-crafted plan.md, tasks.md, WP prompts, and the already-patched dependency DAG). Will re-run /spec-kitty.analyze as pure read-only verification.

**Recommended upstream fixes**:
1. **Add a `spec-kitty agent feature refine --feature <slug>` command** that allows iterating on spec.md/plan.md/tasks.md within an existing feature. It should support targeted updates without scaffolding-from-template.
2. **Correct the /analyze slash-command prompt** to not suggest `/spec-kitty.specify with refinement` — that phrase doesn't describe a real capability in 3.0.3.
3. **Document the manual-edit workflow** as the supported path until (1) ships.

**Resolution**: bug-filed-candidate + documentation-fix-candidate. Kent's refusal to re-run specify on an existing feature was the correct decision given current tooling.

---

## 2026-04-05 — F015 pre-merge state snapshot (crash-recovery context)

**Feature**: 015-documentation-architecture-rationalization
**Spec-kitty version**: 3.0.3
**Workflow step**: pre-merge (before `/spec-kitty.merge`)
**Severity**: observation (captured proactively for crash recovery)

**Context**: Kent noted that `/spec-kitty.merge` historically triggers VS Code crashes. Capturing comprehensive state BEFORE invoking merge so recovery has full context if the command crashes mid-operation.

### Current state at snapshot time

**Main branch HEAD**: `602fc1b chore: commit F015 workspace metadata files`

**All 11 WP branches (approved, not yet merged)**:

| WP | Branch HEAD | Dependencies | Commit message |
|---|---|---|---|
| WP01 | `b8d9fc6` | (none) | feat(WP01): add Divio classification standard reference doc |
| WP02 | `c8d79f0` | (none) | feat(WP02): move misclassified runbook content to canonical homes |
| WP03 | `6a9bb57` | WP01, WP02 | feat(WP03): correct docs/runbooks/ frontmatter, add audience, update links |
| WP04 | `12e4baf` | WP02 | feat(WP04): add frontmatter to F005 research docs + update moved links |
| WP05 | `e5c96b1` | (none) | feat(WP05): add frontmatter to 6 diagnostic files |
| WP06 | `7f59cca` | WP01 | feat(WP06): correct doc_type frontmatter in docs/design/ + standards |
| WP07 | `09da0c5` | WP01–WP06 | feat(WP07): create docs/INDEX.md master documentation map |
| WP08 | `41f09fb` | WP07 | feat(WP08): update CLAUDE.md + AI agent instructions with INDEX refs |
| WP09 | `f6251f5` | WP07 | feat(WP09): document canonical data home + INDEX.md maintenance rule |
| WP10 | `cc15e14` | (none) | feat(WP10): resolve F016 path dependencies per F015 FR-012 |
| WP11 | `c2c339f` | WP02, WP07 | feat(WP11): archive docs-readme.md + update F002 historical link refs |

**All 11 worktrees present** at `.worktrees/015-documentation-architecture-rationalization-WP{01..11}/`.

**All 11 WPs in lane `approved`** (verified via `spec-kitty agent feature accept`).

### Pre-merge accept output summary

- `all_done: true`
- `ok: false` (due to activity_issues — lane=approved vs expected=done)
- `git_dirty: []` (resolved by committing 11 workspace JSONs at commit `602fc1b`)
- `metadata_issues: []`
- `missing_artifacts: []`
- `path_violations: []`
- `warnings: [Optional artifacts missing: contracts]` (expected for doc feature)
- `activity_issues: 11 entries` (all: "canonical lane is 'approved', expected 'done'")

The accept check reports `ok: false` even when all work is substantively complete. The `approved → done` transition is expected to happen at merge time (per `move-task --help` examples which show `--done-override-reason` only for exceptional manual cases).

### Expected merge behavior (from dry-run)

`spec-kitty agent feature merge --dry-run` output:

- **effective_wp_branches**: `[WP08, WP09, WP10, WP11]` — DAG leaves
- **skipped_already_in_target**: `[]`
- **skipped_ancestor_of**: WP01-WP07 all skipped (they are ancestors of the 4 leaves)
- **reason_summary**: "Skipped 7 branch(es) that are ancestors of another candidate tip"

**Planned steps** (from dry-run, 27 steps total):

1. `git checkout main`
2. `git pull --ff-only`
3. `git merge --no-ff 015-documentation-architecture-rationalization-WP08 -m "Merge WP08 ..."`
4. `git merge --no-ff 015-documentation-architecture-rationalization-WP09 -m "Merge WP09 ..."`
5. `git merge --no-ff 015-documentation-architecture-rationalization-WP10 -m "Merge WP10 ..."`
6. `git merge --no-ff 015-documentation-architecture-rationalization-WP11 -m "Merge WP11 ..."`
7-17. `git worktree remove <worktree_path>` (×11)
18-28. `git branch -d <wp-branch>` (×11)

Merging WP08, WP09, WP10, WP11 transitively brings in all 11 WPs' work because of the DAG structure (WP08/WP09 stacked on WP07 which has merge base with WP01-WP06; WP11 stacked on WP02+WP07 merge base).

### Crash recovery information

**If merge crashes during git operations**:

1. **Check main HEAD**: compare to `602fc1b` (pre-merge state). If main advanced, some merges completed.
2. **Check remaining WP branches**: branches that still exist have not been merged/deleted.
3. **Check remaining worktrees**: `git worktree list` — worktrees still present have not been cleaned up.
4. **Re-run merge**: spec-kitty merge is idempotent for already-merged branches (dry-run showed `skipped_already_in_target: []` but it would populate if main advanced).
5. **Manual intervention**: if a merge conflict arises, the user resolves in main repo then `git merge --continue`, then re-run `spec-kitty agent feature merge`.

**If the CLAUDE.md in worktrees reads stale content**: The worktree base is prior to F015 spec alignment. CLAUDE.md in each worktree contains OLD v03 references and OLD directory structure references. This is EXPECTED — those worktrees branched from a pre-WP08 state. The merged main will have the updated CLAUDE.md after WP08 lands.

**Branch naming convention**: All F015 work lives on `015-documentation-architecture-rationalization-WP{01..11}` branches. None are pushed to origin — all work is local.

**Origin sync state**: origin/main is at `634a28b` (from earlier spec-kitty-workflow-journal push). Main locally is 49 commits ahead of origin at snapshot time (`602fc1b`). After merge completes, main will be ~53+ commits ahead, then Kent will push.

### Delivered work summary (to appear on main after merge)

- `docs/INDEX.md` — master documentation map (241 lines, 84 verified links)
- `docs/design/standards/divio-classification.md` — authoritative Divio taxonomy
- `docs/runbooks/*` — 24 files with corrected frontmatter + audience declarations
- `docs/design/research/005-*/` — 9 files with newly-added frontmatter
- `docs/issues/diagnostics/` — 6 files with newly-added frontmatter
- `docs/design/*.md` + `docs/design/standards/` — 8 files with doc_type corrections
- `CLAUDE.md` — new INDEX.md + constitution + data/ references; v03→v1.0 updates
- `ai-agents/claude-code-instructions.md` + `ai-agents/claude-instructions.md` — v03→v1.0 updates
- `docs/design/architecture/README.md` — canonical machine-readable home section
- `docs/design/architecture/change-control.md` — INDEX.md maintenance rule
- `docs/func-spec/F016_change_control_governance.md` — resolved TBD paths
- `docs/archive/docs-readme.md` — archived (was `docs/docs-readme.md`)
- `docs/func-spec/F002_openclaw_install.md` — 2 link reference updates
- Two file moves recorded via `git mv`:
  - `docs/runbooks/visual-docs-style.md` → `docs/design/standards/visual-docs-style.md`
  - `docs/runbooks/office2-backup-and-security.md` → `docs/design/office2-backup-and-security.md`
- F015 spec itself updated for alignment with plan/tasks reality (I1/C1/I3 remediation)

### Recurring spec-kitty observations (referenced by this entry)

- Documentation mission template mismatch (software-dev default used throughout)
- False-positive jsdoc/sphinx generator detection persisted in meta.json
- `finalize-tasks` parser dropped LLM-authored dependencies (required manual repair in commit `64c0632`)
- Multi-parent merge base auto-creation worked correctly (WP03 + WP07 + WP11)
- Manual dependency patches survived all subsequent spec-kitty commands through implement/review/approved (no re-strip observed post-`64c0632`)

---

## 2026-04-05 — spec-kitty merge cleanup misses auto-created merge-base branches

**Feature**: 015-documentation-architecture-rationalization
**Spec-kitty version**: 3.0.3
**Workflow step**: merge (post-merge cleanup)
**Severity**: observation (cruft accumulation, not a hard bug)

**What happened**:
`spec-kitty merge --target main --feature 015-...` completed successfully — merged 4 effective WP branches via DAG ancestry pruning, deleted all 11 WP branches, removed all 11 worktrees. But it **left behind 3 auto-created merge-base branches**:

- `015-documentation-architecture-rationalization-WP03-merge-base`
- `015-documentation-architecture-rationalization-WP07-merge-base`
- `015-documentation-architecture-rationalization-WP11-merge-base`

These branches were auto-created during `/spec-kitty.implement` when a WP had multi-parent dependencies (WP03 → WP01+WP02; WP07 → WP01-WP06; WP11 → WP02+WP07). Their commits are all present in main's history after the merge, so they're safe to delete — but spec-kitty's cleanup missed them.

**Evidence**:
- `git branch -l "015-documentation-architecture-rationalization-*"` after merge shows the 3 merge-base branches.
- `git worktree list` shows only main (all 11 worktrees removed correctly).
- Spec-kitty merge output reports "✓ Deleted branch: ..." for all 11 WP branches but does not mention merge-base branches.

**Hypothesis**: Spec-kitty's merge code enumerates WP branches via the WP naming convention (`<feature>-<WP##>`) but doesn't track the merge-base branches it auto-created (`<feature>-<WP##>-merge-base`). These orphaned branches will accumulate over features if not manually cleaned up.

**Resolution**: bug-filed-candidate — recommend filing upstream: "spec-kitty merge should clean up auto-created merge-base branches alongside WP branches. These are generated by implement for multi-parent deps and become orphaned after merge."

**Mitigation applied**: Manually deleted the 3 merge-base branches via `git branch -D` after merge. Safe because their commits are in main's history (verified via `git log`).

**Impact**: Low-severity cruft. Would accumulate ~N merge-base branches per feature where N = number of multi-parent WPs. Not destructive but clutters `git branch` output over time.

---

## 2026-04-05 — VS Code crash during F016 merge (incident 9)

**Feature**: 016-change-control-governance
**Spec-kitty version**: 3.0.3
**Workflow step**: merge
**Severity**: hard-error (non-idempotent merge interrupted; manual recovery required)

**What I expected**:
`spec-kitty merge --target main --feature 016-change-control-governance` to complete all steps: merge DAG leaves, mark all 9 WPs as done, remove worktrees, delete branches, commit status files.

**What actually happened**:
VS Code crashed during merge execution. The crash occurred after:
- WP08 merge commit (`7207ce2`) completed
- WP09 merge commit (`2a1d455`) completed (these are DAG leaves; all 9 WPs' work is transitively in main)
- WP09 status transitioned to `done` (last event: `01KNG1ABAJTR98HHGPHE66PWH7` at 23:58:13 UTC)
- All 9 worktrees removed
- All 9 WP branches deleted

But before:
- WP01–WP08 status transitions to `done` (all still show `approved` in status.json)
- 5 merge-base branches cleaned up (WP03, WP04, WP05, WP08, WP09 merge-base branches remain)
- Status files committed (status.json, status.events.jsonl modified but uncommitted)
- `docs/INDEX.md` committed (modified by WP09 merge but uncommitted)
- Push to origin

**Evidence**:
- `git log --oneline -2`: `2a1d455 Merge WP09 from 016-change-control-governance` / `7207ce2 Merge WP08 from 016-change-control-governance`
- `git worktree list`: only main (`2a1d455`)
- `git branch -l "016-*"`: 5 merge-base branches only (no WP branches)
- `git status --short`: ` M docs/INDEX.md`, ` M kitty-specs/016-change-control-governance/status.events.jsonl`, ` M kitty-specs/016-change-control-governance/status.json`
- status.json: WP09 lane=`done`, WP01–WP08 lane=`approved`
- Last event in JSONL: `actor: "merge"`, `wp_id: "WP09"`, `to_lane: "done"`

**Additional observations**:
- No parallel development in this session — all workflow steps walked through sequentially (unlike F015 which had parallel WP implementation). Eliminates concurrent worktree writes as a contributing factor.
- markdownlint auto-fix was already disabled (changed to on-save on 2026-04-02). Crash still occurred, disproving the hypothesis that the linter auto-fix loop was the primary FSEvents amplifier.
- F015 merge (incident 8, 11 worktrees) succeeded without crashing earlier in the same session. F016 crashed with fewer worktrees (9). Reinforces that accumulated session state — not worktree count or parallel activity — is the dominant factor.

**Hypothesis**: Same FSEvents overflow mechanism as #416 incidents 3–6. Session duration and accumulated filesystem event state overwhelmed macOS FSEvents queue, causing VS Code crash. The merge processed WP09 last (or only got through one WP's status transition) before the crash killed the process.

**Recovery plan**:
1. Commit uncommitted files: `docs/INDEX.md` + `kitty-specs/016-change-control-governance/status.*`
2. Delete 5 stale merge-base branches
3. Push to origin
4. WP01–WP08 status showing `approved` instead of `done` is a known consequence — the merge actor didn't complete the lane transition events for those WPs

**Resolution**: manual recovery required (same pattern as #416 incidents 3–6)

**Downstream impact**: Feature work is fully merged to main. Only bookkeeping (status files, stale branches, push) remains incomplete. The `approved` status on WP01–WP08 is cosmetically incorrect but functionally irrelevant since the feature is complete.

---
