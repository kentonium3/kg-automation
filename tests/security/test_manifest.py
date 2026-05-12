"""Tests for credential_health_check.manifest."""
from __future__ import annotations

from pathlib import Path

import pytest

from credential_health_check.manifest import (
    Credential,
    ManifestQualityIssue,
    ManifestUnreadableError,
    read_manifest,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_read_valid_manifest_returns_only_well_formed():
    well_formed, malformed = read_manifest(str(FIXTURES / "manifest-valid.json"))
    assert malformed == []
    assert len(well_formed) == 9


def test_kentonium3_pat_present_in_valid_manifest():
    well_formed, _ = read_manifest(str(FIXTURES / "manifest-valid.json"))
    names = [c.name for c in well_formed]
    assert "kentonium3-pat" in names


def test_near_expiry_fixture_well_formed_count_matches_valid():
    valid_well_formed, _ = read_manifest(str(FIXTURES / "manifest-valid.json"))
    near_well_formed, near_malformed = read_manifest(
        str(FIXTURES / "manifest-near-expiry.json")
    )
    assert near_malformed == []
    assert len(near_well_formed) == len(valid_well_formed)


def test_missing_last_reviewed_is_malformed():
    well_formed, malformed = read_manifest(
        str(FIXTURES / "manifest-missing-last-reviewed.json")
    )
    # Fixture: one good entry + one entry missing last_reviewed.
    assert len(well_formed) == 1
    assert len(malformed) == 1
    assert malformed[0].credential_name == "missing-last-reviewed-cred"
    assert "missing last_reviewed" in malformed[0].reason.lower()


def test_bad_review_cadence_is_malformed():
    well_formed, malformed = read_manifest(
        str(FIXTURES / "manifest-bad-review-cadence.json")
    )
    assert len(malformed) == 1
    assert malformed[0].credential_name == "bad-cadence-cred"
    assert "review_cadence" in malformed[0].reason.lower()
    assert "weekly" in malformed[0].reason


def test_invalid_json_raises():
    with pytest.raises(ManifestUnreadableError):
        read_manifest(str(FIXTURES / "manifest-invalid-json.txt"))


def test_not_a_dict_raises():
    with pytest.raises(ManifestUnreadableError):
        read_manifest(str(FIXTURES / "manifest-not-a-dict.json"))


def test_missing_file_raises():
    with pytest.raises(ManifestUnreadableError):
        read_manifest(str(FIXTURES / "does-not-exist.json"))


def test_credential_fields_typed_correctly():
    """Credential record carries parsed date for last_reviewed."""
    well_formed, _ = read_manifest(str(FIXTURES / "manifest-valid.json"))
    for cred in well_formed:
        if cred.name == "kg-felix-bot-pat":
            assert cred.last_reviewed is not None
            assert cred.last_reviewed.isoformat() == "2026-05-11"
            assert cred.review_cadence == "annual"
            break
    else:
        pytest.fail("kg-felix-bot-pat not found in valid manifest")


def test_credentials_are_frozen_dataclasses():
    well_formed, _ = read_manifest(str(FIXTURES / "manifest-valid.json"))
    cred = well_formed[0]
    with pytest.raises(Exception):
        cred.name = "something-else"  # type: ignore[misc]


def test_unknown_extra_fields_are_ignored():
    """Manifest schema is extensible; extra fields don't fail validation."""
    well_formed, malformed = read_manifest(str(FIXTURES / "manifest-valid.json"))
    # Some fixture credentials have extra fields like _fixture_note or
    # created_date_note — those should not show up as malformed.
    assert malformed == []
