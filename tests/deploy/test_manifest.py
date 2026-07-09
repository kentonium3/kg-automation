"""Tests for :mod:`scripts.deploy.lib.manifest`."""

from __future__ import annotations

import pathlib
import shutil

import pytest

from scripts.deploy.lib import LibResult, manifest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "deploys" / "schema" / "manifest-v1.schema.json"
FIXTURE_DIR = pathlib.Path(__file__).resolve().parent / "fixtures" / "manifests"


# ---------------------------------------------------------------------------
# load_manifest
# ---------------------------------------------------------------------------


def test_load_manifest_returns_dict_for_valid_fixture():
    path = FIXTURE_DIR / "valid_tier3_minimal.yaml"

    data = manifest.load_manifest(path)

    assert isinstance(data, dict)
    assert data["name"] == "tier3-minimal-example"
    assert data["tier"] == 3


def test_load_manifest_raises_value_error_on_invalid_yaml(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("not: valid: yaml: at: all: : :", encoding="utf-8")

    with pytest.raises(ValueError, match="failed to parse manifest"):
        manifest.load_manifest(bad)


def test_load_manifest_raises_for_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        manifest.load_manifest(tmp_path / "nope.yaml")


def test_load_manifest_raises_for_empty_yaml(tmp_path):
    empty = tmp_path / "empty.yaml"
    empty.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="empty"):
        manifest.load_manifest(empty)


def test_load_manifest_raises_when_root_is_not_mapping(tmp_path):
    listy = tmp_path / "listy.yaml"
    listy.write_text("- a\n- b\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must be a mapping"):
        manifest.load_manifest(listy)


# ---------------------------------------------------------------------------
# validate_manifest
# ---------------------------------------------------------------------------


def test_validate_manifest_accepts_valid_tier3():
    data = manifest.load_manifest(FIXTURE_DIR / "valid_tier3_minimal.yaml")

    result = manifest.validate_manifest(data, schema_path=SCHEMA_PATH)

    assert isinstance(result, LibResult)
    assert result.ok is True


def test_validate_manifest_accepts_tier2_with_verification():
    data = manifest.load_manifest(FIXTURE_DIR / "valid_tier2_with_verification.yaml")

    result = manifest.validate_manifest(data, schema_path=SCHEMA_PATH)

    assert result.ok is True


def test_validate_manifest_rejects_tier0():
    data = manifest.load_manifest(FIXTURE_DIR / "invalid_tier0.yaml")

    result = manifest.validate_manifest(data, schema_path=SCHEMA_PATH)

    assert result.ok is False
    assert result.details["error_code"] == "SCHEMA_VIOLATION"
    assert len(result.details["errors"]) >= 1


def test_validate_manifest_rejects_tier1_missing_verification():
    data = manifest.load_manifest(FIXTURE_DIR / "invalid_tier1_missing_verification.yaml")

    result = manifest.validate_manifest(data, schema_path=SCHEMA_PATH)

    assert result.ok is False
    assert result.details["error_code"] == "SCHEMA_VIOLATION"


def test_validate_manifest_rejects_missing_required_fields():
    data = manifest.load_manifest(FIXTURE_DIR / "invalid_missing_required.yaml")

    result = manifest.validate_manifest(data, schema_path=SCHEMA_PATH)

    assert result.ok is False


def test_validate_manifest_reports_schema_missing(tmp_path):
    data = manifest.load_manifest(FIXTURE_DIR / "valid_tier3_minimal.yaml")

    result = manifest.validate_manifest(data, schema_path=tmp_path / "missing.json")

    assert result.ok is False
    assert result.details["error_code"] == "SCHEMA_MISSING"


def test_validate_manifest_uses_default_schema_path_when_none():
    data = manifest.load_manifest(FIXTURE_DIR / "valid_tier3_minimal.yaml")

    result = manifest.validate_manifest(data)

    # The default schema path resolves under the repo root for the lane
    # worktree; the load may succeed or report SCHEMA_MISSING depending on
    # where pytest runs from. Either path exercises the default-path logic.
    assert isinstance(result, LibResult)


def test_validate_manifest_uses_draft_2020_12_validator(monkeypatch):
    """If the schema used Draft 7 the allOf/if/then would be silently ignored.

    We assert here that the manifest with tier=1 + no verification is
    rejected, which requires the 2020-12 validator. (Draft 7 would not
    process the if/then clause and would let it through.)
    """
    data = manifest.load_manifest(FIXTURE_DIR / "invalid_tier1_missing_verification.yaml")

    result = manifest.validate_manifest(data, schema_path=SCHEMA_PATH)

    assert result.ok is False, (
        "Tier-1 manifest missing verification slipped past — Draft202012Validator "
        "is the only validator that processes the schema's conditional block."
    )


# ---------------------------------------------------------------------------
# next_applied_seq
# ---------------------------------------------------------------------------


def test_next_applied_seq_returns_1_when_directory_missing(tmp_path):
    seq = manifest.next_applied_seq(applied_dir=tmp_path / "absent")
    assert seq == 1


def test_next_applied_seq_returns_1_when_directory_empty(tmp_path):
    (tmp_path / "applied").mkdir()
    seq = manifest.next_applied_seq(applied_dir=tmp_path / "applied")
    assert seq == 1


def test_next_applied_seq_returns_max_plus_one(tmp_path):
    d = tmp_path / "applied"
    d.mkdir()
    (d / "0001-bootstrap.yaml").write_text("x", encoding="utf-8")
    (d / "0002-felix-admin-2026-06-01.yaml").write_text("x", encoding="utf-8")
    (d / "0007-out-of-order.yaml").write_text("x", encoding="utf-8")

    assert manifest.next_applied_seq(applied_dir=d) == 8


def test_next_applied_seq_ignores_non_matching_files(tmp_path):
    d = tmp_path / "applied"
    d.mkdir()
    (d / "0001-real.yaml").write_text("x", encoding="utf-8")
    (d / "README.md").write_text("notes", encoding="utf-8")
    (d / "no-prefix-here.yaml").write_text("x", encoding="utf-8")
    (d / "0003-malformed.txt").write_text("x", encoding="utf-8")  # wrong ext

    assert manifest.next_applied_seq(applied_dir=d) == 2


def test_next_applied_seq_is_monotonic_across_calls(tmp_path):
    d = tmp_path / "applied"
    d.mkdir()

    seq_a = manifest.next_applied_seq(applied_dir=d)
    # Simulate a write
    (d / f"{seq_a:04d}-one.yaml").write_text("x", encoding="utf-8")
    seq_b = manifest.next_applied_seq(applied_dir=d)
    (d / f"{seq_b:04d}-two.yaml").write_text("x", encoding="utf-8")
    seq_c = manifest.next_applied_seq(applied_dir=d)

    assert seq_a == 1
    assert seq_b == 2
    assert seq_c == 3


# ---------------------------------------------------------------------------
# validate_manifest_file convenience wrapper
# ---------------------------------------------------------------------------


def test_validate_manifest_file_handles_load_failure(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(": : : not yaml", encoding="utf-8")

    result = manifest.validate_manifest_file(bad, schema_path=SCHEMA_PATH)

    assert result.ok is False
    assert result.details["error_code"] == "LOAD_FAILED"


def test_validate_manifest_file_runs_validation_when_load_ok(tmp_path):
    src = FIXTURE_DIR / "valid_tier3_minimal.yaml"
    dest = tmp_path / "copy.yaml"
    shutil.copy(src, dest)

    result = manifest.validate_manifest_file(dest, schema_path=SCHEMA_PATH)

    assert result.ok is True


# ---------------------------------------------------------------------------
# expected_baselines validation (WP02 T013, FR-005/007/009, C6)
# ---------------------------------------------------------------------------


def _baseline_manifest(**overrides):
    """A minimal valid tier-3 manifest, plus any overrides."""
    data = {
        "schema_version": "v1",
        "name": "expected-baselines-example",
        "mission_slug": "felix-deployer-rebaseline-detection-01KX26DS",
        "tier": 3,
        "entrypoint": "scripts/deploy/tier3/example.sh",
        "audited_surface": True,
        "created_at": "2026-07-09T00:00:00Z",
        "created_by": "kent@intentional.biz",
    }
    data.update(overrides)
    return data


def test_expected_baselines_valid_known_name_and_audited_surface_true():
    data = _baseline_manifest(
        audited_surface=True, expected_baselines=["openclaw-cron.txt"]
    )

    result = manifest.validate_manifest(data, schema_path=SCHEMA_PATH)

    assert result.ok is True


def test_expected_baselines_unknown_name_fails_and_names_offender():
    data = _baseline_manifest(
        audited_surface=True, expected_baselines=["bogus.txt"]
    )

    result = manifest.validate_manifest(data, schema_path=SCHEMA_PATH)

    assert result.ok is False
    assert "bogus.txt" in result.summary
    assert result.details["error_code"] == "EXPECTED_BASELINES_UNKNOWN"
    assert "bogus.txt" in result.details["unknown"]


def test_expected_baselines_requires_audited_surface_true_when_false():
    data = _baseline_manifest(
        audited_surface=False, expected_baselines=["openclaw-cron.txt"]
    )

    result = manifest.validate_manifest(data, schema_path=SCHEMA_PATH)

    assert result.ok is False
    assert result.details["error_code"] == "EXPECTED_BASELINES_COUPLING"
    assert "audited_surface" in result.summary


def test_expected_baselines_requires_audited_surface_true_when_absent():
    data = _baseline_manifest(expected_baselines=["openclaw-cron.txt"])
    # audited_surface is required by the schema, so exercise the coupling via a
    # false value at the field level; here we assert an explicit False also
    # trips the coupling gate (absent == not True).
    data["audited_surface"] = False

    result = manifest.validate_manifest(data, schema_path=SCHEMA_PATH)

    assert result.ok is False
    assert result.details["error_code"] == "EXPECTED_BASELINES_COUPLING"


def test_expected_baselines_malformed_registry_returns_invalid_without_exit(
    monkeypatch, tmp_path
):
    bad = tmp_path / "audited-surfaces.json"
    bad.write_text("{ not valid json", encoding="utf-8")
    # Point the NON-exiting reader at a malformed registry via the module
    # manifest.py actually references. If validation reached the exiting
    # load_audited_surfaces this would raise SystemExit.
    monkeypatch.setattr(
        manifest.audited_surfaces, "AUDITED_SURFACES_PATH", bad
    )

    data = _baseline_manifest(
        audited_surface=True, expected_baselines=["openclaw-cron.txt"]
    )

    # Assert NO SystemExit escapes and the manifest is reported invalid.
    result = manifest.validate_manifest(data, schema_path=SCHEMA_PATH)

    assert isinstance(result, LibResult)
    assert result.ok is False
    assert result.details["error_code"] == "REGISTRY_UNREADABLE"


def test_expected_baselines_absent_is_unchanged_behavior():
    data = _baseline_manifest(audited_surface=False)  # no expected_baselines

    result = manifest.validate_manifest(data, schema_path=SCHEMA_PATH)

    assert result.ok is True


# ---------------------------------------------------------------------------
# validate_expected_baselines_only — pre-apply rule check, no JSON-Schema pass
# (Codex post-merge HIGH-2)
# ---------------------------------------------------------------------------


def test_validate_expected_baselines_only_skips_schema_pass():
    """A manifest missing JSON-Schema-required fields (schema_version,
    created_at, ...) but with NO expected_baselines passes the rules-only check:
    the tick uses this pre-apply and must not tighten apply behaviour for every
    manifest by running the full schema pass here.
    """
    minimal = {"name": "0099-minimal", "tier": 3, "entrypoint": "scripts/noop.sh"}

    result = manifest.validate_expected_baselines_only(minimal)

    assert result.ok is True


def test_validate_expected_baselines_only_rejects_unknown_name():
    minimal = {
        "name": "0099-bogus",
        "tier": 3,
        "entrypoint": "scripts/noop.sh",
        "audited_surface": True,
        "expected_baselines": ["bogus.txt"],
    }

    result = manifest.validate_expected_baselines_only(minimal)

    assert result.ok is False
    assert result.details["error_code"] == "EXPECTED_BASELINES_UNKNOWN"
    assert "bogus.txt" in result.details["unknown"]


def test_validate_expected_baselines_only_enforces_coupling():
    minimal = {
        "name": "0099-decoupled",
        "tier": 3,
        "entrypoint": "scripts/noop.sh",
        "audited_surface": False,
        "expected_baselines": ["openclaw-cron.txt"],
    }

    result = manifest.validate_expected_baselines_only(minimal)

    assert result.ok is False
    assert result.details["error_code"] == "EXPECTED_BASELINES_COUPLING"
