"""Tests for credential_health_check.github_writer."""
from __future__ import annotations

import json
import subprocess
from datetime import date
from unittest.mock import patch

import pytest

from credential_health_check.github_writer import (
    GitHubWriteError,
    MANIFEST_QUALITY_TITLE_PREFIX,
    cadence_alert_body,
    cadence_alert_title,
    cadence_alert_title_prefix,
    create_issue,
    dedup_check,
    manifest_quality_body,
    manifest_quality_title,
    staleness_alert_body,
    staleness_alert_title,
    staleness_alert_title_prefix,
)
from credential_health_check.manifest import Credential, ManifestQualityIssue
from credential_health_check.signals import ActivitySignalFailure


def _credential() -> Credential:
    return Credential(
        name="kg-felix-bot-pat",
        review_cadence="annual",
        storage="/home/claude/.config/gh/hosts.yml",
        expiry_notes="Rotate via gh auth flow.",
        type="api-token",
        scope="GitHub PAT for kg-felix-bot.",
        used_by=("felix-doc-auditor",),
        last_reviewed=date(2025, 5, 11),
    )


def _signal_failure() -> ActivitySignalFailure:
    return ActivitySignalFailure(
        credential_name="whatsapp-session",
        reason="WhatsApp default channel last `in` activity was 14d 5h ago, exceeding the 14-day threshold.",
        summary="whatsapp: in:14d 5h (stale)",
    )


# ---------- Title generation ----------


def test_cadence_title_format():
    cred = _credential()
    boundary = date(2026, 5, 11)
    assert cadence_alert_title(cred, boundary) == "Credential review: kg-felix-bot-pat due 2026-05-11"


def test_cadence_title_prefix_stable_ignores_boundary():
    cred = _credential()
    assert cadence_alert_title_prefix(cred) == "Credential review: kg-felix-bot-pat"


def test_staleness_title_format():
    cred = Credential(
        name="whatsapp-session",
        review_cadence="monitor-activity",
        storage="x",
        expiry_notes="x",
    )
    assert staleness_alert_title(cred) == "Credential staleness: whatsapp-session"


def test_staleness_title_prefix_matches_title():
    cred = Credential(
        name="whatsapp-session",
        review_cadence="monitor-activity",
        storage="x",
        expiry_notes="x",
    )
    assert staleness_alert_title_prefix(cred) == "Credential staleness: whatsapp-session"


def test_manifest_quality_title_format():
    assert (
        manifest_quality_title(3, date(2026, 5, 11))
        == "Credential manifest quality: 3 entries with issues — 2026-05-11"
    )


def test_manifest_quality_title_prefix_constant():
    assert MANIFEST_QUALITY_TITLE_PREFIX == "Credential manifest quality"


# ---------- Body templating ----------


def test_cadence_body_contains_credential_name_and_boundary():
    body = cadence_alert_body(
        _credential(),
        date(2026, 6, 5),
        vikunja_task_id=42,
        cycle_date=date(2026, 5, 11),
    )
    assert "kg-felix-bot-pat" in body
    assert "2026-06-05" in body
    assert "#42" in body
    assert "in 25 days" in body  # 2026-06-05 minus 2026-05-11 = 25 days


def test_cadence_body_renders_due_date_one_week_before_boundary():
    body = cadence_alert_body(
        _credential(),
        date(2026, 6, 5),
        vikunja_task_id=42,
        cycle_date=date(2026, 5, 11),
    )
    assert "due 2026-05-29" in body  # boundary 2026-06-05 minus 7 days


def test_cadence_body_includes_rotation_procedure():
    body = cadence_alert_body(
        _credential(),
        date(2026, 6, 5),
        vikunja_task_id=42,
        cycle_date=date(2026, 5, 11),
    )
    assert "Rotate via gh auth flow." in body


def test_staleness_body_contains_signal_reason():
    cred = Credential(
        name="whatsapp-session",
        review_cadence="monitor-activity",
        storage="x",
        expiry_notes="re-link procedure here",
    )
    body = staleness_alert_body(cred, _signal_failure(), date(2026, 5, 11))
    assert "whatsapp-session" in body
    assert "14d 5h ago" in body
    assert "re-link procedure here" in body


def test_staleness_body_notes_no_vikunja_task():
    cred = Credential(
        name="whatsapp-session",
        review_cadence="monitor-activity",
        storage="x",
        expiry_notes="x",
    )
    body = staleness_alert_body(cred, _signal_failure(), date(2026, 5, 11))
    assert "No Vikunja task" in body


def test_manifest_quality_body_lists_all_issues():
    issues = [
        ManifestQualityIssue("cred-a", "missing last_reviewed"),
        ManifestQualityIssue("cred-b", "unrecognised review_cadence"),
    ]
    body = manifest_quality_body(issues, date(2026, 5, 11))
    assert "cred-a" in body
    assert "missing last_reviewed" in body
    assert "cred-b" in body
    assert "unrecognised review_cadence" in body
    assert "2026-05-11" in body
    assert "2 entries" in body or "2" in body  # count reflected somehow


# ---------- dedup_check ----------


def _fake_completed(stdout: str, returncode: int = 0, stderr: str = ""):
    cp = subprocess.CompletedProcess(args=["gh"], returncode=returncode)
    cp.stdout = stdout
    cp.stderr = stderr
    return cp


def test_dedup_check_no_matches_returns_empty_list():
    with patch(
        "credential_health_check.github_writer.subprocess.run",
        return_value=_fake_completed(json.dumps([])),
    ):
        assert dedup_check("Credential review: foo") == []


def test_dedup_check_exact_prefix_match_returns_number():
    with patch(
        "credential_health_check.github_writer.subprocess.run",
        return_value=_fake_completed(
            json.dumps([{"number": 999, "title": "Credential review: foo due 2026-06-01"}])
        ),
    ):
        assert dedup_check("Credential review: foo") == [999]


def test_dedup_check_filters_fuzzy_non_prefix_matches():
    """gh `in:title` search is fuzzy — non-prefix matches must be filtered out."""
    fuzzy_match = {"number": 500, "title": "Something about credential review and foo elsewhere"}
    exact_match = {"number": 501, "title": "Credential review: foo due 2026-06-01"}
    with patch(
        "credential_health_check.github_writer.subprocess.run",
        return_value=_fake_completed(json.dumps([fuzzy_match, exact_match])),
    ):
        assert dedup_check("Credential review: foo") == [501]


def test_dedup_check_raises_on_gh_failure():
    with patch(
        "credential_health_check.github_writer.subprocess.run",
        return_value=_fake_completed("", returncode=1, stderr="boom"),
    ):
        with pytest.raises(GitHubWriteError):
            dedup_check("Credential review: foo")


def test_dedup_check_handles_empty_stdout():
    """An empty stdout from gh shouldn't crash the JSON parser."""
    with patch(
        "credential_health_check.github_writer.subprocess.run",
        return_value=_fake_completed(""),
    ):
        assert dedup_check("Credential review: foo") == []


# ---------- create_issue ----------


def test_create_issue_returns_parsed_number():
    with patch(
        "credential_health_check.github_writer.subprocess.run",
        return_value=_fake_completed("https://github.com/kentonium3/kg-automation/issues/123\n"),
    ):
        assert create_issue("title", "body") == 123


def test_create_issue_raises_on_nonzero_exit():
    with patch(
        "credential_health_check.github_writer.subprocess.run",
        return_value=_fake_completed("", returncode=2, stderr="something broke"),
    ):
        with pytest.raises(GitHubWriteError):
            create_issue("title", "body")


def test_create_issue_raises_on_unparseable_url():
    with patch(
        "credential_health_check.github_writer.subprocess.run",
        return_value=_fake_completed("not-a-url"),
    ):
        with pytest.raises(GitHubWriteError):
            create_issue("title", "body")


def test_create_issue_command_line_shape():
    captured: dict = {}

    def fake_run(cmd, *args, **kwargs):
        captured["cmd"] = cmd
        return _fake_completed("https://github.com/kentonium3/kg-automation/issues/1")

    with patch(
        "credential_health_check.github_writer.subprocess.run",
        side_effect=fake_run,
    ):
        create_issue("My title", "My body", labels=("area/security",), assignees=("kentonium3",))
    cmd = captured["cmd"]
    assert "gh" in cmd[0]
    assert "issue" in cmd
    assert "create" in cmd
    assert "--repo" in cmd
    assert "kentonium3/kg-automation" in cmd
    assert "--title" in cmd
    assert "My title" in cmd
    assert "--label" in cmd
    assert "area/security" in cmd
    assert "--assignee" in cmd
    assert "kentonium3" in cmd
