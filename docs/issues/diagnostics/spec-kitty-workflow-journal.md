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
