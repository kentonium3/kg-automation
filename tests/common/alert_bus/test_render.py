"""Tests for scripts.common.alert_bus.render."""

from __future__ import annotations

from datetime import datetime, timezone

from scripts.common.alert_bus.model import Alert, Severity
from scripts.common.alert_bus.render import (
    DETAIL_VALUE_MAX,
    render_body,
    render_title,
)


def _alert(**overrides) -> Alert:
    kwargs = {
        "source": "felix-deployer/apply",
        "severity": Severity.ERROR,
        "title": "felix-deployer failed",
        "description": "Dry-run failed before apply.",
        "timestamp": datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
    }
    kwargs.update(overrides)
    return Alert(**kwargs)


def test_render_title_is_alert_title():
    assert render_title(_alert()) == "felix-deployer failed"


def test_render_body_core_fields_and_order():
    body = render_body(_alert())
    lines = body.splitlines()
    # timestamp line, source, severity, blank, description
    assert "(UTC)" in lines[0] and "(local)" in lines[0]
    assert lines[1] == "Source: felix-deployer/apply"
    assert lines[2] == "Severity: error"
    assert lines[3] == ""
    assert lines[4] == "Dry-run failed before apply."


def test_render_body_omits_action_when_absent():
    body = render_body(_alert(action=None))
    assert "Action:" not in body


def test_render_body_includes_action_when_present():
    body = render_body(_alert(action="chmod +x the script and re-queue."))
    assert "Action: chmod +x the script and re-queue." in body


def test_render_body_omits_details_block_when_empty():
    # NFR-003: no placeholder, no empty Details: header.
    body = render_body(_alert(details={}))
    assert "Details:" not in body


def test_render_body_includes_details_block():
    body = render_body(_alert(details={"phase": "dry_run", "exit_code": "126"}))
    assert "Details:" in body
    assert "  phase=dry_run" in body
    assert "  exit_code=126" in body


def test_render_body_redacts_before_truncation():
    # A Bearer token longer than the truncation bound; redaction must fire on
    # the whole value BEFORE truncation, so no token bytes survive.
    secret = "Bearer " + ("A" * 600)
    body = render_body(_alert(details={"stderr": secret}))
    assert "[REDACTED]" in body
    assert "AAAAAAAA" not in body


def test_render_body_truncates_long_redacted_value():
    # A long non-secret value is truncated to DETAIL_VALUE_MAX. Spaces every
    # few chars keep it under the redactor's 32-char token threshold so this
    # exercises truncation, not redaction.
    long_value = ("word " * (DETAIL_VALUE_MAX // 2))[: DETAIL_VALUE_MAX + 250]
    body = render_body(_alert(details={"note": long_value}))
    detail_line = next(
        line for line in body.splitlines() if line.strip().startswith("note=")
    )
    rendered_value = detail_line.split("note=", 1)[1]
    assert len(rendered_value) == DETAIL_VALUE_MAX


def test_render_body_naive_timestamp_treated_as_utc():
    naive = datetime(2026, 7, 10, 12, 0)  # no tzinfo
    body = render_body(_alert(timestamp=naive))
    assert "2026-07-10T12:00:00+00:00 (UTC)" in body


def test_render_body_non_string_detail_value_coerced():
    # CLI always passes strings, but the renderer must not crash on an int.
    body = render_body(_alert(details={"code": 126}))  # type: ignore[dict-item]
    assert "  code=126" in body
