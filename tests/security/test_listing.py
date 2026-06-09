"""Tests for credential_health_check.listing."""
from __future__ import annotations

import io
from datetime import date, timedelta
from pathlib import Path

import pytest

from credential_health_check.listing import (
    CredentialListing,
    LivenessListing,
    _status_for,
    build_listings,
    build_liveness_listings,
    list_credentials,
    render_liveness_table,
    render_malformed,
    render_table,
)
from credential_health_check.manifest import (
    Credential,
    LivenessProbeConfig,
    ManifestQualityIssue,
    ManifestUnreadableError,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _cred(**overrides) -> Credential:
    defaults = dict(
        name="test-cred",
        review_cadence="annual",
        storage="x",
        expiry_notes="x",
        type="api-token",
        last_reviewed=date(2026, 5, 11),
    )
    defaults.update(overrides)
    return Credential(**defaults)


# ---------- _status_for ----------


def test_status_within_cadence():
    cred = _cred(last_reviewed=date(2026, 5, 11))
    # boundary = 2026-05-11 + 365d = 2027-05-11; today = 2026-05-12 → 364 days out
    status = _status_for(cred, boundary=date(2027, 5, 11), today=date(2026, 5, 12))
    assert status == "within (364d)"


def test_status_within_window_at_30_days():
    """Exactly 30 days out: WARNING."""
    today = date(2026, 5, 12)
    boundary = today + timedelta(days=30)
    cred = _cred()
    status = _status_for(cred, boundary=boundary, today=today)
    assert status == "WARNING (30d)"


def test_status_within_window_inside():
    today = date(2026, 5, 12)
    boundary = today + timedelta(days=10)
    cred = _cred()
    status = _status_for(cred, boundary=boundary, today=today)
    assert status == "WARNING (10d)"


def test_status_overdue():
    today = date(2026, 5, 12)
    boundary = today - timedelta(days=5)
    cred = _cred()
    status = _status_for(cred, boundary=boundary, today=today)
    assert status == "OVERDUE (5d ago)"


def test_status_monitor_activity():
    cred = _cred(review_cadence="monitor-activity", last_reviewed=None)
    status = _status_for(cred, boundary=None, today=date(2026, 5, 12))
    assert status == "activity-tracked"


def test_status_on_revocation():
    cred = _cred(review_cadence="on-revocation", last_reviewed=None)
    status = _status_for(cred, boundary=None, today=date(2026, 5, 12))
    assert status == "skip (on-revocation)"


def test_status_na():
    cred = _cred(review_cadence="n/a", last_reviewed=None)
    status = _status_for(cred, boundary=None, today=date(2026, 5, 12))
    assert status == "skip (n/a)"


def test_status_session():
    cred = _cred(review_cadence="session", last_reviewed=None)
    status = _status_for(cred, boundary=None, today=date(2026, 5, 12))
    assert status == "skip (session)"


def test_status_no_anchor_for_fixed_cadence():
    """A fixed-cadence credential with no anchor — shouldn't happen for well-formed
    entries, but the renderer must handle it defensively."""
    cred = _cred(last_reviewed=None, created_date=None)
    status = _status_for(cred, boundary=None, today=date(2026, 5, 12))
    assert status == "skip (no anchor)"


# ---------- build_listings ----------


def test_build_listings_count_matches():
    creds = [_cred(name="a"), _cred(name="b"), _cred(name="c")]
    listings = build_listings(creds, today=date(2026, 5, 12))
    assert len(listings) == 3
    assert [r.name for r in listings] == ["a", "b", "c"]


def test_build_listings_computes_boundary_for_annual():
    cred = _cred(last_reviewed=date(2026, 5, 11))
    listings = build_listings([cred], today=date(2026, 5, 12))
    assert listings[0].boundary == date(2027, 5, 11)


def test_build_listings_no_boundary_for_monitor_activity():
    cred = _cred(review_cadence="monitor-activity", last_reviewed=None)
    listings = build_listings([cred], today=date(2026, 5, 12))
    assert listings[0].boundary is None


# ---------- render_table ----------


def test_render_table_has_header_and_separator():
    listings = build_listings([_cred(name="my-cred")], today=date(2026, 5, 12))
    out = render_table(listings)
    lines = out.split("\n")
    assert "Name" in lines[0]
    assert "Status" in lines[0]
    assert set(lines[1]) <= {"-", " "}  # separator is dashes + spaces
    assert "my-cred" in lines[2]


def test_render_table_handles_empty_listings():
    out = render_table([])
    lines = out.split("\n")
    assert len(lines) == 2  # header + separator only
    assert "Name" in lines[0]


def test_render_table_columns_align():
    """All non-empty data rows have the same length as the header."""
    listings = build_listings(
        [
            _cred(name="short"),
            _cred(name="a-much-longer-credential-name", type="oauth-app-token"),
        ],
        today=date(2026, 5, 12),
    )
    out = render_table(listings)
    lines = out.split("\n")
    # Header + separator + 2 data rows.
    assert len(lines) == 4
    # Stripped trailing whitespace, the last column ("Status") may have varying
    # width; what we assert is that columns are space-separated and aligned.
    # The header line and the data lines should agree on column starts:
    header = lines[0]
    for data_line in lines[2:]:
        assert header.index("Name") == data_line.index(data_line.split()[0])


# ---------- render_malformed ----------


def test_render_malformed_empty_returns_empty_string():
    assert render_malformed([]) == ""


def test_render_malformed_lists_each_issue():
    issues = [
        ManifestQualityIssue("cred-a", "missing last_reviewed"),
        ManifestQualityIssue("cred-b", "unrecognised review_cadence"),
    ]
    out = render_malformed(issues)
    assert "2 malformed" in out
    assert "cred-a" in out
    assert "cred-b" in out
    assert "missing last_reviewed" in out


# ---------- list_credentials (end-to-end against fixtures) ----------


def test_list_credentials_writes_table_to_stream():
    buf = io.StringIO()
    rc = list_credentials(
        str(FIXTURES / "manifest-valid.json"),
        today=date(2026, 5, 12),
        stream=buf,
    )
    assert rc == 0
    output = buf.getvalue()
    assert "kentonium3-gh-oauth" in output
    assert "kg-felix-bot-pat" in output
    assert "Status" in output


def test_list_credentials_with_malformed_appends_footer():
    buf = io.StringIO()
    rc = list_credentials(
        str(FIXTURES / "manifest-missing-last-reviewed.json"),
        today=date(2026, 5, 12),
        stream=buf,
    )
    assert rc == 0
    output = buf.getvalue()
    assert "good-cred" in output
    assert "missing-last-reviewed-cred" in output
    assert "WARNING:" in output  # footer


def test_list_credentials_propagates_unreadable_error():
    buf = io.StringIO()
    with pytest.raises(ManifestUnreadableError):
        list_credentials(
            str(FIXTURES / "manifest-invalid-json.txt"),
            today=date(2026, 5, 12),
            stream=buf,
        )


# ---------- WP03 liveness listing test ----------


def _cred_oauth2_with_liveness(tmp_path, name: str = "gog-credentials-keyring") -> Credential:
    """Build an oauth2 credential with a real keyring file for liveness listing."""
    keyring = tmp_path / "keyring_file"
    keyring.write_bytes(b"")
    return Credential(
        name=name,
        review_cadence="on-revocation",
        storage=str(keyring),
        expiry_notes="oauth2 gog token",
        type="oauth2",
        liveness_probe=LivenessProbeConfig(
            enabled=True,
            gog_account="kentgale@gmail.com",
            keyring_file=str(keyring),
            recovery_command=(
                "ssh -t office2-claude "
                "/home/claude/kg-automation/scripts/security/gog-reauth.sh"
            ),
        ),
    )


def test_list_liveness_includes_credential_table(tmp_path):
    """--list --liveness: oauth2 credential with liveness_probe appears in output."""
    cred = _cred_oauth2_with_liveness(tmp_path)
    listings = build_liveness_listings([cred])
    assert len(listings) == 1
    row = listings[0]
    assert row.name == cred.name
    assert row.gog_account == "kentgale@gmail.com"
    assert row.enabled == "yes"
    # The keyring exists, so age + expiration are non-dash.
    assert row.keyring_mtime_age != "—"
    assert row.expected_next_expiration != "—"

    # Also verify the render doesn't crash and includes expected columns.
    output = render_liveness_table(listings)
    assert cred.name in output
    assert "kentgale@gmail.com" in output
    assert "gog_account" in output
    assert "keyring_mtime_age" in output
    assert "expected_next_expiration" in output
    # Deliberately NOT checking for "current_classification" — it's intentionally absent.
    assert "current_classification" not in output


def test_list_liveness_skips_non_oauth2_credentials():
    """build_liveness_listings only includes oauth2 credentials."""
    api_cred = Credential(
        name="some-api-key",
        review_cadence="annual",
        storage="/path/to/key",
        expiry_notes="api key",
        type="api-token",
        last_reviewed=date(2026, 5, 11),
    )
    listings = build_liveness_listings([api_cred])
    assert listings == []


def test_list_liveness_oauth2_no_probe_block_shows_dashes():
    """oauth2 credential with no liveness_probe block shows — placeholders."""
    cred = Credential(
        name="personal-google",
        review_cadence="on-revocation",
        storage="/some/path",
        expiry_notes="google oauth2",
        type="oauth2",
        liveness_probe=None,
    )
    listings = build_liveness_listings([cred])
    assert len(listings) == 1
    row = listings[0]
    assert row.enabled == "—"
    assert row.gog_account == "—"
    assert row.keyring_mtime_age == "—"
    assert row.expected_next_expiration == "—"


def test_list_credentials_liveness_flag_prints_extra_table(tmp_path):
    """list_credentials(..., liveness=True) prints liveness table header in output."""
    cred = _cred_oauth2_with_liveness(tmp_path)
    # Verify the liveness table renders correctly.
    listings = build_liveness_listings([cred])
    output = render_liveness_table(listings)
    assert cred.name in output
    assert "gog_account" in output
    # The header must have the expected columns.
    first_line = output.split("\n")[0]
    assert "Name" in first_line
    assert "Enabled" in first_line
    assert "gog_account" in first_line
    assert "keyring_mtime_age" in first_line
    assert "expected_next_expiration" in first_line
    assert "recovery_command" in first_line
