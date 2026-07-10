# Tasks: Felix Foundation-0 Exec-Hardening — Finding & Doc Reconcile

**Mission:** `f0-exec-hardening-01KX4ZCY` | **Branch:** `feat/f0-exec-hardening`
**Type:** software-dev (docs/governance) | **Runtime footprint:** repo docs + one GitHub issue (filed at merge). **No `openclaw.json` change.**

Two independent work packages with disjoint file ownership — parallelizable.

## Subtask Index

| ID | Description | WP | Parallel |
| --- | --- | --- | --- |
| T001 | Boundary doc §8 Step-3 finding: exec approvals = guardrails not isolation | WP01 | |
| T002 | Per-agent exec-form evidence table + explicit disposition of narrower knobs | WP01 | |
| T003 | Whole-doc gog-ownership sweep (§2/§4/§6/§6.1/§8) to post-#699 reality | WP01 | |
| T004 | Sandbox recommendation + 3-part proof + follow-up-issue draft appendix + §8 pointer | WP01 | |
| T005 | #675 tracker-disposition recommendation (close-as-rescoped) | WP01 | |
| T006 | Model drift: habits + tasker → `anthropic/claude-haiku-4-5` (JSON + narrative) | WP02 | [P] |
| T007 | Per-agent `skills` arrays → live Step-2 sets (calendar → `[]`) | WP02 | [P] |
| T008 | Correct stale per-agent narrative fields #699 missed (capture/calendar/main/route) | WP02 | [P] |
| T009 | Gateway version `v2026.6.5` → `2026.6.11`; annotate main as tracked gog exception | WP02 | [P] |
| T010 | Provenance + validator + NFR-005 semantic grep; narrative agrees with JSON | WP02 | |

---

## WP01 — Finding + full boundary-doc reconcile

- **Goal:** Record the exec-allowlist infeasibility finding (with evidence + narrower-knob disposition + sandbox recommendation) and reconcile the boundary doc's stale post-#699 gog-ownership across the whole document; draft the sandbox follow-up issue + the #675 disposition.
- **Priority:** P1 (the finding is the mission's core deliverable).
- **Independent test:** `docs/design/felix-openclaw-boundary.md` §8 Step 3 reads the finding + sandbox pointer; the whole-doc semantic grep (NFR-005) finds no present-tense "calendar owns/holds gog"; the appendix carries a fileable sandbox-issue draft.
- **Owned files:** `docs/design/felix-openclaw-boundary.md`
- **Requirements:** FR-001, FR-004, FR-005, FR-006, FR-007, NFR-002, NFR-003
- **Dependencies:** none
- **Estimated prompt size:** ~320 lines
- **Prompt:** [tasks/WP01-finding-boundary-reconcile.md](./tasks/WP01-finding-boundary-reconcile.md)

Included subtasks:

- [x] T001 Boundary doc §8 Step-3 finding: exec approvals = guardrails not isolation (WP01)
- [x] T002 Per-agent exec-form evidence table + explicit disposition of narrower knobs (WP01)
- [x] T003 Whole-doc gog-ownership sweep (§2/§4/§6/§6.1/§8) to post-#699 reality (WP01)
- [x] T004 Sandbox recommendation + 3-part proof + follow-up-issue draft appendix + §8 pointer (WP01)
- [x] T005 #675 tracker-disposition recommendation (close-as-rescoped) (WP01)

## WP02 — Reconcile architecture inventory to live config

- **Goal:** Make `service-inventory.json` + its narrative tell the truth for all six agents — model drift, skills fiction, the deeper per-agent narrative fields #699 missed, gateway version, and the main gog-exception — passing the validator + semantic grep.
- **Priority:** P1.
- **Independent test:** `python3 tooling/scripts/validate_architecture_data.py` passes; habits/tasker `model` = `anthropic/claude-haiku-4-5`; calendar `skills` = `[]`; the NFR-005 grep is clean; narrative agrees with JSON.
- **Owned files:** `docs/design/architecture/data/service-inventory.json`, `docs/design/architecture/service-inventory.md`
- **Requirements:** FR-002, FR-003, FR-004, NFR-001, NFR-004, NFR-005
- **Dependencies:** none (shares the gog-ownership facts in research.md with WP01)
- **Estimated prompt size:** ~300 lines
- **Prompt:** [tasks/WP02-inventory-reconcile.md](./tasks/WP02-inventory-reconcile.md)

Included subtasks:

- [x] T006 Model drift: habits + tasker → `anthropic/claude-haiku-4-5` (JSON + narrative) (WP02)
- [x] T007 Per-agent `skills` arrays → live Step-2 sets (calendar → `[]`) (WP02)
- [x] T008 Correct stale per-agent narrative fields #699 missed (capture/calendar/main/route) (WP02)
- [x] T009 Gateway version `v2026.6.5` → `2026.6.11`; annotate main as tracked gog exception (WP02)
- [x] T010 Provenance + validator + NFR-005 semantic grep; narrative agrees with JSON (WP02)

---

## Dependencies & Parallelization

- WP01 and WP02 own **disjoint files** and have **no inter-dependency** → fully parallelizable.
- Both draw gog-ownership facts from `research.md` (Decision 2) — keep them consistent.
- **Merge-time (orchestrator, not a WP):** file the sandbox follow-up issue from WP01's appendix draft, patch the real issue number into boundary §8, and close #675 as rescoped (operator-confirmed). GitHub side-effects are intentionally kept out of the WPs.

## MVP scope

WP01 (the recorded finding) is the mission's core value; WP02 is the truth-in-docs reconcile. Both ship together.
