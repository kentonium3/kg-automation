---
work_package_id: WP04
title: GitHub issue writer + dedup
dependencies:
- WP02
requirement_refs:
- C-003
- C-005
- FR-004
- FR-005
- FR-007
- NFR-005
- NFR-006
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T016
- T017
- T018
- T019
- T020
agent: "claude"
shell_pid: "23039"
history:
- event: created
  at: '2026-05-11T21:43:38Z'
  by: 'spec-kitty.tasks (auto-drive via #115)'
authoritative_surface: scripts/security/credential_health_check/github_writer.py
execution_mode: code_change
owned_files:
- scripts/security/credential_health_check/github_writer.py
- tests/security/test_github_writer.py
tags: []
---

# WP04 — GitHub issue writer + dedup

## Objective

Implement title generation, body templating, dedup-via-search, and issue creation for all three alert variants (cadence, activity-staleness, manifest-quality batch).

## Context

- **Spec** anchors: FR-004 (paired alerts in lockstep), FR-005 (issue body content + title prefix for dedup), FR-007 (dedup-via-existing-open-issue), FR-012 (manifest-quality batched).
- **Contracts** anchor: `contracts/github-issue-writer.md` is the authoritative spec.
- **Plan** anchor: identity = `kg-felix-bot` (C-005); shell out via `gh` CLI.

## Branch Strategy

- **Planning/base branch**: `main`
- **Merge target branch**: `main`
- This WP runs in a lane-allocated worktree; merges to `main`.

## Subtasks

### T016 — Title generators for all 3 variants

**Purpose**: Stable, dedup-safe title strings.

**Steps**:

1. Implement in `scripts/security/credential_health_check/github_writer.py`:
   ```python
   from datetime import date
   from .manifest import Credential, ManifestQualityIssue
   from .signals import ActivitySignalFailure

   def cadence_alert_title(credential: Credential, boundary: date) -> str:
       return f"Credential review: {credential.name} due {boundary.isoformat()}"

   def staleness_alert_title(credential: Credential) -> str:
       return f"Credential staleness: {credential.name}"

   def manifest_quality_title(issue_count: int, cycle_date: date) -> str:
       return f"Credential manifest quality: {issue_count} entries with issues — {cycle_date.isoformat()}"

   def cadence_alert_title_prefix(credential: Credential) -> str:
       """Prefix used for dedup search (stable, ignores boundary date)."""
       return f"Credential review: {credential.name}"

   def staleness_alert_title_prefix(credential: Credential) -> str:
       return f"Credential staleness: {credential.name}"

   MANIFEST_QUALITY_TITLE_PREFIX = "Credential manifest quality"
   ```

**Files**: `scripts/security/credential_health_check/github_writer.py` (create initial).

---

### T017 — Body templating for all 3 variants

**Purpose**: Render the issue body per the templates in `contracts/github-issue-writer.md`.

**Steps**:

1. Implement three body-render functions; each takes the relevant input and returns a Markdown string.
2. Build the body via f-strings or `textwrap.dedent` (no template engine — keep stdlib-only).
3. **Cadence body** receives `(credential, boundary, vikunja_task_id, cycle_date)` and renders the template in `contracts/github-issue-writer.md` §"Cadence-based body".
4. **Staleness body** receives `(credential, signal_failure, cycle_date)` and renders the §"Activity-staleness body" template.
5. **Manifest-quality body** receives `(issues: list[ManifestQualityIssue], cycle_date)` and renders the §"Manifest-quality batch body" template.

**Files**: `scripts/security/credential_health_check/github_writer.py` (modify).

**Edge cases**:

- Credentials with no `used_by` → render as empty list (`""`), not `"None"`.
- `expiry_notes` containing Markdown special characters → reproduce verbatim (the field is meant to be reproduced); GitHub will render appropriately.

---

### T018 — `dedup_check(title_prefix)` via gh issue list

**Purpose**: Query whether any open issue matches a given title prefix.

**Steps**:

1. Implement:
   ```python
   import subprocess, json

   def dedup_check(title_prefix: str) -> list[int]:
       """Return list of open issue numbers whose title starts with title_prefix.
       Empty list means no dedup match (caller should file new artefacts)."""
       result = subprocess.run(
           [
               "gh", "issue", "list",
               "--repo", "kentonium3/kg-automation",
               "--search", f'in:title "{title_prefix}"',
               "--state", "open",
               "--json", "number,title",
               "--limit", "50",
           ],
           capture_output=True, text=True, timeout=15,
       )
       if result.returncode != 0:
           raise GitHubWriteError(f"gh issue list failed: {result.stderr.strip()[:200]}")
       data = json.loads(result.stdout)
       # GitHub's in:title search is fuzzy; filter to exact prefix matches.
       matches = [item["number"] for item in data if item["title"].startswith(title_prefix)]
       return matches
   ```
2. Define `GitHubWriteError(Exception)` at the top of the module.

**Files**: `scripts/security/credential_health_check/github_writer.py` (modify).

---

### T019 — `create_issue(title, body, labels, assignees)` via gh issue create

**Purpose**: Actually file the issue and return its number.

**Steps**:

1. Implement:
   ```python
   def create_issue(title: str, body: str, labels: list[str], assignees: list[str]) -> int:
       """Create a GitHub issue and return the issue number."""
       cmd = [
           "gh", "issue", "create",
           "--repo", "kentonium3/kg-automation",
           "--title", title,
           "--body", body,
       ]
       for label in labels:
           cmd += ["--label", label]
       for assignee in assignees:
           cmd += ["--assignee", assignee]
       result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
       if result.returncode != 0:
           raise GitHubWriteError(f"gh issue create failed: {result.stderr.strip()[:200]}")
       # gh issue create outputs the issue URL on stdout; parse the trailing number.
       url = result.stdout.strip()
       # URL format: https://github.com/kentonium3/kg-automation/issues/<N>
       try:
           return int(url.rsplit("/", 1)[-1])
       except (ValueError, IndexError):
           raise GitHubWriteError(f"gh issue create stdout was not a parseable URL: {url!r}")
   ```
2. Default labels: `["area/security"]`. Default assignees: `["kentonium3"]`.

**Files**: `scripts/security/credential_health_check/github_writer.py` (modify).

---

### T020 — Tests for github_writer

**Purpose**: Exercise the writer paths with stubbed `gh` invocations.

**Steps**:

1. Create `tests/security/test_github_writer.py`.
2. Title tests:
   - `test_cadence_title_format`: against a fixture Credential, assert title matches expected pattern.
   - `test_staleness_title_format`: similar.
   - `test_manifest_quality_title_format`: similar.
3. Body tests:
   - `test_cadence_body_contains_credential_name`, `test_cadence_body_contains_boundary`, `test_cadence_body_contains_vikunja_task_link` — snapshot-style assertions.
   - `test_staleness_body_contains_reason`.
   - `test_manifest_quality_body_lists_all_issues`.
4. Dedup tests (mock `subprocess.run` returning a `CompletedProcess` with crafted JSON stdout):
   - `test_dedup_check_no_matches_returns_empty_list`.
   - `test_dedup_check_exact_prefix_match_returns_number`.
   - `test_dedup_check_filters_non_prefix_matches_from_fuzzy_search` (GitHub's `in:title` is fuzzy; the filter ensures only true prefix matches return).
5. Create tests (mock `subprocess.run`):
   - `test_create_issue_returns_parsed_number`.
   - `test_create_issue_raises_on_nonzero_exit`.
   - `test_create_issue_command_line_shape` — assert the constructed argv contains expected flags.

**Files**: `tests/security/test_github_writer.py` (create, ~150 lines).

---

## Definition of Done

- All five subtasks complete.
- `python -m pytest tests/security/test_github_writer.py -v` → all green.
- The dedup filter step (`item["title"].startswith(prefix)`) is in place — without it, fuzzy search matches would cause false dedup hits.
- Commit prefix: `feat(security):` or `feat(WP04):` referencing #115.

## Risks

- **`gh issue list --search 'in:title "..."'` is fuzzy**: GitHub interprets the phrase loosely. The `startswith()` post-filter is necessary; tests must explicitly cover this case (one fuzzy non-match in the response).
- **`gh issue create` output format**: stable as of `gh 2.x` (a single URL line). If it changes, parsing breaks — tests cover this with a "garbage output" case.
- **Body content**: must not contain credential **values**, only names and storage locations. Per NFR-006, the entire alert path is metadata-only.
- **Labels**: `area/security` is the only label this WP applies. New labels are out of scope for this WP.

## Reviewer guidance

- Verify: titles use the exact stable-prefix patterns defined in T016 (any drift breaks dedup forever — strings are the contract).
- Verify: `dedup_check` post-filters with `startswith()` against GitHub's fuzzy search.
- Verify: `create_issue` defaults to `area/security` label and `kentonium3` assignee.
- Verify: `GitHubWriteError` is raised, never silently swallowed.
- Verify: no credential **value** appears in any rendered body — only names, types, storage paths.

## Suggested implement command

```bash
spec-kitty agent action implement WP04 --agent <name>
```

## Activity Log

- 2026-05-11T22:03:51Z – claude – shell_pid=23039 – Started implementation via action command
- 2026-05-11T22:05:20Z – claude – shell_pid=23039 – 21/21 WP04 tests pass; 80/80 cumulative. Dedup filter for fuzzy in:title search covered.
