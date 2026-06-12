"""Doctrinal cross-link integrity tests (the IC-06 invariant).

The deploy discipline is only discoverable to future agents if every
doctrinal surface keeps its link to the canonical runbook and library
README. This test walks the cross-link graph defined in
``kitty-specs/pull-based-deploy-pipeline-01KTYQQS/plan.md``
("Doctrinal cross-link graph (the IC-06 invariant)") and asserts each
edge as a substring search in the source file.

The test runs in CI on every PR (see
``.github/workflows/deploy-manifest-validate.yml``) so any change to a
doctrinal surface that breaks a link fails the build before merge.

Local execution:
    pytest tests/deploy/test_cross_link.py -v

The test also runs locally for developers. When a target file does not
yet exist in the working tree (e.g., during an isolated work-package
lane workspace where dependent WPs have not merged yet), the missing
target is reported as a skip rather than a failure. In CI on the merged
``main`` branch, the workflow sets ``DEPLOY_CROSS_LINK_STRICT=1`` so
missing targets fail the build instead — preserving the IC-06 invariant
on shipped code. See FR-016 in the mission spec.

T029 cases (tier-0 rejection and Tier-1 missing-verification rejection)
are layered onto the same test surface so the entire CI tier-guard and
cross-link contract is exercised in one pytest run. The T029 cases use
the WP01 fixtures from ``tests/deploy/fixtures/manifests/`` and exercise
an inline ``ci_tier_guard`` helper that matches the contract the deploy
library's ``lib.tier`` module will expose once WP02/WP03 merge to main.
"""

from __future__ import annotations

import json
import os
import pathlib
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator, ValidationError

REPO = pathlib.Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO / "deploys" / "schema" / "manifest-v1.schema.json"
FIXTURES_DIR = pathlib.Path(__file__).resolve().parent / "fixtures" / "manifests"

# The IC-06 cross-link graph.
#
# Each tuple is (source_file, target_substring, rationale). The test
# reads source_file and asserts target_substring appears at least once.
# Edits to this list must also update the graph in plan.md to keep the
# two surfaces in lockstep.
GRAPH: list[tuple[str, str, str]] = [
    (
        "CLAUDE.md",
        "docs/runbooks/deploy/discipline.md",
        "kg-automation CLAUDE.md must reference the discipline runbook",
    ),
    (
        ".kittify/charter/charter.md",
        "docs/runbooks/deploy/discipline.md",
        "Project charter Deployment Constraints rule must point at the discipline runbook",
    ),
    (
        ".kittify/charter/charter.md",
        "scripts/deploy/lib/README.md",
        "Charter Deployment Constraints rule must point at the library README",
    ),
    (
        "docs/runbooks/deployment.md",
        "docs/runbooks/deploy/discipline.md",
        "Existing deployment.md must point at the new discipline runbook",
    ),
    (
        "docs/design/architecture/data/signal-to-doc-map.json",
        "docs/runbooks/deploy/discipline.md",
        "signal-to-doc-map.json must reference the discipline runbook",
    ),
    (
        "docs/design/architecture/data/signal-to-doc-map.json",
        "scripts/deploy/lib/README.md",
        "signal-to-doc-map.json must reference the library README",
    ),
    (
        ".github/ISSUE_TEMPLATE/feature.md",
        "docs/runbooks/deploy/discipline.md",
        "Feature template must link to the discipline runbook",
    ),
    (
        ".github/ISSUE_TEMPLATE/infra.md",
        "docs/runbooks/deploy/discipline.md",
        "Infra template must link to the discipline runbook",
    ),
]

# Targets that must exist as real files after the mission lands on main.
TARGETS: list[str] = [
    "docs/runbooks/deploy/discipline.md",
    "scripts/deploy/lib/README.md",
]


def _strict_mode() -> bool:
    """Whether to treat missing files as failures (CI) vs skips (lane workspace).

    Set ``DEPLOY_CROSS_LINK_STRICT=1`` in the CI workflow so missing
    cross-link targets fail the build on the merged main branch.
    Defaults to non-strict so developers running ``pytest`` in an
    isolated work-package lane workspace can see the rest of the suite
    pass while dependent WPs are still in flight.
    """
    return os.environ.get("DEPLOY_CROSS_LINK_STRICT", "").strip() == "1"


def _missing(path: pathlib.Path, label: str) -> None:
    """Skip or fail depending on strict mode."""
    msg = f"cross-link {label} does not exist in this checkout: {path}"
    if _strict_mode():
        pytest.fail(msg)
    pytest.skip(msg)


@pytest.mark.parametrize("source,target,why", GRAPH)
def test_edge_present(source: str, target: str, why: str) -> None:
    """Every doctrinal edge is present as a literal substring."""
    source_path = REPO / source
    if not source_path.exists():
        _missing(source_path, f"source ({source})")
    text = source_path.read_text(encoding="utf-8")
    assert target in text, f"{why}: missing reference to {target!r} in {source}"


@pytest.mark.parametrize("target", TARGETS)
def test_target_exists(target: str) -> None:
    """Every cross-link target resolves to a real file."""
    path = REPO / target
    if not path.exists():
        _missing(path, f"target ({target})")
    # Sanity: targets must be non-empty so links don't point at an empty stub.
    assert path.stat().st_size > 0, f"cross-link target is empty: {target}"


# ---------------------------------------------------------------------------
# T029 — CI tier guard test cases
#
# WP01 ships the manifest schema and the invalid_* fixtures. The CI
# workflow runs ``tests/deploy/test_manifest_schema.py`` to exercise
# the pure schema-level rejection. This file adds the *workflow-level*
# tier-guard contract: when a tier-0 manifest reaches the CI step, the
# guard must refuse it with a structured error code; when a Tier-1
# manifest is missing its verification block, the same guard must refuse
# it with a different structured error code.
#
# The deploy library's ``scripts/deploy/lib/tier.py`` module (WP02/WP03)
# will expose the canonical ``tier_guard`` function with the same contract
# once those WPs land on main. Until then this file ships an inline
# equivalent so the CI gate and the test surface are decoupled from
# library availability in any single lane workspace.
# ---------------------------------------------------------------------------


class TierGuardResult:
    """Lightweight result object mirroring lib.tier.tier_guard's contract.

    Attributes:
        ok: True when the manifest is allowed; False when rejected.
        details: Structured failure metadata; carries ``error_code`` on rejection.
    """

    __slots__ = ("ok", "details")

    def __init__(self, ok: bool, details: dict[str, Any] | None = None) -> None:
        self.ok = ok
        self.details = details or {}


def _load_schema_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def ci_tier_guard(data: dict[str, Any]) -> TierGuardResult:
    """In-test mirror of lib.tier.tier_guard for the CI mode contract.

    Order of checks:
    1. Schema validation — if the manifest does not conform to v1, reject
       with ``error_code=SCHEMA_INVALID``.
    2. Tier 0 — if the manifest declares tier 0, reject with
       ``error_code=TIER_0_REJECTED`` regardless of any other fields.
    3. Tier 1/2 verification block — reject with
       ``error_code=VERIFICATION_BLOCK_REQUIRED`` when the verification
       key is absent or empty for a tier that requires it.
    """
    validator = _load_schema_validator()
    errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
    if errors:
        # Tier 0 is encoded both at the JSON-schema level (via the enum
        # restriction on the tier property) and at the policy level. We
        # want the policy-level error code to take precedence so the
        # operator sees the actionable message, not a raw schema error.
        if data.get("tier") == 0:
            return TierGuardResult(
                ok=False,
                details={
                    "error_code": "TIER_0_REJECTED",
                    "reason": "Tier 0 changes are hard-locked from the deploy pipeline",
                },
            )
        # Tier 1/2 missing-verification is also encoded at the schema
        # level via the conditional allOf block. Prefer the policy code.
        tier = data.get("tier")
        if tier in (1, 2) and not data.get("verification"):
            return TierGuardResult(
                ok=False,
                details={
                    "error_code": "VERIFICATION_BLOCK_REQUIRED",
                    "reason": f"Tier {tier} manifests must include a verification block",
                },
            )
        return TierGuardResult(
            ok=False,
            details={
                "error_code": "SCHEMA_INVALID",
                "reason": str(errors[0].message),
            },
        )
    if data.get("tier") == 0:
        return TierGuardResult(
            ok=False,
            details={
                "error_code": "TIER_0_REJECTED",
                "reason": "Tier 0 changes are hard-locked from the deploy pipeline",
            },
        )
    return TierGuardResult(ok=True)


def _load_fixture(name: str) -> dict[str, Any]:
    path = FIXTURES_DIR / f"{name}.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_tier_0_fixture_rejected() -> None:
    """A manifest with tier: 0 must fail CI tier guard with TIER_0_REJECTED."""
    data = _load_fixture("invalid_tier0")
    result = ci_tier_guard(data)
    assert not result.ok
    assert result.details.get("error_code") == "TIER_0_REJECTED", (
        f"expected TIER_0_REJECTED, got {result.details!r}"
    )


def test_tier_1_missing_verification_rejected() -> None:
    """A Tier-1 manifest without verification block must fail with VERIFICATION_BLOCK_REQUIRED."""
    data = _load_fixture("invalid_tier1_missing_verification")
    result = ci_tier_guard(data)
    assert not result.ok
    assert result.details.get("error_code") == "VERIFICATION_BLOCK_REQUIRED", (
        f"expected VERIFICATION_BLOCK_REQUIRED, got {result.details!r}"
    )


def test_valid_tier3_passes_ci_tier_guard() -> None:
    """A valid Tier-3 manifest must pass the CI tier guard."""
    data = _load_fixture("valid_tier3_minimal")
    result = ci_tier_guard(data)
    assert result.ok, f"expected pass, got {result.details!r}"


def test_valid_tier2_with_verification_passes() -> None:
    """A valid Tier-2 manifest with verification block must pass."""
    data = _load_fixture("valid_tier2_with_verification")
    result = ci_tier_guard(data)
    assert result.ok, f"expected pass, got {result.details!r}"


# ---------------------------------------------------------------------------
# Workflow-self-test: the CI YAML must wire the tier-guard step.
# This catches accidental removal of the validation step at PR time.
# ---------------------------------------------------------------------------


WORKFLOW_PATH = REPO / ".github" / "workflows" / "deploy-manifest-validate.yml"


def test_workflow_yaml_parses() -> None:
    """The deploy-manifest-validate workflow YAML must be valid."""
    if not WORKFLOW_PATH.exists():
        _missing(WORKFLOW_PATH, "workflow file")
    parsed = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict), "workflow YAML did not parse to a mapping"
    # YAML's `on:` key is interpreted as the boolean True by the YAML 1.1
    # spec used by PyYAML. Accept either spelling so this test does not
    # become brittle to PyYAML upgrades.
    assert ("on" in parsed) or (True in parsed), "workflow missing trigger block"
    assert "jobs" in parsed, "workflow missing jobs block"


def test_workflow_covers_tier_guard_and_cross_link() -> None:
    """Workflow must run both the manifest-schema test and the cross-link test."""
    if not WORKFLOW_PATH.exists():
        _missing(WORKFLOW_PATH, "workflow file")
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "tests/deploy/test_manifest_schema.py" in text, (
        "workflow must run the WP01 manifest-schema test suite (FR-006/FR-008)"
    )
    assert "tests/deploy/test_cross_link.py" in text, (
        "workflow must run the cross-link test suite (FR-016)"
    )


def test_workflow_paths_cover_all_doctrinal_surfaces() -> None:
    """The workflow's paths: filter must cover every source in the cross-link graph.

    If a doctrinal surface changes but the workflow isn't triggered, CI
    silently misses a broken link. This test makes that condition a
    build failure.
    """
    if not WORKFLOW_PATH.exists():
        _missing(WORKFLOW_PATH, "workflow file")
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    required = {
        "deploys/**",
        "scripts/deploy/**",
        "docs/runbooks/deploy/**",
        "docs/runbooks/deployment.md",
        "docs/design/architecture/data/signal-to-doc-map.json",
        ".kittify/charter/charter.md",
        "CLAUDE.md",
        ".github/ISSUE_TEMPLATE/feature.md",
        ".github/ISSUE_TEMPLATE/infra.md",
    }
    missing = [p for p in required if p not in text]
    assert not missing, f"workflow paths filter is missing patterns: {missing}"


def test_workflow_static_crontab_check_present() -> None:
    """The static crontab-literal grep step must be wired into the workflow.

    The static check enforces FR-017 (no system crontab in the deploy
    library; OpenClaw cron only). It belongs in the CI workflow so PRs
    that reintroduce a crontab literal fail at PR time.
    """
    if not WORKFLOW_PATH.exists():
        _missing(WORKFLOW_PATH, "workflow file")
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    # The grep pattern must exclude comment lines so legitimate
    # "# crontab is forbidden" docstrings do not trip the check.
    assert "grep" in text and "crontab" in text, (
        "workflow must include a static crontab-literal check on scripts/deploy/lib/"
    )
    assert "scripts/deploy/lib/" in text, (
        "static check must target scripts/deploy/lib/"
    )
