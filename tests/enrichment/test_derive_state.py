"""Tests for ``scripts.enrichment.derive_state`` (WP02 / T005, T006).

Coverage targets per WP02 § Validation:

- Empty ledger / non-existent file -> None
- Single proposed row -> "proposed"
- Multiple rows -> latest by timestamp
- Terminal-state stickiness (skipped / declined / confirmed):
  a stale proposed row appended AFTER a terminal does NOT change the result
- Per-task isolation: different task_ids tracked independently
- Malformed lines tolerated silently (skip + continue)
- ``derive_states_bulk`` returns one entry per requested id; reads ledger once
- CLI exit codes 0 (success) and 2 (missing ledger path)

All ledger writes land under ``tmp_path``. No Vikunja calls; ``derive_state``
is a pure read-side helper.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

import pytest

from scripts.enrichment import derive_state as derive_state_mod
from scripts.enrichment.derive_state import (
    TERMINAL_STATES,
    derive_state,
    derive_states_bulk,
    main,
)
from scripts.enrichment.schema import VALID_STATES


# ---------------------------------------------------------------------------
# Local helpers + fixtures
# ---------------------------------------------------------------------------


def _row(
    *,
    task_id: int,
    state: str,
    timestamp_utc: str,
    source: str = "agent",
    note: Optional[str] = None,
    schema_version: int = 1,
    extra: Optional[dict] = None,
) -> dict:
    """Build a canonical enrichment record dict."""
    rec = {
        "task_id": task_id,
        "state": state,
        "timestamp_utc": timestamp_utc,
        "source": source,
        "schema_version": schema_version,
        "note": note,
    }
    if extra:
        rec.update(extra)
    return rec


def _write_ledger(path: Path, rows: list[dict]) -> Path:
    """Write rows as JSONL to ``path`` (creates parent dirs)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=False) + "\n")
    return path


@pytest.fixture
def ledger_path(tmp_path: Path) -> Path:
    """Path to a fresh JSONL ledger under tmp_path (not eagerly created)."""
    return tmp_path / "state" / "enrichment" / "enrichment-history.jsonl"


# ---------------------------------------------------------------------------
# Constants smoke
# ---------------------------------------------------------------------------


class TestModuleConstants:
    def test_terminal_states_exact_membership(self):
        """The terminal set is exactly {skipped, declined, confirmed}."""
        assert TERMINAL_STATES == frozenset(
            {"skipped", "declined", "confirmed"}
        )

    def test_terminal_states_subset_of_valid_states(self):
        """Every terminal state must be a valid enrichment state."""
        assert TERMINAL_STATES <= VALID_STATES

    def test_proposed_is_not_terminal(self):
        """``proposed`` is the only non-terminal state."""
        assert "proposed" not in TERMINAL_STATES
        assert "proposed" in VALID_STATES


# ---------------------------------------------------------------------------
# derive_state: empty / missing
# ---------------------------------------------------------------------------


class TestEmptyLedger:
    def test_missing_file_returns_none(self, ledger_path):
        """Missing ledger file -> None (no exception)."""
        assert not ledger_path.exists()
        assert derive_state(1234, ledger_path=ledger_path) is None

    def test_empty_file_returns_none(self, ledger_path):
        """Existing but empty ledger -> None."""
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_text("", encoding="utf-8")
        assert derive_state(1234, ledger_path=ledger_path) is None

    def test_whitespace_only_lines_returns_none(self, ledger_path):
        """File with only blank lines -> None."""
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_text("\n  \n\t\n", encoding="utf-8")
        assert derive_state(1234, ledger_path=ledger_path) is None

    def test_ledger_has_rows_but_not_for_this_task(self, ledger_path):
        """Task with no rows in a populated ledger -> None."""
        _write_ledger(
            ledger_path,
            [
                _row(
                    task_id=1000,
                    state="proposed",
                    timestamp_utc="2026-05-23T19:00:00Z",
                )
            ],
        )
        assert derive_state(9999, ledger_path=ledger_path) is None


# ---------------------------------------------------------------------------
# derive_state: single-row paths
# ---------------------------------------------------------------------------


class TestSingleRow:
    @pytest.mark.parametrize(
        "state", ["proposed", "confirmed", "skipped", "declined"]
    )
    def test_single_row_returns_its_state(self, ledger_path, state):
        """A single row maps to its state for all 4 vocab values."""
        _write_ledger(
            ledger_path,
            [
                _row(
                    task_id=42,
                    state=state,
                    timestamp_utc="2026-05-23T12:00:00Z",
                )
            ],
        )
        assert derive_state(42, ledger_path=ledger_path) == state


# ---------------------------------------------------------------------------
# derive_state: multi-row newest-by-timestamp
# ---------------------------------------------------------------------------


class TestMultiRowNewestWins:
    def test_multiple_proposed_rows_returns_proposed(self, ledger_path):
        """Two proposed rows -> proposed (newest still maps the same state)."""
        _write_ledger(
            ledger_path,
            [
                _row(
                    task_id=10,
                    state="proposed",
                    timestamp_utc="2026-05-20T10:00:00Z",
                ),
                _row(
                    task_id=10,
                    state="proposed",
                    timestamp_utc="2026-05-21T11:00:00Z",
                ),
            ],
        )
        assert derive_state(10, ledger_path=ledger_path) == "proposed"

    def test_proposed_then_confirmed_returns_confirmed(self, ledger_path):
        """proposed then confirmed (terminal) -> confirmed."""
        _write_ledger(
            ledger_path,
            [
                _row(
                    task_id=10,
                    state="proposed",
                    timestamp_utc="2026-05-20T10:00:00Z",
                ),
                _row(
                    task_id=10,
                    state="confirmed",
                    timestamp_utc="2026-05-21T11:00:00Z",
                ),
            ],
        )
        assert derive_state(10, ledger_path=ledger_path) == "confirmed"

    def test_unsorted_input_still_picks_newest(self, ledger_path):
        """Rows can be written in any order; sort happens internally."""
        _write_ledger(
            ledger_path,
            [
                _row(
                    task_id=10,
                    state="confirmed",
                    timestamp_utc="2026-05-21T11:00:00Z",
                ),
                _row(
                    task_id=10,
                    state="proposed",
                    timestamp_utc="2026-05-20T10:00:00Z",
                ),
            ],
        )
        assert derive_state(10, ledger_path=ledger_path) == "confirmed"


# ---------------------------------------------------------------------------
# derive_state: terminal-state stickiness
# ---------------------------------------------------------------------------


class TestTerminalStickiness:
    @pytest.mark.parametrize(
        "terminal", ["skipped", "declined", "confirmed"]
    )
    def test_terminal_then_late_proposed_still_returns_terminal(
        self, ledger_path, terminal
    ):
        """A stale proposed row appended AFTER a terminal does NOT win.

        Single-offer policy: terminal states close the cycle. A misbehaving
        reconcile (or operator-repair) that adds a later ``proposed`` row
        must not re-open the closed cycle.
        """
        _write_ledger(
            ledger_path,
            [
                _row(
                    task_id=10,
                    state="proposed",
                    timestamp_utc="2026-05-20T10:00:00Z",
                ),
                _row(
                    task_id=10,
                    state=terminal,
                    timestamp_utc="2026-05-21T11:00:00Z",
                ),
                # Misbehaving: a later proposed row AFTER the terminal.
                _row(
                    task_id=10,
                    state="proposed",
                    timestamp_utc="2026-05-22T12:00:00Z",
                ),
            ],
        )
        assert (
            derive_state(10, ledger_path=ledger_path) == terminal
        )

    def test_two_terminals_newest_terminal_wins(self, ledger_path):
        """When two terminal states exist, the newest one is returned.

        Realistic scenario: operator_repair overwriting a previous
        skipped with declined (or vice versa).
        """
        _write_ledger(
            ledger_path,
            [
                _row(
                    task_id=10,
                    state="skipped",
                    timestamp_utc="2026-05-21T11:00:00Z",
                ),
                _row(
                    task_id=10,
                    state="declined",
                    timestamp_utc="2026-05-22T12:00:00Z",
                ),
            ],
        )
        assert derive_state(10, ledger_path=ledger_path) == "declined"


# ---------------------------------------------------------------------------
# derive_state: per-task isolation
# ---------------------------------------------------------------------------


class TestPerTaskIsolation:
    def test_two_tasks_with_different_terminals(self, ledger_path):
        """Tasks tracked independently; one task's terminal doesn't bleed into the other."""
        _write_ledger(
            ledger_path,
            [
                _row(
                    task_id=10,
                    state="proposed",
                    timestamp_utc="2026-05-20T10:00:00Z",
                ),
                _row(
                    task_id=20,
                    state="skipped",
                    timestamp_utc="2026-05-20T10:00:00Z",
                ),
                _row(
                    task_id=10,
                    state="confirmed",
                    timestamp_utc="2026-05-21T11:00:00Z",
                ),
                _row(
                    task_id=20,
                    state="declined",
                    timestamp_utc="2026-05-21T11:00:00Z",
                ),
            ],
        )
        assert derive_state(10, ledger_path=ledger_path) == "confirmed"
        # 20: skipped (terminal, sticky) then declined (newer terminal).
        # Per the "newest terminal wins" test, expect declined.
        assert derive_state(20, ledger_path=ledger_path) == "declined"
        assert derive_state(99, ledger_path=ledger_path) is None


# ---------------------------------------------------------------------------
# derive_state: malformed-line tolerance
# ---------------------------------------------------------------------------


class TestMalformedTolerance:
    def test_invalid_json_line_skipped(self, ledger_path):
        """A non-JSON line is skipped; valid lines still produce a result."""
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with ledger_path.open("w", encoding="utf-8") as fh:
            fh.write("{not valid json\n")
            fh.write(
                json.dumps(
                    _row(
                        task_id=10,
                        state="proposed",
                        timestamp_utc="2026-05-23T12:00:00Z",
                    )
                )
                + "\n"
            )
        assert derive_state(10, ledger_path=ledger_path) == "proposed"

    def test_non_dict_payload_skipped(self, ledger_path):
        """A JSON list or scalar line is skipped silently."""
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with ledger_path.open("w", encoding="utf-8") as fh:
            fh.write("[1, 2, 3]\n")
            fh.write('"a string"\n')
            fh.write(
                json.dumps(
                    _row(
                        task_id=10,
                        state="skipped",
                        timestamp_utc="2026-05-23T12:00:00Z",
                    )
                )
                + "\n"
            )
        assert derive_state(10, ledger_path=ledger_path) == "skipped"

    def test_missing_state_field_skipped(self, ledger_path):
        """A row without a ``state`` field is skipped silently."""
        _write_ledger(
            ledger_path,
            [
                {
                    "task_id": 10,
                    "timestamp_utc": "2026-05-23T12:00:00Z",
                    "source": "agent",
                },
                _row(
                    task_id=10,
                    state="confirmed",
                    timestamp_utc="2026-05-23T13:00:00Z",
                ),
            ],
        )
        assert derive_state(10, ledger_path=ledger_path) == "confirmed"

    def test_non_string_state_skipped(self, ledger_path):
        """A row where ``state`` is not a string is ignored."""
        _write_ledger(
            ledger_path,
            [
                {
                    "task_id": 10,
                    "state": 42,
                    "timestamp_utc": "2026-05-23T12:00:00Z",
                    "source": "agent",
                },
                _row(
                    task_id=10,
                    state="declined",
                    timestamp_utc="2026-05-23T13:00:00Z",
                ),
            ],
        )
        assert derive_state(10, ledger_path=ledger_path) == "declined"

    def test_unknown_state_value_skipped(self, ledger_path):
        """A row with an unrecognized state token is ignored at the value-set check."""
        _write_ledger(
            ledger_path,
            [
                {
                    "task_id": 10,
                    "state": "weird_state",
                    "timestamp_utc": "2026-05-23T12:00:00Z",
                    "source": "agent",
                },
            ],
        )
        assert derive_state(10, ledger_path=ledger_path) is None


# ---------------------------------------------------------------------------
# derive_states_bulk
# ---------------------------------------------------------------------------


class TestDeriveStatesBulk:
    def test_bulk_returns_one_entry_per_id(self, ledger_path):
        """Every requested id gets a dict entry (None when no rows exist)."""
        _write_ledger(
            ledger_path,
            [
                _row(
                    task_id=1,
                    state="proposed",
                    timestamp_utc="2026-05-23T12:00:00Z",
                ),
                _row(
                    task_id=2,
                    state="confirmed",
                    timestamp_utc="2026-05-23T13:00:00Z",
                ),
            ],
        )
        result = derive_states_bulk(
            [1, 2, 99], ledger_path=ledger_path
        )
        assert result == {1: "proposed", 2: "confirmed", 99: None}

    def test_bulk_empty_request_returns_empty_dict(self, ledger_path):
        """Empty input list returns an empty result dict."""
        result = derive_states_bulk([], ledger_path=ledger_path)
        assert result == {}

    def test_bulk_missing_file_returns_none_for_all(self, ledger_path):
        """Missing file -> None for every requested id."""
        result = derive_states_bulk(
            [1, 2, 3], ledger_path=ledger_path
        )
        assert result == {1: None, 2: None, 3: None}

    def test_bulk_respects_terminal_stickiness(self, ledger_path):
        """Bulk path uses the same per-task pick logic."""
        _write_ledger(
            ledger_path,
            [
                _row(
                    task_id=1,
                    state="proposed",
                    timestamp_utc="2026-05-20T10:00:00Z",
                ),
                _row(
                    task_id=1,
                    state="skipped",
                    timestamp_utc="2026-05-21T11:00:00Z",
                ),
                _row(
                    task_id=1,
                    state="proposed",
                    timestamp_utc="2026-05-22T12:00:00Z",
                ),
            ],
        )
        assert derive_states_bulk([1], ledger_path=ledger_path) == {
            1: "skipped"
        }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCLI:
    def test_cli_success_emits_json(self, ledger_path, capsys):
        """``main`` returns 0 and prints the result JSON on success."""
        _write_ledger(
            ledger_path,
            [
                _row(
                    task_id=42,
                    state="proposed",
                    timestamp_utc="2026-05-23T12:00:00Z",
                )
            ],
        )
        rc = main(
            ["--task-id", "42", "--ledger-path", str(ledger_path)]
        )
        captured = capsys.readouterr()
        assert rc == 0
        payload = json.loads(captured.out)
        assert payload == {"task_id": 42, "state": "proposed"}

    def test_cli_missing_ledger_returns_2(self, tmp_path, capsys):
        """``main`` returns 2 when the ledger path does not exist."""
        missing = tmp_path / "nope" / "ledger.jsonl"
        rc = main(
            ["--task-id", "42", "--ledger-path", str(missing)]
        )
        captured = capsys.readouterr()
        assert rc == 2
        payload = json.loads(captured.err)
        assert payload["ok"] is False
        assert "ledger path does not exist" in payload["error"]

    def test_cli_task_with_no_rows_returns_null_state(
        self, ledger_path, capsys
    ):
        """``main`` returns 0 with ``state=None`` when the task has no rows."""
        _write_ledger(
            ledger_path,
            [
                _row(
                    task_id=1,
                    state="proposed",
                    timestamp_utc="2026-05-23T12:00:00Z",
                )
            ],
        )
        rc = main(
            ["--task-id", "999", "--ledger-path", str(ledger_path)]
        )
        captured = capsys.readouterr()
        assert rc == 0
        payload = json.loads(captured.out)
        assert payload == {"task_id": 999, "state": None}
