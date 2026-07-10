"""Unit tests for felix-health-check's alert-bus migration (WP03, #701).

These tests exercise the ``AlertResult`` → ``{attempted, sent, detail}``
adapter (``_delivery_record``) and the ``send_alert`` wrapper that feeds it,
proving the ``last-run.json`` delivery shape is byte-compatible with the
pre-migration output across the three delivery outcomes:

    - missing topic  → ``{"attempted": False, "sent": False, ...}``
    - curl failure   → ``{"attempted": True,  "sent": False, ...}``
    - success        → ``{"attempted": True,  "sent": True,  "detail": "delivered"}``

The bus is mocked at the ``run.emit`` seam so no live ntfy I/O occurs.
"""
from __future__ import annotations

import pytest

from scripts.common.alert_bus import Alert, AlertResult, Severity
from scripts.office2.felix_health_check import run


# --- _delivery_record: the AlertResult -> legacy-dict adapter --------------


def test_delivery_record_missing_topic() -> None:
    """Blank topic → no attempt was made; failure reason surfaces as detail."""
    result = AlertResult(
        ok=False, reason="NTFY_MISSING_TOPIC", topic_configured=False
    )

    record = run._delivery_record(result)

    assert record == {
        "attempted": False,
        "sent": False,
        "detail": "NTFY_MISSING_TOPIC",
    }
    # Exact key set + types must match the pre-migration signal-file shape.
    assert list(record.keys()) == ["attempted", "sent", "detail"]
    assert isinstance(record["attempted"], bool)
    assert isinstance(record["sent"], bool)
    assert isinstance(record["detail"], str)


def test_delivery_record_curl_failure() -> None:
    """Topic configured but delivery failed → attempted=True, sent=False."""
    result = AlertResult(
        ok=False, reason="ntfy POST failed: rc=22", topic_configured=True
    )

    record = run._delivery_record(result)

    assert record == {
        "attempted": True,
        "sent": False,
        "detail": "ntfy POST failed: rc=22",
    }


def test_delivery_record_success() -> None:
    """Successful delivery → attempted=True, sent=True, detail='delivered'."""
    result = AlertResult(ok=True, reason=None, topic_configured=True)

    record = run._delivery_record(result)

    assert record == {
        "attempted": True,
        "sent": True,
        "detail": "delivered",
    }


# --- send_alert: emit() wiring + adapter round-trip ------------------------


def _capture_emit(monkeypatch, result: AlertResult) -> list[Alert]:
    """Patch ``run.emit`` to return ``result`` and record the Alert it saw."""
    captured: list[Alert] = []

    def _fake_emit(alert: Alert) -> AlertResult:
        captured.append(alert)
        return result

    monkeypatch.setattr(run, "emit", _fake_emit)
    return captured


def test_send_alert_missing_topic(monkeypatch) -> None:
    captured = _capture_emit(
        monkeypatch,
        AlertResult(ok=False, reason="NTFY_MISSING_TOPIC", topic_configured=False),
    )

    delivery = run.send_alert("FAILURES_DETECTED", "some output")

    assert delivery == {
        "attempted": False,
        "sent": False,
        "detail": "NTFY_MISSING_TOPIC",
    }
    assert len(captured) == 1


def test_send_alert_curl_failure(monkeypatch) -> None:
    captured = _capture_emit(
        monkeypatch,
        AlertResult(ok=False, reason="delivery failed", topic_configured=True),
    )

    delivery = run.send_alert("UNKNOWN", "some output")

    assert delivery == {
        "attempted": True,
        "sent": False,
        "detail": "delivery failed",
    }
    assert len(captured) == 1


def test_send_alert_success(monkeypatch) -> None:
    captured = _capture_emit(
        monkeypatch,
        AlertResult(ok=True, reason=None, topic_configured=True),
    )

    delivery = run.send_alert("SCRIPT_MISSING", "some output")

    assert delivery == {
        "attempted": True,
        "sent": True,
        "detail": "delivered",
    }
    assert len(captured) == 1


def test_send_alert_builds_expected_alert(monkeypatch) -> None:
    """The Alert handed to emit() carries the canonical source/severity/title
    and folds the (already-truncated) bash output into details — the bus
    renderer does any further truncation/redaction."""
    captured = _capture_emit(
        monkeypatch,
        AlertResult(ok=True, reason=None, topic_configured=True),
    )

    run.send_alert("FAILURES_DETECTED", "line1\nline2")

    alert = captured[0]
    assert alert.source == "felix-health-check/run"
    assert alert.severity is Severity.ERROR
    assert alert.title == "Felix Health Check — office2"
    assert alert.details["status"] == "FAILURES_DETECTED"
    assert alert.details["output"] == "line1\nline2"
    assert "FAILURES_DETECTED" in alert.description


def test_send_alert_never_raises_via_bus_guarantee(monkeypatch) -> None:
    """emit() never raises (NFR-001); send_alert must not introduce a raise
    for the routine failure path — it returns the failure record instead."""
    _capture_emit(
        monkeypatch,
        AlertResult(ok=False, reason="ntfy down", topic_configured=True),
    )

    # Should not raise.
    delivery = run.send_alert("UNKNOWN", "output")
    assert delivery["sent"] is False


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (
            AlertResult(ok=False, reason="NTFY_MISSING_TOPIC", topic_configured=False),
            {"attempted": False, "sent": False, "detail": "NTFY_MISSING_TOPIC"},
        ),
        (
            AlertResult(ok=False, reason="rc=7", topic_configured=True),
            {"attempted": True, "sent": False, "detail": "rc=7"},
        ),
        (
            AlertResult(ok=True, reason=None, topic_configured=True),
            {"attempted": True, "sent": True, "detail": "delivered"},
        ),
    ],
)
def test_adapter_matrix(result: AlertResult, expected: dict) -> None:
    """Full three-outcome matrix asserting exact byte-compatible shape."""
    assert run._delivery_record(result) == expected
