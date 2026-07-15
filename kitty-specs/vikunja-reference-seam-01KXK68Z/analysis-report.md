---
schema_version: 1
artifact_type: spec-kitty.analysis-report
command: /spec-kitty.analyze
mission_slug: vikunja-reference-seam-01KXK68Z
mission_id: 01KXK68ZQGWPK68ES7809SM148
generated_at: '2026-07-15T17:35:18.410784+00:00'
analyzer_agent: unknown
input_artifacts:
  spec.md:
    path: /Users/kentgale/repos/kg-automation/kitty-specs/vikunja-reference-seam-01KXK68Z/spec.md
    sha256: 629bab173f01051ee5d5f025f40e0607084444612045213b1cd4fac070dfe596
  plan.md:
    path: /Users/kentgale/repos/kg-automation/kitty-specs/vikunja-reference-seam-01KXK68Z/plan.md
    sha256: 7cbff4b8f36ef75f37700af1a5aa9ba55b22c5ff3fa41490c2cb3115b25889d6
  tasks.md:
    path: /Users/kentgale/repos/kg-automation/kitty-specs/vikunja-reference-seam-01KXK68Z/tasks.md
    sha256: f0cba354879f8bb00302c1ed13126bba390c018317b478837ebb4fc8c880e00f
  charter:
    path: /Users/kentgale/repos/kg-automation/.kittify/charter/charter.md
    sha256: 4891223a0c3fc0dc96917475523586e8f3147a3ccaa113ecb7ff19da646e82e2
verdict: ready
issue_counts:
  critical: 0
  medium: 1
  high: 0
  low: 1
  info: 0
findings:
- id: F1
  severity: medium
  category: inconsistency
  summary: 'FR-011/FR-012 require attaching the q:schedule (and Tier-1) label on routing, but FR-006 + the WP01 registry declare only felix:ignore and defer taxonomy labels to #749 — the label q:schedule has no declared registry id to attach by.'
- id: F2
  severity: low
  category: inconsistency
  summary: WP05 prompt cites constraint C-006 (endpoint-safety), which is not defined in this spec's C-001..C-005 set; it refers to the original route_someday helper contract.
---

## Specification Analysis Report

**Mission:** vikunja-reference-seam-01KXK68Z (#748 + #745). Artifacts analyzed:
`spec.md`, `plan.md`, `tasks.md` (+ `data-model.md`, `contracts/`, `research.md`).
Charter mode: compact — no charter MUST conflicts detected.

| ID | Category | Severity | Location(s) | Summary | Recommendation |
|----|----------|----------|-------------|---------|----------------|
| F1 | Inconsistency | MEDIUM | spec.md FR-006 / FR-011 / FR-012; data-model.md (labels); tasks WP01/T001, WP05/T019 | FR-011/012 route "someday"/Tier-1 captures by attaching the `q:schedule` label, but FR-006 + the registry declare only `felix:ignore` and defer the `f:/q:/t:/loe:` taxonomy labels to #749. Attaching a label in Vikunja needs its id → an undeclared `q:schedule` has no id to attach by. WP05/T019 documents a decision path (declare live-probed, or defer to #749 via option b), so it is resolvable at WP time, but the spec does not state which. | Add `q:schedule` (and any Tier-1 labels the router determinably applies) to the registry at seed (live-probed id), **or** reword FR-011/012 so label attachment is explicitly best-effort and deferred to #749 when the id is unavailable. Baseline routing (no-due-date task in Inbox) works either way, so not blocking. |
| F2 | Inconsistency | LOW | WP05-capture-routing-and-sc001-gate.md (T018 "per C-006") | The WP cites `C-006`, which is not among this spec's constraints (C-001..C-005). It refers to the original `route_someday` helper contract's endpoint-safety rule (never `POST /tasks/<id>`). | Cite the rule via `[[reference_vikunja_post_partial_replace]]` / "use the CREATE endpoint `PUT /projects/<id>/tasks`" without the stale `C-006` id, to avoid a dangling constraint reference. |

**Coverage Summary Table** (functional requirements → tasks; 13/13 mapped, confirmed by `map-requirements`):

| Requirement Key | Has Task? | Task IDs (WP) | Notes |
|-----------------|-----------|---------------|-------|
| FR-001 declared registry | Yes | WP01 (T001–T004) | |
| FR-002 runtime-only resolution | Yes | WP03, WP04, WP05 | SC-001 grep gate = WP05/T022 |
| FR-003 fail-loud resolution | Yes | WP01 (T003–T005) | |
| FR-004 drift/unreachable validator | Yes | WP02 (T006–T008) | |
| FR-005 migrate call sites | Yes | WP03, WP04 (+WP05 route_someday) | 9-site inventory |
| FR-006 per-token label (felix:ignore) | Yes | WP04 (T016) | taxonomy labels deferred #749 — see F1 |
| FR-007 post-reset names / exclude felix-bot Inbox | Yes | WP01 (T001) | |
| FR-008 preserve {kind,value} selector | Yes | WP01 (T001–T003), WP03 (T009) | |
| FR-009 unprovisioned state | Yes | WP01 (T003) | |
| FR-010 fall-through → Inbox | Yes | WP05 (T018, T020) | |
| FR-011 someday → q:schedule+no-due-date | Yes | WP05 (T018, T019) | see F1 |
| FR-012 Tier-1 labels where determinable | Yes | WP05 (T019) | see F1 |
| FR-013 preserve routing-log/dedup | Yes | WP05 (T018, T021) | |
| NFR-001 zero hot-path network | Yes | WP01 (T005) | asserted in tests |
| NFR-002 ≤2 list round trips | Yes | WP02 (T007–T008) | asserted in tests |
| NFR-003 no new deps | Yes | WP01 | stdlib only |

**Charter Alignment Issues:** none (compact charter; the plan's Charter/Constitution Check
maps single-source-of-truth, fail-loud, Directive 6 deterministic split, JSON validation,
no-vestiges, and active-surface hygiene — all satisfied).

**Unmapped Tasks:** none. Every subtask T001–T022 rolls under a WP mapped to ≥1 FR.

**Metrics:**
- Total functional requirements: 13 (+3 NFR, +5 constraints, +5 success criteria)
- Total tasks: 22 subtasks across 5 work packages
- Coverage: 100% (13/13 FR with ≥1 task; NFR-001/002/003 covered)
- Ambiguity count: 0 blocking (FR-012 "where determinable" is intentionally deferred to #749's intake loop)
- Duplication count: 0
- Critical issues: 0

## Next Actions

- **No CRITICAL/HIGH findings → cleared to implement.** Verdict: `ready`.
- **Recommended before or during WP05:** resolve F1 — decide whether `q:schedule`
  (+ determinable Tier-1 labels) is declared in the registry this mission or label
  application is deferred to #749. Cheapest fix: add `q:schedule` to the WP01
  registry seed (live-probed id) + note it in FR-006; then WP05/T019 attaches by id.
- **Optional (LOW):** fix the F2 `C-006` citation in WP05.
