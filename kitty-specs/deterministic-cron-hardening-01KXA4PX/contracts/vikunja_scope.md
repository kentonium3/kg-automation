# Contract: vikunja_scope (IC-01)

**Module**: `scripts/common/vikunja_scope.py` (importable; no CLI required)

## Accessors

- `get_escalation_excluded_project_ids() -> list[int]`
  Returns the project IDs escalation excludes. Today `[11, 13]`.
- `get_habit_selector() -> HabitSelector`
  Returns `{"kind": "project_id"|"label", "value": <int|str>}`. Today `{"kind":"project_id","value":13}`.
- `habit_project_id() -> int | None`
  Convenience: the int project id when `kind == "project_id"`, else `None` (label form).

## Invariants
- Consumers MUST use accessors, never literal IDs.
- Changing the taxonomy (e.g. habit identity project→label) is a value edit in this module only — **0 changes** to enumeration/selection logic (NFR-004).

## Tests (tests/common/test_vikunja_scope.py)
- Accessors return the current values.
- `habit_project_id()` returns the int for the project_id form and `None` for a label form.
- A label-form selector round-trips through `get_habit_selector()` (proves the #714 swap is config-only).
