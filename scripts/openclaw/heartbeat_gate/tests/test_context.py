"""Tests for ``heartbeat_gate.context`` (WP-03 T021)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.openclaw.heartbeat_gate.context import (
    GateContext,
    MissingTickError,
    classify_heartbeat_md,
    load_context,
)
from scripts.openclaw.heartbeat_gate.tests.conftest import write_last_tick


# ---------------------------------------------------------------------------
# classify_heartbeat_md
# ---------------------------------------------------------------------------


def test_classify_empty_string() -> None:
    assert classify_heartbeat_md("") == "empty"


def test_classify_whitespace_only() -> None:
    assert classify_heartbeat_md("   \n   \n\t\n") == "empty"


def test_classify_template_comment_only() -> None:
    text = (
        "# Keep this file empty when nothing is scheduled.\n"
        "# When you want Felix to do something, add a line.\n"
    )
    assert classify_heartbeat_md(text) == "empty"


def test_classify_html_comment_template() -> None:
    text = "<!-- Keep this file empty when nothing scheduled -->\n"
    assert classify_heartbeat_md(text) == "empty"


def test_classify_html_comment_lowercase_template() -> None:
    text = "<!-- keep this file empty for now -->\n"
    assert classify_heartbeat_md(text) == "empty"


def test_classify_heading_only_is_empty() -> None:
    text = "# Today\n\n# Tomorrow\n"
    assert classify_heartbeat_md(text) == "empty"


def test_classify_code_fence_noise_only() -> None:
    # Code fence + horizontal-rule noise only -> still empty.
    text = "```\n```\n---\n"
    assert classify_heartbeat_md(text) == "empty"


def test_classify_has_actionable_task() -> None:
    text = "# Today\n\nReview WP-03 implementation status\n"
    assert classify_heartbeat_md(text) == "has_tasks"


def test_classify_single_actionable_line() -> None:
    assert (
        classify_heartbeat_md("Check whether the gate is firing.")
        == "has_tasks"
    )


def test_classify_mixed_template_and_actionable() -> None:
    text = (
        "# Keep this file empty when nothing scheduled.\n"
        "\n"
        "Run the WhatsApp pairing test at 10am.\n"
    )
    assert classify_heartbeat_md(text) == "has_tasks"


def test_classify_whitespace_only_single_line() -> None:
    # One whitespace-only line should not become "has_tasks".
    assert classify_heartbeat_md("    \n") == "empty"


# ---------------------------------------------------------------------------
# load_context
# ---------------------------------------------------------------------------


def test_load_context_missing_tick_raises(tmp_path: Path) -> None:
    with pytest.raises(MissingTickError):
        load_context(
            tmp_path / "nope.json",
            tmp_path / "heartbeat.md",
            tick_id="01J",
        )


def test_load_context_no_tripped_signals_yields_empty_novelty(
    tmp_path: Path,
) -> None:
    last_tick = write_last_tick(tmp_path / "last-tick.json")
    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text("# Keep this file empty when nothing scheduled\n")
    ctx = load_context(last_tick, hb, tick_id="01JTICK")
    assert isinstance(ctx, GateContext)
    assert ctx.novelty_markers == []
    assert ctx.heartbeat_md_state == "empty"
    assert ctx.digest_snapshot_at_utc == "2026-06-01T17:15:00Z"
    assert ctx.tick_id == "01JTICK"


def test_load_context_two_tripped_signals_yields_both_ids(
    tmp_path: Path,
) -> None:
    signals = [
        {
            "signal_id": "whatsapp_creds_restore",
            "count_cycle": 12,
            "count_rolling": 35,
            "threshold_status": "tripped_both",
        },
        {
            "signal_id": "web_watchdog_reconnect",
            "count_cycle": 10,
            "count_rolling": 25,
            "threshold_status": "tripped_cycle",
        },
        {
            "signal_id": "openclaw_unhandled_error",
            "count_cycle": 0,
            "count_rolling": 0,
            "threshold_status": "below",
        },
    ]
    last_tick = write_last_tick(
        tmp_path / "last-tick.json", signals_evaluated=signals
    )
    ctx = load_context(
        last_tick,
        tmp_path / "missing-heartbeat.md",
        tick_id="01JT",
    )
    assert ctx.novelty_markers == [
        "whatsapp_creds_restore",
        "web_watchdog_reconnect",
    ]
    # Missing HEARTBEAT.md is treated as empty.
    assert ctx.heartbeat_md_state == "empty"


def test_load_context_heartbeat_with_tasks_classified(tmp_path: Path) -> None:
    last_tick = write_last_tick(tmp_path / "last-tick.json")
    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text("# Today\n\nDeploy the heartbeat gate at 10am.\n")
    ctx = load_context(last_tick, hb, tick_id="01JT")
    assert ctx.heartbeat_md_state == "has_tasks"


def test_load_context_propagates_signal_extraction_errors(
    tmp_path: Path,
) -> None:
    errors = [
        {
            "signal_id": "openclaw_unhandled_error",
            "error_type": "source_missing",
            "error_message": "log file not found",
        }
    ]
    last_tick = write_last_tick(tmp_path / "last-tick.json", errors=errors)
    ctx = load_context(
        last_tick, tmp_path / "no-such.md", tick_id="01JT"
    )
    assert ctx.errors == errors


def test_load_context_malformed_json_raises_decode_error(
    tmp_path: Path,
) -> None:
    last_tick = tmp_path / "last-tick.json"
    last_tick.write_text("{not valid json")
    with pytest.raises(json.JSONDecodeError):
        load_context(last_tick, tmp_path / "hb.md", tick_id="01J")


def test_load_context_handles_missing_fields_gracefully(tmp_path: Path) -> None:
    # A minimal but valid JSON without any of the expected keys -> all
    # collection fields default to empty, no exception.
    last_tick = tmp_path / "last-tick.json"
    last_tick.write_text("{}")
    ctx = load_context(last_tick, tmp_path / "hb.md", tick_id="01J")
    assert ctx.signals_evaluated == []
    assert ctx.issues_filed == []
    assert ctx.errors == []
    assert ctx.novelty_markers == []
    assert ctx.digest_snapshot_at_utc == ""
