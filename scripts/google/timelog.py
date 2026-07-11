"""Felix time-log main-facing normalizer (WP03).

``main`` (the LLM) has already extracted the candidate fields from the
natural-language WhatsApp message (F7). This module does **no NL regex and no
LLM anywhere** — it validates the already-structured args, resolves the given
client name to a Sheets tab (tabs-as-truth + an aliases config), drives WP02's
:mod:`scripts.google.sheets_helper` for the actual Sheets write, manages
conversation-keyed pending/ledger state, and returns a typed
:data:`TimelogResult` JSON on stdout.

Contract (authoritative): ``kitty-specs/felix-time-logging-01KX79HT/contracts/timelog-cli.md``
§C1 and ``data-model.md`` (``TimeEntry``, ``TimelogResult``, ``ClientAliases``,
``PendingTimelog``, ``RecentWriteLedger``). The 13-status union, its field
names, and the ``correction_ambiguous.reason`` enum are matched **byte-for-byte**
— any rename silently breaks the main<->helper contract.

**Main-facing NORMALIZER contract (F9).** Every *handled* status - including
``error`` and ``client_created_entry_failed`` - prints its JSON result and
exits ``0`` so ``main`` can render it safely. Exit ``2`` is reserved for a
usage/arg error (malformed flags); it is never used to signal a dialog state.

**Deterministic, no LLM.** The only "parsing" performed here is deterministic
date-token normalization (``today``/``yesterday``/explicit ``YYYY-MM-DD``) and
numeric/flag validation. All NL judgment lives in ``main``.

Invocation (repo convention): ``python3 -m scripts.google.timelog ...``.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scripts.common.alert_bus import Alert, Severity, emit
from scripts.google import sheets_helper

if TYPE_CHECKING:  # pragma: no cover - typing only, no runtime import
    from collections.abc import Sequence

__all__ = ["main"]

# --------------------------------------------------------------------------- #
# Exit codes (contract F9 - NOT the sheets_helper 0/1/2 convention)
# --------------------------------------------------------------------------- #

EXIT_OK = 0
EXIT_USAGE = 2

# --------------------------------------------------------------------------- #
# State locations (env-overridable, mirrors alert_bus/ledger.py)
# --------------------------------------------------------------------------- #

DEFAULT_STATE_DIR = "/data/services/timelog/state"
STATE_DIR_ENV = "FELIX_TIMELOG_STATE_DIR"

# Client-aliases config (committed, repo-relative).
DEFAULT_CLIENTS_CONFIG = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "design"
    / "architecture"
    / "data"
    / "timelog-clients.json"
)
CLIENTS_CONFIG_ENV = "FELIX_TIMELOG_CLIENTS_CONFIG"

# Conversation-keyed pending-record TTL (data-model.md PendingTimelog).
PENDING_TTL_SECONDS = 30 * 60

# Bounded recent-write ledger: how many records to retain per account
# regardless of TTL (belt-and-suspenders bound alongside time-based aging).
LEDGER_MAX_RECORDS = 50
# Recent-write ledger TTL (data-model.md RecentWriteLedger).
LEDGER_TTL_SECONDS = 30 * 60

REQUIRED_FIELDS = ("client", "hours", "description", "date")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


# --------------------------------------------------------------------------- #
# Atomic JSON state I/O (mirrors scripts/common/alert_bus/ledger.py)
# --------------------------------------------------------------------------- #


def _state_dir() -> Path:
    """Resolve the state directory, honoring ``FELIX_TIMELOG_STATE_DIR``."""
    override = os.environ.get(STATE_DIR_ENV, "").strip()
    return Path(override) if override else Path(DEFAULT_STATE_DIR)


def _pending_path(account: str) -> Path:
    return _state_dir() / f"pending-{account}.json"


def _ledger_path(account: str) -> Path:
    return _state_dir() / f"ledger-{account}.json"


def _read_json(path: Path, default: Any) -> Any:
    """Best-effort JSON read; returns ``default`` if missing/unreadable/invalid."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError):
        # Corrupt/unreadable state is treated as absent (fail-safe) rather than
        # crashing the normalizer.
        return default


def _write_json_atomic(path: Path, value: Any) -> None:
    """Write *value* as JSON to *path* atomically (temp file + os.rename) under
    an exclusive lock, mirroring ``alert_bus/ledger.py``'s discipline.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + f".tmp-{os.getpid()}")
    fd = os.open(str(tmp_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.write(fd, json.dumps(value, sort_keys=True).encode("utf-8"))
        os.fsync(fd)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    os.replace(tmp_path, path)


# --------------------------------------------------------------------------- #
# Correlation source (channel + conversation + source-msg-id)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Source:
    channel: str
    conversation_id: str
    source_message_id: str

    def as_dict(self) -> dict[str, str]:
        return {
            "channel": self.channel,
            "conversation_id": self.conversation_id,
            "source_message_id": self.source_message_id,
        }

    def matches(self, other: dict[str, Any]) -> bool:
        return (
            other.get("channel") == self.channel
            and other.get("conversation_id") == self.conversation_id
            and other.get("source_message_id") == self.source_message_id
        )


# --------------------------------------------------------------------------- #
# PendingTimelog state
# --------------------------------------------------------------------------- #


def _load_pending(account: str) -> dict[str, Any] | None:
    return _read_json(_pending_path(account), None)


def _save_pending(account: str, record: dict[str, Any] | None) -> None:
    """Persist *record*, or clear the file entirely when ``None``."""
    if record is None:
        path = _pending_path(account)
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return
    _write_json_atomic(_pending_path(account), record)


def _new_pending(
    source: Source, partial: dict[str, Any], awaiting: str
) -> dict[str, Any]:
    now = _utc_now()
    return {
        "source": source.as_dict(),
        "partial": partial,
        "awaiting": awaiting,
        "nonce": uuid.uuid4().hex,
        "created_at": _iso(now),
        "expires_at": _iso(now + timedelta(seconds=PENDING_TTL_SECONDS)),
    }


def _pending_age_seconds(record: dict[str, Any]) -> float:
    expires_at = _parse_iso(record["expires_at"])
    return (_utc_now() - expires_at).total_seconds()


def _pending_is_expired(record: dict[str, Any]) -> bool:
    return _utc_now() > _parse_iso(record["expires_at"])


# --------------------------------------------------------------------------- #
# RecentWriteLedger state
# --------------------------------------------------------------------------- #


def _load_ledger(account: str) -> list[dict[str, Any]]:
    data = _read_json(_ledger_path(account), [])
    return data if isinstance(data, list) else []


def _save_ledger(account: str, records: list[dict[str, Any]]) -> None:
    _write_json_atomic(_ledger_path(account), records)


def _prune_ledger(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop expired entries and bound the list to :data:`LEDGER_MAX_RECORDS`."""
    now = _utc_now()
    live = [r for r in records if _parse_iso(r["expires_at"]) > now]
    live.sort(key=lambda r: r["written_at"])
    if len(live) > LEDGER_MAX_RECORDS:
        live = live[-LEDGER_MAX_RECORDS:]
    return live


def _append_ledger_record(
    account: str,
    *,
    entry_id: str,
    source: Source,
    tab: str,
    row_index: int,
    entry: dict[str, Any],
) -> None:
    now = _utc_now()
    record = {
        "write_id": uuid.uuid4().hex,
        "entry_id": entry_id,
        "source": source.as_dict(),
        "tab": tab,
        "row_index": row_index,
        "entry": entry,
        "written_at": _iso(now),
        "expires_at": _iso(now + timedelta(seconds=LEDGER_TTL_SECONDS)),
    }
    records = _prune_ledger(_load_ledger(account))
    records.append(record)
    _save_ledger(account, records)


def _most_recent(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not records:
        return None
    return max(records, key=lambda r: r["written_at"])


# --------------------------------------------------------------------------- #
# Client alias config + resolution (FR-002 - tabs-as-truth + aliases)
# --------------------------------------------------------------------------- #


def _clients_config_path() -> Path:
    override = os.environ.get(CLIENTS_CONFIG_ENV, "").strip()
    return Path(override) if override else DEFAULT_CLIENTS_CONFIG


def _load_client_aliases() -> dict[str, list[str]]:
    """Load ``{canonical: [aliases...]}`` from the committed config.

    Best-effort: a missing/corrupt config resolves to no aliases (tab-title
    matching still works; only fuzzy alias matching is unavailable).
    """
    data = _read_json(_clients_config_path(), {})
    clients = data.get("clients", {}) if isinstance(data, dict) else {}
    return clients if isinstance(clients, dict) else {}


def _normalize_name(name: str) -> str:
    return name.strip().lower()


@dataclass
class ClientResolution:
    status: str  # "resolved" | "unknown" | "ambiguous"
    tab: str | None = None
    closest: str | None = None
    candidates: list[str] | None = None


def _resolve_client(heard: str, tabs: list[str]) -> ClientResolution:
    """Resolve *heard* (the spoken/typed client name) to a single tab.

    Order: normalize -> exact tab-title match -> alias match -> else unknown.
    Multiple matches (either from ambiguous aliasing across canonicals, or an
    alias that maps to a name matching >1 live tab) -> ambiguous.
    """
    normalized = _normalize_name(heard)

    # 1) Exact tab-title match (case/space-tolerant).
    exact_matches = [t for t in tabs if _normalize_name(t) == normalized]
    if len(exact_matches) == 1:
        return ClientResolution(status="resolved", tab=exact_matches[0])
    if len(exact_matches) > 1:
        return ClientResolution(status="ambiguous", candidates=sorted(set(exact_matches)))

    # 2) Alias match: heard name matches an alias of some canonical client;
    # the canonical name must itself be a live tab (tabs-as-truth).
    aliases = _load_client_aliases()
    alias_matches: list[str] = []
    for canonical, alias_list in aliases.items():
        if not isinstance(alias_list, list):
            continue
        if any(_normalize_name(a) == normalized for a in alias_list) or (
            _normalize_name(canonical) == normalized
        ):
            if canonical in tabs:
                alias_matches.append(canonical)

    unique_alias_matches = sorted(set(alias_matches))
    if len(unique_alias_matches) == 1:
        return ClientResolution(status="resolved", tab=unique_alias_matches[0])
    if len(unique_alias_matches) > 1:
        return ClientResolution(status="ambiguous", candidates=unique_alias_matches)

    # 3) No match at all -> unknown_client. Offer a best-effort "closest" tab
    # (simple substring heuristic; deterministic, no fuzzy-matching library).
    closest = _closest_tab(normalized, tabs)
    return ClientResolution(status="unknown", closest=closest)


def _closest_tab(normalized_heard: str, tabs: list[str]) -> str | None:
    """Deterministic best-effort candidate: a tab whose normalized name
    contains (or is contained by) the heard name. No fuzzy-match library, no
    LLM - pure substring containment, first match wins (tabs order is
    whatever list-tabs returned).
    """
    for tab in tabs:
        norm_tab = _normalize_name(tab)
        if normalized_heard in norm_tab or norm_tab in normalized_heard:
            return tab
    return None


# --------------------------------------------------------------------------- #
# Deterministic date-token normalization (NOT NL parsing - F1 exemption)
# --------------------------------------------------------------------------- #


def _normalize_date(raw: str) -> str | None:
    """Return an ISO ``YYYY-MM-DD`` string, or ``None`` if unparseable.

    Only ``today``/``yesterday`` (case-insensitive) and explicit ISO dates are
    accepted - this is deterministic token normalization, not NL parsing.
    """
    token = raw.strip().lower()
    if token == "today":
        return date.today().isoformat()
    if token == "yesterday":
        return (date.today() - timedelta(days=1)).isoformat()
    try:
        return date.fromisoformat(raw.strip()).isoformat()
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Sheets-helper call boundary (WP02) - the single seam tests mock
# --------------------------------------------------------------------------- #


class SheetsOpError(Exception):
    """Raised when a sheets_helper op does not succeed (fail-safe boundary)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


def _call_sheets_helper(argv: list[str]) -> dict[str, Any]:
    """Invoke :func:`scripts.google.sheets_helper.main` in-process.

    Captures stdout, parses the first JSON line as the structured result, and
    raises :class:`SheetsOpError` on a non-zero exit (this is the single seam
    tests mock/patch to simulate WP02 success/failure without touching a real
    Sheets workbook).
    """
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exit_code = sheets_helper.main(argv)
    output = buf.getvalue()
    if exit_code != 0:
        first_line = output.strip().splitlines()[0] if output.strip() else ""
        raise SheetsOpError(f"sheets_helper {argv[:1]} failed (exit {exit_code}): {first_line}")
    lines = output.strip().splitlines()
    if not lines:
        raise SheetsOpError(f"sheets_helper {argv[:1]} produced no output")
    try:
        return json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise SheetsOpError(f"sheets_helper {argv[:1]} produced non-JSON output: {exc}") from exc


def _sh_list_tabs(account: str) -> list[str]:
    result = _call_sheets_helper(["list-tabs", "--account", account])
    tabs = result.get("tabs", [])
    return tabs if isinstance(tabs, list) else []


def _sh_create_tab(tab: str, account: str) -> bool:
    """Returns whether the tab was newly created (``False`` = already existed)."""
    result = _call_sheets_helper(["create-tab", "--tab", tab, "--account", account])
    return bool(result.get("created", False))


def _sh_append_row(
    tab: str, entry_id: str, values: list[Any], account: str
) -> tuple[int, list[Any]]:
    result = _call_sheets_helper(
        [
            "append-row",
            "--tab",
            tab,
            "--entry-id",
            entry_id,
            "--values",
            json.dumps(values),
            "--account",
            account,
        ]
    )
    return int(result["row_index"]), list(result.get("values", values))


def _sh_update_last(tab: str, row: int, values: list[Any], account: str) -> None:
    _call_sheets_helper(
        [
            "update-last",
            "--tab",
            tab,
            "--row",
            str(row),
            "--values",
            json.dumps(values),
            "--account",
            account,
        ]
    )


def _sh_delete_last(tab: str, row: int, account: str) -> None:
    _call_sheets_helper(["delete-last", "--tab", tab, "--row", str(row), "--account", account])


# --------------------------------------------------------------------------- #
# TimeEntry row shape (data-model.md)
# --------------------------------------------------------------------------- #


def _row_values(entry: dict[str, Any]) -> list[Any]:
    """Column order: date | hours | client | description | billable | logged_at | entry_id."""
    return [
        entry["date"],
        entry["hours"],
        entry["client"],
        entry["description"],
        entry["billable"],
        entry["logged_at"],
        entry["entry_id"],
    ]


def _make_receipt(action: str, entry: dict[str, Any]) -> str:
    billable_note = "" if entry["billable"] else " (non-billable)"
    verb = {"logged": "Logged", "corrected": "Corrected", "deleted": "Removed"}[action]
    if action == "deleted":
        return (
            f"✅ Removed {entry['hours']}h for {entry['client']} "
            f"({entry['date']}): {entry['description']}{billable_note}"
        )
    return (
        f"✅ {verb} {entry['hours']}h for {entry['client']} "
        f"({entry['date']}): {entry['description']}{billable_note}"
    )


# --------------------------------------------------------------------------- #
# Alerting (NFR-003) - error / client_created_entry_failed only
# --------------------------------------------------------------------------- #


def _alert_write_failed(*, detail: str, tab: str | None, account: str, op: str) -> None:
    """Emit a #701 Alert for a write failure. Never raises; never swallows the
    caller's TimelogResult (emit() itself never raises).
    """
    details: dict[str, str] = {"account": account, "op": op}
    if tab is not None:
        details["tab"] = tab
    emit(
        Alert(
            source="scripts/google/timelog",
            severity=Severity.ERROR,
            title="Time-log write failed",
            description=detail,
            action="Check Sheets API/auth health; retry is safe (idempotent).",
            details=details,
        )
    )


# --------------------------------------------------------------------------- #
# TimelogResult builders - one per status, byte-for-byte per data-model.md
# --------------------------------------------------------------------------- #


def _result_logged(tab: str, entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "logged",
        "tab": tab,
        "row": entry,
        "receipt": _make_receipt("logged", entry),
    }


def _result_unknown_client(heard: str, closest: str | None) -> dict[str, Any]:
    return {"status": "unknown_client", "heard": heard, "closest": closest}


def _result_need_field(missing: str, partial: dict[str, Any]) -> dict[str, Any]:
    return {"status": "need_field", "missing": missing, "partial": partial}


def _result_ambiguous(candidates: list[str]) -> dict[str, Any]:
    return {"status": "ambiguous", "candidates": candidates}


def _result_error(detail: str) -> dict[str, Any]:
    return {"status": "error", "detail": detail}


def _result_not_timelog() -> dict[str, Any]:
    return {"status": "not_timelog"}


def _result_no_pending() -> dict[str, Any]:
    return {"status": "no_pending", "awaiting": "none"}


def _result_stale_pending(age_s: float) -> dict[str, Any]:
    return {"status": "stale_pending", "age_s": age_s}


def _result_client_created_entry_failed(tab: str, detail: str) -> dict[str, Any]:
    return {"status": "client_created_entry_failed", "tab": tab, "detail": detail}


def _result_corrected(tab: str, entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "corrected",
        "tab": tab,
        "row": entry,
        "receipt": _make_receipt("corrected", entry),
    }


def _result_deleted(tab: str, entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "deleted",
        "tab": tab,
        "row": entry,
        "receipt": _make_receipt("deleted", entry),
    }


def _result_no_last_write() -> dict[str, Any]:
    return {"status": "no_last_write"}


def _result_correction_ambiguous(reason: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "correction_ambiguous", "reason": reason, "candidates": candidates}


# --------------------------------------------------------------------------- #
# Primary invocation: validate structured args -> resolve client -> write
# --------------------------------------------------------------------------- #


def _build_partial(args: argparse.Namespace) -> dict[str, Any]:
    partial: dict[str, Any] = {}
    if args.client:
        partial["client"] = args.client
    if args.hours is not None:
        partial["hours"] = args.hours
    if args.description:
        partial["description"] = args.description
    if args.date:
        partial["date"] = args.date
    return partial


def _missing_field(args: argparse.Namespace) -> str | None:
    """Return the name of the first missing required field, else ``None``."""
    if not args.client:
        return "client"
    if args.hours is None:
        return "hours"
    if not args.description:
        return "description"
    if not args.date:
        return "date"
    return None


def _handle_primary(args: argparse.Namespace, source: Source) -> dict[str, Any]:
    if getattr(args, "not_timelog", False):
        return _result_not_timelog()

    missing = _missing_field(args)
    if missing is not None:
        return _result_need_field(missing, _build_partial(args))

    normalized_date = _normalize_date(args.date)
    if normalized_date is None:
        return _result_need_field("date", _build_partial(args))

    try:
        tabs = _sh_list_tabs(args.account)
    except SheetsOpError as exc:
        _alert_write_failed(detail=str(exc), tab=None, account=args.account, op="list-tabs")
        return _result_error(str(exc))

    resolution = _resolve_client(args.client, tabs)
    if resolution.status == "unknown":
        pending = _new_pending(source, _build_partial(args), awaiting="client")
        _save_pending(args.account, pending)
        return _result_unknown_client(args.client, resolution.closest)
    if resolution.status == "ambiguous":
        pending = _new_pending(source, _build_partial(args), awaiting="client")
        _save_pending(args.account, pending)
        return _result_ambiguous(resolution.candidates or [])

    assert resolution.tab is not None  # resolved
    return _write_entry(
        tab=resolution.tab,
        client=resolution.tab,
        hours=args.hours,
        description=args.description,
        normalized_date=normalized_date,
        billable=not args.non_billable,
        account=args.account,
        source=source,
    )


def _write_entry(
    *,
    tab: str,
    client: str,
    hours: float,
    description: str,
    normalized_date: str,
    billable: bool,
    account: str,
    source: Source,
) -> dict[str, Any]:
    """Append one row via WP02's helper; only ``logged`` on read-back confirm."""
    entry_id = str(uuid.uuid4())
    entry = {
        "date": normalized_date,
        "hours": hours,
        "client": client,
        "description": description,
        "billable": billable,
        "logged_at": _iso(_utc_now()),
        "entry_id": entry_id,
    }
    try:
        row_index, _confirmed_values = _sh_append_row(
            tab, entry_id, _row_values(entry), account
        )
    except SheetsOpError as exc:
        _alert_write_failed(detail=str(exc), tab=tab, account=account, op="append-row")
        return _result_error(str(exc))

    _append_ledger_record(
        account, entry_id=entry_id, source=source, tab=tab, row_index=row_index, entry=entry
    )
    # A successful primary write clears any stale pending for this source.
    _clear_correlated_pending(account, source)
    return _result_logged(tab, entry)


def _clear_correlated_pending(account: str, source: Source) -> None:
    record = _load_pending(account)
    if record is not None and source.matches(record.get("source", {})):
        _save_pending(account, None)


# --------------------------------------------------------------------------- #
# Follow-up handling: --confirm-client / --add-client / --field
# --------------------------------------------------------------------------- #


def _resolve_pending_or_signal(
    args: argparse.Namespace, source: Source
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return ``(pending_record, None)`` if a correlated live record is found,
    else ``(None, signal)`` where *signal* is the ``no_pending`` /
    ``stale_pending`` TimelogResult to return immediately.
    """
    record = _load_pending(args.account)
    if record is None or not source.matches(record.get("source", {})):
        return None, _result_no_pending()
    if _pending_is_expired(record):
        age_s = _pending_age_seconds(record)
        _save_pending(args.account, None)
        return None, _result_stale_pending(age_s)
    return record, None


def _handle_confirm_client(args: argparse.Namespace, source: Source) -> dict[str, Any]:
    record, signal = _resolve_pending_or_signal(args, source)
    if signal is not None:
        return signal
    assert record is not None
    partial = dict(record["partial"])
    partial["client"] = args.confirm_client

    missing = _first_missing_from_partial(partial)
    if missing is not None:
        updated = _new_pending(source, partial, awaiting=f"field:{missing}")
        _save_pending(args.account, updated)
        return _result_need_field(missing, partial)

    normalized_date = _normalize_date(str(partial["date"]))
    if normalized_date is None:
        updated = _new_pending(source, partial, awaiting="field:date")
        _save_pending(args.account, updated)
        return _result_need_field("date", partial)

    try:
        tabs = _sh_list_tabs(args.account)
    except SheetsOpError as exc:
        _alert_write_failed(detail=str(exc), tab=None, account=args.account, op="list-tabs")
        return _result_error(str(exc))

    resolution = _resolve_client(args.confirm_client, tabs)
    if resolution.status == "unknown":
        updated = _new_pending(source, partial, awaiting="client")
        _save_pending(args.account, updated)
        return _result_unknown_client(args.confirm_client, resolution.closest)
    if resolution.status == "ambiguous":
        updated = _new_pending(source, partial, awaiting="client")
        _save_pending(args.account, updated)
        return _result_ambiguous(resolution.candidates or [])

    assert resolution.tab is not None
    return _write_entry(
        tab=resolution.tab,
        client=resolution.tab,
        hours=float(partial["hours"]),
        description=str(partial["description"]),
        normalized_date=normalized_date,
        billable=not bool(partial.get("non_billable", False)),
        account=args.account,
        source=source,
    )


def _handle_add_client(args: argparse.Namespace, source: Source) -> dict[str, Any]:
    """New-client onboarding two-step (FR-004/F3): create-tab then append-row.

    A partial mutation (tab created, append failed) -> ``client_created_entry_failed``,
    never ``logged``. Retry is idempotent (create-tab no-ops; append dedupes by
    entry_id).
    """
    record, signal = _resolve_pending_or_signal(args, source)
    if signal is not None:
        return signal
    assert record is not None
    partial = dict(record["partial"])
    tab = args.add_client

    missing = _first_missing_from_partial(partial)
    if missing is not None:
        updated = _new_pending(source, partial, awaiting=f"field:{missing}")
        _save_pending(args.account, updated)
        return _result_need_field(missing, partial)

    normalized_date = _normalize_date(str(partial["date"]))
    if normalized_date is None:
        updated = _new_pending(source, partial, awaiting="field:date")
        _save_pending(args.account, updated)
        return _result_need_field("date", partial)

    try:
        _sh_create_tab(tab, args.account)
    except SheetsOpError as exc:
        _alert_write_failed(detail=str(exc), tab=tab, account=args.account, op="create-tab")
        return _result_error(str(exc))

    entry_id = str(uuid.uuid4())
    entry = {
        "date": normalized_date,
        "hours": float(partial["hours"]),
        "client": tab,
        "description": str(partial["description"]),
        "billable": not bool(partial.get("non_billable", False)),
        "logged_at": _iso(_utc_now()),
        "entry_id": entry_id,
    }
    try:
        row_index, _confirmed = _sh_append_row(tab, entry_id, _row_values(entry), args.account)
    except SheetsOpError as exc:
        detail = f"tab created; append failed ({exc}) - time NOT logged"
        _alert_write_failed(detail=detail, tab=tab, account=args.account, op="append-row")
        return _result_client_created_entry_failed(tab, detail)

    _append_ledger_record(
        args.account,
        entry_id=entry_id,
        source=source,
        tab=tab,
        row_index=row_index,
        entry=entry,
    )
    _clear_correlated_pending(args.account, source)
    return _result_logged(tab, entry)


def _first_missing_from_partial(partial: dict[str, Any]) -> str | None:
    for field_name in REQUIRED_FIELDS:
        if field_name not in partial or partial[field_name] in (None, ""):
            return field_name
    return None


def _handle_field(args: argparse.Namespace, source: Source) -> dict[str, Any]:
    record, signal = _resolve_pending_or_signal(args, source)
    if signal is not None:
        return signal
    assert record is not None
    partial = dict(record["partial"])

    name, _, value = args.field.partition("=")
    if name not in REQUIRED_FIELDS or not value:
        return _result_need_field(
            record.get("awaiting", "field").removeprefix("field:") or "field", partial
        )
    partial[name] = value

    missing = _first_missing_from_partial(partial)
    if missing is not None:
        updated = _new_pending(source, partial, awaiting=f"field:{missing}")
        _save_pending(args.account, updated)
        return _result_need_field(missing, partial)

    normalized_date = _normalize_date(str(partial["date"]))
    if normalized_date is None:
        updated = _new_pending(source, partial, awaiting="field:date")
        _save_pending(args.account, updated)
        return _result_need_field("date", partial)

    try:
        hours = float(partial["hours"])
    except (TypeError, ValueError):
        updated = _new_pending(source, partial, awaiting="field:hours")
        _save_pending(args.account, updated)
        return _result_need_field("hours", partial)

    try:
        tabs = _sh_list_tabs(args.account)
    except SheetsOpError as exc:
        _alert_write_failed(detail=str(exc), tab=None, account=args.account, op="list-tabs")
        return _result_error(str(exc))

    resolution = _resolve_client(str(partial["client"]), tabs)
    if resolution.status == "unknown":
        updated = _new_pending(source, partial, awaiting="client")
        _save_pending(args.account, updated)
        return _result_unknown_client(str(partial["client"]), resolution.closest)
    if resolution.status == "ambiguous":
        updated = _new_pending(source, partial, awaiting="client")
        _save_pending(args.account, updated)
        return _result_ambiguous(resolution.candidates or [])

    assert resolution.tab is not None
    return _write_entry(
        tab=resolution.tab,
        client=resolution.tab,
        hours=hours,
        description=str(partial["description"]),
        normalized_date=normalized_date,
        billable=not bool(partial.get("non_billable", False)),
        account=args.account,
        source=source,
    )


# --------------------------------------------------------------------------- #
# Corrections: --correct / --delete-last (FR-006, most-recent ledger entry)
# --------------------------------------------------------------------------- #


def _resolve_correction_target(
    account: str, source: Source
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return ``(target_record, None)`` for the unambiguous most-recent ledger
    entry belonging to *source*'s conversation, else ``(None, signal)`` --
    ``no_last_write`` (empty ledger) or ``correction_ambiguous`` (the natural
    target has expired / gone stale, or a **globally** newer write landed
    after it from elsewhere -- so "most recent" no longer unambiguously means
    what this conversation's follow-up intends, F4).

    The natural target is this conversation's own most-recent write (a
    follow-up like "make that 3h" refers to what *this* conversation just
    logged). If the ledger's single global most-recent record is not this
    conversation's target, a newer write happened after it -> ambiguous
    rather than silently mutating the wrong row.

    Uses the **raw** (unpruned) ledger so an expired target is still visible
    for the staleness check below, rather than silently vanishing (which
    would misreport a stale target as an empty ledger / ``no_last_write``).
    """
    records = _load_ledger(account)
    if not records:
        return None, _result_no_last_write()

    own_records = [r for r in records if source.matches(r.get("source", {}))]
    if not own_records:
        return None, _result_no_last_write()

    target = _most_recent(own_records)
    assert target is not None
    if _parse_iso(target["expires_at"]) <= _utc_now():
        return None, _result_correction_ambiguous(
            "stale", [{"tab": target["tab"], "row_index": target["row_index"]}]
        )

    newer = [r for r in records if r["written_at"] > target["written_at"]]
    if newer:
        return None, _result_correction_ambiguous(
            "newer_write",
            [{"tab": r["tab"], "row_index": r["row_index"]} for r in newer],
        )

    return target, None


def _handle_correct(args: argparse.Namespace, source: Source) -> dict[str, Any]:
    target, signal = _resolve_correction_target(args.account, source)
    if signal is not None:
        return signal
    assert target is not None

    entry = dict(target["entry"])
    if args.hours is not None:
        entry["hours"] = args.hours
    if args.description:
        entry["description"] = args.description
    if args.date:
        normalized_date = _normalize_date(args.date)
        if normalized_date is not None:
            entry["date"] = normalized_date
    if args.non_billable:
        entry["billable"] = False
    entry["logged_at"] = _iso(_utc_now())

    try:
        _sh_update_last(target["tab"], target["row_index"], _row_values(entry), args.account)
    except SheetsOpError as exc:
        _alert_write_failed(detail=str(exc), tab=target["tab"], account=args.account, op="update-last")
        return _result_error(str(exc))

    _replace_ledger_entry(args.account, target["write_id"], entry, source)
    return _result_corrected(target["tab"], entry)


def _handle_delete_last(args: argparse.Namespace, source: Source) -> dict[str, Any]:
    target, signal = _resolve_correction_target(args.account, source)
    if signal is not None:
        return signal
    assert target is not None

    try:
        _sh_delete_last(target["tab"], target["row_index"], args.account)
    except SheetsOpError as exc:
        _alert_write_failed(detail=str(exc), tab=target["tab"], account=args.account, op="delete-last")
        return _result_error(str(exc))

    _remove_ledger_entry(args.account, target["write_id"])
    return _result_deleted(target["tab"], target["entry"])


def _replace_ledger_entry(
    account: str, write_id: str, new_entry: dict[str, Any], source: Source
) -> None:
    records = _prune_ledger(_load_ledger(account))
    now = _utc_now()
    for record in records:
        if record["write_id"] == write_id:
            record["entry"] = new_entry
            record["written_at"] = _iso(now)
            record["expires_at"] = _iso(now + timedelta(seconds=LEDGER_TTL_SECONDS))
            record["source"] = source.as_dict()
            break
    _save_ledger(account, records)


def _remove_ledger_entry(account: str, write_id: str) -> None:
    records = _prune_ledger(_load_ledger(account))
    records = [r for r in records if r["write_id"] != write_id]
    _save_ledger(account, records)


# --------------------------------------------------------------------------- #
# argument parsing
# --------------------------------------------------------------------------- #


def _positive_float(raw: str) -> float:
    try:
        return float(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"--hours must be numeric, got {raw!r}") from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="timelog",
        description="Felix time-log main-facing normalizer (validate/resolve/write).",
    )
    parser.add_argument("--client")
    parser.add_argument("--hours", type=_positive_float)
    parser.add_argument("--date")
    parser.add_argument("--description")
    parser.add_argument("--non-billable", dest="non_billable", action="store_true")
    parser.add_argument("--not-timelog", dest="not_timelog", action="store_true")

    parser.add_argument("--confirm-client")
    parser.add_argument("--add-client")
    parser.add_argument("--field")
    parser.add_argument("--correct", action="store_true")
    parser.add_argument("--delete-last", dest="delete_last", action="store_true")

    parser.add_argument("--channel", default="whatsapp")
    parser.add_argument("--conversation", required=True)
    parser.add_argument("--source-msg-id", dest="source_msg_id", required=True)
    parser.add_argument("--account", default="personal")
    parser.add_argument("--json", action="store_true", help="no-op; output is always JSON")

    return parser


def _dispatch(args: argparse.Namespace) -> dict[str, Any]:
    source = Source(
        channel=args.channel,
        conversation_id=args.conversation,
        source_message_id=args.source_msg_id,
    )

    if args.confirm_client:
        return _handle_confirm_client(args, source)
    if args.add_client:
        return _handle_add_client(args, source)
    if args.field:
        return _handle_field(args, source)
    if args.correct:
        return _handle_correct(args, source)
    if args.delete_last:
        return _handle_delete_last(args, source)

    return _handle_primary(args, source)


def main(argv: "Sequence[str] | None" = None) -> int:
    """CLI entry point.

    Returns the process exit code: ``0`` for any handled ``TimelogResult``
    status (including ``error`` / ``client_created_entry_failed``), ``2`` only
    on a usage/arg error (malformed flags) - the normalizer contract (F9).
    """
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse already printed its usage message to stderr and would exit
        # 2; make that explicit/stable regardless of argparse's own default.
        return exc.code if isinstance(exc.code, int) else EXIT_USAGE

    result = _dispatch(args)
    print(json.dumps(result, sort_keys=True))
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
