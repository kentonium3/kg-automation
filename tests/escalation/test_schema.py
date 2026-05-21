"""Tests for scripts/escalation/schema.py (WP01 / T005).

Exhaustive coverage of ``validate_event_params``:

- Happy path for every event_type (5 cases).
- Unknown ``state`` value rejected.
- Missing required parameter per event_type (4 cases).
- Bad type / bad value for each typed parameter (4 cases).
- Shared ``project_id`` field — missing + bad-type (2 cases).
- Short-circuit verification: only the first error is raised.

Schema module is pure (no I/O); all tests are deterministic and fast.
"""
from __future__ import annotations

import pytest

from scripts.escalation.schema import (
    EVENT_TYPE_PARAMETERS,
    EscalationSchemaError,
    validate_event_params,
)


# ---------------------------------------------------------------------------
# Happy paths — one per event_type
# ---------------------------------------------------------------------------


def test_validate_level_sent_happy_path(make_jsonl_record):
    """level_sent with level=1 + project_id is valid."""
    record = make_jsonl_record(state="level_sent", level=1, project_id=4)
    # Should not raise.
    assert validate_event_params(record) is None


def test_validate_snoozed_happy_path(make_jsonl_record):
    """snoozed with snooze_days + snooze_until + project_id is valid."""
    record = make_jsonl_record(
        state="snoozed",
        snooze_days=3,
        snooze_until="2026-05-24",
        project_id=4,
    )
    assert validate_event_params(record) is None


def test_validate_dismissed_happy_path(make_jsonl_record):
    """dismissed needs no extra params; optional reason passes through."""
    record = make_jsonl_record(
        state="dismissed",
        project_id=4,
        reason="Not relevant",
    )
    assert validate_event_params(record) is None


def test_validate_done_happy_path(make_jsonl_record):
    """done needs no extra params beyond project_id."""
    record = make_jsonl_record(state="done", project_id=4)
    assert validate_event_params(record) is None


def test_validate_rescheduled_happy_path(make_jsonl_record):
    """rescheduled with reschedule_to + project_id is valid."""
    record = make_jsonl_record(
        state="rescheduled",
        reschedule_to="2026-06-15",
        project_id=4,
    )
    assert validate_event_params(record) is None


# ---------------------------------------------------------------------------
# Unknown state
# ---------------------------------------------------------------------------


def test_validate_unknown_state_raises(make_jsonl_record):
    """A state not in EVENT_TYPE_PARAMETERS is rejected naming the field."""
    record = make_jsonl_record(state="acknowledged", project_id=4)
    with pytest.raises(EscalationSchemaError) as excinfo:
        validate_event_params(record)
    msg = str(excinfo.value)
    assert "state" in msg
    assert "acknowledged" in msg


def test_validate_missing_state_raises(make_jsonl_record):
    """A record without a ``state`` field is rejected."""
    record = make_jsonl_record(project_id=4)
    del record["state"]
    with pytest.raises(EscalationSchemaError) as excinfo:
        validate_event_params(record)
    assert "state" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Missing required structured parameter — one per event_type that has any
# ---------------------------------------------------------------------------


def test_validate_level_sent_missing_level_raises(make_jsonl_record):
    """level_sent without ``level`` is rejected naming the field."""
    record = make_jsonl_record(state="level_sent", project_id=4)
    with pytest.raises(EscalationSchemaError) as excinfo:
        validate_event_params(record)
    assert "level" in str(excinfo.value)


def test_validate_snoozed_missing_snooze_days_raises(make_jsonl_record):
    """snoozed without ``snooze_days`` is rejected naming the field."""
    record = make_jsonl_record(
        state="snoozed",
        snooze_until="2026-05-24",
        project_id=4,
    )
    with pytest.raises(EscalationSchemaError) as excinfo:
        validate_event_params(record)
    assert "snooze_days" in str(excinfo.value)


def test_validate_snoozed_missing_snooze_until_raises(make_jsonl_record):
    """snoozed without ``snooze_until`` is rejected naming the field."""
    record = make_jsonl_record(
        state="snoozed",
        snooze_days=3,
        project_id=4,
    )
    with pytest.raises(EscalationSchemaError) as excinfo:
        validate_event_params(record)
    assert "snooze_until" in str(excinfo.value)


def test_validate_rescheduled_missing_reschedule_to_raises(make_jsonl_record):
    """rescheduled without ``reschedule_to`` is rejected naming the field."""
    record = make_jsonl_record(state="rescheduled", project_id=4)
    with pytest.raises(EscalationSchemaError) as excinfo:
        validate_event_params(record)
    assert "reschedule_to" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Bad type / bad value on a parameter
# ---------------------------------------------------------------------------


def test_validate_level_sent_bad_level_value(make_jsonl_record):
    """level outside {1, 2} is rejected (e.g., level=3)."""
    record = make_jsonl_record(state="level_sent", level=3, project_id=4)
    with pytest.raises(EscalationSchemaError) as excinfo:
        validate_event_params(record)
    assert "level" in str(excinfo.value)
    assert "3" in str(excinfo.value)


def test_validate_level_sent_bad_level_type(make_jsonl_record):
    """level given as a string is rejected with type-named error."""
    record = make_jsonl_record(state="level_sent", level="1", project_id=4)
    with pytest.raises(EscalationSchemaError) as excinfo:
        validate_event_params(record)
    assert "level" in str(excinfo.value)


def test_validate_snoozed_bad_snooze_until_date(make_jsonl_record):
    """snooze_until that doesn't match YYYY-MM-DD is rejected."""
    record = make_jsonl_record(
        state="snoozed",
        snooze_days=3,
        snooze_until="not-a-date",
        project_id=4,
    )
    with pytest.raises(EscalationSchemaError) as excinfo:
        validate_event_params(record)
    assert "snooze_until" in str(excinfo.value)


def test_validate_snoozed_unparseable_snooze_until(make_jsonl_record):
    """snooze_until that matches the regex but isn't a real date is rejected."""
    record = make_jsonl_record(
        state="snoozed",
        snooze_days=3,
        snooze_until="2026-13-99",
        project_id=4,
    )
    with pytest.raises(EscalationSchemaError) as excinfo:
        validate_event_params(record)
    assert "snooze_until" in str(excinfo.value)


def test_validate_rescheduled_bad_reschedule_to(make_jsonl_record):
    """reschedule_to that matches the regex but isn't a real date is rejected."""
    record = make_jsonl_record(
        state="rescheduled",
        reschedule_to="2026-13-99",
        project_id=4,
    )
    with pytest.raises(EscalationSchemaError) as excinfo:
        validate_event_params(record)
    assert "reschedule_to" in str(excinfo.value)


def test_validate_snoozed_negative_snooze_days(make_jsonl_record):
    """snooze_days <= 0 is rejected."""
    record = make_jsonl_record(
        state="snoozed",
        snooze_days=-1,
        snooze_until="2026-05-24",
        project_id=4,
    )
    with pytest.raises(EscalationSchemaError) as excinfo:
        validate_event_params(record)
    assert "snooze_days" in str(excinfo.value)


def test_validate_snoozed_bad_snooze_days_type(make_jsonl_record):
    """snooze_days given as a bool is rejected (bool subclasses int in Python)."""
    record = make_jsonl_record(
        state="snoozed",
        snooze_days=True,
        snooze_until="2026-05-24",
        project_id=4,
    )
    with pytest.raises(EscalationSchemaError) as excinfo:
        validate_event_params(record)
    assert "snooze_days" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Optional ``reason`` field (data-model Entity 1 — optional on dismissed/done)
# ---------------------------------------------------------------------------


def test_validate_done_reason_must_be_str(make_jsonl_record):
    """state=done with non-str reason is rejected naming the field."""
    record = make_jsonl_record(state="done", project_id=4, reason=123)
    with pytest.raises(EscalationSchemaError) as excinfo:
        validate_event_params(record)
    assert "reason" in str(excinfo.value)


def test_validate_dismissed_reason_must_be_str(make_jsonl_record):
    """state=dismissed with non-str reason is rejected naming the field."""
    record = make_jsonl_record(state="dismissed", project_id=4, reason=123)
    with pytest.raises(EscalationSchemaError) as excinfo:
        validate_event_params(record)
    assert "reason" in str(excinfo.value)


def test_validate_done_reason_str_happy_path(make_jsonl_record):
    """state=done with a str reason passes (no exception)."""
    record = make_jsonl_record(
        state="done",
        project_id=4,
        reason="not relevant anymore",
    )
    assert validate_event_params(record) is None


# ---------------------------------------------------------------------------
# Shared project_id field
# ---------------------------------------------------------------------------


def test_validate_missing_project_id_raises(make_jsonl_record):
    """A record without project_id is rejected."""
    record = make_jsonl_record(state="done", project_id=4)
    del record["project_id"]
    with pytest.raises(EscalationSchemaError) as excinfo:
        validate_event_params(record)
    assert "project_id" in str(excinfo.value)


def test_validate_bad_project_id_type_raises(make_jsonl_record):
    """project_id as a string (not int) is rejected."""
    record = make_jsonl_record(state="done", project_id="4")
    with pytest.raises(EscalationSchemaError) as excinfo:
        validate_event_params(record)
    assert "project_id" in str(excinfo.value)


def test_validate_non_positive_project_id_raises(make_jsonl_record):
    """project_id=0 is rejected (must be positive)."""
    record = make_jsonl_record(state="done", project_id=0)
    with pytest.raises(EscalationSchemaError) as excinfo:
        validate_event_params(record)
    assert "project_id" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Short-circuit behavior
# ---------------------------------------------------------------------------


def test_validate_short_circuits_on_first_error(make_jsonl_record):
    """A record with multiple errors raises once with the first-encountered field.

    Construction: state=level_sent (so ``level`` is required and the missing
    parameter check runs BEFORE the project_id check) + project_id=-1 (also
    invalid). The validator must raise on the missing ``level`` parameter,
    NOT on the bad ``project_id``, because (b) runs before (d).
    """
    record = make_jsonl_record(state="level_sent", project_id=-1)
    # Note: missing ``level`` AND bad project_id.
    with pytest.raises(EscalationSchemaError) as excinfo:
        validate_event_params(record)
    msg = str(excinfo.value)
    # First-encountered field is ``level`` (missing required param).
    assert "level" in msg
    # project_id is not yet mentioned because validation short-circuited.
    assert "project_id" not in msg


# ---------------------------------------------------------------------------
# EVENT_TYPE_PARAMETERS shape — guards against drift from data-model
# ---------------------------------------------------------------------------


def test_event_type_parameters_keys_match_domain_states():
    """The EVENT_TYPE_PARAMETERS keys must exactly mirror DOMAIN_STATES["escalation"]."""
    from scripts.common.state_log_schema import DOMAIN_STATES

    assert set(EVENT_TYPE_PARAMETERS.keys()) == set(DOMAIN_STATES["escalation"])
