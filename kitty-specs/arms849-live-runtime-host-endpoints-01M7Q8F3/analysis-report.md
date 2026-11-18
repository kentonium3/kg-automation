---
schema_version: 1
artifact_type: spec-kitty.analysis-report
command: /spec-kitty.analyze
mission_slug: arms849-live-runtime-host-endpoints-01M7Q8F3
mission_id: 01M7Q8F38CE7TDBVJEYGT1YA7B
generated_at: '2026-11-18T18:47:03.061756+00:00'
analyzer_agent: unknown
input_artifacts:
  spec.md:
    path: .worktrees/arms849-live-runtime-host-endpoints-01M7Q8F3-coord/kitty-specs/arms849-live-runtime-host-endpoints-01M7Q8F3/spec.md
    sha256: 8ea8e7b3799bf351abcceb9ee38ce00404a1ddffabc3f1fa252a3ae0767d82f5
  plan.md:
    path: .worktrees/arms849-live-runtime-host-endpoints-01M7Q8F3-coord/kitty-specs/arms849-live-runtime-host-endpoints-01M7Q8F3/plan.md
    sha256: 2a2a8b916fd9f8f9c5085e2566159b89494bd8100c4f36035cb096a48ac15f40
  tasks.md:
    path: .worktrees/arms849-live-runtime-host-endpoints-01M7Q8F3-coord/kitty-specs/arms849-live-runtime-host-endpoints-01M7Q8F3/tasks.md
    sha256: ecad6eb2d87e033045f813756ad49f9c60f7d30d847069891aeff8ae48ab7748
  charter:
    path: .kittify/charter/charter.yaml
    sha256: 212313e7295e83d9a2fc22d6b35aa7460974a9c3d3af46ecee9b1673d3624a0a
verdict: blocked
issue_counts:
  critical: 1
  high: 1
  medium: 2
  low: 2
  info: 0
findings:
- id: C1
  severity: critical
  category: charter
  summary: spec.md has no explicit documentation-synchronization requirement (charter Project Directive 5); the N/A appears only in plan.md's Charter Check.
- id: U1
  severity: high
  category: underspecification
  summary: WP01 T-a/T-b/T-c patch arm_g.make_bridge by importing arm_g, which imports graphiti_core; the checker's fresh-worktree-ci step stubs graphiti_core to raise, so these tests would fail there and block SC-002.
- id: A1
  severity: medium
  category: ambiguity
  summary: WP03 T011 step 3 leaves stripping the four overrides from the office and CI suites to the implementer's choice.
- id: I1
  severity: medium
  category: inconsistency
  summary: Setting ARMS849_FALKOR_HOST/PORT in the live step changes the second required live node's falkor_endpoint fixture (no own substrate up/down); spec and plan do not record this.
- id: I2
  severity: low
  category: inconsistency
  summary: plan.md places T-a..T-e in test_arms849_integration.py and omits test_arms849_resume.py; tasks put T-a..T-c in a new test_arms849_endpoints.py and own the resume test.
- id: G1
  severity: low
  category: coverage
  summary: NFR-002 and SC-002 have no implementing subtask; they are proven only by the post-merge quickstart checker run.
---

## Specification Analysis Report

Mission `arms849-live-runtime-host-endpoints-01M7Q8F3`, analysed 2026-11-18 against spec.md, plan.md, tasks.md, the three WP prompts and `.kittify/charter/charter.md`.

| ID | Category | Severity | Location(s) | Summary | Recommendation |
|----|----------|----------|-------------|---------|----------------|
| C1 | Charter | CRITICAL | spec.md Requirements; charter.md Project Directives item 5 | The charter says every mission specification must include an explicit documentation-synchronization requirement "covering architecture JSON, markdown views, runbooks, INDEX, and roadmap status as applicable". The spec has none. plan.md's Charter Check records "No `docs/design/architecture/` update applies", but that is the plan, not the spec. Verified 2026-11-18: no file under `docs/` or `scripts/research/` (non-.py) names `check_849_premerge`, `live-required-nodes`, `ARMS849_LIVE` or the override variables, so the requirement's content is "none applicable; quickstart.md is the only operational procedure". | Add a constraint to spec.md stating the documentation-sync requirement and its N/A scope with the evidence, dated, citing this report. No WP change. |
| U1 | Underspecification | HIGH | tasks/WP01 T005 (shared fixture step 3, T-c); scripts/research/check_849_premerge.py:377-383; arm_g.py:83 | WP01 tells the implementer to patch `scripts.research.arms849.arm_g.make_bridge`. Patching that attribute imports `arm_g`, whose top level imports `graphiti_core`. The checker's `fresh-worktree-ci` step puts a stub `graphiti_core/__init__.py` on `PYTHONPATH` that raises `ModuleNotFoundError` (repo CI also lacks graphiti_core). T-a, T-b and T-c would therefore error in that step, `fresh-worktree-ci` would fail, and SC-002 ("every checker step passes") could not be met. The same applies to T-c's child process, which inherits `PYTHONPATH`. WP02 T-e relies on the cache-absent skip coming first, and has no explicit graphiti-absent skip. | WP01: stand in for `arm_g` at the import boundary without importing it: install a fake module under `sys.modules["scripts.research.arms849.arm_g"]` and as the package attribute, so the real `_factory_g`'s lazy `from scripts.research.arms849 import arm_g` binds the fake. The tests then run (not skip) in CI. T-c's child does the same. WP02 T-e: add an explicit skip when `graphiti_core` is not importable, with the research-environment reason. |
| A1 | Ambiguity | MEDIUM | tasks/WP03 T011 step 3 | "Decide, and state in a comment, whether..." leaves a design decision to the implementer, and T013's assertion is conditional on it. | Make it definite: strip the four keys wherever `ARMS849_LIVE` is stripped, so an operator's exported override cannot leak into the office or CI suites, and assert it in T-f. |
| I1 | Inconsistency | MEDIUM | spec.md User Story 1; plan.md D5; tests/research/test_arms849_arm_g.py `falkor_endpoint` | The second required live node's fixture uses `ARMS849_FALKOR_HOST/PORT` when set, and otherwise runs `substrate up`/`down` itself. Once the checker sets them (D5), that node reuses the checker's stack instead of cycling it. WP02 and WP03 note this, but spec and plan do not. | Record the interaction in plan.md D5 (dated, citing this report) so the post-merge reviewer and the checker-run reader expect it. |
| I2 | Inconsistency | LOW | plan.md Project Structure and test-plan rows; tasks.md WP01 | The plan names `test_arms849_integration.py` for T-a..T-e. The tasks moved T-a..T-c to a new `tests/research/test_arms849_endpoints.py`, so that WP01 and WP02 own disjoint files, and added `test_arms849_resume.py` (its `container_health` fake breaks under D3). | No action needed: the tasks give the reason. Optionally add a dated note to plan.md. |
| G1 | Coverage | LOW | spec.md NFR-002, SC-002; tasks.md | No subtask implements NFR-002 or SC-002. Nothing in this mission changes `live-smoke` or `live-down`, so they are proven only by the quickstart checker run after the merge. | No change. Keep the quickstart run as the binding evidence. |

**Coverage Summary Table:**

| Requirement Key | Has Task? | Task IDs | Notes |
|-----------------|-----------|----------|-------|
| FR-001 live-runtime-accepts-explicit-endpoints | Yes | T001-T005 | T-b positive control; half-by-half |
| FR-002 defaults-remain-in-network | Yes | T001-T005 | T-a ratchet, paired with T-b |
| FR-003 live-node-reads-host-overrides | Yes | T006-T008 | |
| FR-004 checker-passes-and-records-ports | Yes | T010, T011, T013 | |
| FR-005 verifier-requires-overrides | Yes | T010, T012, T014 | |
| FR-006 red-first-override-demonstration | Yes | T009 | |
| NFR-001 research-suite-stays-green | Yes | T005, T007, T009, T013 | every WP's test strategy |
| NFR-002 in-container-run-unregressed | No (live run) | quickstart | G1 |
| C-001 no-production-env-override | Yes | T003, T005 (T-c), T006 | |
| C-002 allowlist-untouched | Yes | T005 (T-b) | |
| C-003 option-b-rejected | Yes | T008 | node stays host pytest |
| C-004 lead-does-not-implement | Yes | all (agent_profile python-pedro) | |
| SC-001 | Yes | T008 + quickstart | |
| SC-002 | No (live run) | quickstart | G1; blocked by U1 if unfixed |
| SC-003 | Yes | T014 + quickstart | |

**Charter Alignment Issues:** C1 (Project Directive 5). All other charter items hold: tests ship with the code (Testing Standards), fixtures are shaped like real records (T-g mutates a checker-produced record), integration verification form (a) is defined (quickstart.md), Tier 3, no audited surface, no deployed-service or architecture change.

**Unmapped Tasks:** none.

**Metrics:**

- Total Requirements: 15 (6 FR, 2 NFR, 4 C, 3 SC)
- Total Tasks: 14 subtasks in 3 work packages
- Coverage: 13/15 (87%) with at least one subtask; the 2 others (NFR-002, SC-002) are covered by the live verification only
- Ambiguity Count: 1
- Duplication Count: 0
- Critical Issues Count: 1

## Next Actions

- Resolve C1 and U1 before `/spec-kitty.implement`: add the documentation-sync constraint to spec.md; revise WP01 T005 (fake `arm_g` module at the import boundary) and WP02 T009 (explicit graphiti-absent skip).
- Resolve A1 and I1 in the same pass, since they are cheap: make WP03 T011 step 3 definite; record the falkor_endpoint interaction in plan.md D5.
- Re-run `/spec-kitty.analyze` afterwards. Editing spec, plan or tasks makes this report stale.
