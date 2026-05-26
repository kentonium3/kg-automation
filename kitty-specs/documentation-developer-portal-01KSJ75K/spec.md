# Documentation Developer Portal

**Mission:** documentation-developer-portal-01KSJ75K
**Mission type:** software-dev
**Target branch:** main
**Source:** GitHub issue #417 + `docs/temp/documentation_blueprint.md` (v1.2)

---

## Intent

Create a single guided sitemap for the `kg-automation` (Felix) documentation
suite so that AI agents and human contributors can orient themselves in under
30 seconds without reading the full flat catalog. The portal complements
`docs/INDEX.md` (which remains the master directory listing) by adding
onboarding sequences, a TL;DR of the execution loop, a verification command
quick-reference, and a virtual filter that groups runbooks by their existing
`audience:` frontmatter.

A single navigation pointer is added to `CLAUDE.md` so AI sessions can
discover the portal. No other content in `CLAUDE.md` is altered — it remains
the authoritative, self-contained runtime instruction book.

---

## User Scenarios & Testing

### Scenario 1 — New AI session lands on the repo

**Actor:** Fresh Claude Code (or other AI agent) session, no prior context.
**Action:** Reads `CLAUDE.md` per its session-start instructions; encounters
the new pointer; follows it to `docs/DEVELOPER_PORTAL.md`.
**Expected outcome:** Within one screen of the portal, the agent can identify
which onboarding sequence to follow (Feature Dev / Runbook Execution / Bug
Fix) and reaches its first task-relevant doc with no additional searching.

### Scenario 2 — Agent needs to run an automated runbook

**Actor:** Agent dispatched to execute a runbook task on `office2`.
**Action:** Opens the portal, scans the Virtual Runbook Filter for
`audience: agents`, picks the relevant runbook.
**Expected outcome:** Agent does not waste tokens reading human-only
runbooks (e.g., `obsidian-setup.md`). Agent-executable runbooks are listed
together, separated from human-only and dual-audience runbooks.

### Scenario 3 — Contributor verifies a doc change locally

**Actor:** Human or agent that just edited a markdown file.
**Action:** Opens the portal's Verification Command Quick-Reference.
**Expected outcome:** All local validation commands (`pytest`,
`validate_docs.py`, `sync_mermaid_views.py`, etc.) appear in one place
without hunting through README files.

### Scenario 4 — Reviewer audits the CLAUDE.md change

**Actor:** Mission reviewer.
**Action:** Runs `git diff` on `CLAUDE.md`.
**Expected outcome:** Diff is a single additive block (one new pointer
line). No existing safety guardrails, git rules, spec-kitty flow text, or
runbook references are removed, renamed, or rephrased.

### Acceptance edge cases

- A runbook missing the `audience:` frontmatter field must surface in a
  clearly labeled "Unclassified" or equivalent bucket so it is fixable
  without silently dropping from the filter.
- `validate_docs.py` must pass against the new portal file with no new
  errors and no new warnings introduced by the portal's frontmatter.

---

## Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | Create `docs/DEVELOPER_PORTAL.md` with valid YAML frontmatter that passes `validate_docs.py` (required fields: `title`, `doc_type`, `status`; `doc_type` chosen from the allowed enum). | Proposed |
| FR-002 | The portal contains a **Quick-Start Onboarding Sequence** section that presents at least three named onboarding paths (Feature Development, Runbook Execution, Bug Fix) as ordered checklists or sequenced links. | Proposed |
| FR-003 | The portal contains an **Execution Loop Explained** section of no more than three paragraphs that summarizes the Local Workspace → GitHub → `office2` host → OpenClaw run lifecycle and links directly to `docs/runbooks/agent-workspace-reconciliation.md` and `docs/runbooks/openclaw-agent-setup.md`. The section must not duplicate raw content from those runbooks. | Proposed |
| FR-004 | The portal contains a **Verification Command Quick-Reference** section that groups local validation commands (at minimum: `pytest`, `python tooling/scripts/validate_docs.py`, `python tooling/scripts/sync_mermaid_views.py`) in one place. | Proposed |
| FR-005 | The portal contains a **Virtual Runbook Filter** that lists every markdown file under `docs/runbooks/**/*.md`, grouped by its `audience:` frontmatter value (`agents`, `humans`, `agents_and_humans`). Files missing the `audience:` field appear in a distinct "Unclassified" bucket. | Proposed |
| FR-006 | `CLAUDE.md` is updated to include a single new navigation line, placed under the existing **Architecture Documentation** section, pointing to `docs/DEVELOPER_PORTAL.md`. | Proposed |
| FR-007 | `CLAUDE.md` is otherwise unchanged: no existing line is rephrased, reordered, removed, or relocated. The diff on `CLAUDE.md` is purely additive. | Proposed |
| FR-008 | `docs/INDEX.md` is updated to reference the new portal so the master index remains complete. | Proposed |
| FR-009 | The portal links back to `docs/INDEX.md` so readers who land at the portal can discover the master catalog. | Proposed |

## Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|---|---|---|---|
| NFR-001 | Portal page load time for an LLM agent (reading from disk) is bounded by file size, not by recursion. | Portal markdown file ≤ 25 KB. | Proposed |
| NFR-002 | Doc validation remains green across the repo after the change. | `python tooling/scripts/validate_docs.py` exits 0 with zero new blockers and zero new warnings attributable to this mission. | Proposed |
| NFR-003 | Maintenance cost of the portal is low enough to survive monthly runbook drift without manual update. | Virtual Runbook Filter is generated (or, if hand-maintained, justified in plan) from the existing `audience:` frontmatter; no new metadata field is introduced. | Proposed |

## Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | `CLAUDE.md` content beyond the single new pointer line is strictly preserved. Removing, rewording, reordering, or relocating any existing line is out of scope and would fail review. | Proposed |
| C-002 | No physical directory restructuring under `docs/`. The virtual filter operates on existing file locations and metadata only. | Proposed |
| C-003 | No new frontmatter fields are added to existing runbooks. The `audience:` enum (`agents`, `humans`, `agents_and_humans`) is used as-is. | Proposed |
| C-004 | No CLI risk-tier helper (`check-risk.py`), no programmatic context/prerequisite resolver, no dependency-driven auditing. These were explicitly removed or deferred in blueprint v1.2. | Proposed |
| C-005 | The Execution Loop Explained section must not duplicate content from `agent-workspace-reconciliation.md` or `openclaw-agent-setup.md`. It is a TL;DR + pointers, not a third source of truth. | Proposed |
| C-006 | The portal does not modify, supersede, or rephrase any guidance in `docs/constitution/FELIX-CONSTITUTION.md`. It only links to it. | Proposed |

---

## Out of Scope

- Modifying, relocating, or thinning existing `CLAUDE.md` content beyond the single pointer line
- Physical directory moves under `docs/runbooks/` or any other `docs/` subtree
- Phase 2 of the blueprint (CLI risk-tier helper / `check-risk.py`) — explicitly removed in v1.2
- Phase 3 of the blueprint (programmatic context resolver / `resolve_context.py`) — eliminated as over-engineering
- Phase 4 of the blueprint (dependency-driven auditing) — deferred indefinitely
- Adding new frontmatter fields to existing runbooks
- Auto-generation tooling for the virtual filter (if it's hand-maintained at first, that's acceptable for Phase 1)

---

## Success Criteria

| ID | Criterion | How verified |
|---|---|---|
| SC-001 | A new contributor (human or agent) can identify their onboarding path within 30 seconds of opening the portal. | Manual review: portal's Quick-Start section presents named paths above the fold. |
| SC-002 | The portal's Execution Loop section does not duplicate runbook content. | Reviewer diffs the section against the linked runbooks; no copy-paste blocks. |
| SC-003 | The full `docs/runbooks/**/*.md` set is represented in the Virtual Runbook Filter. | Reviewer cross-references the filter's listed files against `find docs/runbooks -name '*.md'`. |
| SC-004 | `CLAUDE.md` change is purely additive. | `git diff CLAUDE.md` shows only added lines; no removed or modified lines. |
| SC-005 | Doc validation passes. | `python tooling/scripts/validate_docs.py` exits 0. |
| SC-006 | The portal appears in `docs/INDEX.md`. | Index contains a link to the new portal. |

---

## Assumptions

- Runbook `audience:` frontmatter values are accurate today; plan phase confirms by sampling.
- `validate_docs.py` accepts the chosen `doc_type` (likely `index` or `guide`, both in the allowed enum) without schema changes.
- The "Architecture Documentation" section header in `CLAUDE.md` is the right anchor for the new pointer line; if planning discovers a more natural location, it may move the line within `CLAUDE.md` provided the surrounding content is preserved untouched.
- The portal can be hand-maintained for Phase 1; an auto-generation script is a separate, later concern if drift becomes a real problem.

---

## Key Entities

This mission produces and modifies documents only. No code entities, services, or data records are created or modified.

- **`docs/DEVELOPER_PORTAL.md`** — new file. Type: markdown with YAML frontmatter. Owner: this mission.
- **`CLAUDE.md`** — modified file. One new line added. Existing content preserved.
- **`docs/INDEX.md`** — modified file. One new index entry added.

---

## Dependencies

- Requires read access to the existing `audience:` frontmatter values in `docs/runbooks/**/*.md` (already present in the repo).
- Requires `tooling/scripts/validate_docs.py` to be runnable (already part of the standard developer workflow).
- No external services, no `office2` deployment, no credentials, no third-party APIs.

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Portal duplicates content from the runbooks it links to, creating two sources of truth | Future readers see contradictory descriptions of the execution loop; maintenance debt doubles | C-005 forbids duplication; review checks the 3-paragraph cap and that the section is genuinely a TL;DR + pointers |
| The `CLAUDE.md` edit accidentally truncates or rephrases surrounding safety-critical text | Loss of authoritative runtime context for AI sessions; potential operational failure | C-001 + FR-007 mandate a purely additive diff; review compares `git diff CLAUDE.md` against the constraint |
| Virtual Runbook Filter drifts out of sync as runbooks are added or have their `audience:` changed | Filter becomes stale or misclassifies files | NFR-003 + assumption that hand-maintained is acceptable for Phase 1; if drift becomes a problem, an auto-generation script becomes its own issue |
| `doc_type` choice for the portal fails schema validation | CI breaks on the new file | Plan phase picks a value from the allowed enum (`{'index', 'guide', 'reference', ...}`) and confirms via `validate_docs.py` before declaring complete |
