"""Unit tests for ``scripts/openclaw/heartbeat_gate/baselines/measure-tokens.py``.

The module file uses a hyphenated name (CLI convention), so it is
imported via ``importlib.util.spec_from_file_location`` rather than the
usual ``from scripts...`` form.

Coverage focus:
- :func:`aggregate_session` -- preamble detection, tick boundary,
  multi-key usage aliases, optional window filter.
- :func:`aggregate_session_dir` -- multi-file walk + merge.
- :func:`build_historical_baseline` -- observed-cost-vs-list-pricing
  selection and methodology echo.
- :func:`_atomic_write_json` -- write-tmp+rename invariant.
- CLI ``main`` -- happy paths (single session, session-dir, sample
  fallback) and error paths (missing source, no-tick aggregate).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Import the hyphenated module by path.
# ---------------------------------------------------------------------------

_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "baselines" / "measure-tokens.py"
)
_spec = importlib.util.spec_from_file_location("measure_tokens", _MODULE_PATH)
assert _spec is not None and _spec.loader is not None
measure_tokens = importlib.util.module_from_spec(_spec)
sys.modules["measure_tokens"] = measure_tokens
_spec.loader.exec_module(measure_tokens)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _user(text: str, ts: str = "2026-05-10T12:00:00.000Z") -> dict:
    """Build a user-role message record matching the OpenClaw shape."""
    return {
        "type": "message",
        "timestamp": ts,
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": text}],
        },
    }


def _assistant(
    *,
    text: str = "OK",
    ts: str = "2026-05-10T12:00:01.000Z",
    usage: dict[str, Any] | None = None,
) -> dict:
    """Build an assistant-role message with the OpenClaw `usage` shape."""
    msg: dict[str, Any] = {
        "role": "assistant",
        "content": [{"type": "text", "text": text}],
    }
    if usage is not None:
        msg["usage"] = usage
    return {"type": "message", "timestamp": ts, "message": msg}


def _write_jsonl(path: Path, records: list[dict]) -> Path:
    path.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )
    return path


HB_PREAMBLE = (
    "System: [2026-05-10 12:00:00 UTC] WhatsApp gateway connected.\n\n"
    "Read HEARTBEAT.md if it exists (workspace context). Follow it "
    "strictly. Do not infer or repeat old tasks from prior chats. If "
    "nothing needs attention, reply HEARTBEAT_OK."
)


# ---------------------------------------------------------------------------
# aggregate_session
# ---------------------------------------------------------------------------


class TestAggregateSession:
    def test_picks_up_heartbeat_via_preamble_substring(self, tmp_path: Path) -> None:
        f = tmp_path / "s.jsonl"
        _write_jsonl(
            f,
            [
                _user(HB_PREAMBLE, ts="2026-05-10T12:00:00Z"),
                _assistant(
                    text="HEARTBEAT_OK",
                    usage={
                        "input": 5,
                        "output": 8,
                        "cacheRead": 1000,
                        "cacheWrite": 200,
                        "cost": {"total": 0.42},
                    },
                ),
            ],
        )
        agg = measure_tokens.aggregate_session(f)
        assert agg["tick_count"] == 1
        assert agg["total_input_tokens"] == 5
        assert agg["total_output_tokens"] == 8
        assert agg["total_cache_read_input_tokens"] == 1000
        assert agg["total_cache_write_input_tokens"] == 200
        assert agg["total_cost_usd_observed"] == pytest.approx(0.42)
        assert agg["earliest_tick_utc"] == "2026-05-10T12:00:00Z"
        assert agg["latest_tick_utc"] == "2026-05-10T12:00:00Z"

    def test_supports_anthropic_sdk_long_form_usage_keys(
        self, tmp_path: Path
    ) -> None:
        """SDK uses ``input_tokens`` / ``cache_read_input_tokens`` etc."""
        f = tmp_path / "s.jsonl"
        _write_jsonl(
            f,
            [
                _user(HB_PREAMBLE),
                _assistant(
                    usage={
                        "input_tokens": 7,
                        "output_tokens": 9,
                        "cache_read_input_tokens": 2000,
                        "cache_creation_input_tokens": 100,
                    }
                ),
            ],
        )
        agg = measure_tokens.aggregate_session(f)
        assert agg["total_input_tokens"] == 7
        assert agg["total_output_tokens"] == 9
        assert agg["total_cache_read_input_tokens"] == 2000
        assert agg["total_cache_write_input_tokens"] == 100

    def test_ignores_non_heartbeat_user_turns(self, tmp_path: Path) -> None:
        """A WhatsApp turn must not be counted as a heartbeat."""
        f = tmp_path / "s.jsonl"
        _write_jsonl(
            f,
            [
                _user("Conversation info (untrusted metadata): hi"),
                _assistant(
                    text="NO_REPLY",
                    usage={"input": 99, "output": 99, "cost": {"total": 9.99}},
                ),
                _user(HB_PREAMBLE, ts="2026-05-10T13:00:00Z"),
                _assistant(
                    text="HEARTBEAT_OK",
                    usage={"input": 1, "output": 2, "cost": {"total": 0.01}},
                ),
            ],
        )
        agg = measure_tokens.aggregate_session(f)
        assert agg["tick_count"] == 1
        # The 9.99 from the WhatsApp turn must not leak in.
        assert agg["total_input_tokens"] == 1
        assert agg["total_output_tokens"] == 2
        assert agg["total_cost_usd_observed"] == pytest.approx(0.01)

    def test_resets_in_tick_on_subsequent_non_heartbeat_user_turn(
        self, tmp_path: Path
    ) -> None:
        f = tmp_path / "s.jsonl"
        _write_jsonl(
            f,
            [
                _user(HB_PREAMBLE, ts="2026-05-10T12:00:00Z"),
                _assistant(usage={"input": 1, "output": 1}),
                _user("Conversation info: hi", ts="2026-05-10T12:30:00Z"),
                # This assistant turn is NOT in a heartbeat anymore.
                _assistant(usage={"input": 999, "output": 999}),
            ],
        )
        agg = measure_tokens.aggregate_session(f)
        assert agg["tick_count"] == 1
        assert agg["total_input_tokens"] == 1

    def test_multi_assistant_turns_within_one_tick_are_summed(
        self, tmp_path: Path
    ) -> None:
        f = tmp_path / "s.jsonl"
        _write_jsonl(
            f,
            [
                _user(HB_PREAMBLE),
                _assistant(usage={"input": 2, "output": 3}),
                _assistant(usage={"input": 4, "output": 5}),
            ],
        )
        agg = measure_tokens.aggregate_session(f)
        assert agg["total_input_tokens"] == 6
        assert agg["total_output_tokens"] == 8

    def test_window_filter_excludes_ticks_outside_bounds(
        self, tmp_path: Path
    ) -> None:
        f = tmp_path / "s.jsonl"
        _write_jsonl(
            f,
            [
                _user(HB_PREAMBLE, ts="2026-04-01T00:00:00Z"),
                _assistant(usage={"input": 1, "output": 1}),
                _user(HB_PREAMBLE, ts="2026-05-10T12:00:00Z"),
                _assistant(usage={"input": 2, "output": 2}),
                _user(HB_PREAMBLE, ts="2026-06-15T00:00:00Z"),
                _assistant(usage={"input": 3, "output": 3}),
            ],
        )
        agg = measure_tokens.aggregate_session(
            f,
            window_start="2026-05-01T00:00:00Z",
            window_end="2026-06-01T00:00:00Z",
        )
        assert agg["tick_count"] == 1
        assert agg["total_input_tokens"] == 2
        assert agg["earliest_tick_utc"] == "2026-05-10T12:00:00Z"

    def test_window_end_is_exclusive(self, tmp_path: Path) -> None:
        f = tmp_path / "s.jsonl"
        _write_jsonl(
            f,
            [
                _user(HB_PREAMBLE, ts="2026-05-19T00:00:00Z"),
                _assistant(usage={"input": 1, "output": 1}),
            ],
        )
        agg = measure_tokens.aggregate_session(
            f, window_end="2026-05-19T00:00:00Z"
        )
        assert agg["tick_count"] == 0

    def test_malformed_line_is_skipped_with_warning(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        f = tmp_path / "s.jsonl"
        f.write_text(
            json.dumps(_user(HB_PREAMBLE))
            + "\nnot-json\n"
            + json.dumps(_assistant(usage={"input": 1, "output": 1}))
            + "\n",
            encoding="utf-8",
        )
        agg = measure_tokens.aggregate_session(f)
        assert agg["tick_count"] == 1
        assert agg["total_input_tokens"] == 1
        err = capsys.readouterr().err
        assert "malformed line 2" in err

    def test_user_text_string_form_is_supported(self, tmp_path: Path) -> None:
        """Some OpenClaw records carry `content` as a string, not a list."""
        f = tmp_path / "s.jsonl"
        record_user = {
            "type": "message",
            "timestamp": "2026-05-10T12:00:00Z",
            "message": {"role": "user", "content": HB_PREAMBLE},
        }
        _write_jsonl(
            f,
            [
                record_user,
                _assistant(usage={"input": 1, "output": 1}),
            ],
        )
        agg = measure_tokens.aggregate_session(f)
        assert agg["tick_count"] == 1


# ---------------------------------------------------------------------------
# aggregate_session_dir
# ---------------------------------------------------------------------------


class TestAggregateSessionDir:
    def test_walks_all_jsonl_variants(self, tmp_path: Path) -> None:
        d = tmp_path / "sessions"
        d.mkdir()
        _write_jsonl(
            d / "active.jsonl",
            [
                _user(HB_PREAMBLE, ts="2026-05-10T12:00:00Z"),
                _assistant(usage={"input": 1, "output": 1, "cost": {"total": 0.10}}),
            ],
        )
        _write_jsonl(
            d / "old.jsonl.reset.2026-05-09T04-00-00Z",
            [
                _user(HB_PREAMBLE, ts="2026-05-09T12:00:00Z"),
                _assistant(usage={"input": 2, "output": 2, "cost": {"total": 0.20}}),
            ],
        )
        _write_jsonl(
            d / "stale.jsonl.deleted.2026-05-08T04-00-00Z",
            [
                _user(HB_PREAMBLE, ts="2026-05-08T12:00:00Z"),
                _assistant(usage={"input": 3, "output": 3, "cost": {"total": 0.30}}),
            ],
        )
        # Non-session noise — must NOT be walked.
        (d / "README.txt").write_text("ignore me", encoding="utf-8")
        agg = measure_tokens.aggregate_session_dir(d)
        assert agg["files_walked"] == 3
        assert agg["tick_count"] == 3
        assert agg["total_input_tokens"] == 6
        assert agg["total_cost_usd_observed"] == pytest.approx(0.60)
        assert agg["earliest_tick_utc"] == "2026-05-08T12:00:00Z"
        assert agg["latest_tick_utc"] == "2026-05-10T12:00:00Z"

    def test_window_filter_applies_across_files(self, tmp_path: Path) -> None:
        d = tmp_path / "sessions"
        d.mkdir()
        _write_jsonl(
            d / "a.jsonl",
            [
                _user(HB_PREAMBLE, ts="2026-04-01T00:00:00Z"),
                _assistant(usage={"input": 100, "output": 100}),
            ],
        )
        _write_jsonl(
            d / "b.jsonl",
            [
                _user(HB_PREAMBLE, ts="2026-05-10T00:00:00Z"),
                _assistant(usage={"input": 1, "output": 1}),
            ],
        )
        agg = measure_tokens.aggregate_session_dir(
            d,
            window_start="2026-05-01T00:00:00Z",
            window_end="2026-06-01T00:00:00Z",
        )
        assert agg["tick_count"] == 1
        assert agg["total_input_tokens"] == 1

    def test_empty_dir_returns_zero_tick_count(self, tmp_path: Path) -> None:
        d = tmp_path / "empty-sessions"
        d.mkdir()
        agg = measure_tokens.aggregate_session_dir(d)
        assert agg["tick_count"] == 0
        assert agg["files_walked"] == 0
        assert agg["earliest_tick_utc"] is None
        assert agg["latest_tick_utc"] is None


# ---------------------------------------------------------------------------
# build_historical_baseline
# ---------------------------------------------------------------------------


class TestBuildHistoricalBaseline:
    def test_observed_cost_is_used_when_present(self) -> None:
        agg = {
            "tick_count": 10,
            "earliest_tick_utc": "2026-05-05T00:00:00Z",
            "latest_tick_utc": "2026-05-18T00:00:00Z",
            "total_input_tokens": 50,
            "total_cache_read_input_tokens": 1000,
            "total_cache_write_input_tokens": 500,
            "total_output_tokens": 200,
            "total_cost_usd_observed": 1.50,
            "files_walked": 5,
        }
        payload = measure_tokens.build_historical_baseline(
            agg,
            window_days=14,
            git_sha="abc123",
            git_branch="feat/foo",
            source_path=Path("/tmp/sessions"),
            source_kind="session-dir",
            window_start="2026-05-05T00:00:00Z",
            window_end="2026-05-19T00:00:00Z",
        )
        assert payload["cost_source"] == "observed-from-session-log"
        assert payload["observed_total_cost_usd"] == pytest.approx(1.5)
        assert payload["total_heartbeats"] == 10
        assert payload["ticks_per_day"] == pytest.approx(10 / 14)
        # estimated_monthly_cost_usd uses observed cost: 1.5/14 * 30
        assert payload["estimated_monthly_cost_usd"] == pytest.approx(
            round(1.5 / 14 * 30, 2)
        )
        assert payload["subject"]["git_sha"] == "abc123"
        assert payload["subject"]["files_walked"] == 5
        assert (
            payload["methodology"]["window_start_filter_utc"]
            == "2026-05-05T00:00:00Z"
        )

    def test_falls_back_to_list_pricing_when_observed_cost_missing(self) -> None:
        agg = {
            "tick_count": 1,
            "earliest_tick_utc": None,
            "latest_tick_utc": None,
            "total_input_tokens": 1_000_000,  # 1M input @ $3/MTok = $3
            "total_cache_read_input_tokens": 0,
            "total_cache_write_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost_usd_observed": 0.0,
        }
        payload = measure_tokens.build_historical_baseline(
            agg,
            window_days=1,
            git_sha="",
            git_branch="",
            source_path=Path("/tmp/x"),
        )
        assert payload["cost_source"] == "computed-from-list-pricing"
        assert payload["estimated_total_cost_usd_from_list_pricing"] == pytest.approx(
            3.0
        )

    def test_window_days_zero_does_not_divide(self) -> None:
        agg = {
            "tick_count": 0,
            "earliest_tick_utc": None,
            "latest_tick_utc": None,
            "total_input_tokens": 0,
            "total_cache_read_input_tokens": 0,
            "total_cache_write_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost_usd_observed": 0.0,
        }
        payload = measure_tokens.build_historical_baseline(
            agg,
            window_days=0,
            git_sha="",
            git_branch="",
            source_path=Path("/tmp/x"),
        )
        assert payload["ticks_per_day"] == 0
        assert payload["estimated_monthly_cost_usd"] == 0


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


class TestAtomicWriteJson:
    def test_writes_payload_via_tmp_then_rename(self, tmp_path: Path) -> None:
        target = tmp_path / "baseline.json"
        measure_tokens._atomic_write_json(target, {"k": "v"})
        assert target.exists()
        assert json.loads(target.read_text())["k"] == "v"
        # No leftover .tmp
        assert not (tmp_path / "baseline.json.tmp").exists()

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        target = tmp_path / "baseline.json"
        target.write_text('{"old": true}', encoding="utf-8")
        measure_tokens._atomic_write_json(target, {"new": True})
        assert json.loads(target.read_text())["new"] is True


# ---------------------------------------------------------------------------
# In-window helper
# ---------------------------------------------------------------------------


class TestInWindow:
    def test_no_bounds_returns_true_even_for_no_timestamp(self) -> None:
        assert measure_tokens._in_window(None, None, None) is True

    def test_missing_timestamp_with_bounds_returns_false(self) -> None:
        assert (
            measure_tokens._in_window(None, "2026-05-01T00:00:00Z", None)
            is False
        )

    def test_below_start_returns_false(self) -> None:
        assert (
            measure_tokens._in_window(
                "2026-04-30T00:00:00Z",
                "2026-05-01T00:00:00Z",
                None,
            )
            is False
        )

    def test_at_or_above_end_returns_false(self) -> None:
        assert (
            measure_tokens._in_window(
                "2026-05-19T00:00:00Z",
                None,
                "2026-05-19T00:00:00Z",
            )
            is False
        )


# ---------------------------------------------------------------------------
# Usage-key alias coercion
# ---------------------------------------------------------------------------


class TestCoerceInt:
    def test_returns_first_present_alias(self) -> None:
        usage = {"input": 5, "input_tokens": 99}
        assert (
            measure_tokens._coerce_int(usage, ("input_tokens", "input")) == 99
        )

    def test_returns_zero_when_no_alias_present(self) -> None:
        assert (
            measure_tokens._coerce_int({}, ("input_tokens", "input")) == 0
        )

    def test_skips_non_numeric_alias_and_tries_next(self) -> None:
        usage = {"input_tokens": "not-a-number", "input": 3}
        assert (
            measure_tokens._coerce_int(usage, ("input_tokens", "input")) == 3
        )


# ---------------------------------------------------------------------------
# CLI / main
# ---------------------------------------------------------------------------


class TestCLI:
    def test_sample_mode_emits_placeholder(self, tmp_path: Path) -> None:
        out = tmp_path / "baseline.json"
        rc = measure_tokens.main(["--mode", "sample", "--out", str(out)])
        assert rc == 0
        payload = json.loads(out.read_text())
        assert payload["window_days"] == 0
        assert payload["total_heartbeats"] == 0
        assert "DEFERRED" in payload["methodology"]["summary"]

    def test_historical_session_mode_writes_real_baseline(
        self, tmp_path: Path
    ) -> None:
        session = tmp_path / "session.jsonl"
        _write_jsonl(
            session,
            [
                _user(HB_PREAMBLE, ts="2026-05-10T12:00:00Z"),
                _assistant(
                    usage={
                        "input": 5,
                        "output": 10,
                        "cacheRead": 1000,
                        "cacheWrite": 200,
                        "cost": {"total": 0.50},
                    }
                ),
            ],
        )
        out = tmp_path / "baseline.json"
        rc = measure_tokens.main(
            [
                "--mode",
                "historical",
                "--session",
                str(session),
                "--window-days",
                "7",
                "--out",
                str(out),
            ]
        )
        assert rc == 0
        payload = json.loads(out.read_text())
        assert payload["total_heartbeats"] == 1
        assert payload["total_input_tokens"] == 5
        assert payload["cost_source"] == "observed-from-session-log"
        assert payload["subject"]["source_kind"] == "session"

    def test_historical_session_dir_mode_walks_directory(
        self, tmp_path: Path
    ) -> None:
        d = tmp_path / "sessions"
        d.mkdir()
        _write_jsonl(
            d / "a.jsonl",
            [
                _user(HB_PREAMBLE, ts="2026-05-10T12:00:00Z"),
                _assistant(
                    usage={"input": 1, "output": 1, "cost": {"total": 0.1}}
                ),
            ],
        )
        _write_jsonl(
            d / "b.jsonl",
            [
                _user(HB_PREAMBLE, ts="2026-05-11T12:00:00Z"),
                _assistant(
                    usage={"input": 2, "output": 2, "cost": {"total": 0.2}}
                ),
            ],
        )
        out = tmp_path / "baseline.json"
        rc = measure_tokens.main(
            [
                "--mode",
                "historical",
                "--session-dir",
                str(d),
                "--window-days",
                "14",
                "--out",
                str(out),
            ]
        )
        assert rc == 0
        payload = json.loads(out.read_text())
        assert payload["total_heartbeats"] == 2
        assert payload["subject"]["source_kind"] == "session-dir"
        assert payload["subject"]["files_walked"] == 2

    def test_historical_requires_exactly_one_source(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        out = tmp_path / "baseline.json"
        rc = measure_tokens.main(
            ["--mode", "historical", "--out", str(out)]
        )
        assert rc == 1
        assert "exactly one of" in capsys.readouterr().err

    def test_historical_with_both_session_and_dir_errors(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        session = tmp_path / "s.jsonl"
        session.write_text("", encoding="utf-8")
        d = tmp_path / "sessions"
        d.mkdir()
        out = tmp_path / "baseline.json"
        rc = measure_tokens.main(
            [
                "--mode",
                "historical",
                "--session",
                str(session),
                "--session-dir",
                str(d),
                "--out",
                str(out),
            ]
        )
        assert rc == 1
        assert "exactly one of" in capsys.readouterr().err

    def test_historical_session_path_must_be_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        out = tmp_path / "baseline.json"
        rc = measure_tokens.main(
            [
                "--mode",
                "historical",
                "--session",
                str(tmp_path / "missing.jsonl"),
                "--out",
                str(out),
            ]
        )
        assert rc == 1
        assert "must be a file" in capsys.readouterr().err

    def test_historical_session_dir_path_must_be_directory(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        out = tmp_path / "baseline.json"
        rc = measure_tokens.main(
            [
                "--mode",
                "historical",
                "--session-dir",
                str(tmp_path / "no-such-dir"),
                "--out",
                str(out),
            ]
        )
        assert rc == 1
        assert "must be a directory" in capsys.readouterr().err

    def test_historical_zero_ticks_returns_exit_code_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        session = tmp_path / "session.jsonl"
        _write_jsonl(
            session,
            [
                _user("Conversation info: hi"),
                _assistant(usage={"input": 1, "output": 1}),
            ],
        )
        out = tmp_path / "baseline.json"
        rc = measure_tokens.main(
            [
                "--mode",
                "historical",
                "--session",
                str(session),
                "--out",
                str(out),
            ]
        )
        assert rc == 2
        assert "no ticks matched" in capsys.readouterr().err

    def test_historical_window_filter_passes_through(
        self, tmp_path: Path
    ) -> None:
        session = tmp_path / "session.jsonl"
        _write_jsonl(
            session,
            [
                _user(HB_PREAMBLE, ts="2026-04-01T00:00:00Z"),
                _assistant(usage={"input": 100, "output": 100}),
                _user(HB_PREAMBLE, ts="2026-05-10T12:00:00Z"),
                _assistant(usage={"input": 1, "output": 1}),
            ],
        )
        out = tmp_path / "baseline.json"
        rc = measure_tokens.main(
            [
                "--mode",
                "historical",
                "--session",
                str(session),
                "--window-start",
                "2026-05-01T00:00:00Z",
                "--window-end",
                "2026-06-01T00:00:00Z",
                "--out",
                str(out),
            ]
        )
        assert rc == 0
        payload = json.loads(out.read_text())
        assert payload["total_heartbeats"] == 1
        assert payload["total_input_tokens"] == 1
