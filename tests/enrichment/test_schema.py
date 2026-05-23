"""Tests for ``scripts.enrichment.schema`` (WP01 / T003).

Coverage targets:

- :class:`EnrichmentCompletion` dataclass invariants (frozen, field order,
  defaults).
- :data:`VALID_STATES` and :data:`VALID_SOURCES` exact contents.
- :data:`SCHEMA_VERSION` and :data:`DEFAULT_LEDGER_PATH` values.
- :func:`validate_record` happy path + every short-circuit error path.

Schema module is pure (no I/O); all tests are deterministic and fast.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from scripts.enrichment.schema import (
    DEFAULT_LEDGER_PATH,
    SCHEMA_VERSION,
    VALID_SOURCES,
    VALID_STATES,
    EnrichmentCompletion,
    EnrichmentSchemaError,
    validate_record,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_valid_states_exact_contents(self):
        """VALID_STATES locks the deployed AGENTS.md vocabulary."""
        assert VALID_STATES == frozenset(
            {"proposed", "confirmed", "skipped", "declined"}
        )

    def test_valid_states_is_frozenset(self):
        """Immutability — VALID_STATES must not be mutable mid-run."""
        assert isinstance(VALID_STATES, frozenset)

    def test_valid_sources_exact_contents(self):
        """VALID_SOURCES mirrors the escalation source set."""
        assert VALID_SOURCES == frozenset(
            {"agent", "reconcile", "backfill", "operator_repair"}
        )

    def test_valid_sources_is_frozenset(self):
        assert isinstance(VALID_SOURCES, frozenset)

    def test_schema_version_is_one(self):
        assert SCHEMA_VERSION == 1
        assert isinstance(SCHEMA_VERSION, int)

    def test_default_ledger_path_is_canonical_office2_path(self):
        """Default ledger path matches data-model.md and spec FR-001."""
        assert DEFAULT_LEDGER_PATH == Path(
            "/data/services/openclaw/state/enrichment/enrichment-history.jsonl"
        )
        assert isinstance(DEFAULT_LEDGER_PATH, Path)


# ---------------------------------------------------------------------------
# Dataclass shape + invariants (data-model.md E1)
# ---------------------------------------------------------------------------


class TestDataclassInvariants:
    def test_is_frozen(self):
        """Frozen dataclass — cannot mutate fields post-construction."""
        rec = EnrichmentCompletion(
            task_id=1, state="proposed",
            timestamp_utc="2026-05-23T19:00:00Z",
            source="agent",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            rec.state = "confirmed"  # type: ignore[misc]

    def test_field_order_matches_data_model(self):
        """Field order is canonical (data-model.md E1) for deterministic JSONL."""
        names = [f.name for f in dataclasses.fields(EnrichmentCompletion)]
        assert names == [
            "task_id",
            "state",
            "timestamp_utc",
            "source",
            "schema_version",
            "note",
        ]

    def test_schema_version_default(self):
        """schema_version defaults to SCHEMA_VERSION (1)."""
        rec = EnrichmentCompletion(
            task_id=1, state="proposed",
            timestamp_utc="2026-05-23T19:00:00Z",
            source="agent",
        )
        assert rec.schema_version == SCHEMA_VERSION

    def test_note_default_is_none(self):
        rec = EnrichmentCompletion(
            task_id=1, state="proposed",
            timestamp_utc="2026-05-23T19:00:00Z",
            source="agent",
        )
        assert rec.note is None

    def test_to_dict_preserves_field_order(self):
        """to_dict() keys appear in the dataclass field declaration order."""
        rec = EnrichmentCompletion(
            task_id=42,
            state="confirmed",
            timestamp_utc="2026-05-23T19:30:00Z",
            source="agent",
            note="created from delegation",
        )
        d = rec.to_dict()
        assert list(d.keys()) == [
            "task_id",
            "state",
            "timestamp_utc",
            "source",
            "schema_version",
            "note",
        ]
        assert d["task_id"] == 42
        assert d["state"] == "confirmed"
        assert d["schema_version"] == 1
        assert d["note"] == "created from delegation"

    def test_equality_and_hash(self):
        """Frozen dataclass is hashable + equality compares all fields."""
        a = EnrichmentCompletion(
            task_id=1, state="proposed",
            timestamp_utc="2026-05-23T19:00:00Z",
            source="agent",
        )
        b = EnrichmentCompletion(
            task_id=1, state="proposed",
            timestamp_utc="2026-05-23T19:00:00Z",
            source="agent",
        )
        assert a == b
        assert hash(a) == hash(b)
        # Set membership works because the dataclass is hashable.
        assert {a, b} == {a}


# ---------------------------------------------------------------------------
# validate_record — happy path
# ---------------------------------------------------------------------------


@pytest.fixture
def good_record() -> dict:
    """A minimally-valid enrichment record dict."""
    return {
        "task_id": 1234,
        "state": "proposed",
        "timestamp_utc": "2026-05-23T19:00:00Z",
        "source": "agent",
        "schema_version": 1,
        "note": None,
    }


class TestValidateHappyPaths:
    def test_all_states_valid(self, good_record):
        """Every state in VALID_STATES validates cleanly."""
        for state in VALID_STATES:
            rec = dict(good_record, state=state)
            # Should not raise.
            assert validate_record(rec) is None

    def test_all_sources_valid(self, good_record):
        """Every source in VALID_SOURCES validates cleanly."""
        for source in VALID_SOURCES:
            rec = dict(good_record, source=source)
            assert validate_record(rec) is None

    def test_note_str_passes(self, good_record):
        rec = dict(good_record, note="hello")
        assert validate_record(rec) is None

    def test_note_absent_passes(self, good_record):
        """``note`` is optional; absence is fine."""
        rec = dict(good_record)
        del rec["note"]
        assert validate_record(rec) is None

    def test_schema_version_absent_passes(self, good_record):
        """``schema_version`` is optional in the dict form."""
        rec = dict(good_record)
        del rec["schema_version"]
        assert validate_record(rec) is None


# ---------------------------------------------------------------------------
# validate_record — error paths (short-circuit, first failure wins)
# ---------------------------------------------------------------------------


class TestValidateMissingRequired:
    @pytest.mark.parametrize(
        "field", ["task_id", "state", "timestamp_utc", "source"]
    )
    def test_missing_required_raises(self, good_record, field):
        rec = dict(good_record)
        del rec[field]
        with pytest.raises(EnrichmentSchemaError, match=field):
            validate_record(rec)


class TestValidateTaskId:
    def test_task_id_string_rejected(self, good_record):
        rec = dict(good_record, task_id="123")
        with pytest.raises(EnrichmentSchemaError, match="task_id"):
            validate_record(rec)

    def test_task_id_bool_rejected(self, good_record):
        """``bool`` is an int subclass — must be explicitly rejected."""
        rec = dict(good_record, task_id=True)
        with pytest.raises(EnrichmentSchemaError, match="task_id"):
            validate_record(rec)

    def test_task_id_zero_rejected(self, good_record):
        rec = dict(good_record, task_id=0)
        with pytest.raises(EnrichmentSchemaError, match="positive"):
            validate_record(rec)

    def test_task_id_negative_rejected(self, good_record):
        rec = dict(good_record, task_id=-1)
        with pytest.raises(EnrichmentSchemaError, match="positive"):
            validate_record(rec)


class TestValidateState:
    def test_unknown_state_rejected(self, good_record):
        rec = dict(good_record, state="pending")
        with pytest.raises(EnrichmentSchemaError, match="pending"):
            validate_record(rec)

    def test_state_non_string_rejected(self, good_record):
        rec = dict(good_record, state=123)
        with pytest.raises(EnrichmentSchemaError, match="state"):
            validate_record(rec)


class TestValidateSource:
    def test_unknown_source_rejected(self, good_record):
        rec = dict(good_record, source="rogue_writer")
        with pytest.raises(EnrichmentSchemaError, match="rogue_writer"):
            validate_record(rec)

    def test_source_non_string_rejected(self, good_record):
        rec = dict(good_record, source=42)
        with pytest.raises(EnrichmentSchemaError, match="source"):
            validate_record(rec)


class TestValidateTimestamp:
    def test_timestamp_non_string_rejected(self, good_record):
        rec = dict(good_record, timestamp_utc=12345)
        with pytest.raises(EnrichmentSchemaError, match="timestamp_utc"):
            validate_record(rec)

    def test_timestamp_empty_rejected(self, good_record):
        rec = dict(good_record, timestamp_utc="")
        with pytest.raises(EnrichmentSchemaError, match="timestamp_utc"):
            validate_record(rec)

    def test_timestamp_whitespace_only_rejected(self, good_record):
        rec = dict(good_record, timestamp_utc="   ")
        with pytest.raises(EnrichmentSchemaError, match="timestamp_utc"):
            validate_record(rec)


class TestValidateNote:
    def test_note_non_string_rejected(self, good_record):
        rec = dict(good_record, note=123)
        with pytest.raises(EnrichmentSchemaError, match="note"):
            validate_record(rec)

    def test_note_explicit_none_passes(self, good_record):
        rec = dict(good_record, note=None)
        assert validate_record(rec) is None


class TestValidateSchemaVersion:
    def test_schema_version_string_rejected(self, good_record):
        rec = dict(good_record, schema_version="1")
        with pytest.raises(EnrichmentSchemaError, match="schema_version"):
            validate_record(rec)

    def test_schema_version_bool_rejected(self, good_record):
        rec = dict(good_record, schema_version=True)
        with pytest.raises(EnrichmentSchemaError, match="schema_version"):
            validate_record(rec)
