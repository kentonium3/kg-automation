"""Tests for ``scripts.common.state_log.append``.

Covers:

- Happy path: directory + file creation, file mode/permissions, single-line
  on-disk encoding.
- Idempotency: same ``(task_id, date, state)`` is a no-op; different
  ``state`` for the same ``(task_id, date)`` is a new record.
- Validation: each required field missing produces a ``ValueError``,
  every domain enum rejection, field-type rejections (task_id, title,
  date, timestamp, note), unknown domain, and domain mismatch between
  argument and record.

All tests use the ``state_dir`` fixture from ``conftest.py`` to isolate
writes to ``tmp_path``; production ``/data/services/openclaw/state`` is
never touched.
"""
from __future__ import annotations

import copy
import json
import os
import stat

import pytest

from scripts.common import state_log
from scripts.common.state_log_schema import DOMAIN_STATES, REQUIRED_FIELDS


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_append_happy_path_creates_file(state_dir, good_habits_record):
    """First append bootstraps the state dir + file and writes exactly one line."""
    state_log.append("habits", good_habits_record)

    assert state_dir.exists(), "state_dir should be created on first append"
    assert state_dir.is_dir()

    # Contract-named mode constants (the values the implementation
    # passes to mkdir/os.open).
    assert state_log.STATE_DIR_MODE == 0o775
    assert state_log.STATE_FILE_MODE == 0o664

    # Actual on-disk mode is (requested mode) AND NOT (umask). We assert
    # the bits the implementation requested are not exceeded and the
    # owner has read+write at minimum. (Umask-stripping of group-write
    # is environment-dependent and validated outside the test surface.)
    dir_mode = stat.S_IMODE(os.stat(state_dir).st_mode)
    assert dir_mode & ~state_log.STATE_DIR_MODE == 0, (
        f"dir_mode 0o{dir_mode:o} has bits outside "
        f"requested 0o{state_log.STATE_DIR_MODE:o}"
    )
    assert dir_mode & 0o700 == 0o700, (
        f"dir_mode 0o{dir_mode:o} should grant owner rwx"
    )

    path = state_dir / "habits-history.jsonl"
    assert path.exists(), "habits-history.jsonl should be created"

    file_mode = stat.S_IMODE(os.stat(path).st_mode)
    assert file_mode & ~state_log.STATE_FILE_MODE == 0, (
        f"file_mode 0o{file_mode:o} has bits outside "
        f"requested 0o{state_log.STATE_FILE_MODE:o}"
    )
    assert file_mode & 0o600 == 0o600, (
        f"file_mode 0o{file_mode:o} should grant owner rw"
    )

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1, "exactly one line written"
    parsed = json.loads(lines[0])
    assert parsed == good_habits_record


def test_append_writes_each_domain_to_its_own_file(state_dir):
    """Different domains write to different per-domain files."""
    state_log.append("habits", {
        "domain": "habits",
        "task_id": 1,
        "title": "h",
        "date": "2026-05-19",
        "state": "complete",
        "source": "test",
        "timestamp": "2026-05-19T00:00:00+00:00",
    })
    state_log.append("escalation", {
        "domain": "escalation",
        "task_id": 2,
        "title": "e",
        "date": "2026-05-19",
        "state": "dismissed",
        "source": "test",
        "timestamp": "2026-05-19T00:00:00+00:00",
    })
    state_log.append("enrichment", {
        "domain": "enrichment",
        "task_id": 3,
        "title": "x",
        "date": "2026-05-19",
        "state": "pending",
        "source": "test",
        "timestamp": "2026-05-19T00:00:00+00:00",
    })
    assert (state_dir / "habits-history.jsonl").exists()
    assert (state_dir / "escalation-history.jsonl").exists()
    assert (state_dir / "enrichment-history.jsonl").exists()


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def test_append_is_idempotent_on_dedup_tuple(state_dir, good_habits_record):
    """Re-appending the same (task_id, date, state) is a no-op (no duplicate)."""
    state_log.append("habits", good_habits_record)
    state_log.append("habits", good_habits_record)

    path = state_dir / "habits-history.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1, "idempotent append must not write a duplicate line"


def test_append_idempotency_ignores_other_fields(state_dir, good_habits_record):
    """Idempotency dedup is on (task_id, date, state) only.

    Two records with the same dedup tuple but different ``note``/``source``/
    ``timestamp``/``title`` MUST still dedup — the first one wins.
    """
    state_log.append("habits", good_habits_record)

    variant = copy.deepcopy(good_habits_record)
    variant["title"] = "different title"
    variant["source"] = "vikunja-ui"
    variant["note"] = "added later"
    variant["timestamp"] = "2026-05-19T22:00:00+00:00"
    state_log.append("habits", variant)

    path = state_dir / "habits-history.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    # Original record is preserved (first-write-wins).
    assert parsed["title"] == good_habits_record["title"]
    assert parsed["source"] == good_habits_record["source"]


def test_append_different_state_creates_new_record(state_dir, good_habits_record):
    """Different state for same (task_id, date) is a fresh record (no dedup)."""
    incomplete = copy.deepcopy(good_habits_record)
    incomplete["state"] = "incomplete"
    state_log.append("habits", incomplete)
    state_log.append("habits", good_habits_record)  # state="complete"

    path = state_dir / "habits-history.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    parsed_states = [json.loads(line)["state"] for line in lines]
    assert parsed_states == ["incomplete", "complete"]


def test_append_different_date_creates_new_record(state_dir, good_habits_record):
    """Different date for same (task_id, state) is a fresh record."""
    next_day = copy.deepcopy(good_habits_record)
    next_day["date"] = "2026-05-20"
    next_day["timestamp"] = "2026-05-20T11:05:11+00:00"
    state_log.append("habits", good_habits_record)
    state_log.append("habits", next_day)

    path = state_dir / "habits-history.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


# ---------------------------------------------------------------------------
# Validation — required-field absence
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("missing_field", REQUIRED_FIELDS)
def test_append_missing_required_field_raises(
    state_dir, good_habits_record, missing_field
):
    """Removing any REQUIRED_FIELDS entry produces a ValueError naming the field."""
    record = copy.deepcopy(good_habits_record)
    del record[missing_field]
    with pytest.raises(ValueError) as exc_info:
        state_log.append("habits", record)
    assert missing_field in str(exc_info.value), (
        f"error message should name the missing field {missing_field!r}: "
        f"{exc_info.value}"
    )


# ---------------------------------------------------------------------------
# Validation — domain state enum
# ---------------------------------------------------------------------------

# One invalid state per domain. Capitalization tests that the enum check
# is case-sensitive (per the data-model contract).
@pytest.mark.parametrize(
    "domain,template,bad_state",
    [
        (
            "habits",
            {
                "domain": "habits",
                "task_id": 1,
                "title": "t",
                "date": "2026-05-19",
                "source": "test",
                "timestamp": "2026-05-19T00:00:00+00:00",
            },
            "Complete",  # capitalization mismatch
        ),
        (
            "escalation",
            {
                "domain": "escalation",
                "task_id": 1,
                "title": "t",
                "date": "2026-05-19",
                "source": "test",
                "timestamp": "2026-05-19T00:00:00+00:00",
            },
            "escalated",  # not in enum
        ),
        (
            "enrichment",
            {
                "domain": "enrichment",
                "task_id": 1,
                "title": "t",
                "date": "2026-05-19",
                "source": "test",
                "timestamp": "2026-05-19T00:00:00+00:00",
            },
            "done",  # not in enum
        ),
    ],
)
def test_append_invalid_state_for_domain_raises(
    state_dir, domain, template, bad_state
):
    """A state outside the per-domain enum produces a ValueError quoting it."""
    record = copy.deepcopy(template)
    record["state"] = bad_state
    with pytest.raises(ValueError) as exc_info:
        state_log.append(domain, record)
    msg = str(exc_info.value)
    assert bad_state in msg, f"error should quote bad state: {msg}"
    # At least one of the allowed states should be named (sanity).
    allowed = DOMAIN_STATES[domain]
    assert any(s in msg for s in allowed), (
        f"error should mention allowed enum members for {domain}: {msg}"
    )


# ---------------------------------------------------------------------------
# Validation — field type / value
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "task_id_value",
    [
        "14",         # string, not int
        0,            # zero (must be positive)
        -1,           # negative
        14.0,         # float
    ],
)
def test_append_invalid_task_id_raises(state_dir, good_habits_record, task_id_value):
    record = copy.deepcopy(good_habits_record)
    record["task_id"] = task_id_value
    with pytest.raises(ValueError) as exc_info:
        state_log.append("habits", record)
    assert "task_id" in str(exc_info.value)


@pytest.mark.parametrize("title_value", ["", "   ", "\t\n"])
def test_append_empty_title_raises(state_dir, good_habits_record, title_value):
    record = copy.deepcopy(good_habits_record)
    record["title"] = title_value
    with pytest.raises(ValueError) as exc_info:
        state_log.append("habits", record)
    assert "title" in str(exc_info.value)


def test_append_non_string_title_raises(state_dir, good_habits_record):
    record = copy.deepcopy(good_habits_record)
    record["title"] = 123
    with pytest.raises(ValueError) as exc_info:
        state_log.append("habits", record)
    assert "title" in str(exc_info.value)


@pytest.mark.parametrize(
    "date_value",
    [
        "2026/05/19",    # wrong separator
        "5-19-2026",     # wrong order
        "2026-05-32",    # invalid day
        "2026-13-01",    # invalid month
        "26-05-19",      # 2-digit year
        12345,           # wrong type
        "",
    ],
)
def test_append_invalid_date_raises(state_dir, good_habits_record, date_value):
    record = copy.deepcopy(good_habits_record)
    record["date"] = date_value
    with pytest.raises(ValueError) as exc_info:
        state_log.append("habits", record)
    assert "date" in str(exc_info.value)


@pytest.mark.parametrize(
    "ts_value",
    [
        "2026-05-19T11:00:00",        # no tz offset
        "2026-05-19 11:00:00+00:00",  # space instead of T (still parses, has tz)
        "not-a-timestamp",
        "",
        12345,
    ],
)
def test_append_invalid_timestamp_raises(state_dir, good_habits_record, ts_value):
    record = copy.deepcopy(good_habits_record)
    record["timestamp"] = ts_value

    # The space-separator variant DOES parse via fromisoformat in Python 3.13
    # and DOES include tz info → should be accepted. Skip that case.
    if ts_value == "2026-05-19 11:00:00+00:00":
        state_log.append("habits", record)
        return

    with pytest.raises(ValueError) as exc_info:
        state_log.append("habits", record)
    assert "timestamp" in str(exc_info.value)


@pytest.mark.parametrize("source_value", ["", 123, None])
def test_append_invalid_source_raises(state_dir, good_habits_record, source_value):
    record = copy.deepcopy(good_habits_record)
    record["source"] = source_value
    with pytest.raises(ValueError) as exc_info:
        state_log.append("habits", record)
    assert "source" in str(exc_info.value)


@pytest.mark.parametrize("note_value", [123, ["a", "b"], {"k": "v"}])
def test_append_invalid_note_type_raises(state_dir, good_habits_record, note_value):
    """``note`` must be str or None (but the key may be omitted)."""
    record = copy.deepcopy(good_habits_record)
    record["note"] = note_value
    with pytest.raises(ValueError) as exc_info:
        state_log.append("habits", record)
    assert "note" in str(exc_info.value)


def test_append_note_omitted_is_allowed(state_dir, good_habits_record):
    """Omitting ``note`` entirely is valid (note is optional)."""
    record = copy.deepcopy(good_habits_record)
    del record["note"]
    state_log.append("habits", record)
    path = state_dir / "habits-history.jsonl"
    assert path.exists()
    assert len(path.read_text().splitlines()) == 1


def test_append_note_as_string_is_allowed(state_dir, good_habits_record):
    record = copy.deepcopy(good_habits_record)
    record["note"] = "user-added explanation"
    state_log.append("habits", record)
    path = state_dir / "habits-history.jsonl"
    parsed = json.loads(path.read_text().splitlines()[0])
    assert parsed["note"] == "user-added explanation"


# ---------------------------------------------------------------------------
# Validation — domain argument
# ---------------------------------------------------------------------------

def test_append_unknown_domain_raises(state_dir, good_habits_record):
    """Calling append() with a domain outside DOMAIN_STATES raises ValueError."""
    with pytest.raises(ValueError) as exc_info:
        state_log.append("unknown_domain", good_habits_record)
    msg = str(exc_info.value)
    assert "unknown_domain" in msg
    # The error should name the allowed domains so the caller can self-correct.
    for known in DOMAIN_STATES:
        assert known in msg, f"allowed domain {known!r} should appear in error"


def test_append_mismatched_domain_raises(state_dir, good_habits_record):
    """Record's ``domain`` field must equal the ``domain`` argument."""
    # good_habits_record has domain="habits" but we call with "escalation".
    with pytest.raises(ValueError) as exc_info:
        state_log.append("escalation", good_habits_record)
    msg = str(exc_info.value)
    assert "habits" in msg
    assert "escalation" in msg


def test_append_does_not_create_file_on_validation_failure(
    state_dir, good_habits_record
):
    """A validation failure must not create the per-domain file."""
    record = copy.deepcopy(good_habits_record)
    del record["task_id"]
    with pytest.raises(ValueError):
        state_log.append("habits", record)
    # File should not exist — validation runs before any I/O.
    assert not (state_dir / "habits-history.jsonl").exists()


# ---------------------------------------------------------------------------
# Safety — production state path is not touched
# ---------------------------------------------------------------------------

PRODUCTION_STATE = "/data/services/openclaw/state"


def test_state_dir_fixture_diverges_from_production_path(state_dir):
    """Defensive: confirm the test fixture re-points STATE_DIR away from prod."""
    assert str(state_dir) != PRODUCTION_STATE
    assert PRODUCTION_STATE not in str(state_dir)
    assert state_log.STATE_DIR == state_dir


# ---------------------------------------------------------------------------
# Defensive code-path coverage on _idempotency_match
# ---------------------------------------------------------------------------

def test_idempotency_match_tolerates_blank_and_malformed_lines(
    state_dir, good_habits_record
):
    """Blank / malformed / key-missing lines in the file are skipped silently.

    Hand-seeds the file with garbage lines, then calls append() to force
    the dedup-scan path to walk over those lines without crashing.
    """
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "habits-history.jsonl"
    # Pre-seed with blank line + malformed JSON + obj-missing-keys.
    seeded = (
        "\n"                                # blank line → continue (129-130)
        + "{not json\n"                     # malformed JSON → continue (133-134)
        + json.dumps({"foo": "bar"}) + "\n"  # missing keys → continue (137-138)
    )
    path.write_text(seeded, encoding="utf-8")
    # Now append a fresh record. The pre-seeded lines must NOT cause a
    # crash and must NOT match the dedup tuple.
    state_log.append("habits", good_habits_record)
    lines = path.read_text(encoding="utf-8").splitlines()
    # Last line is the new record; preserved garbage lines come first.
    parsed_last = json.loads(lines[-1])
    assert parsed_last == good_habits_record
