"""Tests for ``heartbeat_gate.validate_ledger`` (#676 T007-T010, INV-006).

Two independent things are proven here, matching the contract's scope
note for the historical-fidelity invariant:

1. **Ledger replay** (``replay_ledger`` / ``iter_ledger_records`` /
   ``main``): recomputes the escalate-vs-not boolean from
   ``novelty_markers_seen`` / ``heartbeat_md_state`` / ``errors`` for
   every record in a committed fixture ledger and asserts 0 missed
   escalations. A second, deliberately-mislabeled fixture proves the
   harness actually fails (non-zero exit / missed > 0) when the
   invariant is violated -- i.e. the gate has teeth.

2. **Synthetic label-split fixtures** (direct ``GateContext`` +
   ``decide_deterministic`` calls): the ledger does NOT carry
   ``issues_filed`` or ``signals_evaluated``, so the ``LOG_AND_SKIP`` vs.
   ``HEARTBEAT_OK`` split can only be validated by hand-built contexts,
   per the contract's "Historical-fidelity invariant" scope note. These
   tests import ``decide_deterministic`` directly -- the SAME function
   the replay imports -- so there is exactly one source of truth for the
   escalation rule across both this file and ``gate.py``.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.openclaw.heartbeat_gate.context import GateContext
from scripts.openclaw.heartbeat_gate.gate import decide_deterministic
from scripts.openclaw.heartbeat_gate.validate_ledger import (
    OVER_ESCALATION_THRESHOLD_PCT,
    ReplayResult,
    iter_ledger_records,
    main,
    replay_ledger,
)


FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_LEDGER = FIXTURES_DIR / "gate-ledger-sample.jsonl"
MISLABELED_LEDGER = FIXTURES_DIR / "gate-ledger-mislabeled.jsonl"


# ---------------------------------------------------------------------------
# T010: replay against the committed fixture -- 0 missed, over within
# threshold
# ---------------------------------------------------------------------------


def test_replay_fixture_ledger_has_zero_missed() -> None:
    result = replay_ledger(iter_ledger_records(SAMPLE_LEDGER))
    assert result.missed == 0
    assert result.missed_tick_ids == []


def test_replay_fixture_ledger_over_escalation_within_threshold() -> None:
    result = replay_ledger(iter_ledger_records(SAMPLE_LEDGER))
    assert result.over_escalation_pct <= OVER_ESCALATION_THRESHOLD_PCT


def test_replay_fixture_ledger_passed_is_true() -> None:
    result = replay_ledger(iter_ledger_records(SAMPLE_LEDGER))
    assert result.passed is True


def test_replay_fixture_ledger_counts_all_five_records() -> None:
    result = replay_ledger(iter_ledger_records(SAMPLE_LEDGER))
    assert result.total == 5
    # 3 escalate (novelty / has_tasks / errors) + 1 HEARTBEAT_OK +
    # 1 LOG_AND_SKIP, per the fixture's committed shape (T008).
    assert result.actual_escalate == 3
    assert result.actual_non_escalate == 2


# ---------------------------------------------------------------------------
# T010: deliberately-mislabeled fixture proves the harness FAILS as
# designed
# ---------------------------------------------------------------------------


def test_replay_mislabeled_fixture_detects_missed_escalation() -> None:
    """A ledger record claiming ESCALATE_TO_SONNET with no firing trigger
    must be counted as ``missed`` -- proving the gate has teeth.
    """
    result = replay_ledger(iter_ledger_records(MISLABELED_LEDGER))
    assert result.missed == 1
    assert "01JBAD0002" in result.missed_tick_ids
    assert result.passed is False


def test_cli_exit_code_zero_on_clean_fixture() -> None:
    exit_code = main(["--ledger", str(SAMPLE_LEDGER)])
    assert exit_code == 0


def test_cli_exit_code_nonzero_on_mislabeled_fixture() -> None:
    exit_code = main(["--ledger", str(MISLABELED_LEDGER)])
    assert exit_code != 0


def test_cli_subprocess_module_invocation_exit_codes() -> None:
    """End-to-end: invoke as ``python3 -m scripts...validate_ledger`` (the
    documented invocation form, C-006) and check real process exit codes.
    """
    repo_root = Path(__file__).resolve().parents[4]

    clean = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.openclaw.heartbeat_gate.validate_ledger",
            "--ledger",
            str(SAMPLE_LEDGER),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    assert clean.returncode == 0, clean.stderr

    bad = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.openclaw.heartbeat_gate.validate_ledger",
            "--ledger",
            str(MISLABELED_LEDGER),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    assert bad.returncode != 0


def test_cli_missing_ledger_file_exits_nonzero(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.jsonl"
    exit_code = main(["--ledger", str(missing)])
    assert exit_code != 0


# ---------------------------------------------------------------------------
# iter_ledger_records: JSONL parsing
# ---------------------------------------------------------------------------


def test_iter_ledger_records_skips_blank_lines(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(
        '{"tick_id": "a", "outcome": "HEARTBEAT_OK"}\n'
        "\n"
        '{"tick_id": "b", "outcome": "HEARTBEAT_OK"}\n',
        encoding="utf-8",
    )
    records = list(iter_ledger_records(ledger))
    assert len(records) == 2
    assert records[0]["tick_id"] == "a"
    assert records[1]["tick_id"] == "b"


def test_iter_ledger_records_raises_on_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "nope.jsonl"
    with pytest.raises(FileNotFoundError):
        list(iter_ledger_records(missing))


# ---------------------------------------------------------------------------
# ReplayResult properties
# ---------------------------------------------------------------------------


def test_replay_result_over_escalation_pct_zero_when_empty() -> None:
    result = ReplayResult(
        total=0, actual_escalate=0, actual_non_escalate=0, missed=0, over=0
    )
    assert result.over_escalation_pct == 0.0
    assert result.passed is True


def test_replay_result_fails_when_over_escalation_exceeds_threshold() -> None:
    # 2 out of 10 records over-escalated => 20% > 5% threshold.
    result = ReplayResult(
        total=10,
        actual_escalate=0,
        actual_non_escalate=10,
        missed=0,
        over=2,
        over_tick_ids=["a", "b"],
    )
    assert result.over_escalation_pct == 20.0
    assert result.passed is False


# ---------------------------------------------------------------------------
# T009: synthetic GateContext label-split fixtures (ledger replay cannot
# cover this per the contract's scope note -- LOG_AND_SKIP vs
# HEARTBEAT_OK needs issues_filed / signals_evaluated, which the ledger
# does not persist)
# ---------------------------------------------------------------------------


def _quiet_context(**overrides: object) -> GateContext:
    defaults: dict[str, object] = dict(
        tick_id="01JSYN0001",
        digest_snapshot_at_utc="2026-06-01T17:15:00Z",
        signals_evaluated=[],
        issues_filed=[],
        errors=[],
        heartbeat_md_state="empty",
        novelty_markers=[],
    )
    defaults.update(overrides)
    return GateContext(**defaults)  # type: ignore[arg-type]


def test_label_split_issues_filed_nonempty_is_log_and_skip() -> None:
    ctx = _quiet_context(
        issues_filed=[{"signal_id": "whatsapp_creds_restore", "issue_number": 491}],
    )
    decision = decide_deterministic(ctx)
    assert decision.outcome == "LOG_AND_SKIP"


def test_label_split_below_threshold_nonzero_activity_is_log_and_skip() -> None:
    ctx = _quiet_context(
        signals_evaluated=[
            {
                "signal_id": "web_watchdog_reconnect",
                "count_cycle": 2,
                "count_rolling": 5,
                "threshold_status": "below",
            },
        ],
    )
    decision = decide_deterministic(ctx)
    assert decision.outcome == "LOG_AND_SKIP"


def test_label_split_fully_quiet_is_heartbeat_ok() -> None:
    ctx = _quiet_context()
    decision = decide_deterministic(ctx)
    assert decision.outcome == "HEARTBEAT_OK"


def test_label_split_novelty_trigger_is_escalate() -> None:
    ctx = _quiet_context(novelty_markers=["whatsapp_creds_restore"])
    decision = decide_deterministic(ctx)
    assert decision.outcome == "ESCALATE_TO_SONNET"


def test_label_split_has_tasks_trigger_is_escalate() -> None:
    ctx = _quiet_context(heartbeat_md_state="has_tasks")
    decision = decide_deterministic(ctx)
    assert decision.outcome == "ESCALATE_TO_SONNET"


def test_label_split_errors_trigger_is_escalate() -> None:
    ctx = _quiet_context(errors=[{"error_type": "source_missing"}])
    decision = decide_deterministic(ctx)
    assert decision.outcome == "ESCALATE_TO_SONNET"
