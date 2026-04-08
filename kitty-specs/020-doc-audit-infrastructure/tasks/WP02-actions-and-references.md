---
work_package_id: WP02
title: Commit Convention, GitHub Actions & Index Updates
dependencies: [WP01]
requirement_refs:
- FR-003
- FR-004
- FR-005
- FR-006
planning_base_branch: main
merge_target_branch: main
branch_strategy: 'Current branch at workflow start: main. Planning/base branch: main. Merge target: main. WP02 depends on WP01.'
subtasks: [T004, T005, T006, T007, T008]
history:
- date: '2026-04-08T19:40:49Z'
  action: created
  by: tasks-prompt
authoritative_surface: .github/workflows/
execution_mode: code_change
owned_files:
- CLAUDE.md
- .github/workflows/doc-audit-trigger.yml
- .github/workflows/doc-audit-weekly.yml
- docs/INDEX.md
- docs/design/architecture/README.md
---

# WP02: Commit Convention, GitHub Actions & Index Updates

## Objective

Complete the doc audit infrastructure by:

1. Documenting the `[doc-audit]` commit tag convention in CLAUDE.md
2. Creating the post-merge GitHub Action that auto-creates scoped audit issues
3. Creating the weekly cron stub that creates full-scope audit issues
4. Updating INDEX.md and architecture README to reference the new artifacts

## Context

- **WP01 deliverables** (prerequisites): `doc-domain-map.json` and `docs-debt.md`
  template must exist before this WP begins
- **Existing workflow**: `.github/workflows/docs-ci.yml` — validates docs on
  push/PR to main; the new workflows are separate and non-blocking
- **Audit issue labels**: Use `P2-debt` plus the relevant `area/` label(s)
- **Trigger mechanism**: PR merge only (not push) per plan.md decision — weekly
  stub covers spec-kitty merges and direct pushes as safety net
- **Spec references**: FR-003, FR-004, FR-005, FR-006
- **Constraints**: C-002 (GITHUB_TOKEN only), C-003 (tag is advisory),
  C-004 (weekly creates human issue, not agent run)

## Branch Strategy

- **Planning base branch**: `main`
- **Merge target branch**: `main`
- **Depends on**: WP01
- **Implementation command**: `spec-kitty implement WP02 --base WP01`

---

## Subtask T004: Add `[doc-audit]` Commit Tag to CLAUDE.md

**Purpose**: Document the commit tag convention so Claude Code and contributors
know when and how to use it. This is advisory only (no CI enforcement per C-003).

**File**: `CLAUDE.md` (repo root)

**Steps**:

1. Locate the `## Git Workflow` section in CLAUDE.md
2. Add a new subsection or paragraph about the `[doc-audit]` tag:

   ```markdown
   ### Doc Audit Tag

   Append `[doc-audit]` to commit messages when a commit includes documentation
   maintenance changes that are not the primary purpose of the commit. This tag
   signals to the future felix-doc-auditor agent that the commit contains
   untracked maintenance changes worth auditing.

   Example: `fix: repair vikunja filter logic [doc-audit]`

   This is advisory only — no CI enforcement. The tag is a convention for
   future automated scanning.
   ```

3. Keep it concise — 4-6 lines of content maximum
4. Do not modify any other section of CLAUDE.md

**Validation**:
- [ ] `[doc-audit]` tag is documented in CLAUDE.md Git Workflow section
- [ ] Purpose is clear: signals untracked doc maintenance for future audit
- [ ] Marked as advisory (no CI enforcement)
- [ ] Example commit message included
- [ ] No other CLAUDE.md sections modified

---

## Subtask T005: Create Post-Merge Audit Trigger Workflow

**Purpose**: Automatically create a scoped audit issue when a PR with area
labels is merged to main. This is the primary automation that makes doc
auditing systematic.

**File**: `.github/workflows/doc-audit-trigger.yml`

**Steps**:

1. Create the workflow file with this trigger:
   ```yaml
   name: Doc Audit Trigger
   on:
     pull_request:
       types: [closed]
       branches: [main]
   ```

2. Add a single job that:
   a. Checks if the PR was actually merged (not just closed):
      ```yaml
      if: github.event.pull_request.merged == true
      ```
   b. Checks out the repo (needs domain map file):
      ```yaml
      - uses: actions/checkout@v4
      ```
   c. Extracts area labels from the PR using the event payload:
      ```yaml
      - name: Extract area labels
        id: labels
        run: |
          AREA_LABELS=$(echo '${{ toJson(github.event.pull_request.labels) }}' | \
            jq -r '[.[] | select(.name | startswith("area/")) | .name] | join(",")')
          echo "area_labels=$AREA_LABELS" >> "$GITHUB_OUTPUT"
          if [ -z "$AREA_LABELS" ]; then
            echo "skip=true" >> "$GITHUB_OUTPUT"
          else
            echo "skip=false" >> "$GITHUB_OUTPUT"
          fi
      ```
   d. Exits early if no area labels found (Scenario 2):
      ```yaml
      - name: Skip if no area labels
        if: steps.labels.outputs.skip == 'true'
        run: echo "No area labels — skipping audit issue creation"
      ```
   e. Reads doc-domain-map.json and builds a checklist of affected docs:
      ```yaml
      - name: Build audit checklist
        if: steps.labels.outputs.skip != 'true'
        id: checklist
        run: |
          DOMAIN_MAP="docs/design/architecture/data/doc-domain-map.json"
          if [ ! -f "$DOMAIN_MAP" ]; then
            echo "Domain map not found — skipping"
            echo "skip=true" >> "$GITHUB_OUTPUT"
            exit 0
          fi

          IFS=',' read -ra LABELS <<< "${{ steps.labels.outputs.area_labels }}"
          CHECKLIST=""
          for label in "${LABELS[@]}"; do
            DOCS=$(jq -r --arg l "$label" '.domains[$l] // [] | .[]' "$DOMAIN_MAP")
            if [ -n "$DOCS" ]; then
              CHECKLIST="${CHECKLIST}\n### ${label}\n"
              while IFS= read -r doc; do
                CHECKLIST="${CHECKLIST}- [ ] ${doc}\n"
              done <<< "$DOCS"
            fi
          done

          # Write to file to avoid shell escaping issues
          echo -e "$CHECKLIST" > /tmp/audit-checklist.md
          echo "skip=false" >> "$GITHUB_OUTPUT"
      ```
   f. Creates the audit issue using `gh`:
      ```yaml
      - name: Create audit issue
        if: steps.labels.outputs.skip != 'true' && steps.checklist.outputs.skip != 'true'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          PR_NUMBER=${{ github.event.pull_request.number }}
          PR_TITLE="${{ github.event.pull_request.title }}"
          AREA_LABELS="${{ steps.labels.outputs.area_labels }}"

          BODY="## Doc Audit: PR #${PR_NUMBER}

          **PR**: #${PR_NUMBER} — ${PR_TITLE}
          **Areas**: ${AREA_LABELS}

          Review the following documentation for accuracy after this merge:

          $(cat /tmp/audit-checklist.md)

          ---
          *Auto-generated by doc-audit-trigger. See doc-domain-map.json for scope.*"

          # Build label args
          LABEL_ARGS="--label P2-debt"
          IFS=',' read -ra LABELS <<< "$AREA_LABELS"
          for label in "${LABELS[@]}"; do
            LABEL_ARGS="$LABEL_ARGS --label $label"
          done

          gh issue create \
            --title "Doc audit: PR #${PR_NUMBER} (${AREA_LABELS})" \
            $LABEL_ARGS \
            --body "$BODY"
      ```

3. Set permissions:
   ```yaml
   permissions:
     issues: write
     contents: read
   ```

4. Ensure the workflow is NOT a required status check (NFR-001)

**Validation**:
- [ ] Workflow triggers only on merged PRs to main (not closed-but-unmerged)
- [ ] Extracts area labels correctly from PR
- [ ] Exits silently when no area labels present
- [ ] Reads doc-domain-map.json and builds correct checklist
- [ ] Handles missing domain map gracefully (no error, just skip)
- [ ] Creates issue with P2-debt label plus area labels
- [ ] Issue body includes PR reference and domain-scoped checklist
- [ ] Uses only GITHUB_TOKEN (no additional secrets)

**Edge Cases**:
- PR has area labels but those labels aren't in the domain map: creates issue
  with empty checklist sections — acceptable, will be obvious to triage
- PR merged by spec-kitty (direct merge commit, no PR): workflow does NOT fire —
  this is by design, weekly stub is the safety net
- Domain map JSON is malformed: jq will fail, step will error but won't block
  anything (non-required check)

---

## Subtask T006: Create Weekly Audit Cron Stub

**Purpose**: Safety-net audit that fires weekly to catch documentation drift
from spec-kitty merges, direct pushes, and any PRs the trigger might miss.

**File**: `.github/workflows/doc-audit-weekly.yml`

**Steps**:

1. Create the workflow with cron schedule:
   ```yaml
   name: Doc Audit Weekly
   on:
     schedule:
       - cron: '0 5 * * 0'  # Sunday 05:00 UTC = Sunday midnight ET (EST+5)
     workflow_dispatch:  # Allow manual trigger for testing
   ```

2. Add permissions:
   ```yaml
   permissions:
     issues: write
     contents: read
   ```

3. Create a single job that:
   a. Checks out the repo
   b. Checks for existing open weekly audit issue to prevent duplicates (NFR-003):
      ```yaml
      - name: Check for existing weekly audit
        id: existing
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          COUNT=$(gh issue list --label "P2-debt" --state open \
            --search "Weekly doc audit" --json number --jq 'length')
          if [ "$COUNT" -gt "0" ]; then
            echo "skip=true" >> "$GITHUB_OUTPUT"
            echo "Open weekly audit issue already exists — skipping"
          else
            echo "skip=false" >> "$GITHUB_OUTPUT"
          fi
      ```
   c. Reads the full domain map and builds a complete checklist:
      ```yaml
      - name: Build full checklist
        if: steps.existing.outputs.skip != 'true'
        run: |
          DOMAIN_MAP="docs/design/architecture/data/doc-domain-map.json"
          if [ ! -f "$DOMAIN_MAP" ]; then
            echo "Domain map not found — skipping"
            exit 0
          fi

          CHECKLIST=""
          for label in $(jq -r '.domains | keys[]' "$DOMAIN_MAP"); do
            DOCS=$(jq -r --arg l "$label" '.domains[$l] | .[]' "$DOMAIN_MAP")
            CHECKLIST="${CHECKLIST}\n### ${label}\n"
            while IFS= read -r doc; do
              CHECKLIST="${CHECKLIST}- [ ] ${doc}\n"
            done <<< "$DOCS"
          done

          echo -e "$CHECKLIST" > /tmp/weekly-checklist.md
      ```
   d. Creates the weekly audit issue:
      ```yaml
      - name: Create weekly audit issue
        if: steps.existing.outputs.skip != 'true'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          DATE=$(date +%Y-%m-%d)
          gh issue create \
            --title "Weekly doc audit — ${DATE}" \
            --label "P2-debt" \
            --body "## Weekly Documentation Audit

          **Week of**: ${DATE}

          Full-scope documentation review. Check each document for accuracy
          against current system state.

          $(cat /tmp/weekly-checklist.md)

          ---
          *Auto-generated by doc-audit-weekly. See doc-domain-map.json for scope.*"
      ```

4. Note: The cron uses `0 5 * * 0` for UTC, which is midnight ET during EST
   (UTC-5). During EDT (UTC-4), it fires at 1:00 AM ET — acceptable.

**Validation**:
- [ ] Workflow triggers on schedule (Sunday) and on workflow_dispatch
- [ ] Deduplication check prevents creating when open weekly issue exists
- [ ] Full-scope checklist covers all 8 domains
- [ ] Handles missing domain map gracefully
- [ ] Issue is labeled P2-debt
- [ ] Title includes date for easy identification
- [ ] Uses only GITHUB_TOKEN

---

## Subtask T007: Update docs/INDEX.md

**Purpose**: Add references to the new domain map and docs-debt template so
they are discoverable through the documentation index.

**File**: `docs/INDEX.md`

**Steps**:

1. In the **docs/design/architecture/data/** section (under "Machine-readable
   state (JSON)"), add a new bullet:
   ```markdown
   - [Doc Domain Map](<./design/architecture/data/doc-domain-map.json>)
   ```

2. In a suitable location (near the Feature Specifications or Issues section),
   add a reference to the docs-debt template. The most natural place is near
   the existing "Templates" sub-section under Feature Specifications:
   ```markdown
   - [Docs Debt Issue Template](<../.github/ISSUE_TEMPLATE/docs-debt.md>)
   ```

   Alternatively, add a note in the "Adding a New Document" section:
   ```markdown
   5. If a documentation gap is identified, file it using the
      [docs-debt issue template](../.github/ISSUE_TEMPLATE/docs-debt.md).
   ```

3. Do not restructure existing content — add only the new references

**Validation**:
- [ ] Domain map referenced in the architecture data section
- [ ] Docs-debt template referenced or mentioned
- [ ] Links use correct relative paths
- [ ] No existing content modified beyond adding new entries

---

## Subtask T008: Update Architecture README Data Files Table

**Purpose**: Add the domain map to the Data Files table in the architecture
README so it's discoverable alongside other JSON data files.

**File**: `docs/design/architecture/README.md`

**Steps**:

1. Locate the `## Data Files` table in the README
2. Add a new row for the domain map:
   ```markdown
   | [doc-domain-map.json](<./data/doc-domain-map.json>) | Area label → doc file mapping for audit scope |
   ```
3. Place it in alphabetical order or at the end of the table

**Validation**:
- [ ] New row added to Data Files table
- [ ] Link path is correct (relative to README location)
- [ ] Description is concise and accurate
- [ ] No existing rows modified

---

## Definition of Done

- [ ] `[doc-audit]` tag documented in CLAUDE.md Git Workflow section
- [ ] doc-audit-trigger.yml creates scoped audit issues on PR merge with area labels
- [ ] doc-audit-trigger.yml exits silently for PRs without area labels
- [ ] doc-audit-weekly.yml creates weekly full-scope audit issue
- [ ] doc-audit-weekly.yml deduplicates (no stacking of open weekly issues)
- [ ] docs/INDEX.md references domain map and template
- [ ] docs/design/architecture/README.md lists domain map in Data Files table
- [ ] All workflows use only GITHUB_TOKEN
- [ ] No workflows are configured as required status checks

## Risks

| Risk | Mitigation |
|------|-----------|
| Post-merge action fails on malformed JSON | Graceful skip if domain map missing or invalid |
| Weekly cron schedule off by 1 hour in EDT | Acceptable — fires at 1 AM ET instead of midnight |
| Audit issue volume overwhelms triage | P2-debt priority; can be batch-processed |
| GITHUB_TOKEN lacks issue write permission | Default token has this for same-repo; tested by first merge |

## Reviewer Guidance

1. Verify CLAUDE.md change is minimal — only the `[doc-audit]` tag paragraph
2. Check post-merge workflow: does it extract labels correctly? Does it skip no-label PRs?
3. Check weekly workflow: does deduplication search query match the issue title pattern?
4. Verify INDEX.md and architecture README changes are additive only
5. Confirm both workflows have correct permissions block
6. Check that neither workflow is set as a required check
