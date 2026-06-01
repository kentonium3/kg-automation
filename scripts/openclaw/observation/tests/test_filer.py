"""Tests for ``filer.py`` — deterministic filer (WP-02 T013).

Covers the public entrypoints:

- :func:`file_threshold_trip`: success, subprocess failure, timeout,
  unparseable stdout, identity-mismatch stderr.
- :func:`check_existing_issue_open`: OPEN, CLOSED, gh missing, timeout,
  malformed JSON, non-zero exit. All fail-open semantics verified.
- Tempfile cleanup: tempfiles created during a filing attempt are
  deleted whether the subprocess succeeded or failed.
- Contract test: invoke ``felix-file-issue.py --dry-run`` against the
  filer's constructed args; verifies the schema is in sync.

Tests use ``monkeypatch.setattr(subprocess, "run", ...)`` to inject
fake subprocess results without spinning up the helper. The contract
test is the one exception — it runs the real helper in ``--dry-run``
mode so any argparse drift is caught.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.openclaw.observation import filer  # noqa: E402
from scripts.openclaw.observation.filer import (  # noqa: E402
    FilingError,
    FilingResult,
    _build_subprocess_args,
    build_observed_context,
    build_problem_statement,
    build_title,
    check_existing_issue_open,
    file_threshold_trip,
)
from scripts.openclaw.observation.signals.config_loader import (  # noqa: E402
    SignalDefinition,
)
from scripts.openclaw.observation.signals.types import (  # noqa: E402
    SignalExtraction,
)
from scripts.openclaw.observation.state import (  # noqa: E402
    SignalState,
)


_NOW = datetime(2026, 6, 1, 18, 0, 0, tzinfo=timezone.utc)


def _signal_def(signal_id: str = "whatsapp_creds_restore") -> SignalDefinition:
    return SignalDefinition(
        signal_id=signal_id,
        source_kind="openclaw_log",
        source_path_pattern="/tmp/openclaw/openclaw-*.log",
        match_pattern="restored corrupted WhatsApp creds.json from backup",
        match_kind="substring",
        cycle_threshold=6,
        rolling_window_minutes=60,
        rolling_threshold=18,
        dedup_strategy="open_issue_present",
        dedup_window_hours=24,
        priority="P2",
        area_label="felix-core",
        tier_hypothesis="3",
        excerpt_lines=5,
        enabled=True,
    )


_SENTINEL_DEFAULT_EXCERPTS = object()


def _extraction(
    *,
    count_cycle: int = 12,
    count_rolling: int = 35,
    excerpts=_SENTINEL_DEFAULT_EXCERPTS,
) -> SignalExtraction:
    if excerpts is _SENTINEL_DEFAULT_EXCERPTS:
        excerpts = [
            '{"0":"{\\"module\\":\\"web-session\\"}",'
            '"2":"restored corrupted WhatsApp creds.json from backup",'
            '"time":"2026-06-01T17:30:00Z"}'
        ]
    return SignalExtraction(
        signal_id="whatsapp_creds_restore",
        count_cycle=count_cycle,
        count_rolling=count_rolling,
        excerpts=excerpts,
        last_event_at_utc=datetime(
            2026, 6, 1, 17, 59, 0, tzinfo=timezone.utc
        ),
        new_cursor=None,
    )


def _state(last_filed_issue_ref: Optional[int] = None) -> SignalState:
    return SignalState(
        signal_id="whatsapp_creds_restore",
        cycle_id="prev",
        last_cycle_count=0,
        rolling_buckets=[],
        last_event_at_utc=None,
        last_filed_issue_ref=last_filed_issue_ref,
        last_filed_at_utc=None,
        last_log_position=None,
    )


# ---------------------------------------------------------------------------
# Title + body construction
# ---------------------------------------------------------------------------


def test_build_title_includes_counts_and_window():
    title = build_title(_signal_def(), _extraction())
    assert "WhatsApp creds.json corruption" in title
    assert "12 events in 15-min cycle" in title
    assert "35" in title
    # Helper adds the "Bug: " prefix; we must not.
    assert not title.startswith("Bug:")


def test_build_title_falls_back_to_signal_id_for_unknown():
    sig = _signal_def(signal_id="some_new_signal_name")
    extraction = SignalExtraction(
        signal_id="some_new_signal_name",
        count_cycle=1,
        count_rolling=1,
        excerpts=[],
    )
    title = build_title(sig, extraction)
    assert "some new signal name" in title


def test_build_problem_statement_mentions_thresholds_and_source():
    sig = _signal_def()
    statement = build_problem_statement(
        sig, _extraction(), _state(), _NOW
    )
    assert "12" in statement and "35" in statement
    assert "60-minute" in statement
    assert sig.source_path_pattern in statement
    assert sig.signal_id in statement
    assert "deterministically" in statement


def test_build_problem_statement_handles_no_last_event_time():
    extraction = SignalExtraction(
        signal_id="whatsapp_creds_restore",
        count_cycle=10,
        count_rolling=10,
        excerpts=[],
        last_event_at_utc=None,
    )
    statement = build_problem_statement(
        _signal_def(), extraction, _state(), _NOW
    )
    assert "unknown" in statement


def test_build_observed_context_caps_at_excerpt_lines():
    sig = _signal_def()
    excerpts = [f'{{"i":{i}}}' for i in range(20)]
    extraction = _extraction(excerpts=excerpts)
    out = build_observed_context(sig, extraction)
    # Joined with blank lines; should have exactly excerpt_lines=5 entries.
    assert out.count('"i":') == sig.excerpt_lines


def test_build_observed_context_handles_empty_excerpts():
    extraction = _extraction(excerpts=[])
    out = build_observed_context(_signal_def(), extraction)
    assert "No representative excerpts" in out


# ---------------------------------------------------------------------------
# file_threshold_trip — success path
# ---------------------------------------------------------------------------


class _FakeCompleted:
    def __init__(self, *, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_file_threshold_trip_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """Happy path: helper exits 0 with a JSON line; filer returns the issue."""
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        captured["kwargs"] = kwargs
        # Verify the tempfiles exist at subprocess-invocation time.
        ps_idx = argv.index("--problem-statement-file") + 1
        ctx_idx = argv.index("--observed-context-file") + 1
        captured["ps_path"] = Path(argv[ps_idx])
        captured["ctx_path"] = Path(argv[ctx_idx])
        assert captured["ps_path"].is_file()
        assert captured["ctx_path"].is_file()
        return _FakeCompleted(
            returncode=0,
            stdout=(
                '{"issue_number": 491, "issue_url": '
                '"https://github.com/kentonium3/kg-automation/issues/491", '
                '"title": "Bug: ...", "labels": ["P2-bug"]}\n'
                "SUMMARY: type=bug priority=P2 area=felix-core tier=3 "
                "spec=brief issue=#491\n"
            ),
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = file_threshold_trip(
        _signal_def(), _extraction(), _state(), _NOW
    )

    assert isinstance(result, FilingResult)
    assert result.error is None
    assert result.issue_number == 491
    assert result.issue_url == (
        "https://github.com/kentonium3/kg-automation/issues/491"
    )
    # Tempfiles cleaned up after success.
    assert not captured["ps_path"].exists()
    assert not captured["ctx_path"].exists()
    # Required args present.
    argv = captured["argv"]
    assert "--type" in argv and argv[argv.index("--type") + 1] == "bug"
    assert "--priority" in argv
    assert "--spec-ready-eval" in argv
    assert argv[argv.index("--spec-ready-eval") + 1] == "brief"
    # No --dry-run in production calls (per contract).
    assert "--dry-run" not in argv
    # Timeout passed.
    assert captured["kwargs"]["timeout"] == filer.FILER_SUBPROCESS_TIMEOUT_SEC


def test_file_threshold_trip_naive_now_returns_invocation_error():
    naive_now = datetime(2026, 6, 1, 18, 0, 0)
    result = file_threshold_trip(
        _signal_def(), _extraction(), _state(), naive_now
    )
    assert result.error is not None
    assert result.error.error_type == "filer_invocation_error"


# ---------------------------------------------------------------------------
# file_threshold_trip — error paths
# ---------------------------------------------------------------------------


def test_file_threshold_trip_subprocess_failed(
    monkeypatch: pytest.MonkeyPatch,
):
    captured_paths: dict = {}

    def fake_run(argv, **kwargs):
        ps_idx = argv.index("--problem-statement-file") + 1
        ctx_idx = argv.index("--observed-context-file") + 1
        captured_paths["ps"] = Path(argv[ps_idx])
        captured_paths["ctx"] = Path(argv[ctx_idx])
        return _FakeCompleted(
            returncode=1,
            stderr="ERROR: gh CLI rate-limited\n",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = file_threshold_trip(
        _signal_def(), _extraction(), _state(), _NOW
    )

    assert result.error is not None
    assert result.error.error_type == "filer_subprocess_failed"
    assert "rate-limited" in result.error.error_message
    # Tempfiles cleaned even on failure.
    assert not captured_paths["ps"].exists()
    assert not captured_paths["ctx"].exists()


def test_file_threshold_trip_timeout(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict = {}

    def fake_run(argv, **kwargs):
        ps_idx = argv.index("--problem-statement-file") + 1
        captured["ps"] = Path(argv[ps_idx])
        raise subprocess.TimeoutExpired(cmd=argv, timeout=kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = file_threshold_trip(
        _signal_def(), _extraction(), _state(), _NOW
    )
    assert result.error is not None
    assert result.error.error_type == "filer_timeout"
    assert "60" in result.error.error_message
    assert not captured["ps"].exists()


def test_file_threshold_trip_output_unparseable(
    monkeypatch: pytest.MonkeyPatch,
):
    def fake_run(argv, **kwargs):
        return _FakeCompleted(
            returncode=0, stdout="ERROR: something weird happened\n"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = file_threshold_trip(
        _signal_def(), _extraction(), _state(), _NOW
    )
    assert result.error is not None
    assert result.error.error_type == "filer_output_unparseable"


def test_file_threshold_trip_output_json_missing_issue_number(
    monkeypatch: pytest.MonkeyPatch,
):
    # JSON line present but ``issue_number`` is missing — the
    # generic line scanner skips lines without that field, so this
    # falls back to ``filer_output_unparseable``.
    def fake_run(argv, **kwargs):
        return _FakeCompleted(
            returncode=0,
            stdout='{"title": "Bug: x"}\nSUMMARY: ...\n',
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = file_threshold_trip(
        _signal_def(), _extraction(), _state(), _NOW
    )
    assert result.error is not None
    assert result.error.error_type == "filer_output_unparseable"


def test_file_threshold_trip_identity_mismatch(
    monkeypatch: pytest.MonkeyPatch,
):
    def fake_run(argv, **kwargs):
        return _FakeCompleted(
            returncode=1,
            stderr=(
                "ERROR: gh identity check failed: Expected gh identity "
                "'kg-felix-bot' but found 'kentonium3'. Use ...\n"
            ),
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = file_threshold_trip(
        _signal_def(), _extraction(), _state(), _NOW
    )
    assert result.error is not None
    assert result.error.error_type == "filer_identity_mismatch"


def test_file_threshold_trip_invocation_error_when_python_missing(
    monkeypatch: pytest.MonkeyPatch,
):
    def fake_run(argv, **kwargs):
        raise FileNotFoundError("python3 not in PATH")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = file_threshold_trip(
        _signal_def(), _extraction(), _state(), _NOW
    )
    assert result.error is not None
    assert result.error.error_type == "filer_invocation_error"


# ---------------------------------------------------------------------------
# check_existing_issue_open
# ---------------------------------------------------------------------------


def test_check_existing_issue_open_returns_true_for_open(
    monkeypatch: pytest.MonkeyPatch,
):
    def fake_run(argv, **kwargs):
        assert "issue" in argv and "view" in argv
        assert "--json" in argv and "state" in argv
        return _FakeCompleted(returncode=0, stdout='{"state":"OPEN"}\n')

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert check_existing_issue_open(491) is True


def test_check_existing_issue_open_returns_false_for_closed(
    monkeypatch: pytest.MonkeyPatch,
):
    def fake_run(argv, **kwargs):
        return _FakeCompleted(returncode=0, stdout='{"state":"CLOSED"}\n')

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert check_existing_issue_open(491) is False


def test_check_existing_issue_open_fail_open_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
):
    def fake_run(argv, **kwargs):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=10)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert check_existing_issue_open(491) is False
    err = capsys.readouterr().err
    assert "timed out" in err


def test_check_existing_issue_open_fail_open_on_gh_missing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
):
    def fake_run(argv, **kwargs):
        raise FileNotFoundError("gh not in PATH")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert check_existing_issue_open(491) is False
    err = capsys.readouterr().err
    assert "gh CLI unavailable" in err


def test_check_existing_issue_open_fail_open_on_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
):
    def fake_run(argv, **kwargs):
        return _FakeCompleted(
            returncode=1, stderr="GraphQL: Could not resolve issue"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert check_existing_issue_open(99999) is False


def test_check_existing_issue_open_fail_open_on_malformed_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
):
    def fake_run(argv, **kwargs):
        return _FakeCompleted(returncode=0, stdout="not-json-at-all")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert check_existing_issue_open(491) is False


def test_check_existing_issue_open_fail_open_on_missing_state_key(
    monkeypatch: pytest.MonkeyPatch,
):
    def fake_run(argv, **kwargs):
        return _FakeCompleted(
            returncode=0, stdout='{"unrelated":"field"}'
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert check_existing_issue_open(491) is False


# ---------------------------------------------------------------------------
# Contract test — runs the REAL felix-file-issue.py --dry-run
# ---------------------------------------------------------------------------


def test_contract_felix_file_issue_dry_run_accepts_filer_args(tmp_path: Path):
    """Construct the filer's argv and invoke the helper with ``--dry-run``.

    This catches argument-schema drift between the deterministic filer
    and ``felix-file-issue.py``. If a future change to either side
    adds/removes/renames a flag, this test fails fast.
    """
    helper = filer.DEFAULT_FELIX_FILE_ISSUE_PATH
    assert helper.is_file(), f"helper missing: {helper}"

    ps_path = tmp_path / "ps.md"
    ctx_path = tmp_path / "ctx.md"
    ps_path.write_text("Problem statement text.", encoding="utf-8")
    ctx_path.write_text("Observed context excerpts.", encoding="utf-8")

    argv = _build_subprocess_args(
        signal_def=_signal_def(),
        title=build_title(_signal_def(), _extraction()),
        problem_statement_path=ps_path,
        observed_context_path=ctx_path,
        felix_file_issue_path=helper,
    )
    # Inject --dry-run so the helper does NOT actually invoke gh CLI
    # and does NOT verify the active identity. The contract test is
    # purely a schema check.
    argv.append("--dry-run")

    completed = subprocess.run(
        argv, capture_output=True, text=True, timeout=30, check=False
    )
    assert completed.returncode == 0, (
        f"helper rejected filer args:\n"
        f"stdout: {completed.stdout}\n"
        f"stderr: {completed.stderr}"
    )
    # The helper's --dry-run prints "=== TITLE ===" etc.
    assert "=== TITLE ===" in completed.stdout
    assert "Bug:" in completed.stdout
