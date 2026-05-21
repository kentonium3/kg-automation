"""Unit tests for ``doc_audit.output.tick_signal``.

Verifies the writer against
``kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/
contracts/tick-signal.contract.md`` schema v1.0:

- Atomic write semantics (tempfile-then-rename in same directory).
- Current-state overwrite semantics (second call replaces first).
- Parent directory auto-creation.
- Schema completeness (every contract field present, correct types).
- Status / exit_code alignment per the contract table.
- ``print_summary_line`` format matches the canonical SUMMARY: pattern.
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
from typing import Any

import pytest

from doc_audit.data_model import TickResult
from doc_audit.output.tick_signal import (
    DRIVER_VERSION,
    SCHEMA_VERSION,
    _build_signal_dict,
    _compute_duration,
    print_summary_line,
    write_tick_signal,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(
    *,
    status: str = "success",
    started_utc: str = "2026-05-20T16:00:00Z",
    ended_utc: str = "2026-05-20T16:00:07Z",
    signals_seen: int = 2,
    signals_processed: int = 2,
    audits_processed: list[int] | None = None,
    pending_approvals_applied: list[int] | None = None,
    pending_approvals_filed: list[int] | None = None,
    tier_a_commits: list[str] | None = None,
    debt_filed: list[int] | None = None,
    drift_events_consumed: int = 0,
    errors: list[str] | None = None,
    judgment_calls: dict[str, int] | None = None,
    token_usage: dict[str, int] | None = None,
) -> TickResult:
    result = TickResult(
        started_utc=started_utc,
        ended_utc=ended_utc,
        status=status,
        signals_seen=signals_seen,
        signals_processed=signals_processed,
        tier_a_commits=list(tier_a_commits or []),
        pending_approvals_filed=list(pending_approvals_filed or []),
        pending_approvals_applied=list(pending_approvals_applied or []),
        debt_filed=list(debt_filed or []),
        drift_events_consumed=drift_events_consumed,
        errors=list(errors or []),
        judgment_calls=dict(
            judgment_calls
            or {
                "tier_classification": 0,
                "debt_body_generation": 0,
                "cross_file_implication": 0,
            }
        ),
        token_usage=dict(
            token_usage
            or {
                "input_tokens": 0,
                "cache_hit_input_tokens": 0,
                "output_tokens": 0,
            }
        ),
    )
    # The data-model E-008 doesn't carry audits_processed today; the
    # driver attaches it dynamically. Match that pattern in tests.
    result.audits_processed = list(audits_processed or [])
    return result


# ---------------------------------------------------------------------------
# _compute_duration
# ---------------------------------------------------------------------------


def test_compute_duration_basic():
    result = _make_result(
        started_utc="2026-05-20T16:00:00Z",
        ended_utc="2026-05-20T16:00:07Z",
    )
    assert _compute_duration(result) == pytest.approx(7.0)


def test_compute_duration_unparseable_returns_zero():
    result = _make_result(started_utc="not-a-time", ended_utc="also-not")
    assert _compute_duration(result) == 0.0


def test_compute_duration_missing_field_returns_zero():
    result = _make_result(started_utc="", ended_utc="")
    assert _compute_duration(result) == 0.0


# ---------------------------------------------------------------------------
# _build_signal_dict — schema completeness
# ---------------------------------------------------------------------------


CONTRACT_TOP_KEYS = {
    "schema_version",
    "timestamp_utc",
    "status",
    "exit_code",
    "driver_version",
    "duration_seconds",
    "host",
    "tick",
    "judgment",
    "errors",
    "next_scheduled_tick_utc",
}

CONTRACT_TICK_KEYS = {
    "signals_seen",
    "signals_processed",
    "audits_processed",
    "pending_approvals_applied",
    "pending_approvals_filed",
    "tier_a_commits",
    "debt_filed",
    "drift_events_consumed",
}

CONTRACT_JUDGMENT_KEYS = {
    "tier_classification_calls",
    "debt_body_generation_calls",
    "cross_file_implication_calls",
    "input_tokens",
    "cache_hit_input_tokens",
    "output_tokens",
}


def test_signal_dict_top_keys_match_contract():
    result = _make_result()
    d = _build_signal_dict(result, "2026-05-20T17:00:00Z")
    assert set(d.keys()) == CONTRACT_TOP_KEYS


def test_signal_dict_tick_keys_match_contract():
    result = _make_result()
    d = _build_signal_dict(result, "2026-05-20T17:00:00Z")
    assert set(d["tick"].keys()) == CONTRACT_TICK_KEYS


def test_signal_dict_judgment_keys_match_contract():
    result = _make_result()
    d = _build_signal_dict(result, "2026-05-20T17:00:00Z")
    assert set(d["judgment"].keys()) == CONTRACT_JUDGMENT_KEYS


def test_signal_dict_schema_version_locked():
    result = _make_result()
    d = _build_signal_dict(result, "2026-05-20T17:00:00Z")
    assert d["schema_version"] == "1.0"
    assert SCHEMA_VERSION == "1.0"


def test_signal_dict_driver_version_locked():
    result = _make_result()
    d = _build_signal_dict(result, "2026-05-20T17:00:00Z")
    assert d["driver_version"] == DRIVER_VERSION


# ---------------------------------------------------------------------------
# status ↔ exit_code alignment
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status,expected_exit",
    [("success", 0), ("partial", 2), ("failure", 1)],
)
def test_status_maps_to_correct_exit_code(status: str, expected_exit: int):
    result = _make_result(status=status)
    d = _build_signal_dict(result, "2026-05-20T17:00:00Z")
    assert d["status"] == status
    assert d["exit_code"] == expected_exit


def test_unknown_status_defaults_to_failure_exit_code():
    result = _make_result(status="bogus")
    d = _build_signal_dict(result, "2026-05-20T17:00:00Z")
    # Status preserved truthfully; exit_code defaults to 1 (failure).
    assert d["status"] == "bogus"
    assert d["exit_code"] == 1


def test_failure_status_written(tmp_config):
    """Contract: failure status → JSON has exit_code=1."""
    result = _make_result(status="failure", errors=["something broke"])
    target = write_tick_signal(tmp_config, result, "2026-05-20T17:00:00Z")
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["status"] == "failure"
    assert data["exit_code"] == 1
    assert data["errors"] == ["something broke"]


# ---------------------------------------------------------------------------
# Atomic write semantics
# ---------------------------------------------------------------------------


def test_write_creates_artifact_at_configured_path(tmp_config):
    result = _make_result()
    target = write_tick_signal(tmp_config, result, "2026-05-20T17:00:00Z")
    assert target == Path(tmp_config.paths.tick_signal_path)
    assert target.exists()


def test_write_signal_atomic_no_tmp_remnant(tmp_config):
    """After a successful write, no ``*.tmp`` siblings should remain."""
    result = _make_result()
    target = write_tick_signal(tmp_config, result, "2026-05-20T17:00:00Z")
    parent = target.parent
    leftovers = [p for p in parent.iterdir() if p.suffix == ".tmp"]
    assert leftovers == [], f"tempfile leaked: {leftovers}"


def test_write_signal_overwrites_existing(tmp_config):
    """Current-state semantics: second call overwrites first."""
    first = _make_result(status="success", signals_seen=1)
    write_tick_signal(tmp_config, first, "2026-05-20T17:00:00Z")

    second = _make_result(status="failure", signals_seen=5, errors=["nope"])
    target = write_tick_signal(tmp_config, second, "2026-05-20T18:00:00Z")

    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["status"] == "failure"
    assert data["tick"]["signals_seen"] == 5
    assert data["errors"] == ["nope"]


def test_write_signal_creates_parent_dir(tmp_config, tmp_path):
    """Parent directory is auto-created if absent."""
    # Repoint tick_signal_path at a deeper, not-yet-existing dir.
    deeper = tmp_path / "deep" / "nested" / "last-tick.json"
    # The Config is frozen, so swap the entire path object via a
    # fresh PathsConfig:
    from dataclasses import replace as _replace
    new_paths = _replace(tmp_config.paths, tick_signal_path=str(deeper))
    new_config = _replace(tmp_config, paths=new_paths)

    result = _make_result()
    target = write_tick_signal(new_config, result, "2026-05-20T17:00:00Z")
    assert target == deeper
    assert deeper.exists()
    assert deeper.parent.is_dir()


def test_write_signal_serializes_lists_by_value(tmp_config):
    """Mutating the source TickResult AFTER write does not affect the file."""
    result = _make_result(tier_a_commits=["abc"], debt_filed=[100])
    target = write_tick_signal(tmp_config, result, "2026-05-20T17:00:00Z")

    # Mutate source after write.
    result.tier_a_commits.append("def")
    result.debt_filed.append(200)

    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["tick"]["tier_a_commits"] == ["abc"]
    assert data["tick"]["debt_filed"] == [100]


def test_write_uses_os_rename_not_shutil_move(tmp_config, monkeypatch):
    """Atomic write goes through ``os.rename``, not ``shutil.move``."""
    calls: dict[str, int] = {"rename": 0, "move": 0}
    real_rename = os.rename

    def counting_rename(src, dst):
        calls["rename"] += 1
        return real_rename(src, dst)

    monkeypatch.setattr(
        "doc_audit.output.tick_signal.os.rename", counting_rename
    )

    result = _make_result()
    write_tick_signal(tmp_config, result, "2026-05-20T17:00:00Z")
    assert calls["rename"] == 1


# ---------------------------------------------------------------------------
# Schema completeness against the contract example
# ---------------------------------------------------------------------------


def test_signal_schema_complete_against_contract_example(tmp_config):
    """Written JSON has every field shown in the contract's example."""
    result = _make_result(
        signals_seen=2,
        signals_processed=2,
        audits_processed=[320, 321],
        tier_a_commits=["abc1234"],
        debt_filed=[340],
        judgment_calls={
            "tier_classification": 3,
            "debt_body_generation": 1,
            "cross_file_implication": 0,
        },
        token_usage={
            "input_tokens": 6420,
            "cache_hit_input_tokens": 4180,
            "output_tokens": 540,
        },
    )
    target = write_tick_signal(tmp_config, result, "2026-05-20T17:00:00Z")
    data = json.loads(target.read_text(encoding="utf-8"))

    # Top-level
    assert data["schema_version"] == "1.0"
    assert data["status"] == "success"
    assert data["exit_code"] == 0
    assert isinstance(data["duration_seconds"], (int, float))
    assert data["next_scheduled_tick_utc"] == "2026-05-20T17:00:00Z"
    assert isinstance(data["host"], str) and data["host"]

    # tick.*
    tick = data["tick"]
    assert tick["signals_seen"] == 2
    assert tick["audits_processed"] == [320, 321]
    assert tick["tier_a_commits"] == ["abc1234"]
    assert tick["debt_filed"] == [340]

    # judgment.*
    j = data["judgment"]
    assert j["tier_classification_calls"] == 3
    assert j["debt_body_generation_calls"] == 1
    assert j["input_tokens"] == 6420
    assert j["cache_hit_input_tokens"] == 4180
    assert j["output_tokens"] == 540


# ---------------------------------------------------------------------------
# print_summary_line
# ---------------------------------------------------------------------------


def test_print_summary_line_format(capsys):
    result = _make_result(
        status="success",
        audits_processed=[1, 2, 3],
        tier_a_commits=["abc1234"],
        debt_filed=[100, 101],
        drift_events_consumed=4,
        token_usage={
            "input_tokens": 1000,
            "cache_hit_input_tokens": 500,
            "output_tokens": 200,
        },
        started_utc="2026-05-20T16:00:00Z",
        ended_utc="2026-05-20T16:00:07Z",
    )
    print_summary_line(result)
    out = capsys.readouterr().out.strip()
    # The exact canonical format per contract §"Stdout-summary line".
    assert out == (
        "SUMMARY: status=success audits=3 debt=2 tier_a=1 drift=4 "
        "dur=7.0s tokens=in:1000(cache:500)/out:200"
    )


def test_print_summary_line_zero_state(capsys):
    """Empty result produces a single canonical line with zeros."""
    result = _make_result(
        status="success",
        audits_processed=[],
        tier_a_commits=[],
        debt_filed=[],
        drift_events_consumed=0,
        token_usage={
            "input_tokens": 0,
            "cache_hit_input_tokens": 0,
            "output_tokens": 0,
        },
    )
    print_summary_line(result)
    out = capsys.readouterr().out.strip()
    assert out.startswith("SUMMARY: status=success audits=0 debt=0 tier_a=0 ")


def test_print_summary_line_failure_status(capsys):
    result = _make_result(status="failure", errors=["network broke"])
    print_summary_line(result)
    out = capsys.readouterr().out
    assert "status=failure" in out
