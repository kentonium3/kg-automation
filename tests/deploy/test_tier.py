"""Tests for :mod:`scripts.deploy.lib.tier`."""

from __future__ import annotations

import pathlib

import pytest

from scripts.deploy.lib import LibResult, tier

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
FIXTURE_DIR = pathlib.Path(__file__).resolve().parent / "fixtures" / "manifests"


def _minimal_tier_manifest(t: int, *, with_verification: bool = False, entrypoint: str | None = None) -> dict:
    m: dict = {
        "schema_version": "v1",
        "name": f"example-tier{t}",
        "mission_slug": "pull-based-deploy-pipeline-01KTYQQS",
        "tier": t,
        "entrypoint": entrypoint or f"scripts/deploy/tier{t}/example.sh",
        "audited_surface": False,
        "created_at": "2026-06-12T20:00:00Z",
        "created_by": "kent@intentional.biz",
    }
    if with_verification:
        m["verification"] = {
            "pre": ["true"],
            "post": ["true"],
        }
    return m


# ---------------------------------------------------------------------------
# Mode validation
# ---------------------------------------------------------------------------


def test_tier_guard_rejects_unknown_mode():
    result = tier.tier_guard(_minimal_tier_manifest(3), mode="foo")

    assert isinstance(result, LibResult)
    assert result.ok is False
    assert result.details["error_code"] == "INVALID_MODE"


def test_tier_guard_rejects_non_dict_manifest():
    result = tier.tier_guard("not a manifest", mode="ci")  # type: ignore[arg-type]

    assert result.ok is False
    assert result.details["error_code"] == "INVALID_MANIFEST"


def test_tier_guard_rejects_manifest_missing_tier_field():
    bad = _minimal_tier_manifest(3)
    bad.pop("tier")

    result = tier.tier_guard(bad, mode="ci")

    assert result.ok is False
    assert result.details["error_code"] == "INVALID_MANIFEST"


# ---------------------------------------------------------------------------
# Tier 0 rejection (both modes)
# ---------------------------------------------------------------------------


def test_tier_guard_ci_rejects_tier_zero():
    # Bypass schema constraints: build the dict directly.
    bad = _minimal_tier_manifest(3)
    bad["tier"] = 0

    result = tier.tier_guard(bad, mode="ci")

    assert result.ok is False
    assert result.details["error_code"] == "TIER_0_REJECTED"
    assert "manual" in result.summary.lower() or "tier 0" in result.summary.lower()


def test_tier_guard_runtime_rejects_tier_zero():
    bad = _minimal_tier_manifest(3)
    bad["tier"] = 0

    result = tier.tier_guard(bad, mode="runtime")

    assert result.ok is False
    assert result.details["error_code"] == "TIER_0_REJECTED"


def test_tier_guard_loads_invalid_tier0_fixture_and_rejects():
    """Ensure the canonical Tier 0 fixture is rejected (real-world shape)."""
    from scripts.deploy.lib import manifest as manifest_mod

    bad = manifest_mod.load_manifest(FIXTURE_DIR / "invalid_tier0.yaml")
    result = tier.tier_guard(bad, mode="ci")

    assert result.ok is False
    assert result.details["error_code"] == "TIER_0_REJECTED"


# ---------------------------------------------------------------------------
# Tier 1/2 require verification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("t", [1, 2])
def test_tier_guard_ci_rejects_tier_1_or_2_without_verification(t):
    bad = _minimal_tier_manifest(t)
    assert "verification" not in bad

    result = tier.tier_guard(bad, mode="ci")

    assert result.ok is False
    assert result.details["error_code"] == "VERIFICATION_BLOCK_REQUIRED"
    assert result.details["tier"] == t


@pytest.mark.parametrize("t", [1, 2])
def test_tier_guard_runtime_rejects_tier_1_or_2_without_verification(t, tmp_path):
    # Make the entrypoint exist so we know the failure is from the verification
    # check, not the runtime entrypoint check.
    entrypoint = tmp_path / "x.sh"
    entrypoint.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    entrypoint.chmod(0o755)
    bad = _minimal_tier_manifest(t, entrypoint=str(entrypoint))

    result = tier.tier_guard(bad, mode="runtime")

    assert result.ok is False
    assert result.details["error_code"] == "VERIFICATION_BLOCK_REQUIRED"


def test_tier_guard_ci_passes_tier_2_with_verification():
    good = _minimal_tier_manifest(2, with_verification=True)

    result = tier.tier_guard(good, mode="ci")

    assert result.ok is True
    assert "pass" in result.summary.lower()
    assert result.details["tier"] == 2


# ---------------------------------------------------------------------------
# Runtime mode: entrypoint existence
# ---------------------------------------------------------------------------


def test_tier_guard_runtime_rejects_missing_entrypoint(tmp_path):
    bad = _minimal_tier_manifest(3, entrypoint=str(tmp_path / "does-not-exist.sh"))

    result = tier.tier_guard(bad, mode="runtime")

    assert result.ok is False
    assert result.details["error_code"] == "ENTRYPOINT_NOT_FOUND"


def test_tier_guard_runtime_rejects_empty_entrypoint():
    bad = _minimal_tier_manifest(3)
    bad["entrypoint"] = ""

    result = tier.tier_guard(bad, mode="runtime")

    assert result.ok is False
    assert result.details["error_code"] == "ENTRYPOINT_NOT_FOUND"


def test_tier_guard_runtime_passes_when_entrypoint_exists(tmp_path):
    entrypoint = tmp_path / "ok.sh"
    entrypoint.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    entrypoint.chmod(0o755)
    good = _minimal_tier_manifest(3, entrypoint=str(entrypoint))

    result = tier.tier_guard(good, mode="runtime")

    assert result.ok is True
    assert result.details["tier"] == 3


def test_tier_guard_ci_does_not_check_entrypoint_on_disk(tmp_path):
    """CI mode is pure metadata — missing entrypoint must NOT trip it."""
    bad = _minimal_tier_manifest(3, entrypoint=str(tmp_path / "missing.sh"))

    result = tier.tier_guard(bad, mode="ci")

    # tier 3 + no verification required, entrypoint not checked in ci.
    assert result.ok is True


# ---------------------------------------------------------------------------
# Pass path: Tier 3/4 minimal manifests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("t", [3, 4])
def test_tier_guard_ci_passes_tier_3_and_4(t):
    good = _minimal_tier_manifest(t)

    result = tier.tier_guard(good, mode="ci")

    assert result.ok is True
    assert result.details["tier"] == t
    assert result.details["mode"] == "ci"


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


def test_mode_constants_match_expected_values():
    assert tier.MODE_CI == "ci"
    assert tier.MODE_RUNTIME == "runtime"
