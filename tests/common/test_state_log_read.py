"""Tests for ``scripts.common.state_log.read``.

Covers every filter combination of ``read()``:

- Missing-file path returns ``[]``.
- No-filter call returns all records in append order.
- Filter by ``task_id``, ``date`` exact, ``date_from``/``date_to`` range
  (inclusive both ends, single-day, and empty/inverted range), ``state``,
  ``source``.
- Combined filters (AND).
- Unknown filter kwarg raises ``TypeError`` naming the offender.
- Unknown domain raises ``ValueError`` naming the allowed domains.
- Forward-compatibility: unknown extra fields on stored records survive
  round-trip via ``read()``.

Shared fixtures (``state_dir``, ``good_habits_record``) live in
``tests/common/conftest.py``.
"""
from __future__ import annotations

import copy
import json

import pytest

from scripts.common import state_log
from scripts.common.state_log_schema import DOMAIN_STATES


def _record(
    task_id: int,
    *,
    date: str = "2026-05-19",
    state: str = "complete",
    source: str = "whatsapp",
    title: str | None = None,
    note: str | None = None,
) -> dict:
    """Build a valid habits record with overridable bits."""
    return {
        "domain": "habits",
        "task_id": task_id,
        "title": title or f"task {task_id}",
        "date": date,
        "state": state,
        "source": source,
        "note": note,
        "timestamp": f"{date}T11:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# Empty / missing-file paths
# ---------------------------------------------------------------------------

def test_read_returns_empty_list_when_file_missing(state_dir):
    """No appends → file does not exist → read() returns []."""
    assert state_log.read("habits") == []


def test_read_returns_empty_list_when_file_empty(state_dir):
    """File exists but has zero bytes → read() returns []."""
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "habits-history.jsonl").write_text("", encoding="utf-8")
    assert state_log.read("habits") == []


def test_read_skips_blank_and_malformed_lines(state_dir):
    """Blank lines and unparseable JSON are silently skipped."""
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "habits-history.jsonl"
    good = _record(1)
    path.write_text(
        "\n"
        + json.dumps(good)
        + "\n"
        + "\n"
        + "{not valid json}\n"
        + json.dumps(_record(2))
        + "\n",
        encoding="utf-8",
    )
    rows = state_log.read("habits")
    assert [r["task_id"] for r in rows] == [1, 2]


# ---------------------------------------------------------------------------
# No-filter call returns everything in append order
# ---------------------------------------------------------------------------

def test_read_returns_all_records_in_append_order(state_dir):
    state_log.append("habits", _record(14))
    state_log.append("habits", _record(15))
    state_log.append("habits", _record(17))
    rows = state_log.read("habits")
    assert [r["task_id"] for r in rows] == [14, 15, 17]


# ---------------------------------------------------------------------------
# Filter by task_id
# ---------------------------------------------------------------------------

def test_read_filter_by_task_id(state_dir):
    state_log.append("habits", _record(14))
    state_log.append("habits", _record(15))
    state_log.append("habits", _record(17))
    rows = state_log.read("habits", task_id=15)
    assert len(rows) == 1
    assert rows[0]["task_id"] == 15


def test_read_filter_by_task_id_no_match(state_dir):
    state_log.append("habits", _record(14))
    assert state_log.read("habits", task_id=99) == []


# ---------------------------------------------------------------------------
# Filter by date exact
# ---------------------------------------------------------------------------

def test_read_filter_by_date_exact(state_dir):
    state_log.append("habits", _record(14, date="2026-05-17"))
    state_log.append("habits", _record(14, date="2026-05-18"))
    state_log.append("habits", _record(14, date="2026-05-19"))
    rows = state_log.read("habits", date="2026-05-18")
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-05-18"


# ---------------------------------------------------------------------------
# Filter by date range (date_from / date_to, inclusive)
# ---------------------------------------------------------------------------

def test_read_filter_by_date_range_inclusive(state_dir):
    state_log.append("habits", _record(14, date="2026-05-17"))
    state_log.append("habits", _record(15, date="2026-05-18"))
    state_log.append("habits", _record(16, date="2026-05-19"))
    state_log.append("habits", _record(17, date="2026-05-20"))
    rows = state_log.read(
        "habits", date_from="2026-05-18", date_to="2026-05-19"
    )
    assert sorted(r["date"] for r in rows) == ["2026-05-18", "2026-05-19"]


def test_read_filter_by_date_range_single_day(state_dir):
    """date_from == date_to → match only that day."""
    state_log.append("habits", _record(14, date="2026-05-18"))
    state_log.append("habits", _record(15, date="2026-05-19"))
    rows = state_log.read(
        "habits", date_from="2026-05-19", date_to="2026-05-19"
    )
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-05-19"


def test_read_filter_by_date_range_empty_when_inverted(state_dir):
    """date_from > date_to → returns []."""
    state_log.append("habits", _record(14, date="2026-05-18"))
    state_log.append("habits", _record(15, date="2026-05-19"))
    rows = state_log.read(
        "habits", date_from="2026-05-20", date_to="2026-05-19"
    )
    assert rows == []


def test_read_filter_only_date_from(state_dir):
    state_log.append("habits", _record(1, date="2026-05-17"))
    state_log.append("habits", _record(2, date="2026-05-19"))
    rows = state_log.read("habits", date_from="2026-05-18")
    assert [r["task_id"] for r in rows] == [2]


def test_read_filter_only_date_to(state_dir):
    state_log.append("habits", _record(1, date="2026-05-17"))
    state_log.append("habits", _record(2, date="2026-05-19"))
    rows = state_log.read("habits", date_to="2026-05-18")
    assert [r["task_id"] for r in rows] == [1]


# ---------------------------------------------------------------------------
# Filter by state and source
# ---------------------------------------------------------------------------

def test_read_filter_by_state(state_dir):
    state_log.append("habits", _record(14, state="complete"))
    state_log.append("habits", _record(15, state="skipped"))
    state_log.append("habits", _record(16, state="incomplete"))
    rows = state_log.read("habits", state="skipped")
    assert [r["task_id"] for r in rows] == [15]


def test_read_filter_by_source(state_dir):
    state_log.append("habits", _record(14, source="whatsapp"))
    state_log.append("habits", _record(15, source="vikunja-ui"))
    state_log.append("habits", _record(16, source="whatsapp"))
    rows = state_log.read("habits", source="vikunja-ui")
    assert [r["task_id"] for r in rows] == [15]


# ---------------------------------------------------------------------------
# Combined filters (AND semantics)
# ---------------------------------------------------------------------------

def test_read_combined_filters_are_anded(state_dir):
    state_log.append("habits", _record(14, state="complete"))
    state_log.append(
        "habits",
        _record(14, state="incomplete"),
    )
    state_log.append("habits", _record(15, state="complete"))
    rows = state_log.read("habits", task_id=14, state="complete")
    assert len(rows) == 1
    assert rows[0]["task_id"] == 14 and rows[0]["state"] == "complete"


def test_read_combined_filters_no_match(state_dir):
    state_log.append("habits", _record(14, state="complete"))
    rows = state_log.read("habits", task_id=14, state="skipped")
    assert rows == []


def test_read_combined_filters_task_id_date_state_source(state_dir):
    """Apply all four exact filters together."""
    state_log.append(
        "habits",
        _record(14, date="2026-05-18", state="complete", source="whatsapp"),
    )
    state_log.append(
        "habits",
        _record(14, date="2026-05-19", state="complete", source="whatsapp"),
    )
    state_log.append(
        "habits",
        _record(14, date="2026-05-19", state="skipped", source="whatsapp"),
    )
    rows = state_log.read(
        "habits",
        task_id=14,
        date="2026-05-19",
        state="complete",
        source="whatsapp",
    )
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-05-19"
    assert rows[0]["state"] == "complete"


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

def test_read_unknown_kwarg_raises_type_error(state_dir):
    """A typo'd filter name raises TypeError naming the offender."""
    state_log.append("habits", _record(14))
    with pytest.raises(TypeError) as exc_info:
        state_log.read("habits", task=14)  # typo for task_id
    msg = str(exc_info.value)
    assert "task" in msg


def test_read_unknown_kwarg_lists_allowed_keys(state_dir):
    """The TypeError should hint at the allowed filter kwargs."""
    with pytest.raises(TypeError) as exc_info:
        state_log.read("habits", garbage="x")
    msg = str(exc_info.value)
    # At least one of the legitimate kwargs should be named.
    assert any(k in msg for k in ("task_id", "date", "state", "source"))


def test_read_unknown_domain_raises_value_error(state_dir):
    """Unknown domain on read() raises ValueError listing allowed domains."""
    with pytest.raises(ValueError) as exc_info:
        state_log.read("unknown_domain")
    msg = str(exc_info.value)
    assert "unknown_domain" in msg
    for known in DOMAIN_STATES:
        assert known in msg


# ---------------------------------------------------------------------------
# Forward compatibility
# ---------------------------------------------------------------------------

def test_read_preserves_unknown_extra_fields(state_dir):
    """Unknown extra fields on a stored record survive read() round-trip.

    Forward-compat invariant: a future writer may emit additional fields;
    today's reader must NOT drop them so downstream consumers see them.
    """
    state_dir.mkdir(parents=True, exist_ok=True)
    record = _record(14)
    record["extra_field"] = "future"
    record["another_one"] = {"nested": True}
    path = state_dir / "habits-history.jsonl"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    rows = state_log.read("habits")
    assert len(rows) == 1
    assert rows[0]["extra_field"] == "future"
    assert rows[0]["another_one"] == {"nested": True}


def test_read_per_domain_isolation(state_dir):
    """read('habits') does not return escalation records and vice versa."""
    state_log.append("habits", _record(14))
    state_log.append("escalation", {
        "domain": "escalation",
        "task_id": 99,
        "title": "esc",
        "date": "2026-05-19",
        "state": "dismissed",
        "source": "test",
        "note": None,
        "timestamp": "2026-05-19T11:00:00+00:00",
    })
    habits_rows = state_log.read("habits")
    escalation_rows = state_log.read("escalation")
    assert [r["task_id"] for r in habits_rows] == [14]
    assert [r["task_id"] for r in escalation_rows] == [99]


# Defensive safety check — pin the production path away from tests.
def test_state_dir_fixture_diverges_from_production_path(state_dir):
    assert "/data/services/openclaw/state" not in str(state_dir)
    assert state_log.STATE_DIR == state_dir
