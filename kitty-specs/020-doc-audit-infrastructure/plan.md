# Implementation Plan: Doc Audit Infrastructure

**Branch**: `main` | **Date**: 2026-04-08 | **Spec**: [spec.md](spec.md)
**GitHub Issue**: #104
**Mission**: software-dev

---

## Summary

Create the infrastructure for systematic documentation auditing: a JSON
domain map, a docs-debt issue template, a commit tag convention, a
post-merge GitHub Action trigger, and a weekly cron stub. All artifacts
are static files (JSON, YAML, Markdown) — no application code.

## Technical Context

**Language/Version**: YAML (GitHub Actions workflows, issue template),
JSON (domain map), Markdown (CLAUDE.md edit, INDEX.md updates)
**Primary Dependencies**: GitHub Actions, `gh` CLI, `GITHUB_TOKEN`
**Testing**: Manual verification — merge a test PR, confirm audit issue
creation; verify weekly cron fires on schedule
**Constraints**: Actions must not block merges (non-required check);
`GITHUB_TOKEN` only (no additional secrets)

## Research Findings

### Post-merge trigger mechanism

**Decision**: Trigger on PR merge to main only (not on push).
**Rationale**: spec-kitty merges create merge commits directly, not PRs.
Triggering on push would require commit-message parsing to detect area
labels, which is fragile. PR-triggered audits cover manual PRs; the
weekly stub is the safety net for spec-kitty merges and direct pushes.
**Alternative rejected**: Push trigger with commit parsing — too complex,
false positive risk.

### Label for audit issues

**Decision**: Use `P2-debt` for auto-created audit issues, plus the
relevant `area/` label(s) from the PR.
**Rationale**: The existing `P1-debt`/`P2-debt` labels serve the same
purpose as the proposed `type/debt`. Auto-created audits are P2 (not
blocking current work); manually-filed critical gaps can use P1-debt.
**Alternative rejected**: Creating a new `type/debt` label — adds
taxonomy complexity with no benefit.

### Domain map schema

**Decision**: JSON object keyed by area label name, each value is an
array of relative file paths.
**Rationale**: Matches the pattern of other architecture data files
(service-inventory.json). Simple enough to edit by hand.

## Constitution Check

*Charter not migrated. Governance checked against Felix Constitution.*

- No agents deployed — N/A for autonomy levels
- GitHub Actions run in GitHub's environment, not on office2 — no Tier
  concerns
- No credentials or secrets involved beyond GITHUB_TOKEN
- No privacy boundary impact

Pass.

## Project Structure

### Files Created

```
docs/design/architecture/data/
└── doc-domain-map.json          # FR-1: domain→docs mapping

.github/ISSUE_TEMPLATE/
└── docs-debt.md                 # FR-2: documentation gap template

.github/workflows/
├── doc-audit-trigger.yml        # FR-4: post-merge audit issue creation
└── doc-audit-weekly.yml         # FR-5: weekly safety-net stub
```

### Files Modified

```
CLAUDE.md                        # FR-3: [doc-audit] tag convention
docs/INDEX.md                    # FR-6: domain map + template references
docs/design/architecture/README.md  # FR-6: domain map in Data Files table
```

## Implementation Approach

### WP1: Domain map + issue template (static files)

Create the doc-domain-map.json with entries for all 8 area labels.
Create the docs-debt.md issue template following the existing template
pattern. These are the foundation that the GitHub Actions reference.

### WP2: CLAUDE.md convention + GitHub Actions + INDEX updates

Add the `[doc-audit]` tag to CLAUDE.md. Create both workflows. Update
INDEX.md and architecture README. The workflows reference
doc-domain-map.json from WP1.

### Verification

After merging, create a test PR with an area label and merge it to
confirm the post-merge action fires correctly.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Post-merge action fails silently | Low | Low | Non-required check; weekly stub is backup |
| Domain map becomes stale | Medium | Medium | Updating map is part of definition of done for new docs |
| Audit issue volume too high | Low | Low | P2-debt is backlog priority; can be triaged down |

---

**Branch contract (confirmed)**:
- Current branch: `main`
- Planning/base branch: `main`
- Merge target: `main`
- Branch matches target: **yes**

---

**END OF PLAN**
