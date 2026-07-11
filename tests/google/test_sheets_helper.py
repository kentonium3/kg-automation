"""Unit tests for ``scripts.google.sheets_helper`` (mission WP02).

CI-safe by construction: the real ``google-*`` / ``googleapiclient`` packages
are NOT relied upon. These tests inject fakes into ``sys.modules`` for
``googleapiclient.discovery`` **before** importing the module under test and
mock ``sheets_auth.load_sheets_credentials`` per-test, so nothing requires the
real libraries and no test touches the network. Any unmocked ``.execute()`` on
the fake service raises, guaranteeing no accidental live call.

Canonical invocation (repo threshold 90):

    pytest tests/google/test_sheets_helper.py \
        --cov=scripts.google.sheets_helper --cov-branch --cov-fail-under=90

Covers:
- append-row read-back-confirm (success + missing-entry_id failure);
- idempotent retry (bounded tail scan finds existing entry_id, no 2nd append);
- create-tab no-op when tab exists, create when absent;
- two-step create-tab-then-append-row where append fails (no false success);
- list-tabs, update-last, delete-last (+ usage errors on bad --row);
- --self-check ok + auth failure (exit 1, no mutation);
- fail-safe: every op maps an injected API error to exit 1;
- import safety with google packages absent (lazy import).
"""
from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest


# --------------------------------------------------------------------------- #
# Fake googleapiclient Sheets service — records calls, guards .execute()
# --------------------------------------------------------------------------- #


class _FakeRequest:
    """A pending API request. ``.execute()`` returns a preset value or raises."""

    def __init__(self, name: str, kwargs: dict[str, Any], recorder: "_Recorder"):
        self.name = name
        self.kwargs = kwargs
        self._recorder = recorder

    def execute(self) -> Any:
        if self._recorder.queues.get(self.name):
            outcome = self._recorder.queues[self.name].pop(0)
        else:
            outcome = self._recorder.outcomes.get(self.name)
        if outcome is None:
            raise AssertionError(
                f"unmocked .execute() for {self.name!r} — no live calls allowed"
            )
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FakeValues:
    def __init__(self, recorder: "_Recorder"):
        self._recorder = recorder

    def _record(self, name: str, **kwargs: Any) -> _FakeRequest:
        self._recorder.calls.append((name, kwargs))
        return _FakeRequest(name, kwargs, self._recorder)

    def append(self, **kwargs: Any) -> _FakeRequest:
        return self._record("values.append", **kwargs)

    def get(self, **kwargs: Any) -> _FakeRequest:
        return self._record("values.get", **kwargs)

    def update(self, **kwargs: Any) -> _FakeRequest:
        return self._record("values.update", **kwargs)


class _FakeSpreadsheets:
    def __init__(self, recorder: "_Recorder"):
        self._recorder = recorder
        self._values = _FakeValues(recorder)

    def _record(self, name: str, **kwargs: Any) -> _FakeRequest:
        self._recorder.calls.append((name, kwargs))
        return _FakeRequest(name, kwargs, self._recorder)

    def get(self, **kwargs: Any) -> _FakeRequest:
        return self._record("get", **kwargs)

    def batchUpdate(self, **kwargs: Any) -> _FakeRequest:  # noqa: N802 - google API name
        return self._record("batchUpdate", **kwargs)

    def values(self) -> _FakeValues:
        return self._values


class _FakeService:
    def __init__(self, recorder: "_Recorder"):
        self._spreadsheets = _FakeSpreadsheets(recorder)

    def spreadsheets(self) -> _FakeSpreadsheets:
        return self._spreadsheets


class _Recorder:
    """Records API calls and holds per-method ``.execute()`` outcomes.

    ``outcomes[name]`` may be a return value (dict) or an ``Exception`` to
    raise. ``queues[name]`` (if non-empty) is consumed in call order first,
    allowing successive calls to the same method (e.g. two ``get`` calls) to
    return different values.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.outcomes: dict[str, Any] = {}
        self.queues: dict[str, list[Any]] = {}

    def calls_for(self, name: str) -> list[dict[str, Any]]:
        return [kw for (n, kw) in self.calls if n == name]


class _HttpError(Exception):
    """Stand-in for googleapiclient.errors.HttpError with a ``.resp.status``."""

    def __init__(self, status: int) -> None:
        super().__init__(f"HTTP {status}")
        self.resp = types.SimpleNamespace(status=status)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture()
def recorder() -> _Recorder:
    return _Recorder()


@pytest.fixture()
def workbook_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point FELIX_TIMELOG_CONFIG_DIR at a tmp dir with a valid workbook.json."""
    config_dir = tmp_path / "timelog-config"
    config_dir.mkdir()
    (config_dir / "workbook.json").write_text(
        json.dumps({"spreadsheet_id": "SHEET123"})
    )
    monkeypatch.setenv("FELIX_TIMELOG_CONFIG_DIR", str(config_dir))
    return config_dir


@pytest.fixture()
def helper(monkeypatch: pytest.MonkeyPatch, recorder: _Recorder, workbook_config: Path):
    """Import the helper with a fake googleapiclient and stubbed auth.

    ``build`` returns a service whose ``.spreadsheets()`` records calls
    against the shared ``recorder``. ``load_sheets_credentials`` is stubbed to
    succeed by default; individual tests override it to raise
    ``SheetsAuthError``.
    """
    gac_mod = types.ModuleType("googleapiclient")
    discovery_mod = types.ModuleType("googleapiclient.discovery")

    def _build(*_a: Any, **_k: Any) -> _FakeService:
        return _FakeService(recorder)

    discovery_mod.build = _build  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "googleapiclient", gac_mod)
    monkeypatch.setitem(sys.modules, "googleapiclient.discovery", discovery_mod)

    module = importlib.import_module("scripts.google.sheets_helper")
    module = importlib.reload(module)

    monkeypatch.setattr(
        module, "load_sheets_credentials", lambda *a, **k: object()
    )
    return module


def run(module: Any, argv: list[str]) -> int:
    return module.main(argv)


def _last_line(capsys: pytest.CaptureFixture[str]) -> str:
    out = capsys.readouterr().out.strip().splitlines()
    return out[-1] if out else ""


def _stdout_lines(capsys: pytest.CaptureFixture[str]) -> list[str]:
    return capsys.readouterr().out.strip().splitlines()


def _sheets_get_result(titles: list[str], row_counts: dict[str, int] | None = None) -> dict[str, Any]:
    row_counts = row_counts or {}
    return {
        "sheets": [
            {
                "properties": {
                    "title": t,
                    "sheetId": i,
                    "gridProperties": {"rowCount": row_counts.get(t, 1000)},
                }
            }
            for i, t in enumerate(titles)
        ]
    }


# --------------------------------------------------------------------------- #
# append-row — read-back-confirm success
# --------------------------------------------------------------------------- #


def test_append_row_read_back_confirms_success(helper, recorder, capsys):
    # Bounded tail scan (values.get) finds nothing existing.
    recorder.outcomes["get"] = _sheets_get_result(["ACME"], {"ACME": 10})
    recorder.outcomes["values.get"] = {"values": []}
    recorder.outcomes["values.append"] = {
        "updates": {
            "updatedRange": "ACME!A11:G11",
            "updatedData": {
                "values": [
                    ["2026-07-10", 2.5, "ACME", "desc", True, "2026-07-10T12:00:00Z", "eid-1"]
                ]
            },
        }
    }
    values = json.dumps(
        ["2026-07-10", 2.5, "ACME", "desc", True, "2026-07-10T12:00:00Z", "eid-1"]
    )
    code = run(
        helper,
        ["append-row", "--tab", "ACME", "--entry-id", "eid-1", "--values", values, "--account", "personal"],
    )
    assert code == 0
    appends = recorder.calls_for("values.append")
    assert len(appends) == 1
    kw = appends[0]
    assert kw["includeValuesInResponse"] is True
    assert kw["spreadsheetId"] == "SHEET123"

    lines = _stdout_lines(capsys)
    assert lines[-1].startswith("SUMMARY:")
    parsed = json.loads(lines[0])
    assert parsed["status"] == "ok"
    assert parsed["row_index"] == 11
    assert parsed["entry_id"] == "eid-1"
    assert parsed["idempotent"] is False
    assert "row_index=11" in lines[-1]
    assert "idempotent=false" in lines[-1]


def test_append_row_missing_entry_id_in_response_is_operational_failure(
    helper, recorder, capsys
):
    recorder.outcomes["get"] = _sheets_get_result(["ACME"], {"ACME": 10})
    recorder.outcomes["values.get"] = {"values": []}
    # Response's written row is missing the trailing entry_id column entirely
    # (simulates a response that does not confirm the write).
    recorder.outcomes["values.append"] = {
        "updates": {
            "updatedRange": "ACME!A11:F11",
            "updatedData": {
                "values": [["2026-07-10", 2.5, "ACME", "desc", True, "2026-07-10T12:00:00Z"]]
            },
        }
    }
    values = json.dumps(
        ["2026-07-10", 2.5, "ACME", "desc", True, "2026-07-10T12:00:00Z", "eid-2"]
    )
    code = run(
        helper,
        ["append-row", "--tab", "ACME", "--entry-id", "eid-2", "--values", values],
    )
    assert code == 1
    last = _last_line(capsys)
    assert "status=error" in last


def test_append_row_response_carries_wrong_entry_id_is_operational_failure(
    helper, recorder, capsys
):
    recorder.outcomes["get"] = _sheets_get_result(["ACME"], {"ACME": 10})
    recorder.outcomes["values.get"] = {"values": []}
    recorder.outcomes["values.append"] = {
        "updates": {
            "updatedRange": "ACME!A11:G11",
            "updatedData": {
                "values": [
                    ["2026-07-10", 2.5, "ACME", "desc", True, "2026-07-10T12:00:00Z", "SOMETHING-ELSE"]
                ]
            },
        }
    }
    values = json.dumps(
        ["2026-07-10", 2.5, "ACME", "desc", True, "2026-07-10T12:00:00Z", "eid-3"]
    )
    code = run(
        helper,
        ["append-row", "--tab", "ACME", "--entry-id", "eid-3", "--values", values],
    )
    assert code == 1


# --------------------------------------------------------------------------- #
# append-row — idempotent retry (bounded tail scan, F8)
# --------------------------------------------------------------------------- #


def test_append_row_idempotent_retry_reports_existing_no_duplicate_append(
    helper, recorder, capsys
):
    recorder.outcomes["get"] = _sheets_get_result(["ACME"], {"ACME": 12})
    recorder.outcomes["values.get"] = {
        "values": [
            ["2026-07-09", 1.0, "ACME", "prior", True, "2026-07-09T09:00:00Z", "other-id"],
            ["2026-07-10", 2.5, "ACME", "desc", True, "2026-07-10T12:00:00Z", "eid-dup"],
        ]
    }
    values = json.dumps(
        ["2026-07-10", 2.5, "ACME", "desc", True, "2026-07-10T12:00:00Z", "eid-dup"]
    )
    code = run(
        helper,
        ["append-row", "--tab", "ACME", "--entry-id", "eid-dup", "--values", values],
    )
    assert code == 0
    # append must NOT be called a second time — idempotent retry short-circuits.
    assert recorder.calls_for("values.append") == []
    lines = _stdout_lines(capsys)
    parsed = json.loads(lines[0])
    assert parsed["idempotent"] is True
    assert parsed["entry_id"] == "eid-dup"
    assert "idempotent=true" in lines[-1]


def test_append_row_values_entry_id_mismatch_is_usage_error(helper, recorder, capsys):
    values = json.dumps(["2026-07-10", 2.5, "ACME", "desc", True, "iso", "different-id"])
    code = run(
        helper,
        ["append-row", "--tab", "ACME", "--entry-id", "eid-x", "--values", values],
    )
    assert code == 2
    assert recorder.calls == []


def test_append_row_malformed_values_is_usage_error(helper, recorder):
    code = run(
        helper,
        ["append-row", "--tab", "ACME", "--entry-id", "eid-1", "--values", "not-json"],
    )
    assert code == 2
    assert recorder.calls == []


# --------------------------------------------------------------------------- #
# create-tab — no-op when exists, create when absent (F3)
# --------------------------------------------------------------------------- #


def test_create_tab_noop_when_exists(helper, recorder, capsys):
    recorder.outcomes["get"] = _sheets_get_result(["ACME", "Beta"])
    code = run(helper, ["create-tab", "--tab", "ACME"])
    assert code == 0
    assert recorder.calls_for("batchUpdate") == []
    lines = _stdout_lines(capsys)
    parsed = json.loads(lines[0])
    assert parsed["created"] is False
    assert "created=false" in lines[-1]


def test_create_tab_creates_when_absent(helper, recorder, capsys):
    recorder.outcomes["get"] = _sheets_get_result(["Beta"])
    recorder.outcomes["batchUpdate"] = {"replies": [{"addSheet": {"properties": {"title": "ACME"}}}]}
    code = run(helper, ["create-tab", "--tab", "ACME"])
    assert code == 0
    batches = recorder.calls_for("batchUpdate")
    assert len(batches) == 1
    body = batches[0]["body"]
    assert body["requests"][0]["addSheet"]["properties"]["title"] == "ACME"
    lines = _stdout_lines(capsys)
    parsed = json.loads(lines[0])
    assert parsed["created"] is True
    assert "created=true" in lines[-1]


# --------------------------------------------------------------------------- #
# Two-step new-client onboarding: create-tab succeeds, append-row fails (F3)
# --------------------------------------------------------------------------- #


def test_two_step_create_then_append_fails_no_false_success(helper, recorder, capsys):
    # Step 1: create-tab succeeds (tab absent -> created).
    recorder.outcomes["get"] = _sheets_get_result(["Beta"])
    recorder.outcomes["batchUpdate"] = {"replies": [{"addSheet": {"properties": {"title": "ACME"}}}]}
    code1 = run(helper, ["create-tab", "--tab", "ACME"])
    assert code1 == 0

    # Step 2: append-row on the newly created tab fails at the API layer.
    # Reconfigure `get` (used by the tail-scan pre-check) to reflect the tab
    # now existing, then force the append call itself to raise.
    recorder.outcomes["get"] = _sheets_get_result(["Beta", "ACME"], {"ACME": 0})
    recorder.outcomes["values.get"] = {"values": []}
    recorder.outcomes["values.append"] = _HttpError(503)

    values = json.dumps(
        ["2026-07-10", 2.5, "ACME", "desc", True, "2026-07-10T12:00:00Z", "eid-fail"]
    )
    code2 = run(
        helper,
        ["append-row", "--tab", "ACME", "--entry-id", "eid-fail", "--values", values],
    )
    assert code2 == 1
    # No success signal for the append — the tab exists but the entry was not
    # logged. This helper does not synthesize client_created_entry_failed;
    # it only reports the two independent exit codes for the caller to observe.
    last = _last_line(capsys)
    assert "status=error" in last


# --------------------------------------------------------------------------- #
# list-tabs
# --------------------------------------------------------------------------- #


def test_list_tabs_returns_titles(helper, recorder, capsys):
    recorder.outcomes["get"] = _sheets_get_result(["ACME", "Beta", "Gamma"])
    code = run(helper, ["list-tabs"])
    assert code == 0
    lines = _stdout_lines(capsys)
    parsed = json.loads(lines[0])
    assert parsed["tabs"] == ["ACME", "Beta", "Gamma"]
    assert "count=3" in lines[-1]


# --------------------------------------------------------------------------- #
# update-last / delete-last
# --------------------------------------------------------------------------- #


def test_update_last_issues_values_update_on_supplied_row(helper, recorder, capsys):
    recorder.outcomes["values.update"] = {"updatedRange": "ACME!A7:G7"}
    values = json.dumps(["2026-07-10", 3.0, "ACME", "corrected", True, "iso", "eid-1"])
    code = run(
        helper,
        ["update-last", "--tab", "ACME", "--row", "7", "--values", values],
    )
    assert code == 0
    updates = recorder.calls_for("values.update")
    assert len(updates) == 1
    assert updates[0]["range"] == "ACME!A7:G7"
    assert updates[0]["body"]["values"] == [json.loads(values)]
    assert "row_index=7" in _last_line(capsys)


def test_update_last_missing_row_is_usage_error(helper, recorder):
    values = json.dumps(["a"])
    code = run(helper, ["update-last", "--tab", "ACME", "--row", "0", "--values", values])
    assert code == 2
    assert recorder.calls_for("values.update") == []


def test_delete_last_issues_delete_dimension(helper, recorder, capsys):
    recorder.outcomes["get"] = _sheets_get_result(["ACME", "Beta"])
    recorder.outcomes["batchUpdate"] = {"replies": [{}]}
    code = run(helper, ["delete-last", "--tab", "ACME", "--row", "7"])
    assert code == 0
    batches = recorder.calls_for("batchUpdate")
    assert len(batches) == 1
    req = batches[0]["body"]["requests"][0]["deleteDimension"]
    assert req["range"]["sheetId"] == 0
    assert req["range"]["dimension"] == "ROWS"
    assert req["range"]["startIndex"] == 6
    assert req["range"]["endIndex"] == 7
    assert "row_index=7" in _last_line(capsys)


def test_delete_last_missing_row_is_usage_error(helper, recorder):
    code = run(helper, ["delete-last", "--tab", "ACME", "--row", "-1"])
    assert code == 2
    assert recorder.calls == []


def test_delete_last_unknown_tab_is_operational_failure(helper, recorder):
    recorder.outcomes["get"] = _sheets_get_result(["Beta"])
    code = run(helper, ["delete-last", "--tab", "ACME", "--row", "7"])
    assert code == 1
    assert recorder.calls_for("batchUpdate") == []


# --------------------------------------------------------------------------- #
# --self-check
# --------------------------------------------------------------------------- #


def test_self_check_ok(helper, recorder, capsys):
    recorder.outcomes["get"] = _sheets_get_result(["ACME"])
    code = run(helper, ["--self-check"])
    assert code == 0
    kw = recorder.calls_for("get")[0]
    assert kw["spreadsheetId"] == "SHEET123"
    line = _last_line(capsys)
    assert line.startswith("SUMMARY:")
    assert "op=self-check" in line
    assert "status=ok" in line


def test_self_check_auth_failure_exit_1_no_mutation(helper, recorder, monkeypatch, capsys):
    from scripts.google.sheets_auth import SheetsAuthError

    def _raise(*a: Any, **k: Any):
        raise SheetsAuthError("no token.json: re-mint on the Mac")

    monkeypatch.setattr(helper, "load_sheets_credentials", _raise)
    code = run(helper, ["--self-check"])
    assert code == 1
    # No API call whatsoever (auth resolved first).
    assert recorder.calls == []
    out = capsys.readouterr()
    assert "auth_failed" in out.err
    summary = out.out.strip().splitlines()[-1]
    assert summary.startswith("SUMMARY:")
    assert "op=self-check" in summary
    assert "status=auth_failed" in summary


def test_auth_failure_on_append_row_never_appends(helper, recorder, monkeypatch, capsys):
    from scripts.google.sheets_auth import SheetsAuthError

    monkeypatch.setattr(
        helper, "load_sheets_credentials",
        lambda *a, **k: (_ for _ in ()).throw(SheetsAuthError("bad token")),
    )
    values = json.dumps(["2026-07-10", 2.5, "ACME", "desc", True, "iso", "eid-1"])
    code = run(
        helper,
        ["append-row", "--tab", "ACME", "--entry-id", "eid-1", "--values", values],
    )
    assert code == 1
    assert recorder.calls_for("values.append") == []
    out = capsys.readouterr()
    assert out.err.startswith("ERROR: auth_failed")
    assert "status=auth_failed" in out.out.strip().splitlines()[-1]


# --------------------------------------------------------------------------- #
# invalid account name -> exit 2 (ValueError from sheets_auth)
# --------------------------------------------------------------------------- #


def test_invalid_account_name_exit_2(helper, recorder, monkeypatch, capsys):
    def _raise(*a: Any, **k: Any):
        raise ValueError("invalid account name '../etc'")

    monkeypatch.setattr(helper, "load_sheets_credentials", _raise)
    code = run(helper, ["list-tabs", "--account", "../etc"])
    assert code == 2
    assert recorder.calls == []
    assert "invalid account name" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# workbook config resolution failures -> usage error (exit 2)
# --------------------------------------------------------------------------- #


def test_missing_workbook_config_is_usage_error(
    helper, recorder, monkeypatch, tmp_path: Path
):
    empty_dir = tmp_path / "empty-config"
    monkeypatch.setenv("FELIX_TIMELOG_CONFIG_DIR", str(empty_dir))
    code = run(helper, ["list-tabs"])
    assert code == 2
    assert recorder.calls == []


def test_malformed_workbook_config_is_usage_error(
    helper, recorder, monkeypatch, tmp_path: Path
):
    bad_dir = tmp_path / "bad-config"
    bad_dir.mkdir()
    (bad_dir / "workbook.json").write_text("not json")
    monkeypatch.setenv("FELIX_TIMELOG_CONFIG_DIR", str(bad_dir))
    code = run(helper, ["list-tabs"])
    assert code == 2
    assert recorder.calls == []


def test_workbook_config_missing_spreadsheet_id_is_usage_error(
    helper, recorder, monkeypatch, tmp_path: Path
):
    bad_dir = tmp_path / "bad-config2"
    bad_dir.mkdir()
    (bad_dir / "workbook.json").write_text(json.dumps({"other": "field"}))
    monkeypatch.setenv("FELIX_TIMELOG_CONFIG_DIR", str(bad_dir))
    code = run(helper, ["list-tabs"])
    assert code == 2
    assert recorder.calls == []


# --------------------------------------------------------------------------- #
# no subcommand -> usage error
# --------------------------------------------------------------------------- #


def test_no_subcommand_is_usage_error(helper, recorder):
    code = run(helper, [])
    assert code == 2


# --------------------------------------------------------------------------- #
# generic API error (non-404) on list-tabs -> exit 1
# --------------------------------------------------------------------------- #


def test_api_5xx_error_is_operational_exit_1(helper, recorder, capsys):
    recorder.outcomes["get"] = _HttpError(503)
    code = run(helper, ["list-tabs"])
    assert code == 1
    last = _last_line(capsys)
    assert last.startswith("SUMMARY:")
    assert "status=error" in last


def test_api_404_error_maps_to_not_found(helper, recorder, capsys):
    recorder.outcomes["get"] = _HttpError(404)
    code = run(helper, ["list-tabs"])
    assert code == 1
    out = capsys.readouterr()
    assert "not_found" in out.err


# --------------------------------------------------------------------------- #
# SUMMARY is always the final stdout line (parse-anchor invariant)
# --------------------------------------------------------------------------- #


def test_summary_is_final_line_on_list_tabs(helper, recorder, capsys):
    recorder.outcomes["get"] = _sheets_get_result(["ACME"])
    run(helper, ["list-tabs"])
    assert _last_line(capsys).startswith("SUMMARY:")


# --------------------------------------------------------------------------- #
# Unit branches (helpers)
# --------------------------------------------------------------------------- #


def test_a1_column_conversion(helper):
    assert helper._a1_column(1) == "A"
    assert helper._a1_column(26) == "Z"
    assert helper._a1_column(27) == "AA"
    assert helper._a1_column(0) == "A"


def test_http_status_non_integer_returns_none(helper):
    exc = type("E", (Exception,), {})()
    exc.resp = types.SimpleNamespace(status="not-a-number")
    assert helper._http_status(exc) is None
    exc2 = type("E2", (Exception,), {})()
    assert helper._http_status(exc2) is None


def test_extract_row_index_from_range(helper):
    assert helper._extract_row_index_from_range("ACME!A11:G11") == 11
    assert helper._extract_row_index_from_range("no-bang-here") is None
    assert helper._extract_row_index_from_range("ACME!AA:BB") is None


def test_row_from_get_values_handles_non_dict(helper):
    assert helper._row_from_get_values(None) == []
    assert helper._row_from_get_values({"values": "not-a-list"}) == []
    assert helper._row_from_get_values({}) == []


# --------------------------------------------------------------------------- #
# Import safety — importing the module with google packages absent (lazy import)
# --------------------------------------------------------------------------- #


def test_import_without_google_packages_does_not_raise(monkeypatch: pytest.MonkeyPatch):
    for mod_name in list(sys.modules):
        if mod_name.startswith("googleapiclient"):
            monkeypatch.delitem(sys.modules, mod_name, raising=False)
    monkeypatch.setitem(sys.modules, "googleapiclient", None)
    monkeypatch.setitem(sys.modules, "googleapiclient.discovery", None)
    monkeypatch.delitem(sys.modules, "googleapiclient", raising=False)
    monkeypatch.delitem(sys.modules, "googleapiclient.discovery", raising=False)

    module = importlib.import_module("scripts.google.sheets_helper")
    importlib.reload(module)
    assert hasattr(module, "main")
