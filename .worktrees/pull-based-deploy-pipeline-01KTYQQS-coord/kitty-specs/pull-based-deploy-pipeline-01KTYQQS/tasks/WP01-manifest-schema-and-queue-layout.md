---
work_package_id: WP01
title: Manifest schema and queue layout
dependencies: []
requirement_refs:
- FR-001
- FR-008
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-pull-based-deploy-pipeline-01KTYQQS
base_commit: ac62c23241195e58c1a62e371254583cad6092a2
created_at: '2026-06-12T21:52:55.614929+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
agent: "claude:sonnet:implementer-ivan:reviewer"
shell_pid: "19091"
history:
- ts: '2026-06-12T20:30:00Z'
  actor: spec-kitty.tasks
  event: created
agent_profile: implementer-ivan
authoritative_surface: deploys/
execution_mode: code_change
mission_slug: pull-based-deploy-pipeline-01KTYQQS
owned_files:
- deploys/queued/.gitkeep
- deploys/applied/.gitkeep
- deploys/failed/.gitkeep
- deploys/schema/manifest-v1.schema.json
- deploys/schema/README.md
- tests/deploy/__init__.py
- tests/deploy/test_manifest_schema.py
- tests/deploy/fixtures/manifests/**
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Invoke `/ad-hoc-profile-load implementer-ivan` (or load the profile referenced in this WP's `agent_profile` frontmatter) BEFORE reading anything else in this prompt. The profile sets your identity, governance scope, boundaries, and initialization declaration. Without it, your behavior is unscoped and reviewable defects are likely.

## Objective

Establish the canonical manifest schema and the on-disk directory layout that every other WP in this mission depends on. This is the foundation. No code in the deploy library or the applier can be written until the schema is committed.

## Context

This mission delivers a pull-based deploy pipeline. The manifest is the single declarative artifact operators and agents author to request a deploy. The schema must be precise enough that CI can reject malformed entries before merge, and precise enough that the runtime applier can refuse to execute violating manifests.

The canonical schema shape is documented in `kitty-specs/pull-based-deploy-pipeline-01KTYQQS/contracts/manifest-v1.schema.json`. WP01 mirrors it to `deploys/schema/manifest-v1.schema.json` (the runtime location) and builds the test surface.

## Branch Strategy

- planning_base_branch: `main`
- merge_target_branch: `main`
- Execution worktree allocated per computed lane from `lanes.json` after `finalize-tasks`. The `spec-kitty next` flow will direct you to the correct worktree path.

## Subtask guidance

### T001 — Create the directory skeleton

Create the three queue directories with `.gitkeep` placeholders so git tracks them empty, plus the schema directory.

```
deploys/queued/.gitkeep
deploys/applied/.gitkeep
deploys/failed/.gitkeep
deploys/schema/   (directory; populated in T002+T003)
```

Each `.gitkeep` is a 0-byte file (or contains a single newline). Commit the directory skeleton early so subsequent subtasks can write into it.

### T002 — Author the canonical manifest schema

Copy the content from `kitty-specs/pull-based-deploy-pipeline-01KTYQQS/contracts/manifest-v1.schema.json` verbatim into `deploys/schema/manifest-v1.schema.json`. Verify after copy that the `$id` URL matches the canonical commit location (`https://github.com/kentonium3/kg-automation/blob/main/deploys/schema/manifest-v1.schema.json`).

The schema MUST encode (verify each rule before completing):
- `schema_version: v1` is a literal constant
- `tier` enum is `[1, 2, 3, 4]` (Tier 0 is rejected by enum)
- `entrypoint` pattern requires `scripts/deploy/.../<file>.(sh|py)`
- `oneOf: [{required:[mission_slug]}, {required:[issue]}]` — exactly one source identifier
- `allOf` conditional: Tier 1 or 2 manifests require `verification` block
- `allOf` conditional: applied manifests require `apply_mode` and `applied_at`

### T003 — Write the schema README

A one-page summary at `deploys/schema/README.md`. Audience: a coding agent or operator looking to author a manifest. Cover:
- One-line summary of the manifest's purpose
- Pointer to the canonical schema file
- Pointer to the discipline runbook at `docs/runbooks/deploy/discipline.md` (placeholder; WP07 ships this)
- Pointer to the worked quickstart example at `kitty-specs/pull-based-deploy-pipeline-01KTYQQS/quickstart.md`
- The 6 minimum required fields with one-line descriptions

Keep it under 80 lines.

### T004 — Build manifest fixtures

Create at minimum these fixtures under `tests/deploy/fixtures/manifests/`:

- `valid_tier3_minimal.yaml` — minimal queued Tier 3 entry; should validate
- `valid_tier2_with_verification.yaml` — Tier 2 with non-empty verification.pre and .post
- `valid_applied_entry.yaml` — applied entry with `apply_mode: manifest`, `applied_at`
- `invalid_tier0.yaml` — `tier: 0`; should fail validation (rejected by enum)
- `invalid_tier1_missing_verification.yaml` — Tier 1 without verification; should fail
- `invalid_missing_required.yaml` — missing `entrypoint`; should fail
- `invalid_both_source_identifiers.yaml` — both `mission_slug` AND `issue`; should fail oneOf

Fixtures are operator-readable YAML; no Python helpers. Each ≤ 30 lines.

### T005 — Write the schema test

`tests/deploy/test_manifest_schema.py`:

```python
import json, pathlib, yaml, pytest
from jsonschema import validate, ValidationError

SCHEMA = json.loads(pathlib.Path("deploys/schema/manifest-v1.schema.json").read_text())
FIXTURES = pathlib.Path("tests/deploy/fixtures/manifests")

@pytest.mark.parametrize("name", ["valid_tier3_minimal", "valid_tier2_with_verification", "valid_applied_entry"])
def test_valid_manifests(name):
    data = yaml.safe_load((FIXTURES / f"{name}.yaml").read_text())
    validate(instance=data, schema=SCHEMA)  # raises on failure

@pytest.mark.parametrize("name", ["invalid_tier0", "invalid_tier1_missing_verification",
                                   "invalid_missing_required", "invalid_both_source_identifiers"])
def test_invalid_manifests(name):
    data = yaml.safe_load((FIXTURES / f"{name}.yaml").read_text())
    with pytest.raises(ValidationError):
        validate(instance=data, schema=SCHEMA)
```

Also create `tests/deploy/__init__.py` (empty) so pytest discovers the package.

## Test strategy

- `pytest tests/deploy/test_manifest_schema.py -v` — all subtests pass
- `python -c "import json; json.load(open('deploys/schema/manifest-v1.schema.json'))"` — schema is parseable
- Manual diff against `kitty-specs/.../contracts/manifest-v1.schema.json` — bytewise identical content (excluding any path-specific `$id`)

## Definition of Done

- All 5 owned files exist at their declared paths
- Schema file is valid JSON Schema 2020-12
- 7 fixtures exist (3 valid, 4 invalid)
- `pytest tests/deploy/test_manifest_schema.py -v` exits 0
- README is concise (≤80 lines), accurate, and cross-links the right surfaces
- No file outside `owned_files` is modified

## Risks

- **JSON Schema 2020-12 conditional logic** (`allOf` + `if`/`then`) is finicky. Validate against each fixture immediately rather than trusting the spec text. The `jsonschema` Python library defaults to Draft 7; you must explicitly select 2020-12 with `Draft202012Validator`.
- **YAML vs JSON**: tests load YAML and validate; ensure `PyYAML` is in the project's requirements (it should be already; verify by grepping `requirements.txt`).

## Reviewer guidance

Confirm:
1. `manifest-v1.schema.json` matches `contracts/manifest-v1.schema.json` byte-for-byte (excluding `$id`).
2. Every fixture is a YAML file (`.yaml` extension, not `.json`).
3. Test parametrization covers ALL fixture files (no orphan fixtures).
4. The schema file uses `Draft202012Validator`-compatible syntax (no Draft-7 idioms).
5. No additions outside `owned_files`.

## Activity Log

- 2026-06-12T21:53:04Z – claude:sonnet:implementer-ivan:implementer – shell_pid=17746 – Assigned agent via action command
- 2026-06-12T21:56:38Z – claude:sonnet:implementer-ivan:implementer – shell_pid=17746 – Manifest schema, queue layout, 7 fixtures (3 valid + 4 invalid), parametrized test passing. Schema byte-identical to contracts/. pytest exit 0 (7/7). ruff not installed in env; diff-scoped lint skipped per WP prompt's verify-before-running clause.
- 2026-06-12T21:57:08Z – claude:sonnet:implementer-ivan:reviewer – shell_pid=19091 – Started review via action command
- 2026-06-12T22:01:52Z – user – shell_pid=19091 – Review passed by claude:sonnet:implementer-ivan:reviewer: 5 owned files present, schema byte-identical to canonical contract, Draft202012Validator + yaml.safe_load used, 7 fixtures (3 valid + 4 invalid) parametrized in test, pytest 7/7 PASSED exit 0, no out-of-scope changes.
