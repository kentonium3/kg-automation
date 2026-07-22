"""Tests for credential_health_check.manifest."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from credential_health_check.manifest import (
    Credential,
    ManifestQualityError,
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
    assert "kentonium3-gh-oauth" in names


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


# ---------------------------------------------------------------------------
# Liveness probe tests (WP01 — T005)
# ---------------------------------------------------------------------------

_BASE_CRED = {
    "name": "test-cred",
    "type": "oauth2",
    "scope": "test scope",
    "storage": "/tmp/test",
    "host": "office2",
    "used_by": [],
    "deployed_by": "test",
    "review_cadence": "on-revocation",
    "expiry_notes": "Test credential — no real expiry.",
    "last_reviewed": "2026-06-09",
}


def _write_manifest(tmp_path: Path, cred: dict) -> str:
    manifest = {
        "schema_version": "1.1",
        "last_updated": "2026-06-09",
        "credentials": [cred],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    return str(path)


_VALID_PROBE = {
    "enabled": True,
    "command": ["/usr/bin/true", "--self-check"],
    "dead_exit_codes": [3],
    "recovery_command": "re-mint the token on the Mac",
    "timeout_seconds": 20,
}


def test_credential_parses_with_full_liveness_probe_block(tmp_path):
    """A credential with a full generic liveness_probe block parses cleanly."""
    cred_dict = {**_BASE_CRED, "liveness_probe": dict(_VALID_PROBE)}
    well_formed, malformed = read_manifest(_write_manifest(tmp_path, cred_dict))
    assert malformed == []
    assert len(well_formed) == 1
    cred = well_formed[0]
    assert cred.liveness_probe is not None
    assert cred.liveness_probe.enabled is True
    assert cred.liveness_probe.command == ("/usr/bin/true", "--self-check")
    assert cred.liveness_probe.dead_exit_codes == (3,)
    assert cred.liveness_probe.recovery_command == "re-mint the token on the Mac"
    assert cred.liveness_probe.timeout_seconds == 20


def test_timeout_seconds_defaults_to_20(tmp_path):
    """timeout_seconds is optional and defaults to 20."""
    probe = {k: v for k, v in _VALID_PROBE.items() if k != "timeout_seconds"}
    cred_dict = {**_BASE_CRED, "liveness_probe": probe}
    well_formed, malformed = read_manifest(_write_manifest(tmp_path, cred_dict))
    assert malformed == []
    assert well_formed[0].liveness_probe.timeout_seconds == 20


def test_credential_parses_without_liveness_probe_block(tmp_path):
    """A credential without liveness_probe parses cleanly; field is None."""
    well_formed, malformed = read_manifest(_write_manifest(tmp_path, dict(_BASE_CRED)))
    assert malformed == []
    assert len(well_formed) == 1
    assert well_formed[0].liveness_probe is None


def test_liveness_probe_removed_breadcrumb_survives(tmp_path):
    """The `liveness_probe_removed` breadcrumb (a sibling string key, not a
    liveness_probe block) parses cleanly and leaves liveness_probe None. This is
    the gog credential's post-#819 shape — guard it against future tightening."""
    cred_dict = {**_BASE_CRED, "liveness_probe_removed": "2026-07-20 (#819): ..."}
    well_formed, malformed = read_manifest(_write_manifest(tmp_path, cred_dict))
    assert malformed == []
    assert len(well_formed) == 1
    assert well_formed[0].liveness_probe is None


def test_credential_parses_with_disabled_liveness_probe(tmp_path):
    """enabled=false with no other fields parses cleanly; optional fields empty."""
    cred_dict = {**_BASE_CRED, "liveness_probe": {"enabled": False}}
    well_formed, malformed = read_manifest(_write_manifest(tmp_path, cred_dict))
    assert malformed == []
    cred = well_formed[0]
    assert cred.liveness_probe is not None
    assert cred.liveness_probe.enabled is False
    assert cred.liveness_probe.command == ()
    assert cred.liveness_probe.dead_exit_codes == ()
    assert cred.liveness_probe.recovery_command is None


def _probe_without(key: str) -> dict:
    return {k: v for k, v in _VALID_PROBE.items() if k != key}


def test_liveness_probe_enabled_without_command_raises(tmp_path):
    cred_dict = {**_BASE_CRED, "liveness_probe": _probe_without("command")}
    with pytest.raises(ManifestQualityError, match="command"):
        read_manifest(_write_manifest(tmp_path, cred_dict))


def test_liveness_probe_empty_command_raises(tmp_path):
    probe = {**_VALID_PROBE, "command": []}
    cred_dict = {**_BASE_CRED, "liveness_probe": probe}
    with pytest.raises(ManifestQualityError, match="command"):
        read_manifest(_write_manifest(tmp_path, cred_dict))


def test_liveness_probe_relative_command_path_raises(tmp_path):
    """command[0] must be an absolute path."""
    probe = {**_VALID_PROBE, "command": ["python3", "-m", "x"]}
    cred_dict = {**_BASE_CRED, "liveness_probe": probe}
    with pytest.raises(ManifestQualityError, match="absolute"):
        read_manifest(_write_manifest(tmp_path, cred_dict))


def test_liveness_probe_command_non_string_element_raises(tmp_path):
    probe = {**_VALID_PROBE, "command": ["/usr/bin/true", 3]}
    cred_dict = {**_BASE_CRED, "liveness_probe": probe}
    with pytest.raises(ManifestQualityError, match="command"):
        read_manifest(_write_manifest(tmp_path, cred_dict))


def test_liveness_probe_enabled_without_dead_exit_codes_raises(tmp_path):
    cred_dict = {**_BASE_CRED, "liveness_probe": _probe_without("dead_exit_codes")}
    with pytest.raises(ManifestQualityError, match="dead_exit_codes"):
        read_manifest(_write_manifest(tmp_path, cred_dict))


def test_liveness_probe_empty_dead_exit_codes_raises(tmp_path):
    probe = {**_VALID_PROBE, "dead_exit_codes": []}
    cred_dict = {**_BASE_CRED, "liveness_probe": probe}
    with pytest.raises(ManifestQualityError, match="dead_exit_codes"):
        read_manifest(_write_manifest(tmp_path, cred_dict))


def test_liveness_probe_bool_in_dead_exit_codes_raises(tmp_path):
    """bool is an int subclass in Python — must be rejected explicitly."""
    probe = {**_VALID_PROBE, "dead_exit_codes": [True]}
    cred_dict = {**_BASE_CRED, "liveness_probe": probe}
    with pytest.raises(ManifestQualityError, match="dead_exit_codes"):
        read_manifest(_write_manifest(tmp_path, cred_dict))


def test_liveness_probe_enabled_without_recovery_command_raises(tmp_path):
    cred_dict = {**_BASE_CRED, "liveness_probe": _probe_without("recovery_command")}
    with pytest.raises(ManifestQualityError, match="recovery_command"):
        read_manifest(_write_manifest(tmp_path, cred_dict))


def test_liveness_probe_non_bool_enabled_raises(tmp_path):
    probe = {**_VALID_PROBE, "enabled": "true"}
    cred_dict = {**_BASE_CRED, "liveness_probe": probe}
    with pytest.raises(ManifestQualityError, match="enabled"):
        read_manifest(_write_manifest(tmp_path, cred_dict))


def test_liveness_probe_non_int_timeout_raises(tmp_path):
    probe = {**_VALID_PROBE, "timeout_seconds": "20"}
    cred_dict = {**_BASE_CRED, "liveness_probe": probe}
    with pytest.raises(ManifestQualityError, match="timeout_seconds"):
        read_manifest(_write_manifest(tmp_path, cred_dict))


def test_liveness_probe_nonpositive_timeout_raises(tmp_path):
    probe = {**_VALID_PROBE, "timeout_seconds": 0}
    cred_dict = {**_BASE_CRED, "liveness_probe": probe}
    with pytest.raises(ManifestQualityError, match="timeout_seconds"):
        read_manifest(_write_manifest(tmp_path, cred_dict))


def test_liveness_probe_unknown_subkey_raises(tmp_path):
    """liveness_probe block with unknown keys raises ManifestQualityError."""
    cred_dict = {**_BASE_CRED, "liveness_probe": {"foo": "bar"}}
    with pytest.raises(ManifestQualityError, match="unknown keys"):
        read_manifest(_write_manifest(tmp_path, cred_dict))


@pytest.mark.parametrize("bad", [[], "disabled", 3, True])
def test_liveness_probe_non_object_raises(tmp_path, bad):
    """A non-object liveness_probe raises ManifestQualityError, not AttributeError."""
    cred_dict = {**_BASE_CRED, "liveness_probe": bad}
    with pytest.raises(ManifestQualityError, match="must be an object"):
        read_manifest(_write_manifest(tmp_path, cred_dict))


# ---------------------------------------------------------------------------
# expires_at parsing (#852)
# ---------------------------------------------------------------------------


def test_expires_at_parsed_when_valid(tmp_path):
    cred_dict = {**_BASE_CRED, "expires_at": "2026-08-21"}
    well_formed, malformed = read_manifest(_write_manifest(tmp_path, cred_dict))
    assert malformed == []
    assert len(well_formed) == 1
    assert well_formed[0].expires_at is not None
    assert well_formed[0].expires_at.isoformat() == "2026-08-21"


def test_expires_at_absent_is_none(tmp_path):
    cred_dict = {**_BASE_CRED}  # no expires_at
    well_formed, _ = read_manifest(_write_manifest(tmp_path, cred_dict))
    assert well_formed[0].expires_at is None


def test_expires_at_unparseable_is_malformed(tmp_path):
    cred_dict = {**_BASE_CRED, "expires_at": "not-a-date"}
    well_formed, malformed = read_manifest(_write_manifest(tmp_path, cred_dict))
    assert well_formed == []
    assert len(malformed) == 1
    assert malformed[0].credential_name == _BASE_CRED["name"]
    assert "expires_at" in malformed[0].reason
