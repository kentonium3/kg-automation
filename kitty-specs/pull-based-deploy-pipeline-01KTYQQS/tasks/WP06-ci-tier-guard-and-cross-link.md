---
work_package_id: WP06
title: CI tier guard and doctrinal cross-link verification
dependencies:
- WP01
- WP07
- WP08
requirement_refs:
- FR-006
- FR-008
- FR-016
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Execution worktree allocated per computed lane from lanes.json after finalize-tasks.
subtasks:
- T026
- T027
- T028
- T029
agent: claude
history:
- ts: '2026-06-12T20:30:00Z'
  actor: spec-kitty.tasks
  event: created
agent_profile: implementer-ivan
authoritative_surface: .github/workflows/
execution_mode: code_change
mission_slug: pull-based-deploy-pipeline-01KTYQQS
owned_files:
- .github/workflows/deploy-manifest-validate.yml
- tests/deploy/test_cross_link.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Invoke `/ad-hoc-profile-load implementer-ivan` BEFORE reading anything else.

## Objective

Enforce two invariants in CI:
1. Tier-aware controls — manifests in PRs must pass schema validation and tier policy (Tier 0 rejected at PR time).
2. Doctrinal cross-link integrity — the graph that makes the discipline discoverable to future agents must remain closed (no missing edges, no broken targets).

## Context

This is the discipline's enforcement layer. Without WP06, the doctrine layer (WP07) and the schema (WP01) can silently rot: a developer can refactor CLAUDE.md and break the link to the discipline runbook; the manifest schema can drift; a Tier 0 manifest can slip through PR review. WP06 makes all three impossible.

The doctrinal cross-link graph is defined in `kitty-specs/<slug>/plan.md` ("Doctrinal cross-link graph (the IC-06 invariant)"). The test in T027 walks that exact graph.

## Branch Strategy

- planning_base_branch: `main`
- merge_target_branch: `main`
- Execution worktree per `lanes.json`.

## Subtask guidance

### T026 — `.github/workflows/deploy-manifest-validate.yml`

GitHub Actions workflow. Runs on `pull_request` and `push` to main.

```yaml
name: deploy-manifest-validate
on:
  pull_request:
    paths:
      - 'deploys/**'
      - 'scripts/deploy/**'
      - 'docs/runbooks/deploy/**'
      - 'docs/runbooks/deployment.md'
      - 'docs/design/architecture/data/signal-to-doc-map.json'
      - '.kittify/charter/charter.md'
      - 'CLAUDE.md'
      - '.github/ISSUE_TEMPLATE/feature.md'
      - '.github/ISSUE_TEMPLATE/infra.md'
  push:
    branches: [main]

jobs:
  validate:
    runs-on: ubuntu-latest
    timeout-minutes: 2
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.10' }
      - name: Cache pip
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: pip-${{ hashFiles('requirements*.txt') }}
      - run: pip install PyYAML jsonschema pytest
      - name: Manifest schema + tier guard
        run: pytest tests/deploy/test_manifest_schema.py -v
      - name: Doctrinal cross-link integrity
        run: pytest tests/deploy/test_cross_link.py -v
      - name: Static check — no crontab literal in lib/
        run: |
          if grep -rn -E '(^|[^#])\bcrontab\b' scripts/deploy/lib/; then
            echo "::error::Found crontab literal in scripts/deploy/lib/ — use openclaw cron only (#162)"
            exit 1
          fi
```

The 2-minute timeout enforces the <30s budget from NFR-005 with headroom for setup.

### T027 — `tests/deploy/test_cross_link.py`

Walks the doctrinal cross-link graph. Each edge is asserted as a substring search in the source file.

```python
import pathlib, pytest

REPO = pathlib.Path(__file__).resolve().parents[2]

GRAPH = [
    # (source_file, target_substring, why)
    ('CLAUDE.md', 'docs/runbooks/deploy/discipline.md',
     'kg-automation CLAUDE.md must reference the discipline runbook'),
    ('.kittify/charter/charter.md', 'docs/runbooks/deploy/discipline.md',
     'Project charter Deployment Constraints rule must point at discipline runbook'),
    ('.kittify/charter/charter.md', 'scripts/deploy/lib/README.md',
     'Charter rule must point at the library README'),
    ('docs/runbooks/deployment.md', 'docs/runbooks/deploy/discipline.md',
     'Existing deployment.md must point at the new discipline runbook'),
    ('docs/design/architecture/data/signal-to-doc-map.json', 'docs/runbooks/deploy/discipline.md',
     'signal-to-doc-map.json must reference the discipline runbook'),
    ('docs/design/architecture/data/signal-to-doc-map.json', 'scripts/deploy/lib/README.md',
     'signal-to-doc-map.json must reference the library README'),
    ('.github/ISSUE_TEMPLATE/feature.md', 'docs/runbooks/deploy/discipline.md',
     'Feature template must link to the discipline runbook'),
    ('.github/ISSUE_TEMPLATE/infra.md', 'docs/runbooks/deploy/discipline.md',
     'Infra template must link to the discipline runbook'),
]

TARGETS = [
    'docs/runbooks/deploy/discipline.md',
    'scripts/deploy/lib/README.md',
]

@pytest.mark.parametrize('source,target,why', GRAPH)
def test_edge_present(source, target, why):
    text = (REPO / source).read_text()
    assert target in text, f'{why}: missing reference to {target} in {source}'

@pytest.mark.parametrize('target', TARGETS)
def test_target_exists(target):
    assert (REPO / target).exists(), f'cross-link target does not exist: {target}'
```

### T028 — Static crontab-literal check (in workflow YAML, T026)

Already drafted in T026. Verify the grep pattern excludes comments (lines starting with `#`).

### T029 — Tier-0-rejection and schema-invalid test cases

Add to `tests/deploy/test_cross_link.py` (or a sibling test file):

```python
def test_tier_0_fixture_rejected(tmp_path):
    """A manifest with tier: 0 must fail validation in CI mode."""
    from scripts.deploy.lib import manifest, tier
    fixture = REPO / 'tests/deploy/fixtures/manifests/invalid_tier0.yaml'
    data = yaml.safe_load(fixture.read_text())
    result = tier.tier_guard(data, mode='ci')
    assert not result.ok
    assert result.details.get('error_code') == 'TIER_0_REJECTED'

def test_tier_1_missing_verification_rejected():
    """A Tier 1 manifest without verification block must fail CI tier guard."""
    fixture = REPO / 'tests/deploy/fixtures/manifests/invalid_tier1_missing_verification.yaml'
    data = yaml.safe_load(fixture.read_text())
    result = tier.tier_guard(data, mode='ci')
    assert not result.ok
    assert result.details.get('error_code') == 'VERIFICATION_BLOCK_REQUIRED'
```

These reuse the fixtures from WP01.

## Test strategy

- Push a deliberately Tier-0 manifest to a test PR → CI red
- Push a deliberately broken cross-link (e.g., remove the discipline runbook reference from CLAUDE.md) → CI red
- Push a `crontab` literal into `scripts/deploy/lib/cron.py` → CI red
- Push a deploy with no manifest change → CI green (the workflow has `paths:` filter)
- CI wall-clock time stays under 30 s typical (NFR-005)

## Definition of Done

- 2 owned files exist
- Workflow runs on PR opens and on push to main
- All test cases pass when discipline is intact
- Each test case fails predictably when the corresponding invariant is broken (manual verification — write a test PR for each)
- CI wall-clock under 30 s on the typical fast path
- Static crontab check excludes comments correctly

## Risks

- **`paths:` filter on `pull_request`**: GH Actions `paths:` only triggers when files matching the patterns change. Make sure the patterns cover all surfaces the test walks; otherwise CI silently doesn't run when relevant files change.
- **30s budget**: pip install of PyYAML + jsonschema can take ~10s on a cold runner; use `actions/cache` to keep wall-clock low.
- **Cross-link test runs locally too**: developers running `pytest tests/deploy/test_cross_link.py` locally need the same files present. Document in test docstring.
- **Static check false positives**: `crontab` could appear in a docstring legitimately (e.g., "# DO NOT use crontab"). The grep pattern `(^|[^#])\bcrontab\b` excludes lines starting with `#`. Test with a legitimate docstring containing `crontab` to confirm.

## Reviewer guidance

1. Confirm the workflow's `paths:` filter covers every doctrinal surface.
2. Manually break each cross-link in turn and run `pytest tests/deploy/test_cross_link.py` to confirm test fails predictably.
3. Verify the grep pattern excludes comment lines (test with a fixture file containing `# crontab` — should NOT be flagged).
4. Confirm `actions/cache@v4` is keyed on requirement files.
5. Confirm tier-0-rejection test reuses WP01 fixtures (no duplicate fixture data).
