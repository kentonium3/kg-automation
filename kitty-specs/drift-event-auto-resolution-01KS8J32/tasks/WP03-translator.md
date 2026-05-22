---
work_package_id: WP03
title: Translator + ProposedEdit extension
dependencies:
- WP01
requirement_refs:
- C-003
- FR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
created_at: '2026-05-22T19:45:00+00:00'
subtasks:
- T014
- T015
- T016
- T017
history: []
authoritative_surface: scripts/doc_audit/routing/
execution_mode: code_change
mission_id: 01KS8J321F8KE7369R3DA02329
mission_slug: drift-event-auto-resolution-01KS8J32
owned_files:
- scripts/doc_audit/routing/__init__.py
- scripts/doc_audit/routing/drift_to_proposed_edit.py
- scripts/doc_audit/data_model.py
- tests/doc_audit/routing/test_drift_to_proposed_edit.py
tags: []
agent: "agy:gemini-2.5-pro:spec-kitty-review:reviewer"
shell_pid: "10389"
---

# WP03 — Translator + ProposedEdit extension

## Objective

Implement the thin translator that converts a `DriftVerdict (PROPOSED_EDIT)` into a `ProposedEdit` dataclass that the existing `tier_classification` consumes. Adds `drift_derived` as the 8th documented `change_type` value (additive docstring change to `data_model.py`).

## Context

- **Spec**: FR-004 (PROPOSED_EDIT verdicts routed through existing tier_classification), C-003 (tier_classification surface unchanged)
- **Plan**: D3 (change_type enum extension)
- **Data model**: E4 (ProposedEdit, existing, extended)
- **API contract**: [contracts/api.md](../contracts/api.md) — `build()` signature
- **Branching**: planning_base=`main`, merge_target=`main`.

## Subtasks

### T014 — data_model.py docstring update

**Purpose**: Document the new `drift_derived` value.

**Steps**:

1. Read `scripts/doc_audit/data_model.py` end-to-end first.
2. Locate the `ProposedEdit` class (E-004) at line 78ish. Read its docstring.
3. Update the docstring's `change_type` enumeration to include `drift_derived` as the 8th value:
   ```python
   """E-004 ProposedEdit — single edit awaiting application.
   ...
   ``change_type`` is one of (per SKILL.md §4.1 #1-7 plus #8 added in mission
   drift-event-auto-resolution-01KS8J32):
   ``frontmatter_field_bump``, ``frontmatter_updated_by``,
   ``service_version``, ``file_path_rename``,
   ``dead_reference_removal``, ``agent_registry_add``,
   ``autonomy_level_update``, ``drift_derived``.

   The ``drift_derived`` value indicates the edit was synthesized by the
   drift_interpretation Moment 0 LLM judgment. tier_classification handles
   unknown values by falling through to JUDGMENT — the safe default.
   ...
   """
   ```
4. Do NOT modify the dataclass shape itself. Do NOT add a validator (the field is `str`, not enum).
5. Do NOT update SKILL.md from this WP (out of scope; the additive doc change is sufficient and tier_classification's defense-in-depth fallback handles unknown values via JUDGMENT).

**Files**: `scripts/doc_audit/data_model.py` (docstring change only, ~10 line delta).

**Validation**:
- [ ] `grep "drift_derived" scripts/doc_audit/data_model.py` matches at least once
- [ ] Dataclass shape unchanged: `git diff scripts/doc_audit/data_model.py` shows only docstring lines
- [ ] Existing `pytest tests/doc_audit/` runs without regression

---

### T015 — drift_to_proposed_edit.py — build() function

**Purpose**: The translator. Builds a `ProposedEdit` from a `DriftVerdict (PROPOSED_EDIT, conf ≥0.80)`.

**Steps**:

1. Create `scripts/doc_audit/routing/drift_to_proposed_edit.py` with module docstring.
2. Imports: `from doc_audit.data_model import ProposedEdit`. From `doc_audit.judgment.drift_interpretation import DriftVerdict, DriftInterpretationContext`.
3. Module constants:
   ```python
   DRIFT_DERIVED_CHANGE_TYPE = "drift_derived"
   DEFAULT_INITIAL_TIER = "tier_b"  # Placeholder; tier_classification may reassign
   ```
4. `build(verdict: DriftVerdict, context: DriftInterpretationContext, *, allowed_doc_paths: list[str] | None = None) -> ProposedEdit`:
   - Pre-conditions (raise `ValueError` on violation, with specific message):
     - `verdict.verdict == "PROPOSED_EDIT"`
     - `verdict.confidence >= 0.80`
     - `verdict.proposed_edit is not None`
     - `verdict.proposed_edit["doc_path"]` is non-empty string
     - `verdict.proposed_edit["doc_path"]` ∈ `allowed_doc_paths` (if provided) or `{t.path for t in context.doc_targets}` (defaults to context's targets)
     - `verdict.proposed_edit["current_value"]` and `proposed_value` are strings (may be empty in extreme cases — accept)
   - Build evidence_source: f"drift-event:{context.baseline}:{context.event_id}"
   - Return `ProposedEdit(doc_path=verdict.proposed_edit["doc_path"], change_type=DRIFT_DERIVED_CHANGE_TYPE, current_value=verdict.proposed_edit["current_value"], proposed_value=verdict.proposed_edit["proposed_value"], evidence_source=evidence_source, tier=DEFAULT_INITIAL_TIER, confidence="high")`

**Files**: `scripts/doc_audit/routing/drift_to_proposed_edit.py` (~80 lines).

**Validation**:
- [ ] All pre-conditions raise `ValueError` with descriptive messages on violation
- [ ] Out-of-set `doc_path` rejection is explicit (matches FR validation in WP01's `interpret()` but is independent — the translator is a second line of defense)
- [ ] Returned ProposedEdit has all 7 fields populated

---

### T016 — Routing package init

**Purpose**: Create the routing package boundary.

**Steps**:

1. Create `scripts/doc_audit/routing/__init__.py` with:
   ```python
   """Routing helpers for the doc-audit driver.

   Converts upstream judgments (e.g., DriftVerdict from Moment 0
   drift_interpretation) into the dataclasses expected by the
   existing tier_classification / handle_audit_routing pipeline.
   """

   from .drift_to_proposed_edit import build

   __all__ = ["build"]
   ```

**Files**: `scripts/doc_audit/routing/__init__.py` (~15 lines).

**Validation**:
- [ ] `python3 -c "from scripts.doc_audit.routing import build; print('ok')"` prints `ok`

---

### T017 — Tests

**Purpose**: ≥85% coverage; verify pre-conditions and happy path.

**Steps**:

1. Create `tests/doc_audit/routing/test_drift_to_proposed_edit.py`.
2. Helper: build a minimal `DriftInterpretationContext` and `DriftVerdict` for tests (skeleton fixtures since we may not have WP01 yet).
3. Test cases:
   - **Happy path**: PROPOSED_EDIT verdict at conf 0.85; allowed doc_paths includes the proposed path. Assert returned ProposedEdit has change_type="drift_derived", tier="tier_b", confidence="high", evidence_source matches "drift-event:<baseline>:<event_id>" pattern.
   - **Verdict not PROPOSED_EDIT**: pass JUDGMENT_REQUIRED verdict → ValueError.
   - **Verdict not PROPOSED_EDIT (NO_CHANGE_NEEDED)**: ValueError.
   - **Confidence below threshold**: PROPOSED_EDIT with conf 0.79 → ValueError. (Caller should have demoted; this is defense-in-depth.)
   - **proposed_edit is None**: PROPOSED_EDIT verdict with proposed_edit=None → ValueError.
   - **doc_path not in allowed**: proposed_edit.doc_path is "docs/x.json" but allowed_doc_paths is ["docs/y.json"] → ValueError with "out-of-set" or similar text.
   - **doc_path empty string**: → ValueError.
   - **Falls back to context.doc_targets when allowed_doc_paths is None**: build context with doc_targets including the proposed path; assert success.
   - **evidence_source format**: matches `drift-event:{baseline}:{event_id}` exactly.
   - **change_type constant**: assert returned ProposedEdit.change_type == "drift_derived" (not picked from another existing value).

**Files**: `tests/doc_audit/routing/test_drift_to_proposed_edit.py` (~180 lines, ~10 tests).

**Validation**:
- [ ] `pytest tests/doc_audit/routing/test_drift_to_proposed_edit.py -v` ≥85% coverage
- [ ] All pre-condition violations have explicit ValueError tests

---

## Branch Strategy

Planning_base=`main`, merge_target=`main`. Execution worktree per `lanes.json`.

## Test Strategy

pytest with synthetic DriftVerdict / DriftInterpretationContext fixtures (independent of WP01's implementation — fixtures use type stubs or minimal real instances).

## Definition of Done

- [ ] All 4 subtasks complete.
- [ ] `pytest tests/doc_audit/routing/test_drift_to_proposed_edit.py -v` ≥85%.
- [ ] `git diff scripts/doc_audit/data_model.py` shows only docstring changes (dataclass shape unchanged).
- [ ] Routing package importable; existing tier_classification tests unaffected.

## Risks

- **Coupling to data_model.py**: only docstring change. The change_type field is `str`, not enum, so no runtime validation is added. Defense relies on tier_classification's fallback-to-JUDGMENT behavior for unknown change_types.
- **Pre-condition assumptions**: the translator assumes caller (handle_drift_events) has already demoted low-confidence verdicts. Defense-in-depth check at confidence boundary is explicit.

## Reviewer Guidance

1. Verify the data_model.py change is DOCSTRING ONLY. No dataclass-shape modification.
2. Verify all pre-condition violations raise specific, debuggable ValueError messages.
3. Verify evidence_source format is "drift-event:{baseline}:{event_id}" exactly.
4. Verify the new `drift_derived` constant is used as-is (no aliasing to existing change_type values).

## Implementation Command

```bash
spec-kitty agent action implement WP03 --mission drift-event-auto-resolution-01KS8J32 --agent claude:opus:python-implementer:implementer
```

## Activity Log

- 2026-05-22T20:23:25Z – claude:opus:python-implementer:implementer – shell_pid=7174 – Started implementation via action command
- 2026-05-22T20:43:36Z – claude:opus:python-implementer:implementer – shell_pid=7174 – Ready for review: translator + docstring; 19 tests / 100% coverage; no regression on tier_classification
- 2026-05-22T20:43:43Z – agy:gemini-2.5-pro:spec-kitty-review:reviewer – shell_pid=10389 – Started review via action command
- 2026-05-22T20:47:17Z – agy:gemini-2.5-pro:spec-kitty-review:reviewer – shell_pid=10389 – Review passed: Translator implementation meets all specs, verified with 19 unit tests passing at 100% statement coverage; no dataclass-shape changes in data_model.py (docstring change only).
