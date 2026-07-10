"""Tests for scripts.common.alert_bus.model."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from scripts.common.alert_bus.model import (
    SEVERITY_MAP,
    Alert,
    AlertResult,
    Severity,
)


def test_severity_ordering():
    assert Severity.INFO < Severity.WARN < Severity.ERROR < Severity.CRITICAL
    assert Severity.CRITICAL > Severity.INFO
    assert Severity.WARN <= Severity.WARN
    assert Severity.ERROR >= Severity.WARN


def test_severity_all_comparison_operators_reject_non_severity():
    # Each rich-comparison operator returns NotImplemented for non-Severity,
    # so Python raises TypeError rather than giving a misleading answer.
    for op in ("__lt__", "__le__", "__gt__", "__ge__"):
        assert getattr(Severity.INFO, op)(3) is NotImplemented


def test_severity_string_value():
    assert Severity.INFO.value == "info"
    assert Severity.WARN.value == "warn"
    assert Severity.ERROR.value == "error"
    assert Severity.CRITICAL.value == "critical"


def test_severity_comparison_with_non_severity_returns_notimplemented():
    # Comparing to a non-Severity should not blow up; Python falls back.
    assert (Severity.INFO == "info") is True  # str-enum equality
    with pytest.raises(TypeError):
        _ = Severity.INFO < 3  # type: ignore[operator]


def test_severity_map_completeness_and_values():
    assert set(SEVERITY_MAP) == set(Severity)
    assert SEVERITY_MAP[Severity.INFO] == ("low", "information_source")
    assert SEVERITY_MAP[Severity.WARN] == ("default", "warning")
    assert SEVERITY_MAP[Severity.ERROR] == ("high", "rotating_light")
    assert SEVERITY_MAP[Severity.CRITICAL] == ("max", "rotating_light,sos")


def test_alert_minimal_valid():
    alert = Alert(
        source="felix-deployer/apply",
        severity=Severity.ERROR,
        title="failed",
        description="something broke",
    )
    assert alert.action is None
    assert alert.details == {}
    assert alert.timestamp.tzinfo is not None  # UTC-aware default


def test_alert_default_timestamp_is_utc_aware():
    alert = Alert(
        source="s", severity=Severity.INFO, title="t", description="d"
    )
    assert alert.timestamp.utcoffset() == timezone.utc.utcoffset(None)


def test_alert_explicit_timestamp_preserved():
    ts = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    alert = Alert(
        source="s", severity=Severity.INFO, title="t", description="d", timestamp=ts
    )
    assert alert.timestamp == ts


@pytest.mark.parametrize("field", ["source", "title", "description"])
def test_alert_empty_required_field_raises(field):
    kwargs = {
        "source": "s",
        "severity": Severity.INFO,
        "title": "t",
        "description": "d",
    }
    kwargs[field] = ""
    with pytest.raises(ValueError, match=field):
        Alert(**kwargs)


@pytest.mark.parametrize("field", ["source", "title", "description"])
def test_alert_whitespace_required_field_raises(field):
    kwargs = {
        "source": "s",
        "severity": Severity.INFO,
        "title": "t",
        "description": "d",
    }
    kwargs[field] = "   "
    with pytest.raises(ValueError, match=field):
        Alert(**kwargs)


def test_alert_bad_severity_type_raises():
    with pytest.raises(ValueError, match="severity"):
        Alert(source="s", severity="info", title="t", description="d")  # type: ignore[arg-type]


def test_alert_result_defaults():
    result = AlertResult(ok=True)
    assert result.ok is True
    assert result.reason is None
    assert result.topic_configured is True


def test_alert_result_failure_shape():
    result = AlertResult(ok=False, reason="CURL_TIMEOUT", topic_configured=True)
    assert result.ok is False
    assert result.reason == "CURL_TIMEOUT"
