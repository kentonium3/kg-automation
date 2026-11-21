---
work_package_id: WP01
title: Rule library + new-shape fixtures
dependencies: []
requirement_refs:
- FR-014
- FR-020
planning_base_branch: fix/felix-rrule-adaptation
merge_target_branch: fix/felix-rrule-adaptation
branch_strategy: Planning artifacts for this mission were generated on fix/felix-rrule-adaptation. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/felix-rrule-adaptation unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-felix-rrule-adaptation-01M7TKNX
base_commit: 70fcd99ce4b7ef6f5e0ab79c05cf7d8286b431f1
created_at: '2026-11-19T21:47:20.538614+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
phase: Phase 0 - Foundation
history:
- at: '2026-11-19T22:30:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/common/vikunja_rule.py
create_intent:
- scripts/common/vikunja_rule.py
- tests/common/test_vikunja_rule.py
- tests/common/vikunja_v2_factory.py
- tests/common/test_vikunja_v2_factory.py
execution_mode: code_change
model: claude-opus-5-5
owned_files:
- scripts/common/vikunja_rule.py
- tests/common/test_vikunja_rule.py
- tests/common/vikunja_v2_factory.py
- tests/common/test_vikunja_v2_factory.py
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP01 – Rule library + new-shape fixtures

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## ⚠️ IMPORTANT: Review Feedback

Check `spec-kitty agent tasks status` for a `review_ref`. If this WP came back from review, address every feedback item and record each fix with `spec-kitty agent tasks add-history WP01 --note "..."`.

---

## Objectives & Success Criteria

Deliver `scripts/common/vikunja_rule.py`, a **pure** library with no network and no client import, plus a test-only fixture factory for the real Vikunja v2 task body. Every later WP builds on these two.

Done when:
- All functions in the contract exist with type hints and docstrings, and are covered by tests.
- `completion_outcome` implements the revised rules in `data-model.md` exactly, including the "explicit reason only" exhaustion rule.
- The factory's default task has exactly the v2 key set captured live in `research.md` R-003.
- `make test` passes.

## Context & Constraints

- Read `kitty-specs/felix-rrule-adaptation-01M7TKNX/data-model.md`, especially Rule, Completion outcome and Invariants. Also read `contracts/vikunja-client-v2.md` § `vikunja_rule.py`, and `research.md` R-003 and R-010.
- Read `post-plan-review.md`, findings 1 and 2 and re-review new-HIGH 1. The classifier must never call an unverified Done a normal end.
- Server facts (vikunja-harness `d7e202228`):
  - `repeat` responses are lowercase (`daily`, `mo`, `2tu`). `repeats_rrule` is RFC 5545 uppercase.
  - `read_only` is response-only.
  - COUNT is the number of occurrences *remaining* and is decremented on each completion.
  - COUNT exhaustion clears the rule and leaves the task Done. UNTIL having passed leaves it Done with the rule kept.
- Python 3.12 compatible (office2 runs 3.12.3). Stdlib only.
- Charter: fixtures mirror real inputs, and no dead code. Every function here must have a planned caller in a later WP; the caller is noted against each one.

## Branch Strategy

- **Strategy**: {{branch_strategy}}
- **Planning base branch**: {{planning_base_branch}}
- **Merge target branch**: {{merge_target_branch}}

> Populated by `spec-kitty agent mission finalize-tasks`. Execution worktrees are allocated per computed lane from `lanes.json`.

Implementation command:

```bash
spec-kitty agent action implement WP01 --agent claude --mission felix-rrule-adaptation-01M7TKNX
```

## Subtasks & Detailed Guidance

### Subtask T001 – `normalise`, `same_rule`, `has_rule`

- **Purpose**: A single definition of "the same rule", so callers stop comparing raw dicts. Raw dicts differ in list order, casing, `read_only`, and zero-valued parts.
- **Steps**:
  1. `normalise(repeat: Mapping | None) -> dict | None`:
     - Return `None` for `None`, `{}`, or a mapping with no `freq`.
     - Drop `read_only`.
     - Lowercase the string values (`freq`, `wkst`, each `by_day` entry).
     - Sort every `by_*` list. `by_day` entries like `"2tu"` sort as strings, which is fine because equality is all that matters.
     - Drop keys whose value is `0`, `""`, `None` or `[]`. Exception: keep `interval`, defaulting it to `1` when it is missing or 0, because the server treats interval 0 as 1.
     - Keep `until` as the server's RFC3339 string, normalised to `Z` UTC. Reuse `scripts/common/et_datetime.py` if it already has a parser; grep before writing a new one.
  2. `same_rule(a, b) -> bool` returns `normalise(a) == normalise(b)`.
  3. `has_rule(task: Mapping) -> bool` returns `normalise(task.get("repeat")) is not None`.
  4. `rule_equal_except_count(before, after) -> bool` is true when the normalised rules are equal after removing `count`, **and** `after.count == before.count - 1`. WP03 and WP04 use it for "advanced".
- **Files**: `scripts/common/vikunja_rule.py`
- **Callers (no dead code)**: WP03, WP04, WP05, WP06, WP07, WP10.

### Subtask T002 – Rule text ⇄ parts

- **Purpose**: The schedule YAML (WP07), the inventory snapshot (WP10, whose DB column stores rule text) and `create_task --rrule` (WP08) carry RFC 5545 text. Comparisons need parts.
- **Steps**:
  1. `rrule_text_to_parts(text: str) -> dict`:
     - Parse `FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,WE;COUNT=6`, tolerating an optional `RRULE:` prefix.
     - Map the keys `FREQ→freq`, `INTERVAL→interval`, `BYDAY→by_day`, `BYMONTHDAY→by_month_day`, `BYMONTH→by_month`, `BYYEARDAY→by_year_day`, `BYWEEKNO→by_week_no`, `BYSETPOS→by_set_pos`, `BYHOUR→by_hour`, `BYMINUTE→by_minute`, `BYSECOND→by_second`, `COUNT→count`, `UNTIL→until`, `WKST→wkst`.
     - Ints for the numeric lists, lowercase for strings.
     - `UNTIL=20261231T235959Z` → `"2026-12-31T23:59:59Z"`.
     - Raise `ValueError` on an unknown key or a missing FREQ. Do not try to validate RRULE semantics; the server does that (preview 2002).
  2. `parts_to_rrule_text(parts) -> str`: the inverse, with a deterministic key order (FREQ, INTERVAL, then BY* in RFC order, COUNT, UNTIL, WKST), uppercase.
  3. A round trip `parts → text → parts` is identity under `normalise`.
- **Parallel?**: Yes, independent of T001's comparison functions.

### Subtask T003 – `completion_outcome` and `exhaustion_expected`

- **Purpose**: FR-014. Tell a normal advance from a normal end from anything unexpected, without ever treating a bare `done=true` as a normal end.
- **Steps**:
  1. `exhaustion_expected(before: Mapping, *, preview: Callable[..., Mapping] | None) -> Literal["yes", "no", "unknown"]`:
     - The rule is normalised from `before["repeat"]`.
     - No rule → `"no"`. The caller isn't completing a series.
     - `count == 1` → `"yes"`.
     - `until` set **and** `before.get("repeats_from_current_date") is False` **and** `preview` is given: call `preview(repeat=rule, due_date=before["due_date"], repeats_from_current_date=False, count=1)`.
       - `reason` in `{"until_passed", "count_exhausted"}` → `"yes"`.
       - Non-empty occurrences and no reason → `"no"`.
       - **Anything else** (empty list with another reason, `anchor_beyond_horizon`, `no_occurrence`, missing reason) → `"unknown"`.
     - `until` set but the from-current flag is true, or `preview` is None, or `preview` raises → `"unknown"`. Catch the client's `VikunjaError` family by duck-typing an `Exception` subclass. Do **not** import the client; accept exceptions generically and return `"unknown"`.
     - No COUNT and no UNTIL → `"no"`.
  2. `completion_outcome(before, after, *, exhaustion: str) -> Literal["advanced", "series_ended", "unexpected"]`:
     - `advanced`: `has_rule(before)`, `after["done"] is False`, `after["due_date"] > before["due_date"]` (parse both instants), and either `same_rule(before, after)` or `rule_equal_except_count(before, after)`.
     - `series_ended`: `after["done"] is True` and `exhaustion == "yes"`. For COUNT also require `not has_rule(after)`. For UNTIL, the rule is kept.
     - Otherwise `unexpected`.
  3. Keep the function pure. The caller passes `exhaustion`, computed **before** the write.
- **Callers**: WP03 (habit completion), WP04 (escalation done).

### Subtask T004 – New-shape fixture factory

- **Purpose**: Charter rule that fixtures mirror real inputs. About 30 test files encode the dead shape; later WPs convert to this factory.
- **Steps**:
  1. Create `tests/common/vikunja_v2_factory.py`. It is a plain module, **not** a conftest, so any test package can import it.
  2. `V2_TASK_KEYS`: the exact key list from research.md R-003, including `$schema`.
  3. `make_task(**overrides) -> dict` returns a v2 single-task body with realistic defaults:
     - `id=14`, `project_id`, `title`, `done=False`, `due_date="2026-11-20T04:59:59Z"`.
     - `repeat={"freq": "daily", "interval": 1}`, `repeats_rrule="FREQ=DAILY;INTERVAL=1"`, `repeats_from_current_date=False`.
     - `reminders=None`, `labels=[]`, `assignees=None`, and so on.
     - When `repeat` is overridden, derive `repeats_rrule` with `parts_to_rrule_text`, unless `repeats_rrule` is also given.
  4. `make_list_task(**overrides)`: the same, without `repeats_rrule`, because list endpoints omit it (research.md R-003).
  5. `with_reminder(task, relative_to="due_date", relative_period=-3600)` helper.
  6. `strip_rule(task)` returns a copy with `repeat=None`, `repeats_rrule` absent and `repeats_from_current_date=False`. That is what a v1 narrow write leaves behind, and it is the positive control for every round-trip test.
- **Parallel?**: Yes.

### Subtask T005 – Tests

- **Files**: `tests/common/test_vikunja_rule.py`, `tests/common/test_vikunja_v2_factory.py`
- **Cases (minimum)**:
  - `normalise`: casing, list order, `read_only`, `{}`→None, interval default, until normalisation.
  - `same_rule` true and false pairs.
  - `rule_equal_except_count` for COUNT 2→1 (true), 2→2 (false), and a different freq (false).
  - Text round trips for daily, weekly with BYDAY, monthly BYMONTHDAY, COUNT, UNTIL, and the `RRULE:` prefix.
  - `exhaustion_expected`:
    - count 1 → yes;
    - UNTIL with a fake preview returning `until_passed` → yes;
    - UNTIL with an empty list and reason `anchor_beyond_horizon` → unknown;
    - UNTIL with a from-current flag → unknown;
    - preview raising → unknown;
    - no COUNT/UNTIL → no.
  - `completion_outcome`:
    - advanced, same rule;
    - advanced, COUNT 2→1;
    - series_ended, COUNT 1 → done with no rule;
    - series_ended, UNTIL → done with rule kept;
    - **unexpected** for done when exhaustion is unknown;
    - unexpected for done=false with no due-date change;
    - unexpected for a rule that changed beyond COUNT.
  - Factory: the key set equals `V2_TASK_KEYS`; `make_list_task` lacks `repeats_rrule`; `strip_rule` removes the rule.

```bash
python3 -m pytest -q tests/common/test_vikunja_rule.py tests/common/test_vikunja_v2_factory.py
```

## Test Strategy

Unit tests only, with no HTTP. The autouse guard blocks urlopen anyway. Finish with `make test`.

## Risks & Mitigations

- Over-normalising so that two genuinely different rules compare equal. Test the BYDAY and BYMONTHDAY differences explicitly.
- Silently treating "unknown" as "yes". A dedicated test asserts `unexpected` in that case.

## Review Guidance

- Is it pure: no import of `vikunja_client`, no I/O?
- Does it match data-model.md's Completion outcome text word for word?
- Does each function name its caller WP? Reject dead helpers.

## Progress & Status

Use `spec-kitty agent tasks add-history WP01 --note "..."`, `spec-kitty agent tasks mark-status T00x --status done`, and `spec-kitty agent tasks status`. Do not edit status in this file.
