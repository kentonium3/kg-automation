"""Tests for the felix-alert bus durable local ledger (#706)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.common.alert_bus import Alert, AlertResult, Severity, emit
from scripts.common.alert_bus import ledger as ledger_mod


def _read_records(base: Path) -> list[dict]:
    records: list[dict] = []
    for path in sorted(base.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    return records


def _alert(**overrides) -> Alert:
    kwargs = dict(
        source="felix-deployer/apply",
        severity=Severity.ERROR,
        title="felix-deployer failed: felix-calendar-helper",
        description="Dry-run failed before apply.",
        action="chmod +x the deploy script.",
        details={"phase": "dry_run", "exit_code": "126"},
    )
    kwargs.update(overrides)
    return Alert(**kwargs)


def test_record_alert_writes_success_record() -> None:
    result = AlertResult(ok=True, reason=None, topic_configured=True)
    assert ledger_mod.record_alert(_alert(), result) is True

    records = _read_records(ledger_mod.ledger_dir())
    assert len(records) == 1
    rec = records[0]
    assert rec["source"] == "felix-deployer/apply"
    assert rec["severity"] == "error"
    assert rec["title"].startswith("felix-deployer failed")
    assert rec["details"] == {"phase": "dry_run", "exit_code": "126"}
    assert rec["delivery"] == {"ok": True, "reason": None, "topic_configured": True}
    # timestamp round-trips as ISO-8601 UTC.
    assert rec["ts"].endswith("+00:00")


def test_record_alert_writes_on_delivery_failure() -> None:
    # A failed POST is still a recorded fault (FR-3).
    result = AlertResult(ok=False, reason="NTFY_MISSING_TOPIC", topic_configured=False)
    assert ledger_mod.record_alert(_alert(), result) is True

    rec = _read_records(ledger_mod.ledger_dir())[0]
    assert rec["delivery"] == {
        "ok": False,
        "reason": "NTFY_MISSING_TOPIC",
        "topic_configured": False,
    }


def test_record_alert_redacts_description_and_details() -> None:
    secret = "A" * 60  # a 60-char token — matches the redactor's 32+ run rule
    result = AlertResult(ok=True)
    ledger_mod.record_alert(
        _alert(description=f"leak {secret}", details={"stderr": f"boom {secret}"}),
        result,
    )
    rec = _read_records(ledger_mod.ledger_dir())[0]
    assert secret not in rec["description"]
    assert secret not in rec["details"]["stderr"]
    assert "[REDACTED]" in rec["description"]
    assert "[REDACTED]" in rec["details"]["stderr"]


def test_record_alert_is_date_partitioned() -> None:
    # Use a recent (within-retention) date so the file is partitioned by the
    # alert's UTC date and not immediately pruned.
    ts = datetime.now(timezone.utc) - timedelta(days=2)
    day = ts.strftime("%Y-%m-%d")
    ledger_mod.record_alert(_alert(timestamp=ts), AlertResult(ok=True))
    assert (ledger_mod.ledger_dir() / f"{day}.jsonl").is_file()


def test_record_alert_never_raises_on_unwritable_dir(tmp_path, monkeypatch) -> None:
    # Point the ledger dir under an existing *file* so mkdir fails.
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file", encoding="utf-8")
    monkeypatch.setenv(ledger_mod.LEDGER_DIR_ENV, str(blocker / "ledger"))
    assert ledger_mod.record_alert(_alert(), AlertResult(ok=True)) is False  # no raise


def test_prune_removes_old_partitions_keeps_recent() -> None:
    base = ledger_mod.ledger_dir()
    base.mkdir(parents=True, exist_ok=True)
    old_day = (
        datetime.now(timezone.utc).date() - timedelta(days=ledger_mod.RETENTION_DAYS + 5)
    ).strftime("%Y-%m-%d")
    old_file = base / f"{old_day}.jsonl"
    old_file.write_text('{"stale": true}\n', encoding="utf-8")

    # A fresh record triggers the opportunistic prune.
    ledger_mod.record_alert(_alert(), AlertResult(ok=True))

    assert not old_file.exists()  # pruned
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert (base / f"{today}.jsonl").is_file()  # kept


def test_prune_ignores_non_date_files() -> None:
    base = ledger_mod.ledger_dir()
    base.mkdir(parents=True, exist_ok=True)
    keep = base / "notes.jsonl"
    keep.write_text('{"keep": true}\n', encoding="utf-8")
    ledger_mod.record_alert(_alert(), AlertResult(ok=True))
    assert keep.exists()  # non-date-partition files are left alone


def test_emit_writes_ledger_and_returns_result(monkeypatch) -> None:
    # No topic configured -> deliver() returns NTFY_MISSING_TOPIC without POSTing;
    # emit() must still return that result AND write a ledger record (FR-1/FR-3).
    monkeypatch.delenv("FELIX_ALERT_NTFY_TOPIC", raising=False)
    result = emit(_alert())
    assert result.ok is False
    assert result.reason == "NTFY_MISSING_TOPIC"

    records = _read_records(ledger_mod.ledger_dir())
    assert len(records) == 1
    assert records[0]["delivery"]["ok"] is False


def test_emit_ledger_failure_does_not_break_emit(monkeypatch) -> None:
    # Even if the ledger write raises internally, emit() returns a result.
    def _boom(*_a, **_k):
        raise RuntimeError("ledger exploded")

    monkeypatch.setattr(ledger_mod, "record_alert", _boom)
    # Re-import emit's bound name is the same module function; patch where emit looks it up.
    monkeypatch.setattr("scripts.common.alert_bus.record_alert", _boom)
    monkeypatch.delenv("FELIX_ALERT_NTFY_TOPIC", raising=False)
    result = emit(_alert())
    assert isinstance(result, AlertResult)  # no raise; delivery result still returned
