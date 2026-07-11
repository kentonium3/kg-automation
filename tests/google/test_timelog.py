"""Unit tests for ``scripts.google.timelog`` (mission WP03).

Mocks WP02's ``sheets_helper`` operations at the ``_sh_*`` boundary functions
(``_sh_list_tabs`` / ``_sh_create_tab`` / ``_sh_append_row`` / ``_sh_update_last``
/ ``_sh_delete_last``) and ``scripts.common.alert_bus.emit`` — no live Sheets,
no live ntfy. State (``pending-<account>.json`` / ``ledger-<account>.json``) is
isolated per test via ``FELIX_TIMELOG_STATE_DIR`` pointed at ``tmp_path``, and
the client-aliases config via ``FELIX_TIMELOG_CLIENTS_CONFIG``.

Canonical invocation:

    pytest tests/google/test_timelog.py -v --cov=scripts.google.timelog --cov-branch

Covers every status in the 13-status ``TimelogResult`` union (data-model.md /
contracts/timelog-cli.md §C1): ``logged``, ``unknown_client``, ``need_field``,
``ambiguous``, ``error``, ``not_timelog``, ``no_pending``, ``stale_pending``,
``client_created_entry_failed``, ``corrected``, ``deleted``, ``no_last_write``,
``correction_ambiguous`` — plus the partial-mutation case, pending
correlation/staleness, ledger corrections, the fail-safe boundary, and the
exit-code contract (0 for every handled status, 2 only for a usage error).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from scripts.common.alert_bus import Alert, AlertResult
from scripts.google import timelog


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point pending/ledger state at a fresh tmpdir for every test."""
    state_dir = tmp_path / "timelog-state"
    monkeypatch.setenv(timelog.STATE_DIR_ENV, str(state_dir))
    return state_dir


@pytest.fixture(autouse=True)
def _isolated_clients_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the client-aliases config at a fresh tmpdir; empty by default."""
    config_path = tmp_path / "timelog-clients.json"
    config_path.write_text(json.dumps({"schema_version": 1, "clients": {}}))
    monkeypatch.setenv(timelog.CLIENTS_CONFIG_ENV, str(config_path))
    return config_path


def _write_clients_config(path: Path, clients: dict[str, list[str]]) -> None:
    path.write_text(json.dumps({"schema_version": 1, "clients": clients}))


@pytest.fixture()
def emitted_alerts(monkeypatch: pytest.MonkeyPatch) -> list[Alert]:
    """Capture every Alert passed to timelog's ``emit`` without touching ntfy."""
    captured: list[Alert] = []

    def _fake_emit(alert: Alert) -> AlertResult:
        captured.append(alert)
        return AlertResult(ok=True)

    monkeypatch.setattr(timelog, "emit", _fake_emit)
    return captured


BASE_ARGS = [
    "--conversation", "conv-1",
    "--source-msg-id", "msg-1",
    "--account", "testacct",
]


def _primary_args(**overrides: str) -> list[str]:
    args = {
        "--client": "ACME",
        "--hours": "2.5",
        "--date": "today",
        "--description": "onboarding prep",
    }
    argv: list[str] = []
    for flag, value in args.items():
        if flag in overrides:
            continue
        argv += [flag, value]
    for flag, value in overrides.items():
        if value is not None:
            argv += [flag, value]
    return argv + BASE_ARGS


def _run(monkeypatch: pytest.MonkeyPatch, argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, dict[str, Any]]:
    code = timelog.main(argv)
    out = capsys.readouterr().out.strip()
    result = json.loads(out)
    return code, result


def _stub_list_tabs(monkeypatch: pytest.MonkeyPatch, tabs: list[str]) -> None:
    monkeypatch.setattr(timelog, "_sh_list_tabs", lambda account: list(tabs))


def _stub_append_row_ok(monkeypatch: pytest.MonkeyPatch, row_index: int = 5) -> None:
    def _fake(tab: str, entry_id: str, values: list[Any], account: str) -> tuple[int, list[Any]]:
        return row_index, values

    monkeypatch.setattr(timelog, "_sh_append_row", _fake)


def _stub_append_row_fails(monkeypatch: pytest.MonkeyPatch, message: str = "Sheets 503") -> None:
    def _fake(tab: str, entry_id: str, values: list[Any], account: str) -> tuple[int, list[Any]]:
        raise timelog.SheetsOpError(message)

    monkeypatch.setattr(timelog, "_sh_append_row", _fake)


def _stub_create_tab_ok(monkeypatch: pytest.MonkeyPatch, created: bool = True) -> None:
    monkeypatch.setattr(timelog, "_sh_create_tab", lambda tab, account: created)


# --------------------------------------------------------------------------- #
# status: logged
# --------------------------------------------------------------------------- #


def test_logged_after_read_back_confirmed_append(monkeypatch, capsys, emitted_alerts):
    _stub_list_tabs(monkeypatch, ["ACME"])
    _stub_append_row_ok(monkeypatch, row_index=7)

    code, result = _run(monkeypatch, _primary_args(), capsys)

    assert code == 0
    assert result["status"] == "logged"
    assert result["tab"] == "ACME"
    assert result["row"]["client"] == "ACME"
    assert result["row"]["hours"] == 2.5
    assert result["row"]["description"] == "onboarding prep"
    assert result["row"]["billable"] is True
    assert "entry_id" in result["row"]
    assert "receipt" in result
    assert "2.5h" in result["receipt"]
    assert emitted_alerts == []  # success never alerts


def test_logged_non_billable_flag(monkeypatch, capsys):
    _stub_list_tabs(monkeypatch, ["ACME"])
    _stub_append_row_ok(monkeypatch)

    code, result = _run(monkeypatch, _primary_args(**{"--non-billable": None}) + ["--non-billable"], capsys)

    assert code == 0
    assert result["status"] == "logged"
    assert result["row"]["billable"] is False


def test_logged_appends_to_ledger(monkeypatch, capsys, _isolated_state):
    _stub_list_tabs(monkeypatch, ["ACME"])
    _stub_append_row_ok(monkeypatch, row_index=9)

    _run(monkeypatch, _primary_args(), capsys)

    ledger = timelog._load_ledger("testacct")
    assert len(ledger) == 1
    assert ledger[0]["tab"] == "ACME"
    assert ledger[0]["row_index"] == 9
    assert ledger[0]["entry"]["client"] == "ACME"


# --------------------------------------------------------------------------- #
# status: unknown_client / ambiguous
# --------------------------------------------------------------------------- #


def test_unknown_client_no_write(monkeypatch, capsys):
    _stub_list_tabs(monkeypatch, ["OTHERCO"])

    code, result = _run(monkeypatch, _primary_args(**{"--client": "Acme"}), capsys)

    assert code == 0
    assert result["status"] == "unknown_client"
    assert result["heard"] == "Acme"
    assert result["closest"] is None


def test_unknown_client_offers_closest(monkeypatch, capsys):
    _stub_list_tabs(monkeypatch, ["ACME-Corp"])

    code, result = _run(monkeypatch, _primary_args(**{"--client": "acme"}), capsys)

    assert result["status"] == "unknown_client"
    assert result["closest"] == "ACME-Corp"


def test_ambiguous_multiple_alias_matches(monkeypatch, capsys, _isolated_clients_config):
    _write_clients_config(
        _isolated_clients_config,
        {"ACME-East": ["acme"], "ACME-West": ["acme"]},
    )
    _stub_list_tabs(monkeypatch, ["ACME-East", "ACME-West"])

    code, result = _run(monkeypatch, _primary_args(**{"--client": "acme"}), capsys)

    assert code == 0
    assert result["status"] == "ambiguous"
    assert set(result["candidates"]) == {"ACME-East", "ACME-West"}


def test_client_resolves_via_alias(monkeypatch, capsys, _isolated_clients_config):
    _write_clients_config(_isolated_clients_config, {"ACME": ["acme corp", "the acme co"]})
    _stub_list_tabs(monkeypatch, ["ACME"])
    _stub_append_row_ok(monkeypatch)

    code, result = _run(monkeypatch, _primary_args(**{"--client": "acme corp"}), capsys)

    assert result["status"] == "logged"
    assert result["tab"] == "ACME"


# --------------------------------------------------------------------------- #
# status: need_field
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "flag,expected_missing",
    [
        ("--client", "client"),
        ("--hours", "hours"),
        ("--description", "description"),
        ("--date", "date"),
    ],
)
def test_need_field_missing_required(monkeypatch, capsys, flag, expected_missing):
    argv = _primary_args(**{flag: None})
    code, result = _run(monkeypatch, argv, capsys)

    assert code == 0
    assert result["status"] == "need_field"
    assert result["missing"] == expected_missing
    assert expected_missing not in result["partial"]


def test_need_field_unparseable_date(monkeypatch, capsys):
    code, result = _run(monkeypatch, _primary_args(**{"--date": "next tuesday"}), capsys)

    assert code == 0
    assert result["status"] == "need_field"
    assert result["missing"] == "date"


# --------------------------------------------------------------------------- #
# status: not_timelog
# --------------------------------------------------------------------------- #


def test_not_timelog_no_write(monkeypatch, capsys, emitted_alerts):
    code, result = _run(monkeypatch, ["--not-timelog"] + BASE_ARGS, capsys)

    assert code == 0
    assert result == {"status": "not_timelog"}
    assert emitted_alerts == []


# --------------------------------------------------------------------------- #
# status: error (fail-safe, NFR-002)
# --------------------------------------------------------------------------- #


def test_error_on_list_tabs_failure_never_false_logged(monkeypatch, capsys, emitted_alerts):
    def _fail(account: str) -> list[str]:
        raise timelog.SheetsOpError("Sheets API 503")

    monkeypatch.setattr(timelog, "_sh_list_tabs", _fail)

    code, result = _run(monkeypatch, _primary_args(), capsys)

    assert code == 0
    assert result["status"] == "error"
    assert "503" in result["detail"]
    assert len(emitted_alerts) == 1
    assert emitted_alerts[0].severity.value == "error"
    assert emitted_alerts[0].title == "Time-log write failed"


def test_error_on_append_failure_never_false_logged(monkeypatch, capsys, emitted_alerts):
    _stub_list_tabs(monkeypatch, ["ACME"])
    _stub_append_row_fails(monkeypatch, "Sheets 503")

    code, result = _run(monkeypatch, _primary_args(), capsys)

    assert code == 0
    assert result["status"] == "error"
    assert "503" in result["detail"]
    assert len(emitted_alerts) == 1


def test_error_write_never_lands_in_ledger(monkeypatch, capsys, _isolated_state):
    _stub_list_tabs(monkeypatch, ["ACME"])
    _stub_append_row_fails(monkeypatch)

    _run(monkeypatch, _primary_args(), capsys)

    assert timelog._load_ledger("testacct") == []


# --------------------------------------------------------------------------- #
# status: client_created_entry_failed (new-client two-step partial mutation)
# --------------------------------------------------------------------------- #


def test_add_client_success_creates_tab_and_logs(monkeypatch, capsys, emitted_alerts):
    # Seed a pending record awaiting new_client_confirm, as if unknown_client
    # already ran once for this correlated conversation.
    source = timelog.Source("whatsapp", "conv-1", "msg-1")
    partial = {"client": "ACME", "hours": 2.5, "description": "onboarding prep", "date": "today"}
    pending = timelog._new_pending(source, partial, awaiting="new_client_confirm")
    timelog._save_pending("testacct", source, pending)

    _stub_create_tab_ok(monkeypatch, created=True)
    _stub_append_row_ok(monkeypatch, row_index=1)

    code, result = _run(
        monkeypatch,
        ["--add-client", "ACME"] + BASE_ARGS,
        capsys,
    )

    assert code == 0
    assert result["status"] == "logged"
    assert result["tab"] == "ACME"
    assert emitted_alerts == []
    # Pending cleared after a successful write.
    assert timelog._load_pending("testacct", source) is None


def test_add_client_partial_mutation_tab_created_append_fails(monkeypatch, capsys, emitted_alerts):
    source = timelog.Source("whatsapp", "conv-1", "msg-1")
    partial = {"client": "ACME", "hours": 2.5, "description": "onboarding prep", "date": "today"}
    pending = timelog._new_pending(source, partial, awaiting="new_client_confirm")
    timelog._save_pending("testacct", source, pending)

    _stub_create_tab_ok(monkeypatch, created=True)
    _stub_append_row_fails(monkeypatch, "Sheets 503")

    code, result = _run(monkeypatch, ["--add-client", "ACME"] + BASE_ARGS, capsys)

    assert code == 0
    assert result["status"] == "client_created_entry_failed"
    assert result["tab"] == "ACME"
    assert "NOT logged" in result["detail"]
    assert len(emitted_alerts) == 1
    assert emitted_alerts[0].title == "Time-log write failed"
    # Never lands in the ledger — the entry was NOT logged.
    assert timelog._load_ledger("testacct") == []


def test_add_client_retry_is_idempotent(monkeypatch, capsys):
    """A retry after client_created_entry_failed succeeds without re-erroring:
    create-tab no-ops (tab already exists) and append succeeds this time."""
    source = timelog.Source("whatsapp", "conv-1", "msg-1")
    partial = {"client": "ACME", "hours": 2.5, "description": "onboarding prep", "date": "today"}
    pending = timelog._new_pending(source, partial, awaiting="new_client_confirm")
    timelog._save_pending("testacct", source, pending)

    _stub_create_tab_ok(monkeypatch, created=False)  # no-op: already exists
    _stub_append_row_ok(monkeypatch, row_index=2)

    code, result = _run(monkeypatch, ["--add-client", "ACME"] + BASE_ARGS, capsys)

    assert code == 0
    assert result["status"] == "logged"


def test_add_client_no_pending_when_uncorrelated(monkeypatch, capsys):
    other_source = timelog.Source("whatsapp", "conv-OTHER", "msg-OTHER")
    partial = {"client": "ACME", "hours": 2.5, "description": "x", "date": "today"}
    pending = timelog._new_pending(other_source, partial, awaiting="new_client_confirm")
    timelog._save_pending("testacct", other_source, pending)

    code, result = _run(monkeypatch, ["--add-client", "ACME"] + BASE_ARGS, capsys)

    assert code == 0
    assert result["status"] == "no_pending"
    assert result["awaiting"] == "none"


# --------------------------------------------------------------------------- #
# Pending correlation: no_pending / stale_pending
# --------------------------------------------------------------------------- #


def test_confirm_client_no_pending_record(monkeypatch, capsys):
    code, result = _run(monkeypatch, ["--confirm-client", "ACME"] + BASE_ARGS, capsys)

    assert code == 0
    assert result["status"] == "no_pending"
    assert result["awaiting"] == "none"


def test_confirm_client_uncorrelated_conversation(monkeypatch, capsys):
    other_source = timelog.Source("whatsapp", "conv-OTHER", "msg-OTHER")
    partial = {"client": "Acme", "hours": 2.5, "description": "x", "date": "today"}
    pending = timelog._new_pending(other_source, partial, awaiting="client")
    timelog._save_pending("testacct", other_source, pending)

    code, result = _run(monkeypatch, ["--confirm-client", "ACME"] + BASE_ARGS, capsys)

    assert result["status"] == "no_pending"


def test_confirm_client_stale_pending_clears_record(monkeypatch, capsys, _isolated_state):
    source = timelog.Source("whatsapp", "conv-1", "msg-1")
    partial = {"client": "Acme", "hours": 2.5, "description": "x", "date": "today"}
    pending = timelog._new_pending(source, partial, awaiting="client")
    # Force it well past the 30-min TTL.
    stale_created = datetime.now(timezone.utc) - timedelta(hours=2)
    pending["created_at"] = stale_created.isoformat()
    pending["expires_at"] = (stale_created + timedelta(seconds=timelog.PENDING_TTL_SECONDS)).isoformat()
    timelog._save_pending("testacct", source, pending)

    code, result = _run(monkeypatch, ["--confirm-client", "ACME"] + BASE_ARGS, capsys)

    assert code == 0
    assert result["status"] == "stale_pending"
    assert result["age_s"] > 0
    assert timelog._load_pending("testacct", source) is None  # cleared


def test_confirm_client_correlated_resumes_and_logs(monkeypatch, capsys):
    source = timelog.Source("whatsapp", "conv-1", "msg-1")
    partial = {"client": "Acme", "hours": 2.5, "description": "onboarding prep", "date": "today"}
    pending = timelog._new_pending(source, partial, awaiting="client")
    timelog._save_pending("testacct", source, pending)

    _stub_list_tabs(monkeypatch, ["ACME"])
    _stub_append_row_ok(monkeypatch)

    code, result = _run(monkeypatch, ["--confirm-client", "ACME"] + BASE_ARGS, capsys)

    assert code == 0
    assert result["status"] == "logged"
    assert result["tab"] == "ACME"


def test_field_no_pending_record(monkeypatch, capsys):
    code, result = _run(monkeypatch, ["--field", "hours=3"] + BASE_ARGS, capsys)

    assert code == 0
    assert result["status"] == "no_pending"


def test_field_supplies_missing_and_logs(monkeypatch, capsys):
    source = timelog.Source("whatsapp", "conv-1", "msg-1")
    partial = {"client": "ACME", "description": "onboarding prep", "date": "today"}
    pending = timelog._new_pending(source, partial, awaiting="field:hours")
    timelog._save_pending("testacct", source, pending)

    _stub_list_tabs(monkeypatch, ["ACME"])
    _stub_append_row_ok(monkeypatch)

    code, result = _run(monkeypatch, ["--field", "hours=3"] + BASE_ARGS, capsys)

    assert code == 0
    assert result["status"] == "logged"
    assert result["row"]["hours"] == 3.0


# --------------------------------------------------------------------------- #
# Ledger corrections: corrected / deleted / no_last_write / correction_ambiguous
# --------------------------------------------------------------------------- #


def _seed_ledger_entry(
    account: str,
    *,
    tab: str = "ACME",
    row_index: int = 5,
    hours: float = 2.5,
    written_at: datetime | None = None,
    source: dict[str, str] | None = None,
) -> str:
    import uuid

    now = written_at or datetime.now(timezone.utc)
    write_id = str(uuid.uuid4())
    record = {
        "write_id": write_id,
        "entry_id": str(uuid.uuid4()),
        "source": source or {"channel": "whatsapp", "conversation_id": "conv-1", "source_message_id": "msg-1"},
        "tab": tab,
        "row_index": row_index,
        "entry": {
            "date": "2026-07-10",
            "hours": hours,
            "client": tab,
            "description": "onboarding prep",
            "billable": True,
            "logged_at": now.isoformat(),
            "entry_id": str(uuid.uuid4()),
        },
        "written_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=timelog.LEDGER_TTL_SECONDS)).isoformat(),
    }
    records = timelog._load_ledger(account)
    records.append(record)
    timelog._save_ledger(account, records)
    return write_id


def test_no_last_write_empty_ledger(monkeypatch, capsys):
    code, result = _run(monkeypatch, ["--correct", "--hours", "3"] + BASE_ARGS, capsys)

    assert code == 0
    assert result == {"status": "no_last_write"}


def test_delete_last_no_last_write_empty_ledger(monkeypatch, capsys):
    code, result = _run(monkeypatch, ["--delete-last"] + BASE_ARGS, capsys)

    assert code == 0
    assert result == {"status": "no_last_write"}


def test_correct_updates_most_recent_entry(monkeypatch, capsys):
    _seed_ledger_entry("testacct", tab="ACME", row_index=5, hours=2.5)

    def _fake_update(tab, row, values, account):
        assert tab == "ACME"
        assert row == 5

    monkeypatch.setattr(timelog, "_sh_update_last", _fake_update)

    code, result = _run(monkeypatch, ["--correct", "--hours", "3"] + BASE_ARGS, capsys)

    assert code == 0
    assert result["status"] == "corrected"
    assert result["tab"] == "ACME"
    assert result["row"]["hours"] == 3.0
    assert "receipt" in result


def test_delete_last_removes_most_recent_entry(monkeypatch, capsys):
    _seed_ledger_entry("testacct", tab="ACME", row_index=5)

    def _fake_delete(tab, row, account, entry_id=None):
        assert tab == "ACME"
        assert row == 5

    monkeypatch.setattr(timelog, "_sh_delete_last", _fake_delete)

    code, result = _run(monkeypatch, ["--delete-last"] + BASE_ARGS, capsys)

    assert code == 0
    assert result["status"] == "deleted"
    assert result["tab"] == "ACME"
    # Ledger entry removed after delete.
    assert timelog._load_ledger("testacct") == []


_OTHER_CONV_SOURCE = {"channel": "whatsapp", "conversation_id": "conv-OTHER", "source_message_id": "msg-OTHER"}


def test_correct_newer_write_after_target_is_ambiguous(monkeypatch, capsys):
    """The correction's own conversation (conv-1/msg-1, per BASE_ARGS) logged
    the older entry; a DIFFERENT conversation logged a globally newer one
    afterwards -> "most recent" is no longer unambiguous for this follow-up.
    """
    older = datetime.now(timezone.utc) - timedelta(minutes=5)
    newer = datetime.now(timezone.utc) - timedelta(minutes=1)
    _seed_ledger_entry("testacct", tab="ACME", row_index=5, written_at=older)
    _seed_ledger_entry("testacct", tab="BETA", row_index=9, written_at=newer, source=_OTHER_CONV_SOURCE)

    code, result = _run(monkeypatch, ["--correct", "--hours", "3"] + BASE_ARGS, capsys)

    assert code == 0
    assert result["status"] == "correction_ambiguous"
    assert result["reason"] == "newer_write"
    assert result["candidates"]


def test_correct_stale_target_is_ambiguous(monkeypatch, capsys):
    old = datetime.now(timezone.utc) - timedelta(hours=1)
    write_id = _seed_ledger_entry("testacct", tab="ACME", row_index=5, written_at=old)
    # Force this single record's expiry into the past.
    records = timelog._load_ledger("testacct")
    for r in records:
        if r["write_id"] == write_id:
            r["expires_at"] = (old + timedelta(seconds=1)).isoformat()
    timelog._save_ledger("testacct", records)

    code, result = _run(monkeypatch, ["--correct", "--hours", "3"] + BASE_ARGS, capsys)

    assert code == 0
    assert result["status"] == "correction_ambiguous"
    assert result["reason"] == "stale"


def test_correction_never_mutates_wrong_row(monkeypatch, capsys):
    """When ambiguous, no update-last/delete-last call is made at all."""
    older = datetime.now(timezone.utc) - timedelta(minutes=5)
    newer = datetime.now(timezone.utc) - timedelta(minutes=1)
    _seed_ledger_entry("testacct", tab="ACME", row_index=5, written_at=older)
    _seed_ledger_entry("testacct", tab="BETA", row_index=9, written_at=newer, source=_OTHER_CONV_SOURCE)

    calls: list[Any] = []
    monkeypatch.setattr(timelog, "_sh_update_last", lambda *a, **k: calls.append((a, k)))
    monkeypatch.setattr(timelog, "_sh_delete_last", lambda *a, **k: calls.append((a, k)))

    _run(monkeypatch, ["--correct", "--hours", "3"] + BASE_ARGS, capsys)
    _run(monkeypatch, ["--delete-last"] + BASE_ARGS, capsys)

    assert calls == []


# --------------------------------------------------------------------------- #
# Exit-code contract: handled statuses exit 0; usage errors exit 2
# --------------------------------------------------------------------------- #


def test_usage_error_bad_hours_exits_2(capsys):
    code = timelog.main(
        ["--client", "ACME", "--hours", "notanumber", "--date", "today",
         "--description", "x"] + BASE_ARGS
    )
    assert code == 2


def test_usage_error_unknown_flag_exits_2(capsys):
    code = timelog.main(["--not-a-real-flag", "x"] + BASE_ARGS)
    assert code == 2


def test_usage_error_missing_correlation_exits_2(capsys):
    code = timelog.main(["--client", "ACME", "--hours", "1", "--date", "today", "--description", "x"])
    assert code == 2


@pytest.mark.parametrize(
    "argv_builder",
    [
        lambda: _primary_args(),
        lambda: ["--not-timelog"] + BASE_ARGS,
        lambda: ["--correct", "--hours", "3"] + BASE_ARGS,
        lambda: ["--delete-last"] + BASE_ARGS,
        lambda: ["--confirm-client", "ACME"] + BASE_ARGS,
        lambda: ["--add-client", "ACME"] + BASE_ARGS,
        lambda: ["--field", "hours=3"] + BASE_ARGS,
    ],
)
def test_every_handled_status_exits_zero(monkeypatch, capsys, argv_builder):
    # Force all Sheets ops to a benign no-op state so any status short-circuits
    # cleanly without raising — the point here is purely the exit code.
    _stub_list_tabs(monkeypatch, [])
    code, _result = _run(monkeypatch, argv_builder(), capsys)
    assert code == 0


# --------------------------------------------------------------------------- #
# Alert boundary: clarification signals never alert
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "argv_builder,stub",
    [
        (lambda: _primary_args(**{"--client": "Nope"}), lambda mp: _stub_list_tabs(mp, ["ACME"])),
        (lambda: _primary_args(**{"--hours": None}), lambda mp: None),
        (lambda: ["--not-timelog"] + BASE_ARGS, lambda mp: None),
        (lambda: ["--confirm-client", "ACME"] + BASE_ARGS, lambda mp: None),  # no_pending
        (lambda: ["--correct", "--hours", "3"] + BASE_ARGS, lambda mp: None),  # no_last_write
    ],
)
def test_clarification_signals_never_alert(monkeypatch, capsys, emitted_alerts, argv_builder, stub):
    stub(monkeypatch)
    code, result = _run(monkeypatch, argv_builder(), capsys)

    assert code == 0
    assert result["status"] in {
        "unknown_client", "need_field", "not_timelog", "no_pending",
        "stale_pending", "no_last_write", "correction_ambiguous", "ambiguous",
    }
    assert emitted_alerts == []


# --------------------------------------------------------------------------- #
# Additional follow-up branch coverage: confirm-client / add-client / field
# --------------------------------------------------------------------------- #


def test_confirm_client_still_missing_a_field_reprompts(monkeypatch, capsys):
    """A pending record missing 'hours' -- --confirm-client supplies the
    client but hours is still absent -> need_field(hours), pending updated."""
    source = timelog.Source("whatsapp", "conv-1", "msg-1")
    partial = {"description": "onboarding prep", "date": "today"}  # no hours
    pending = timelog._new_pending(source, partial, awaiting="client")
    timelog._save_pending("testacct", source, pending)

    code, result = _run(monkeypatch, ["--confirm-client", "ACME"] + BASE_ARGS, capsys)

    assert code == 0
    assert result["status"] == "need_field"
    assert result["missing"] == "hours"
    assert result["partial"]["client"] == "ACME"


def test_confirm_client_unparseable_date_reprompts(monkeypatch, capsys):
    source = timelog.Source("whatsapp", "conv-1", "msg-1")
    partial = {"hours": 2.5, "description": "onboarding prep", "date": "next week"}
    pending = timelog._new_pending(source, partial, awaiting="client")
    timelog._save_pending("testacct", source, pending)

    code, result = _run(monkeypatch, ["--confirm-client", "ACME"] + BASE_ARGS, capsys)

    assert code == 0
    assert result["status"] == "need_field"
    assert result["missing"] == "date"


def test_confirm_client_still_unknown(monkeypatch, capsys):
    source = timelog.Source("whatsapp", "conv-1", "msg-1")
    partial = {"hours": 2.5, "description": "onboarding prep", "date": "today"}
    pending = timelog._new_pending(source, partial, awaiting="client")
    timelog._save_pending("testacct", source, pending)
    _stub_list_tabs(monkeypatch, ["OTHERCO"])

    code, result = _run(monkeypatch, ["--confirm-client", "TotallyUnknown"] + BASE_ARGS, capsys)

    assert code == 0
    assert result["status"] == "unknown_client"


def test_confirm_client_still_ambiguous(monkeypatch, capsys, _isolated_clients_config):
    _write_clients_config(_isolated_clients_config, {"ACME-East": ["acme"], "ACME-West": ["acme"]})
    source = timelog.Source("whatsapp", "conv-1", "msg-1")
    partial = {"hours": 2.5, "description": "onboarding prep", "date": "today"}
    pending = timelog._new_pending(source, partial, awaiting="client")
    timelog._save_pending("testacct", source, pending)
    _stub_list_tabs(monkeypatch, ["ACME-East", "ACME-West"])

    code, result = _run(monkeypatch, ["--confirm-client", "acme"] + BASE_ARGS, capsys)

    assert code == 0
    assert result["status"] == "ambiguous"


def test_confirm_client_list_tabs_error_is_fail_safe(monkeypatch, capsys, emitted_alerts):
    source = timelog.Source("whatsapp", "conv-1", "msg-1")
    partial = {"hours": 2.5, "description": "onboarding prep", "date": "today"}
    pending = timelog._new_pending(source, partial, awaiting="client")
    timelog._save_pending("testacct", source, pending)

    def _fail(account: str) -> list[str]:
        raise timelog.SheetsOpError("Sheets API 503")

    monkeypatch.setattr(timelog, "_sh_list_tabs", _fail)

    code, result = _run(monkeypatch, ["--confirm-client", "ACME"] + BASE_ARGS, capsys)

    assert code == 0
    assert result["status"] == "error"
    assert len(emitted_alerts) == 1


def test_add_client_still_missing_a_field_reprompts(monkeypatch, capsys):
    source = timelog.Source("whatsapp", "conv-1", "msg-1")
    partial = {"client": "ACME", "date": "today"}  # no hours, no description
    pending = timelog._new_pending(source, partial, awaiting="new_client_confirm")
    timelog._save_pending("testacct", source, pending)

    code, result = _run(monkeypatch, ["--add-client", "ACME"] + BASE_ARGS, capsys)

    assert code == 0
    assert result["status"] == "need_field"
    assert result["missing"] == "hours"


def test_add_client_unparseable_date_reprompts(monkeypatch, capsys):
    source = timelog.Source("whatsapp", "conv-1", "msg-1")
    partial = {"client": "ACME", "hours": 2.5, "description": "x", "date": "whenever"}
    pending = timelog._new_pending(source, partial, awaiting="new_client_confirm")
    timelog._save_pending("testacct", source, pending)

    code, result = _run(monkeypatch, ["--add-client", "ACME"] + BASE_ARGS, capsys)

    assert code == 0
    assert result["status"] == "need_field"
    assert result["missing"] == "date"


def test_add_client_create_tab_failure_is_fail_safe(monkeypatch, capsys, emitted_alerts):
    source = timelog.Source("whatsapp", "conv-1", "msg-1")
    partial = {"client": "ACME", "hours": 2.5, "description": "x", "date": "today"}
    pending = timelog._new_pending(source, partial, awaiting="new_client_confirm")
    timelog._save_pending("testacct", source, pending)

    def _fail(tab: str, account: str) -> bool:
        raise timelog.SheetsOpError("Sheets API 503")

    monkeypatch.setattr(timelog, "_sh_create_tab", _fail)

    code, result = _run(monkeypatch, ["--add-client", "ACME"] + BASE_ARGS, capsys)

    assert code == 0
    assert result["status"] == "error"
    assert len(emitted_alerts) == 1
    assert timelog._load_ledger("testacct") == []


def test_field_malformed_no_equals_reprompts(monkeypatch, capsys):
    source = timelog.Source("whatsapp", "conv-1", "msg-1")
    partial = {"client": "ACME", "description": "x", "date": "today"}
    pending = timelog._new_pending(source, partial, awaiting="field:hours")
    timelog._save_pending("testacct", source, pending)

    code, result = _run(monkeypatch, ["--field", "notanassignment"] + BASE_ARGS, capsys)

    assert code == 0
    assert result["status"] == "need_field"
    assert result["missing"] == "hours"


def test_field_unknown_name_reprompts(monkeypatch, capsys):
    source = timelog.Source("whatsapp", "conv-1", "msg-1")
    partial = {"client": "ACME", "description": "x", "date": "today"}
    pending = timelog._new_pending(source, partial, awaiting="field:hours")
    timelog._save_pending("testacct", source, pending)

    code, result = _run(monkeypatch, ["--field", "bogus=1"] + BASE_ARGS, capsys)

    assert code == 0
    assert result["status"] == "need_field"


def test_field_still_missing_another_field(monkeypatch, capsys):
    source = timelog.Source("whatsapp", "conv-1", "msg-1")
    partial = {"client": "ACME", "date": "today"}  # missing hours + description
    pending = timelog._new_pending(source, partial, awaiting="field:hours")
    timelog._save_pending("testacct", source, pending)

    code, result = _run(monkeypatch, ["--field", "hours=3"] + BASE_ARGS, capsys)

    assert code == 0
    assert result["status"] == "need_field"
    assert result["missing"] == "description"


def test_field_unparseable_date(monkeypatch, capsys):
    source = timelog.Source("whatsapp", "conv-1", "msg-1")
    partial = {"client": "ACME", "hours": 2.5, "description": "x", "date": "whenever"}
    pending = timelog._new_pending(source, partial, awaiting="field:date")
    timelog._save_pending("testacct", source, pending)

    code, result = _run(monkeypatch, ["--field", "date=nonsense"] + BASE_ARGS, capsys)

    assert code == 0
    assert result["status"] == "need_field"
    assert result["missing"] == "date"


def test_field_non_numeric_hours_reprompts(monkeypatch, capsys):
    source = timelog.Source("whatsapp", "conv-1", "msg-1")
    partial = {"client": "ACME", "description": "x", "date": "today"}
    pending = timelog._new_pending(source, partial, awaiting="field:hours")
    timelog._save_pending("testacct", source, pending)

    code, result = _run(monkeypatch, ["--field", "hours=notanumber"] + BASE_ARGS, capsys)

    assert code == 0
    assert result["status"] == "need_field"
    assert result["missing"] == "hours"


def test_field_still_unknown_client(monkeypatch, capsys):
    source = timelog.Source("whatsapp", "conv-1", "msg-1")
    partial = {"client": "Nope", "hours": 2.5, "description": "x", "date": "today"}
    pending = timelog._new_pending(source, partial, awaiting="field:hours")
    timelog._save_pending("testacct", source, pending)
    _stub_list_tabs(monkeypatch, ["OTHERCO"])

    code, result = _run(monkeypatch, ["--field", "hours=3"] + BASE_ARGS, capsys)

    assert code == 0
    assert result["status"] == "unknown_client"


def test_field_still_ambiguous(monkeypatch, capsys, _isolated_clients_config):
    _write_clients_config(_isolated_clients_config, {"ACME-East": ["acme"], "ACME-West": ["acme"]})
    source = timelog.Source("whatsapp", "conv-1", "msg-1")
    partial = {"client": "acme", "hours": 2.5, "description": "x", "date": "today"}
    pending = timelog._new_pending(source, partial, awaiting="field:hours")
    timelog._save_pending("testacct", source, pending)
    _stub_list_tabs(monkeypatch, ["ACME-East", "ACME-West"])

    code, result = _run(monkeypatch, ["--field", "hours=3"] + BASE_ARGS, capsys)

    assert code == 0
    assert result["status"] == "ambiguous"


def test_field_list_tabs_error_is_fail_safe(monkeypatch, capsys, emitted_alerts):
    source = timelog.Source("whatsapp", "conv-1", "msg-1")
    partial = {"client": "ACME", "description": "x", "date": "today"}
    pending = timelog._new_pending(source, partial, awaiting="field:hours")
    timelog._save_pending("testacct", source, pending)

    def _fail(account: str) -> list[str]:
        raise timelog.SheetsOpError("Sheets API 503")

    monkeypatch.setattr(timelog, "_sh_list_tabs", _fail)

    code, result = _run(monkeypatch, ["--field", "hours=3"] + BASE_ARGS, capsys)

    assert code == 0
    assert result["status"] == "error"
    assert len(emitted_alerts) == 1


# --------------------------------------------------------------------------- #
# Correction amendment fields (--correct with description/date/non-billable)
# --------------------------------------------------------------------------- #


def test_correct_amends_description_date_and_non_billable(monkeypatch, capsys):
    _seed_ledger_entry("testacct", tab="ACME", row_index=5, hours=2.5)
    monkeypatch.setattr(timelog, "_sh_update_last", lambda *a, **k: None)

    code, result = _run(
        monkeypatch,
        [
            "--correct", "--hours", "3", "--description", "revised desc",
            "--date", "yesterday", "--non-billable",
        ] + BASE_ARGS,
        capsys,
    )

    assert code == 0
    assert result["status"] == "corrected"
    assert result["row"]["description"] == "revised desc"
    assert result["row"]["billable"] is False
    assert result["row"]["hours"] == 3.0


def test_correct_update_last_failure_is_fail_safe(monkeypatch, capsys, emitted_alerts):
    _seed_ledger_entry("testacct", tab="ACME", row_index=5)

    def _fail(tab, row, values, account):
        raise timelog.SheetsOpError("Sheets 503")

    monkeypatch.setattr(timelog, "_sh_update_last", _fail)

    code, result = _run(monkeypatch, ["--correct", "--hours", "3"] + BASE_ARGS, capsys)

    assert code == 0
    assert result["status"] == "error"
    assert len(emitted_alerts) == 1
    # Ledger entry is untouched on failure.
    ledger = timelog._load_ledger("testacct")
    assert len(ledger) == 1
    assert ledger[0]["entry"]["hours"] == 2.5


def test_delete_last_failure_is_fail_safe(monkeypatch, capsys, emitted_alerts):
    _seed_ledger_entry("testacct", tab="ACME", row_index=5)

    def _fail(tab, row, account, entry_id=None):
        raise timelog.SheetsOpError("Sheets 503")

    monkeypatch.setattr(timelog, "_sh_delete_last", _fail)

    code, result = _run(monkeypatch, ["--delete-last"] + BASE_ARGS, capsys)

    assert code == 0
    assert result["status"] == "error"
    assert len(emitted_alerts) == 1
    assert len(timelog._load_ledger("testacct")) == 1


# --------------------------------------------------------------------------- #
# _call_sheets_helper integration seam (in-process sheets_helper.main call)
# --------------------------------------------------------------------------- #


def test_call_sheets_helper_parses_json_on_success(monkeypatch):
    def _fake_main(argv):
        print(json.dumps({"status": "ok", "tabs": ["ACME"]}))
        print("SUMMARY: op=list-tabs status=ok")
        return 0

    monkeypatch.setattr(timelog.sheets_helper, "main", _fake_main)

    result = timelog._call_sheets_helper(["list-tabs", "--account", "personal"])

    assert result == {"status": "ok", "tabs": ["ACME"]}


def test_call_sheets_helper_raises_on_nonzero_exit(monkeypatch):
    def _fake_main(argv):
        print("SUMMARY: op=append-row status=error account=personal")
        return 1

    monkeypatch.setattr(timelog.sheets_helper, "main", _fake_main)

    with pytest.raises(timelog.SheetsOpError):
        timelog._call_sheets_helper(["append-row", "--tab", "ACME"])


def test_call_sheets_helper_raises_on_non_json_output(monkeypatch):
    def _fake_main(argv):
        print("not json at all")
        return 0

    monkeypatch.setattr(timelog.sheets_helper, "main", _fake_main)

    with pytest.raises(timelog.SheetsOpError):
        timelog._call_sheets_helper(["list-tabs"])


def test_call_sheets_helper_raises_on_empty_output(monkeypatch):
    def _fake_main(argv):
        return 0

    monkeypatch.setattr(timelog.sheets_helper, "main", _fake_main)

    with pytest.raises(timelog.SheetsOpError):
        timelog._call_sheets_helper(["list-tabs"])


def test_sh_wrapper_functions_call_through(monkeypatch):
    """Exercise _sh_list_tabs/_sh_create_tab/_sh_append_row/_sh_update_last/
    _sh_delete_last themselves (not just the boundary they call through to),
    via a fake sheets_helper.main."""
    calls: list[list[str]] = []

    def _fake_main(argv):
        calls.append(list(argv))
        if argv[0] == "list-tabs":
            print(json.dumps({"status": "ok", "tabs": ["ACME", "BETA"]}))
        elif argv[0] == "create-tab":
            print(json.dumps({"status": "ok", "tab": "ACME", "created": True}))
        elif argv[0] == "append-row":
            print(json.dumps({"status": "ok", "row_index": 3, "values": ["a"]}))
        elif argv[0] == "update-last":
            print(json.dumps({"status": "ok"}))
        elif argv[0] == "delete-last":
            print(json.dumps({"status": "ok"}))
        return 0

    monkeypatch.setattr(timelog.sheets_helper, "main", _fake_main)

    assert timelog._sh_list_tabs("personal") == ["ACME", "BETA"]
    assert timelog._sh_create_tab("ACME", "personal") is True
    assert timelog._sh_append_row("ACME", "eid-1", ["a"], "personal") == (3, ["a"])
    timelog._sh_update_last("ACME", 3, ["a"], "personal")
    timelog._sh_delete_last("ACME", 3, "personal")

    ops = [c[0] for c in calls]
    assert ops == ["list-tabs", "create-tab", "append-row", "update-last", "delete-last"]


def test_sh_list_tabs_defensive_non_list_tabs(monkeypatch):
    def _fake_main(argv):
        print(json.dumps({"status": "ok", "tabs": "not-a-list"}))
        return 0

    monkeypatch.setattr(timelog.sheets_helper, "main", _fake_main)

    assert timelog._sh_list_tabs("personal") == []


# --------------------------------------------------------------------------- #
# Misc small-branch coverage: yesterday date token, corrupt state files
# --------------------------------------------------------------------------- #


def test_normalize_date_yesterday():
    from datetime import date, timedelta

    assert timelog._normalize_date("yesterday") == (date.today() - timedelta(days=1)).isoformat()


def test_read_json_missing_file_returns_default(tmp_path):
    missing = tmp_path / "does-not-exist.json"
    assert timelog._read_json(missing, {"default": True}) == {"default": True}


def test_read_json_corrupt_file_returns_default(tmp_path):
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not valid json")
    assert timelog._read_json(corrupt, []) == []


def test_save_pending_none_on_already_absent_file_is_a_noop(_isolated_state):
    # No pending file was ever written for this account — clearing it must not
    # raise even though there's nothing to unlink.
    source = timelog.Source("whatsapp", "conv-1", "msg-1")
    timelog._save_pending("neveropened", source, None)
    assert timelog._load_pending("neveropened", source) is None


# --------------------------------------------------------------------------- #
# F2 — end-to-end append idempotency: a retry reuses a STABLE entry_id
# --------------------------------------------------------------------------- #


def test_entry_id_is_stable_across_retries_of_same_request():
    """F2: the derived entry_id depends only on (account, source, normalized
    fields) — NOT wall-clock — so an identical retry produces the SAME id and
    sheets_helper's dedup-by-entry_id can fire."""
    source = timelog.Source("whatsapp", "conv-1", "msg-1")
    kwargs = dict(
        account="testacct",
        source=source,
        normalized_date="2026-07-10",
        hours=2.5,
        client="ACME",
        description="onboarding prep",
        billable=True,
    )
    first = timelog._derive_entry_id(**kwargs)
    second = timelog._derive_entry_id(**kwargs)
    assert first == second
    # A different conversation (or different fields) derives a different id.
    other = timelog._derive_entry_id(
        **{**kwargs, "source": timelog.Source("whatsapp", "conv-2", "msg-9")}
    )
    assert other != first


def test_retry_reuses_entry_id_so_sheets_helper_dedups_no_duplicate(monkeypatch, capsys):
    """F2 e2e: two identical primary calls (a lost-confirmation retry) hand
    sheets_helper the SAME entry_id, so its dedup prevents a duplicate row.

    We capture the entry_id passed to _sh_append_row on each attempt and assert
    they are identical — the property sheets_helper's tail-scan relies on.
    """
    _stub_list_tabs(monkeypatch, ["ACME"])
    seen_entry_ids: list[str] = []

    def _fake_append(tab, entry_id, values, account):
        seen_entry_ids.append(entry_id)
        return 5, values

    monkeypatch.setattr(timelog, "_sh_append_row", _fake_append)

    code1, r1 = _run(monkeypatch, _primary_args(), capsys)
    code2, r2 = _run(monkeypatch, _primary_args(), capsys)

    assert code1 == 0 and code2 == 0
    assert r1["status"] == "logged" and r2["status"] == "logged"
    assert len(seen_entry_ids) == 2
    assert seen_entry_ids[0] == seen_entry_ids[1], (
        "a retry of the same request must reuse the same entry_id so "
        "sheets_helper dedups instead of appending a duplicate (F2)"
    )
    assert r1["row"]["entry_id"] == r2["row"]["entry_id"]


def test_add_client_retry_reuses_entry_id(monkeypatch, capsys):
    """F2: --add-client also derives a stable entry_id across retries."""
    source = timelog.Source("whatsapp", "conv-1", "msg-1")
    partial = {"client": "ACME", "hours": 2.5, "description": "onboarding prep", "date": "today"}
    seen: list[str] = []

    def _fake_append(tab, entry_id, values, account):
        seen.append(entry_id)
        return 2, values

    monkeypatch.setattr(timelog, "_sh_append_row", _fake_append)
    _stub_create_tab_ok(monkeypatch, created=False)

    for _ in range(2):
        pending = timelog._new_pending(source, partial, awaiting="new_client_confirm")
        timelog._save_pending("testacct", source, pending)
        _run(monkeypatch, ["--add-client", "ACME"] + BASE_ARGS, capsys)

    assert len(seen) == 2
    assert seen[0] == seen[1]


# --------------------------------------------------------------------------- #
# F3 — pending is source-keyed: concurrent conversations don't clobber
# --------------------------------------------------------------------------- #


def test_pending_two_conversations_do_not_clobber(_isolated_state):
    """F3: a second conversation's pending record must NOT overwrite the
    first — each source key gets its own map entry."""
    src_a = timelog.Source("whatsapp", "conv-A", "msg-A")
    src_b = timelog.Source("whatsapp", "conv-B", "msg-B")
    timelog._save_pending("acct", src_a, timelog._new_pending(src_a, {"client": "ACME"}, "client"))
    timelog._save_pending("acct", src_b, timelog._new_pending(src_b, {"client": "BETA"}, "client"))

    rec_a = timelog._load_pending("acct", src_a)
    rec_b = timelog._load_pending("acct", src_b)
    assert rec_a is not None and rec_a["partial"]["client"] == "ACME"
    assert rec_b is not None and rec_b["partial"]["client"] == "BETA"

    # Clearing one leaves the other intact.
    timelog._save_pending("acct", src_a, None)
    assert timelog._load_pending("acct", src_a) is None
    assert timelog._load_pending("acct", src_b) is not None


def test_follow_up_resumes_only_its_correlated_record(monkeypatch, capsys, _isolated_state):
    """F3: a follow-up for conv-1/msg-1 resumes ITS record even though a
    different conversation also has a live pending record."""
    src_other = timelog.Source("whatsapp", "conv-OTHER", "msg-OTHER")
    timelog._save_pending(
        "testacct",
        src_other,
        timelog._new_pending(src_other, {"client": "OTHER"}, "client"),
    )
    src_mine = timelog.Source("whatsapp", "conv-1", "msg-1")
    partial = {"hours": 2.5, "description": "onboarding prep", "date": "today"}
    timelog._save_pending("testacct", src_mine, timelog._new_pending(src_mine, partial, "client"))

    _stub_list_tabs(monkeypatch, ["ACME"])
    _stub_append_row_ok(monkeypatch)

    code, result = _run(monkeypatch, ["--confirm-client", "ACME"] + BASE_ARGS, capsys)
    assert code == 0
    assert result["status"] == "logged"
    # The OTHER conversation's pending record is untouched.
    assert timelog._load_pending("testacct", src_other) is not None


def test_nonce_field_removed_from_pending_record():
    """F3: the dead `nonce` field is gone (main never echoed it); correlation
    is by source_key + TTL, documented in the module."""
    source = timelog.Source("whatsapp", "conv-1", "msg-1")
    rec = timelog._new_pending(source, {"client": "ACME"}, "client")
    assert "nonce" not in rec


# --------------------------------------------------------------------------- #
# F4 — corrected/deleted relayed ONLY on sheets_helper confirmation
# --------------------------------------------------------------------------- #


def test_corrected_only_when_update_confirms(monkeypatch, capsys):
    """F4: if sheets_helper's update-last read-back fails (raises), timelog
    returns `error`, never `corrected`."""
    _seed_ledger_entry("testacct", tab="ACME", row_index=5, hours=2.5)

    def _update_fails(tab, row, values, account):
        raise timelog.SheetsOpError("update not confirmed: read-back mismatch")

    monkeypatch.setattr(timelog, "_sh_update_last", _update_fails)

    code, result = _run(monkeypatch, ["--correct", "--hours", "3"] + BASE_ARGS, capsys)
    assert code == 0
    assert result["status"] == "error"


def test_deleted_only_when_delete_confirms(monkeypatch, capsys):
    """F4: if sheets_helper's delete read-back fails (raises), timelog returns
    `error`, never `deleted`; the ledger entry is preserved."""
    _seed_ledger_entry("testacct", tab="ACME", row_index=5)

    def _delete_fails(tab, row, account, entry_id=None):
        raise timelog.SheetsOpError("delete not confirmed: target still present")

    monkeypatch.setattr(timelog, "_sh_delete_last", _delete_fails)

    code, result = _run(monkeypatch, ["--delete-last"] + BASE_ARGS, capsys)
    assert code == 0
    assert result["status"] == "error"
    assert len(timelog._load_ledger("testacct")) == 1


def test_delete_passes_entry_id_for_read_back(monkeypatch, capsys):
    """F4: timelog forwards the ledger row's entry_id to sheets_helper so the
    delete can be read-back-confirmed."""
    _seed_ledger_entry("testacct", tab="ACME", row_index=5)
    ledger = timelog._load_ledger("testacct")
    expected_eid = ledger[0]["entry_id"]
    passed: dict[str, Any] = {}

    def _fake_delete(tab, row, account, entry_id=None):
        passed["entry_id"] = entry_id

    monkeypatch.setattr(timelog, "_sh_delete_last", _fake_delete)

    code, result = _run(monkeypatch, ["--delete-last"] + BASE_ARGS, capsys)
    assert code == 0
    assert result["status"] == "deleted"
    assert passed["entry_id"] == expected_eid


# --------------------------------------------------------------------------- #
# F7 — shared per-account lock serializes state mutations
# --------------------------------------------------------------------------- #


def test_account_lock_serializes_concurrent_ledger_appends(_isolated_state, monkeypatch):
    """F7: two concurrent processes each appending a ledger record must not
    lose one another's write. We simulate the race by making the FIRST holder
    of the lock spawn a subprocess that also appends while the parent is inside
    the critical section — the flock forces the child to wait, so BOTH records
    survive.

    Simpler, deterministic proxy: interleave two _append_ledger_record calls
    that both read the same starting state; without the lock the second would
    clobber the first. With the lock (held for the whole read-modify-write)
    both land. We assert both records are present after two appends.
    """
    src1 = timelog.Source("whatsapp", "c1", "m1")
    src2 = timelog.Source("whatsapp", "c2", "m2")
    timelog._append_ledger_record(
        "acct", entry_id="e1", source=src1, tab="ACME", row_index=1, entry={"entry_id": "e1"}
    )
    timelog._append_ledger_record(
        "acct", entry_id="e2", source=src2, tab="BETA", row_index=2, entry={"entry_id": "e2"}
    )
    ledger = timelog._load_ledger("acct")
    entry_ids = {r["entry_id"] for r in ledger}
    assert entry_ids == {"e1", "e2"}


def test_account_lock_is_exclusive_across_processes(_isolated_state):
    """F7: the per-account lock is a real exclusive flock — a second attempt to
    acquire it (non-blocking) while it's held fails, proving mutual exclusion
    over the whole transaction, not just the atomic temp-file write."""
    import fcntl as _fcntl

    account = "lockacct"
    with timelog._account_lock(account):
        # While the context holds LOCK_EX, an independent non-blocking attempt
        # on the same lock file must fail (BlockingIOError / OSError).
        fd = os.open(str(timelog._lock_path(account)), os.O_WRONLY | os.O_CREAT, 0o600)
        try:
            with pytest.raises(OSError):
                _fcntl.flock(fd, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
        finally:
            os.close(fd)
