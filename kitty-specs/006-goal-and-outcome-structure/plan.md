# Implementation Plan: Goal and Outcome Structure

**Branch**: `main` | **Date**: 2026-03-30 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/006-goal-and-outcome-structure/spec.md`

## Summary

Establish the foundational goal declaration system across three pillars:
(1) define the canonical "On [date], I have [outcome] as evidenced by [proof]"
format in the Obsidian constitution, (2) extend Vikunja with a Goals project,
structured tasks, and a saved filter via the API, (3) populate Goals-MOC.md
with real declarations. Approach follows the F001 setup script pattern using
the Vikunja REST API, with Obsidian content written via SSH to office2.

## Technical Context

**Language/Version**: Python 3.11+ (setup script), Markdown (Obsidian content)
**Primary Dependencies**: requests (HTTP client for Vikunja API), SSH (office2 access)
**Storage**: Vikunja (SQLite via API), Obsidian vault (Markdown files via Obsidian Sync)
**Testing**: Manual verification via Vikunja API queries and file reads on office2; pytest for setup script
**Target Platform**: office2 (Ubuntu 24.04 LTS), Obsidian vault (synced across Mac/iPhone/office2)
**Project Type**: Configuration + content (no deployed services)
**Constraints**: No new services, ports, or credentials; `02-Growth/_private/` off-limits
**Scale/Scope**: Single user (Kent), handful of goal declarations

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Notes |
| --- | --- | --- |
| Test-first directive | Pass | Setup script verified via API queries; Obsidian content verified via file reads |
| No credentials in code | Pass | Vikunja auth uses interactive JWT (same as F001); no stored secrets |
| Privacy boundary | Pass | `02-Growth/_private/` never accessed |
| Doc synchronization | Pass | Architecture docs updated as part of implementation |
| Tailscale-only network | Pass | Vikunja API at 100.92.197.90:3456 (Tailscale IP) |

## Project Structure

### Documentation (this feature)

```
kitty-specs/006-goal-and-outcome-structure/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 research output
├── data-model.md        # Phase 1 data model
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks/               # Work package prompts (created by /spec-kitty.tasks)
```

### Source Code (repository root)

```
scripts/vikunja/
├── setup_vikunja.py         # F001 baseline setup (existing — read for patterns)
└── setup_goals.py           # F006 goals setup script (new)

docs/handbooks/
├── vikunja-ops.md           # Existing ops runbook (update with goals section)
└── goals-ops.md             # New goals ops runbook

docs/design/architecture/
├── data/
│   └── service-inventory.json   # Update Vikunja entry with goals project note
└── service-inventory.md         # Update narrative with goals project note
```

### Remote (office2 via SSH)

```
~/second-brain/vault/Notes/01-Constitution/
└── Goals-MOC.md             # Rewrite with canonical format and real declarations
```

**Structure Decision**: No new directories created. F006 extends the existing
`scripts/vikunja/` and `docs/handbooks/` patterns from F001. Obsidian content
is written remotely to office2 where Obsidian Sync distributes it.

## Implementation Approach

### Phase A: Vikunja Goal Structure (FR-003, FR-004, FR-005)

1. Create `scripts/vikunja/setup_goals.py` following the F001 pattern:
   - Authenticate to Vikunja API (interactive JWT, same as setup_vikunja.py)
   - Create `metalcasework` label (#ff9800 orange) if not exists
   - Create top-level `Goals` project if not exists
   - Create seed goal declaration task(s) with:
     - Title: short summary
     - Description: full canonical declaration + evidence criteria
     - Due date: target date
     - Label: identity label
   - Create "Goals" saved filter: `project = <goals_project_id> && done = false`,
     sorted by due date ascending
2. Run script against office2 Vikunja instance
3. Verify via Vikunja web UI (desktop and mobile)

### Phase B: Obsidian Goal Format and Goals-MOC (FR-001, FR-002, FR-006, FR-007)

1. Write Goals-MOC.md to office2 via SSH with:
   - Canonical format definition and rules
   - Template section showing the three required elements
   - Active declarations organized by identity context (Personal, Intentional,
     Metal Casework)
   - Archive section (Achieved, Retired) — initially empty
   - At least one real declaration matching what was seeded in Vikunja
2. Verify sync to Mac and iPhone via Obsidian Sync

### Phase C: Documentation (FR-008, FR-009)

1. Create `docs/handbooks/goals-ops.md` covering:
   - Goal declaration format reference
   - How to add a goal manually (Vikunja + Goals-MOC.md two-step)
   - How to close an achieved goal
   - How to retire an abandoned goal
   - Valid vs invalid declaration examples
2. Update `docs/design/architecture/data/service-inventory.json` — add note
   about Goals project under Vikunja entry
3. Update `docs/design/architecture/service-inventory.md` — add narrative note
4. Update `docs/handbooks/vikunja-ops.md` — add Goals project and filter to
   the project structure documentation

## Seed Goal Declarations

Kent must provide at least one real goal declaration during implementation.
Candidates from inbox notes:

1. **Intentional consulting income** — "$5,000/month" (needs specific target date
   and evidence criteria from Kent)
2. **5K race** — Against the Tide, Brewster, June 27, 2026 (needs outcome
   statement and evidence criteria from Kent)

These will be confirmed during the implementation work package before being
committed to Vikunja and Goals-MOC.md.

## Dependencies

| Dependency | Status | Required By |
| --- | --- | --- |
| Vikunja running on office2 | Confirmed (F001) | Phase A |
| Vikunja API accessible via Tailscale | Confirmed (F001) | Phase A |
| SSH access to office2 as claude user | Confirmed | Phase B |
| Obsidian Sync active on office2 | Confirmed | Phase B |
| F001 labels (personal, intentional) | Confirmed | Phase A |
| Goals-MOC.md reset to clean slate | Confirmed (2026-03-29) | Phase B |

## Risks

| Risk | Mitigation |
| --- | --- |
| Vikunja filter expression syntax differs from expectation | Test filter creation in isolation before combining with seed data |
| Goals-MOC.md and Vikunja diverge after initial setup | Ops runbook documents manual two-step; automated sync deferred |
| Kent doesn't provide seed goal declarations | Implementation WP will pause at seed goal step and request input |

## Constitution Re-Check (Post-Design)

| Gate | Status | Notes |
| --- | --- | --- |
| Test-first | Pass | Setup script tested via API verification queries |
| No credentials in code | Pass | Interactive JWT only |
| Privacy boundary | Pass | No `02-Growth/_private/` access |
| Doc synchronization | Pass | Architecture docs, ops runbook, and vikunja-ops all updated |
| Tailscale-only | Pass | All API calls via Tailscale IP |

## Complexity Tracking

No constitution violations to justify. Feature is configuration + content
with no new services, no new credentials, and no architectural complexity.
