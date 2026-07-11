"""Deterministic Google Sheets CLI for the Felix time-log helper (WP02).

This helper authenticates per-account (via WP01's
:mod:`scripts.google.sheets_auth`) and performs the mechanical Sheets ops for
the time-log feature — ``append-row`` / ``create-tab`` / ``list-tabs`` /
``update-last`` / ``delete-last`` plus a deploy ``--self-check`` — exactly per
``kitty-specs/felix-time-logging-01KX79HT/contracts/timelog-cli.md`` §C2
(authoritative for flags, exit codes, read-back/idempotency behavior) and
``data-model.md`` (``TimeEntry`` row shape, append idempotency F8).

Conforms to ``docs/design/helper-script-conventions.md``: argparse
subcommands, long-form flags, meaningful exit codes, a final ``SUMMARY:`` line
on stdout, ``ERROR:`` to stderr.

Exit-code contract (authoritative, mirrors ``calendar_helper.py``):

- ``0`` — success (mutation, if any, completed and read-back-confirmed).
- ``1`` — operational / Sheets API error, or a read-back that fails to confirm
  a write (never a partial/false success).
- ``2`` — usage error (bad/missing args, invalid ``--account``, malformed
  ``--values``/workbook config).

Auth failures from :mod:`scripts.google.sheets_auth` (:class:`SheetsAuthError`)
are mapped to exit ``1`` here — a bad-credentials path never masquerades as a
completed op.

**No LLM anywhere in this helper.** Pure Sheets API + argparse; all judgment
(client resolution, NL extraction) lives upstream in ``timelog.py``.

CI-safe imports: ``google-api-python-client`` is NOT in ``requirements.txt``
(it lives only in a dedicated office2 venv). All google imports are done
**lazily inside functions**, so importing this module never requires the
google packages; unit tests inject fakes via ``sys.modules``.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scripts.google.sheets_auth import (
    DEFAULT_ACCOUNT,
    SCOPES_DEFAULT,
    SheetsAuthError,
    load_sheets_credentials,
)

if TYPE_CHECKING:  # pragma: no cover - typing only, no runtime import
    from collections.abc import Sequence

__all__ = ["main"]

# Exit codes (contract — mirrors calendar_helper.py's 0/1/2 convention).
EXIT_OK = 0
EXIT_OPERATIONAL = 1
EXIT_USAGE = 2

# Trailing column that carries the append-idempotency key (F8). The caller
# passes it as the last element of --values; this helper never invents it.
ENTRY_ID_COLUMN_INDEX = -1

# The Felix time-log header row written into every client tab (F6). A freshly
# created tab gets this as row 1 so the first data entry lands at row 2 and the
# columns are self-describing. Column order matches ``timelog._row_values``.
HEADER_ROW: tuple[str, ...] = (
    "date",
    "hours",
    "client",
    "description",
    "billable",
    "logged_at",
    "entry_id",
)

# Bounded lookback (number of rows scanned from the tail) when de-duping an
# append retry by entry_id (F8). Mirrors calendar_helper's
# IDEMPOTENCY_LOOKBACK bounded-scan pattern.
IDEMPOTENCY_LOOKBACK = 250

# Default workbook-id config location (override via FELIX_TIMELOG_CONFIG_DIR
# for test isolation and alternate staging).
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "felix" / "timelog"
WORKBOOK_CONFIG_FILENAME = "workbook.json"


class HelperError(Exception):
    """Operational/usage error carrying the exit code the CLI should return.

    ``exit_code`` is ``1`` (operational) or ``2`` (usage). Auth failures
    (:class:`SheetsAuthError`) are handled separately in :func:`main` and also
    mapped to exit ``1`` so a bad-credentials path can never be reported as a
    completed action.
    """

    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _usage_error(message: str) -> HelperError:
    return HelperError(message, EXIT_USAGE)


def _operational_error(message: str) -> HelperError:
    return HelperError(message, EXIT_OPERATIONAL)


# --------------------------------------------------------------------------- #
# stdout / stderr discipline
# --------------------------------------------------------------------------- #


def _emit_json(obj: dict[str, Any]) -> None:
    """Print a JSON result object on a stdout line *preceding* the SUMMARY.

    JSON never comes after SUMMARY (agent parse anchor).
    """
    print(json.dumps(obj, sort_keys=True))


def _emit_summary(fields: dict[str, Any]) -> None:
    """Print the final ``SUMMARY:`` stdout line (always last).

    Fields are emitted in insertion order as ``key=value`` pairs.
    """
    parts = " ".join(f"{k}={v}" for k, v in fields.items())
    print(f"SUMMARY: {parts}")


def _emit_error(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)


# --------------------------------------------------------------------------- #
# Workbook-id config resolution
# --------------------------------------------------------------------------- #


def _config_dir() -> Path:
    """Resolve the config home, honoring ``FELIX_TIMELOG_CONFIG_DIR``.

    Read at call time (not import time) so tests can point it at a tmp dir.
    """
    override = os.environ.get("FELIX_TIMELOG_CONFIG_DIR")
    return Path(override) if override else DEFAULT_CONFIG_DIR


def _workbook_config_path() -> Path:
    return _config_dir() / WORKBOOK_CONFIG_FILENAME


def _resolve_spreadsheet_id() -> str:
    """Load ``spreadsheet_id`` from the workbook config file.

    :raises HelperError: (usage, exit 2) if the file is missing, unreadable,
        not valid JSON, or lacks a non-empty ``spreadsheet_id`` string.
    """
    path = _workbook_config_path()
    if not path.exists():
        raise _usage_error(
            f"workbook config not found at {path}; run the one-time bootstrap "
            "to create it (see contract C2 / IC-05)"
        )
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        raise _usage_error(f"cannot read workbook config {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise _usage_error(f"workbook config {path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise _usage_error(f"workbook config {path} must contain a JSON object")
    spreadsheet_id = data.get("spreadsheet_id")
    if not isinstance(spreadsheet_id, str) or not spreadsheet_id:
        raise _usage_error(
            f"workbook config {path} missing a non-empty 'spreadsheet_id' string"
        )
    return spreadsheet_id


# --------------------------------------------------------------------------- #
# Google service construction (lazy import)
# --------------------------------------------------------------------------- #


def _build_service(account: str) -> Any:
    """Load credentials and build the Sheets v4 service.

    Auth is resolved here, before any mutation, so an auth failure
    short-circuits before any read/append/batchUpdate call.

    :raises SheetsAuthError: on any auth failure (mapped to exit 1 by main).
    :raises HelperError: if the google client library is unavailable (exit 1).
    """
    creds = load_sheets_credentials(account, SCOPES_DEFAULT)
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:  # pragma: no cover - env-specific import guard
        raise _operational_error(
            "googleapiclient is not installed in this interpreter; run the "
            "Sheets helper under its dedicated venv"
        ) from exc
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def _quote_a1_title(title: str) -> str:
    """Return an A1-safe, quoted sheet-title prefix for a ``range=``/``ranges=``.

    Sheet titles containing spaces, punctuation, or apostrophes must be wrapped
    in single quotes in A1 notation, and any internal single quote doubled
    (``it's`` -> ``'it''s'``). Always quoting (even simple titles) is valid A1
    and closes the injection/mis-target surface (F5) uniformly — a tab named
    ``ACME`` becomes ``'ACME'`` and a tab named ``Q3 'Big' Co`` becomes
    ``'Q3 ''Big'' Co'``. Callers build ranges as ``f"{_quote_a1_title(tab)}!A1"``.
    """
    return "'" + title.replace("'", "''") + "'"


def _http_status(exc: Exception) -> int | None:
    """Best-effort extraction of an HTTP status from a googleapiclient error."""
    resp = getattr(exc, "resp", None)
    status = getattr(resp, "status", None)
    if status is None:
        return None
    try:
        return int(status)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return None


def _run_execute(request: Any) -> Any:
    """Execute a googleapiclient request, mapping API errors to HelperError.

    A ``404`` maps to a ``not_found`` operational error (exit 1); all other
    API errors are operational (exit 1) as well. The message never leaks
    secrets. Fail-safe: an error here always means "nothing (further) was
    written" from this helper's perspective — callers that already performed
    a prior successful mutation (e.g. create-tab before append-row) are
    responsible for surfacing the resulting partial state.
    """
    try:
        return request.execute()
    except HelperError:  # pragma: no cover - defensive: never raised by .execute()
        raise
    except Exception as exc:  # noqa: BLE001 - map any API/transport error to exit 1
        status = _http_status(exc)
        if status == 404:
            raise _operational_error("not_found") from exc
        raise _operational_error(
            f"sheets API error ({type(exc).__name__}: {exc})"
        ) from exc


# --------------------------------------------------------------------------- #
# list-tabs (also used internally by create-tab's no-op check)
# --------------------------------------------------------------------------- #


def _fetch_sheet_titles(service: Any, spreadsheet_id: str) -> list[str]:
    """Return the current tab (sheet) titles via a bounded ``spreadsheets().get``."""
    result = _run_execute(
        service.spreadsheets().get(spreadsheetId=spreadsheet_id)
    )
    sheets = result.get("sheets", []) if isinstance(result, dict) else []
    titles: list[str] = []
    for sheet in sheets:
        props = sheet.get("properties", {}) if isinstance(sheet, dict) else {}
        title = props.get("title")
        if isinstance(title, str):
            titles.append(title)
    return titles


def _cmd_list_tabs(service: Any, args: argparse.Namespace) -> int:
    spreadsheet_id = _resolve_spreadsheet_id()
    titles = _fetch_sheet_titles(service, spreadsheet_id)
    _emit_json({"status": "ok", "tabs": titles})
    _emit_summary(
        {"op": "list-tabs", "status": "ok", "count": len(titles), "account": args.account}
    )
    return EXIT_OK


# --------------------------------------------------------------------------- #
# create-tab (no-op if already present, F3)
# --------------------------------------------------------------------------- #


def _cmd_create_tab(service: Any, args: argparse.Namespace) -> int:
    spreadsheet_id = _resolve_spreadsheet_id()
    existing_titles = _fetch_sheet_titles(service, spreadsheet_id)

    if args.tab in existing_titles:
        # No-op (F3): retries of new-client onboarding must not error or
        # duplicate the tab.
        _emit_json({"status": "ok", "tab": args.tab, "created": False})
        _emit_summary(
            {
                "op": "create-tab",
                "status": "ok",
                "created": "false",
                "tab": args.tab,
                "account": args.account,
            }
        )
        return EXIT_OK

    _run_execute(
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {"addSheet": {"properties": {"title": args.tab}}}
                ]
            },
        )
    )
    # Write the Felix header row into the fresh tab (F6) so the first data entry
    # lands at row 2 and the columns are self-describing. RAW: header labels are
    # literal text, never formulas.
    _run_execute(
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{_quote_a1_title(args.tab)}!A1",
            valueInputOption="RAW",
            body={"values": [list(HEADER_ROW)]},
        )
    )
    _emit_json({"status": "ok", "tab": args.tab, "created": True})
    _emit_summary(
        {
            "op": "create-tab",
            "status": "ok",
            "created": "true",
            "tab": args.tab,
            "account": args.account,
        }
    )
    return EXIT_OK


# --------------------------------------------------------------------------- #
# append-row (read-back-confirm + idempotent retry, F8/NFR-002)
# --------------------------------------------------------------------------- #


def _parse_values(raw: str) -> list[Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _usage_error(f"--values is not valid JSON: {exc}") from exc
    if not isinstance(data, list) or not data:
        raise _usage_error("--values must be a non-empty JSON array")
    return data


def _row_from_get_values(values_result: dict[str, Any] | None) -> list[list[Any]]:
    if not isinstance(values_result, dict):
        return []
    rows = values_result.get("values", [])
    if not isinstance(rows, list):
        return []
    return rows


def _find_existing_row_by_entry_id(
    service: Any, spreadsheet_id: str, tab: str, entry_id: str
) -> tuple[int, list[Any]] | None:
    """Bounded tail scan for a row already carrying ``entry_id`` (F8).

    Returns ``(row_index, row_values)`` (1-based row index) if found, else
    ``None``. The scan is bounded to the most recent ``IDEMPOTENCY_LOOKBACK``
    rows so a very large tab still yields a stable, fast retry check.
    """
    # Determine the tab's current row count so we can request only the tail.
    meta = _run_execute(
        service.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            ranges=[_quote_a1_title(tab)],
            includeGridData=False,
        )
    )
    sheets = meta.get("sheets", []) if isinstance(meta, dict) else []
    row_count = 0
    for sheet in sheets:
        props = sheet.get("properties", {}) if isinstance(sheet, dict) else {}
        if props.get("title") == tab:
            grid_props = props.get("gridProperties", {})
            row_count = int(grid_props.get("rowCount", 0) or 0)
            break

    start_row = max(1, row_count - IDEMPOTENCY_LOOKBACK + 1)
    quoted = _quote_a1_title(tab)
    range_a1 = (
        f"{quoted}!A{start_row}:ZZ{row_count}"
        if row_count
        else f"{quoted}!A1:ZZ{IDEMPOTENCY_LOOKBACK}"
    )

    values_result = _run_execute(
        service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_a1,
        )
    )
    rows = _row_from_get_values(values_result)
    for offset, row in enumerate(rows):
        if not row:
            continue
        if str(row[ENTRY_ID_COLUMN_INDEX]) == entry_id:
            row_index = start_row + offset
            return row_index, row
    return None


def _extract_row_index_from_range(range_a1: str) -> int | None:
    """Parse the trailing row number out of an ``append`` response's ``updatedRange``.

    Format is like ``"Tab!A5:G5"`` — we want the row number of the first cell.
    """
    if "!" not in range_a1:
        return None
    _, cell_range = range_a1.split("!", 1)
    start_cell = cell_range.split(":", 1)[0]
    digits = "".join(ch for ch in start_cell if ch.isdigit())
    return int(digits) if digits else None


def _cmd_append_row(service: Any, args: argparse.Namespace) -> int:
    values = _parse_values(args.values)
    entry_id = args.entry_id
    if not entry_id:
        raise _usage_error("append-row requires --entry-id")
    if str(values[ENTRY_ID_COLUMN_INDEX]) != entry_id:
        raise _usage_error(
            "--values trailing column must equal --entry-id "
            f"(got {values[ENTRY_ID_COLUMN_INDEX]!r}, expected {entry_id!r})"
        )

    spreadsheet_id = _resolve_spreadsheet_id()

    # Idempotent retry (F8): bounded duplicate lookup by entry_id BEFORE
    # appending, so a retry after a transport error is stable.
    existing = _find_existing_row_by_entry_id(
        service, spreadsheet_id, args.tab, entry_id
    )
    if existing is not None:
        row_index, row_values = existing
        _emit_success_append(
            args, row_index=row_index, values=row_values, idempotent=True
        )
        return EXIT_OK

    append_result = _run_execute(
        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=f"{_quote_a1_title(args.tab)}!A1",
            # RAW (not USER_ENTERED): time-log values are DATA, never formulas.
            # A description like "=SUM(A:A)" or "-1h" must land as literal text,
            # not be evaluated by Sheets (F5 formula-injection defense).
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            includeValuesInResponse=True,
            body={"values": [values]},
        )
    )

    # Read-back-confirm (F8/NFR-002): never report success unless the API
    # response itself confirms the appended row carries its entry_id.
    updates = append_result.get("updates", {}) if isinstance(append_result, dict) else {}
    updated_range = updates.get("updatedRange", "") if isinstance(updates, dict) else ""
    written_rows = updates.get("updatedData", {}).get("values", []) if isinstance(updates, dict) else []

    if not written_rows or not written_rows[0]:
        raise _operational_error(
            "append not confirmed: response did not include includeValuesInResponse data"
        )
    written_row = written_rows[0]
    if str(written_row[ENTRY_ID_COLUMN_INDEX]) != entry_id:
        raise _operational_error(
            "append not confirmed: written row does not carry the expected entry_id "
            f"(expected {entry_id!r}, got {written_row[ENTRY_ID_COLUMN_INDEX]!r})"
        )

    row_index = _extract_row_index_from_range(updated_range)
    if row_index is None:
        raise _operational_error(
            "append not confirmed: could not determine row_index from updatedRange"
        )

    _emit_success_append(
        args, row_index=row_index, values=written_row, idempotent=False
    )
    return EXIT_OK


def _emit_success_append(
    args: argparse.Namespace, *, row_index: int, values: list[Any], idempotent: bool
) -> None:
    _emit_json(
        {
            "status": "ok",
            "tab": args.tab,
            "row_index": row_index,
            "entry_id": args.entry_id,
            "idempotent": idempotent,
            "values": values,
        }
    )
    _emit_summary(
        {
            "op": "append-row",
            "status": "ok",
            "idempotent": str(idempotent).lower(),
            "tab": args.tab,
            "row_index": row_index,
            "account": args.account,
        }
    )


# --------------------------------------------------------------------------- #
# update-last / delete-last (caller supplies the target row)
# --------------------------------------------------------------------------- #


def _cmd_update_last(service: Any, args: argparse.Namespace) -> int:
    if args.row is None or args.row < 1:
        raise _usage_error("update-last requires a positive integer --row")
    values = _parse_values(args.values)
    spreadsheet_id = _resolve_spreadsheet_id()

    last_col = _a1_column(len(values))
    range_a1 = f"{_quote_a1_title(args.tab)}!A{args.row}:{last_col}{args.row}"

    _run_execute(
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_a1,
            # RAW: a correction's values are DATA, not formulas (F5).
            valueInputOption="RAW",
            body={"values": [values]},
        )
    )
    # Read-back-confirm (F4): re-read the row and verify the entry_id/values
    # actually landed before reporting `ok`. An update that silently no-ops or
    # writes to the wrong place must never be reported as corrected.
    _confirm_update(service, spreadsheet_id, args.tab, args.row, values)
    _emit_json({"status": "ok", "tab": args.tab, "row_index": args.row})
    _emit_summary(
        {
            "op": "update-last",
            "status": "ok",
            "tab": args.tab,
            "row_index": args.row,
            "account": args.account,
        }
    )
    return EXIT_OK


def _a1_column(n: int) -> str:
    """Convert a 1-based column count to an A1 column letter (1 -> A, 27 -> AA)."""
    letters = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters or "A"


def _read_row_values(
    service: Any, spreadsheet_id: str, tab: str, row: int, ncols: int
) -> list[Any]:
    """Read back a single row's cell values via ``values().get`` (F4)."""
    last_col = _a1_column(ncols)
    range_a1 = f"{_quote_a1_title(tab)}!A{row}:{last_col}{row}"
    result = _run_execute(
        service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_a1,
        )
    )
    rows = _row_from_get_values(result)
    return rows[0] if rows else []


def _confirm_update(
    service: Any,
    spreadsheet_id: str,
    tab: str,
    row: int,
    expected: list[Any],
) -> None:
    """Verify an ``update-last`` actually landed (F4): read the row back and
    confirm the trailing ``entry_id`` matches. Raises an operational error
    (exit 1) if the read-back does not confirm — a correction is reported
    ``corrected`` only when API-confirmed, never optimistically.
    """
    read_back = _read_row_values(service, spreadsheet_id, tab, row, len(expected))
    if not read_back:
        raise _operational_error(
            "update not confirmed: row read-back was empty after update-last"
        )
    if str(read_back[ENTRY_ID_COLUMN_INDEX]) != str(expected[ENTRY_ID_COLUMN_INDEX]):
        raise _operational_error(
            "update not confirmed: read-back row does not carry the expected "
            f"entry_id (expected {expected[ENTRY_ID_COLUMN_INDEX]!r}, "
            f"got {read_back[ENTRY_ID_COLUMN_INDEX]!r})"
        )


def _confirm_delete(
    service: Any,
    spreadsheet_id: str,
    tab: str,
    row: int,
    expected_entry_id: str | None,
) -> None:
    """Verify a ``delete-last`` actually removed the target (F4).

    After a ``deleteDimension`` the row shifts up, so the *former* row index no
    longer holds the deleted entry_id. Read it back and confirm the expected
    entry_id is absent from that position. If the caller did not pass an
    expected entry_id (none available), a best-effort read still runs but only
    a present-and-matching id fails the confirmation.
    """
    if not expected_entry_id:
        return
    read_back = _read_row_values(
        service, spreadsheet_id, tab, row, len(HEADER_ROW)
    )
    if read_back and str(read_back[ENTRY_ID_COLUMN_INDEX]) == str(expected_entry_id):
        raise _operational_error(
            "delete not confirmed: target row still carries the expected "
            f"entry_id {expected_entry_id!r} after delete-last"
        )


def _sheet_id_for_tab(service: Any, spreadsheet_id: str, tab: str) -> int:
    result = _run_execute(
        service.spreadsheets().get(spreadsheetId=spreadsheet_id)
    )
    sheets = result.get("sheets", []) if isinstance(result, dict) else []
    for sheet in sheets:
        props = sheet.get("properties", {}) if isinstance(sheet, dict) else {}
        if props.get("title") == tab:
            sheet_id = props.get("sheetId")
            if isinstance(sheet_id, int):
                return sheet_id
    raise _operational_error(f"tab {tab!r} not found; cannot resolve sheetId")


def _cmd_delete_last(service: Any, args: argparse.Namespace) -> int:
    if args.row is None or args.row < 1:
        raise _usage_error("delete-last requires a positive integer --row")
    spreadsheet_id = _resolve_spreadsheet_id()
    sheet_id = _sheet_id_for_tab(service, spreadsheet_id, args.tab)

    # batchUpdate deleteDimension uses 0-based, end-exclusive indices.
    start_index = args.row - 1
    end_index = args.row

    _run_execute(
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "deleteDimension": {
                            "range": {
                                "sheetId": sheet_id,
                                "dimension": "ROWS",
                                "startIndex": start_index,
                                "endIndex": end_index,
                            }
                        }
                    }
                ]
            },
        )
    )
    # Read-back-confirm (F4): after the delete the row shifts up, so the target
    # index must NOT still carry the deleted entry_id. Only confirm ``deleted``
    # when API-verified.
    _confirm_delete(
        service, spreadsheet_id, args.tab, args.row, getattr(args, "entry_id", None)
    )
    _emit_json({"status": "ok", "tab": args.tab, "row_index": args.row})
    _emit_summary(
        {
            "op": "delete-last",
            "status": "ok",
            "tab": args.tab,
            "row_index": args.row,
            "account": args.account,
        }
    )
    return EXIT_OK


# --------------------------------------------------------------------------- #
# --self-check
# --------------------------------------------------------------------------- #


def _cmd_self_check(args: argparse.Namespace) -> int:
    """Deploy/preflight: refresh creds + a bounded ``spreadsheets().get``.

    Any auth/scope/refresh failure raises :class:`SheetsAuthError`, mapped by
    :func:`main` to exit 1. Never interactive.
    """
    service = _build_service(args.account)
    spreadsheet_id = _resolve_spreadsheet_id()
    _run_execute(
        service.spreadsheets().get(spreadsheetId=spreadsheet_id, includeGridData=False)
    )
    _emit_summary({"op": "self-check", "status": "ok", "account": args.account})
    return EXIT_OK


# --------------------------------------------------------------------------- #
# argument parsing
# --------------------------------------------------------------------------- #


def _add_common_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--account", default=DEFAULT_ACCOUNT)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sheets_helper",
        description="Deterministic Google Sheets CLI (Felix time-log helper).",
    )
    # Top-level --self-check (no subcommand). Common flags also live at the
    # top level so `--self-check --account X` parses without a subcommand.
    parser.add_argument("--self-check", dest="self_check", action="store_true")
    _add_common_flags(parser)

    sub = parser.add_subparsers(dest="command")

    p_append = sub.add_parser("append-row", help="Append one row to a client's tab")
    _add_common_flags(p_append)
    p_append.add_argument("--tab", required=True)
    p_append.add_argument("--entry-id", dest="entry_id", required=True)
    p_append.add_argument("--values", required=True)

    p_create = sub.add_parser("create-tab", help="Create a client tab (no-op if exists)")
    _add_common_flags(p_create)
    p_create.add_argument("--tab", required=True)

    p_list = sub.add_parser("list-tabs", help="List the workbook's tab titles")
    _add_common_flags(p_list)

    p_update = sub.add_parser("update-last", help="Overwrite a specific row")
    _add_common_flags(p_update)
    p_update.add_argument("--tab", required=True)
    p_update.add_argument("--row", type=int, required=True)
    p_update.add_argument("--values", required=True)

    p_delete = sub.add_parser("delete-last", help="Delete a specific row")
    _add_common_flags(p_delete)
    p_delete.add_argument("--tab", required=True)
    p_delete.add_argument("--row", type=int, required=True)
    # Optional: the entry_id the deleted row is expected to carry, so the
    # delete can be read-back-confirmed (F4). If omitted, delete-back-confirm
    # is skipped (best-effort).
    p_delete.add_argument("--entry-id", dest="entry_id", default=None)

    return parser


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #


def _dispatch(args: argparse.Namespace) -> int:
    """Run the resolved command. Auth is built lazily inside each path."""
    if args.self_check:
        return _cmd_self_check(args)

    if args.command == "append-row":
        service = _build_service(args.account)
        return _cmd_append_row(service, args)
    if args.command == "create-tab":
        service = _build_service(args.account)
        return _cmd_create_tab(service, args)
    if args.command == "list-tabs":
        service = _build_service(args.account)
        return _cmd_list_tabs(service, args)
    if args.command == "update-last":
        service = _build_service(args.account)
        return _cmd_update_last(service, args)
    if args.command == "delete-last":
        service = _build_service(args.account)
        return _cmd_delete_last(service, args)

    # No subcommand and no --self-check → usage error.
    raise _usage_error(
        "no subcommand given (expected append-row/create-tab/list-tabs/"
        "update-last/delete-last or --self-check)"
    )


def main(argv: "Sequence[str] | None" = None) -> int:
    """CLI entry point. Returns the process exit code (contract 0/1/2)."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        return _dispatch(args)
    except SheetsAuthError as exc:
        # Auth failure: never mutated (auth resolved before any read/append/
        # batchUpdate). Mapped to operational exit 1 per C2 (sheets_helper
        # keeps the calendar-helper 0/1/2 convention; there is no separate
        # auth exit code here).
        _emit_error(f"auth_failed {exc}")
        account = getattr(args, "account", DEFAULT_ACCOUNT)
        op = "self-check" if getattr(args, "self_check", False) else (args.command or "unknown")
        _emit_summary({"op": op, "status": "auth_failed", "account": account})
        return EXIT_OPERATIONAL
    except ValueError as exc:
        # Raised by sheets_auth for an invalid --account name (usage → exit 2).
        _emit_error(str(exc))
        return EXIT_USAGE
    except HelperError as exc:
        _emit_error(str(exc))
        account = getattr(args, "account", DEFAULT_ACCOUNT)
        op = "self-check" if getattr(args, "self_check", False) else (args.command or "unknown")
        _emit_summary({"op": op, "status": "error", "account": account})
        return exc.exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
