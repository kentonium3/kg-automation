"""Tests for ``tick.py`` — cycle orchestrator (WP-02 T013).

End-to-end with a small synthetic fixture log and mocked filer +
gh-CLI calls. Verifies:

- Threshold below → no filing attempted.
- Threshold tripped with no prior issue → filer invoked, last-tick.json
  records the filing, state file updated with last_filed_issue_ref.
- Threshold tripped with prior issue still OPEN → filer NOT invoked,
  ``issues_skipped_dedup`` populated.
- Threshold tripped with prior issue CLOSED → filer invoked.
- ``--dry-run`` does not save state and does not call the filer; the
  last-tick.json carries ``dry_run: true``.
- ``--replay-log`` substitutes a static log and implicitly forces
  ``dry_run`` for filing (no gh CLI shell-out).
- Per-signal extractor error → ``exit_status == "partial"``, other
  signals still run, last-tick.json's errors list populated.
- Config-load failure → ``exit_status == "failure"``, exit code 1.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.openclaw.observation import filer as _filer  # noqa: E402
from scripts.openclaw.observation import tick  # noqa: E402
from scripts.openclaw.observation.filer import (  # noqa: E402
    FilingError,
    FilingResult,
)
from scripts.openclaw.observation.signals.config_loader import (  # noqa: E402
    SignalDefinition,
)
from scripts.openclaw.observation.signals.types import (  # noqa: E402
    SignalExtraction,
)
from scripts.openclaw.observation.state import (  # noqa: E402
    RollingBucket,
    SignalState,
    load_state,
    save_state,
)
from scripts.openclaw.observation.tick import (  # noqa: E402
    CycleRecord,
    _atomic_write_json,
    _threshold_status,
    new_cycle_id,
    run_cycle,
)


_NOW = datetime(2026, 6, 1, 18, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures: minimal TOML config + log fixture
# ---------------------------------------------------------------------------


_SEED_LINE = (
    '{{"0":"{{\\"module\\":\\"web-session\\"}}",'
    '"2":"restored corrupted WhatsApp creds.json from backup",'
    '"_meta":{{"logLevelName":"WARN"}},'
    '"time":"{ts}"}}'
)


def _write_seed_log(path: Path, n_creds: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        _SEED_LINE.format(
            ts=f"2026-06-01T17:{(i * 2) % 60:02d}:00.000+00:00"
        )
        for i in range(n_creds)
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_config(
    path: Path,
    log_path: Path,
    *,
    cycle_threshold: int = 3,
    rolling_threshold: int = 5,
) -> None:
    """Write a minimal TOML config pointing at ``log_path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""[meta]
schema_version = 1

[signals.whatsapp_creds_restore]
source_kind             = "openclaw_log"
source_path_pattern     = "{log_path}"
match_pattern           = "restored corrupted WhatsApp creds.json from backup"
match_kind              = "substring"
cycle_threshold         = {cycle_threshold}
rolling_window_minutes  = 60
rolling_threshold       = {rolling_threshold}
dedup_strategy          = "open_issue_present"
priority                = "P2"
area_label              = "felix-core"
tier_hypothesis         = "3"
excerpt_lines           = 5
enabled                 = true
""",
        encoding="utf-8",
    )


def _read_last_tick(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# new_cycle_id format
# ---------------------------------------------------------------------------


def test_new_cycle_id_is_26_chars_and_crockford():
    cycle_id = new_cycle_id(_NOW)
    assert len(cycle_id) == 26
    valid = set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")
    assert all(c in valid for c in cycle_id)


def test_new_cycle_id_is_time_sortable():
    earlier = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    later = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    e_id = new_cycle_id(earlier)
    l_id = new_cycle_id(later)
    assert e_id < l_id


# ---------------------------------------------------------------------------
# Threshold-below path
# ---------------------------------------------------------------------------


def test_threshold_below_files_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    log_path = tmp_path / "openclaw-2026-06-01.log"
    _write_seed_log(log_path, n_creds=2)  # below threshold (3)
    config_path = tmp_path / "config.toml"
    _write_config(config_path, log_path)

    # Fail loudly if the filer is invoked.
    monkeypatch.setattr(
        _filer,
        "file_threshold_trip",
        lambda *a, **kw: pytest.fail("filer must not be called below threshold"),
    )
    monkeypatch.setattr(
        _filer,
        "check_existing_issue_open",
        lambda *a, **kw: pytest.fail("dedup must not be called below threshold"),
    )

    last_tick_path = tmp_path / "last-tick.json"
    ledger_path = tmp_path / "ledger.jsonl"
    state_dir = tmp_path / "state"

    rc = run_cycle(
        config_path=config_path,
        state_dir=state_dir,
        last_tick_path=last_tick_path,
        ledger_path=ledger_path,
        now_utc=_NOW,
    )
    assert rc == 0
    payload = _read_last_tick(last_tick_path)
    assert payload["exit_status"] == "success"
    assert payload["issues_filed"] == []
    assert payload["issues_skipped_dedup"] == []
    sig = payload["signals_evaluated"][0]
    assert sig["threshold_status"] == "below"
    assert sig["count_cycle"] == 2


# ---------------------------------------------------------------------------
# Threshold-tripped, no prior issue → filer invoked
# ---------------------------------------------------------------------------


def test_threshold_tripped_no_prior_files_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    log_path = tmp_path / "openclaw-2026-06-01.log"
    _write_seed_log(log_path, n_creds=10)  # well above cycle=3 rolling=5
    config_path = tmp_path / "config.toml"
    _write_config(config_path, log_path)

    captured: dict = {}

    def fake_filer(signal_def, extraction, state, now_utc, **kw):
        captured["signal_id"] = signal_def.signal_id
        captured["count_cycle"] = extraction.count_cycle
        return FilingResult(
            issue_number=491,
            issue_url=(
                "https://github.com/kentonium3/kg-automation/issues/491"
            ),
            error=None,
        )

    monkeypatch.setattr(_filer, "file_threshold_trip", fake_filer)
    # No prior state file → dedup check shouldn't even run.
    monkeypatch.setattr(
        _filer,
        "check_existing_issue_open",
        lambda *a, **kw: pytest.fail("dedup must not run without prior ref"),
    )

    last_tick_path = tmp_path / "last-tick.json"
    ledger_path = tmp_path / "ledger.jsonl"
    state_dir = tmp_path / "state"

    rc = run_cycle(
        config_path=config_path,
        state_dir=state_dir,
        last_tick_path=last_tick_path,
        ledger_path=ledger_path,
        now_utc=_NOW,
    )
    assert rc == 0
    assert captured["signal_id"] == "whatsapp_creds_restore"
    payload = _read_last_tick(last_tick_path)
    assert payload["exit_status"] == "success"
    assert len(payload["issues_filed"]) == 1
    assert payload["issues_filed"][0]["issue_number"] == 491
    # State file persisted with last_filed_issue_ref set.
    state = load_state(state_dir, "whatsapp_creds_restore")
    assert state is not None
    assert state.last_filed_issue_ref == 491
    assert state.last_filed_at_utc is not None


# ---------------------------------------------------------------------------
# Threshold-tripped with prior OPEN issue → suppressed
# ---------------------------------------------------------------------------


def test_threshold_tripped_with_prior_open_suppresses_filing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    log_path = tmp_path / "openclaw-2026-06-01.log"
    _write_seed_log(log_path, n_creds=10)
    config_path = tmp_path / "config.toml"
    _write_config(config_path, log_path)

    # Seed state with a prior filed issue ref.
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    seeded = SignalState(
        signal_id="whatsapp_creds_restore",
        cycle_id="prev",
        last_cycle_count=8,
        rolling_buckets=[],
        last_event_at_utc=None,
        last_filed_issue_ref=400,
        last_filed_at_utc="2026-05-31T23:00:00Z",
        last_log_position=None,
    )
    save_state(state_dir, seeded)

    monkeypatch.setattr(
        _filer,
        "check_existing_issue_open",
        lambda n, **kw: n == 400,  # issue 400 is OPEN
    )
    monkeypatch.setattr(
        _filer,
        "file_threshold_trip",
        lambda *a, **kw: pytest.fail(
            "filer must not run when prior issue is OPEN"
        ),
    )

    last_tick_path = tmp_path / "last-tick.json"
    ledger_path = tmp_path / "ledger.jsonl"

    rc = run_cycle(
        config_path=config_path,
        state_dir=state_dir,
        last_tick_path=last_tick_path,
        ledger_path=ledger_path,
        now_utc=_NOW,
    )
    assert rc == 0
    payload = _read_last_tick(last_tick_path)
    assert payload["issues_filed"] == []
    assert len(payload["issues_skipped_dedup"]) == 1
    assert payload["issues_skipped_dedup"][0]["existing_issue_ref"] == 400


# ---------------------------------------------------------------------------
# Threshold-tripped with prior CLOSED issue → files again
# ---------------------------------------------------------------------------


def test_threshold_tripped_with_prior_closed_files_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    log_path = tmp_path / "openclaw-2026-06-01.log"
    _write_seed_log(log_path, n_creds=10)
    config_path = tmp_path / "config.toml"
    _write_config(config_path, log_path)

    state_dir = tmp_path / "state"
    state_dir.mkdir()
    seeded = SignalState(
        signal_id="whatsapp_creds_restore",
        cycle_id="prev",
        last_cycle_count=8,
        rolling_buckets=[],
        last_event_at_utc=None,
        last_filed_issue_ref=400,
        last_filed_at_utc="2026-05-31T23:00:00Z",
        last_log_position=None,
    )
    save_state(state_dir, seeded)

    monkeypatch.setattr(
        _filer, "check_existing_issue_open", lambda n, **kw: False
    )
    monkeypatch.setattr(
        _filer,
        "file_threshold_trip",
        lambda *a, **kw: FilingResult(
            issue_number=510,
            issue_url=(
                "https://github.com/kentonium3/kg-automation/issues/510"
            ),
            error=None,
        ),
    )

    last_tick_path = tmp_path / "last-tick.json"
    ledger_path = tmp_path / "ledger.jsonl"

    rc = run_cycle(
        config_path=config_path,
        state_dir=state_dir,
        last_tick_path=last_tick_path,
        ledger_path=ledger_path,
        now_utc=_NOW,
    )
    assert rc == 0
    payload = _read_last_tick(last_tick_path)
    assert len(payload["issues_filed"]) == 1
    assert payload["issues_filed"][0]["issue_number"] == 510
    # State updated to new ref.
    state = load_state(state_dir, "whatsapp_creds_restore")
    assert state is not None
    assert state.last_filed_issue_ref == 510


# ---------------------------------------------------------------------------
# --dry-run path
# ---------------------------------------------------------------------------


def test_dry_run_skips_filer_and_state_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    log_path = tmp_path / "openclaw-2026-06-01.log"
    _write_seed_log(log_path, n_creds=10)
    config_path = tmp_path / "config.toml"
    _write_config(config_path, log_path)

    monkeypatch.setattr(
        _filer,
        "file_threshold_trip",
        lambda *a, **kw: pytest.fail("dry-run must not call filer"),
    )
    monkeypatch.setattr(
        _filer,
        "check_existing_issue_open",
        lambda *a, **kw: pytest.fail("dry-run must not call gh"),
    )

    last_tick_path = tmp_path / "last-tick.json"
    ledger_path = tmp_path / "ledger.jsonl"
    state_dir = tmp_path / "state"

    rc = run_cycle(
        config_path=config_path,
        state_dir=state_dir,
        last_tick_path=last_tick_path,
        ledger_path=ledger_path,
        now_utc=_NOW,
        dry_run=True,
    )
    assert rc == 0
    payload = _read_last_tick(last_tick_path)
    assert payload["dry_run"] is True
    # No state file written.
    assert not state_dir.exists() or not any(state_dir.iterdir())
    # SUMMARY line includes the [DRY-RUN] prefix.
    out = capsys.readouterr().out
    assert out.startswith("[DRY-RUN] SUMMARY:")


# ---------------------------------------------------------------------------
# --replay-log path
# ---------------------------------------------------------------------------


def test_replay_log_uses_static_file_and_implies_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Replay-log substitutes a single file regardless of source_path_pattern."""
    # Config points at a path that does NOT exist in tmp_path …
    config_path = tmp_path / "config.toml"
    _write_config(config_path, tmp_path / "does-not-exist.log")
    # … but the replay log is a real file with content.
    replay_log = tmp_path / "replay.log"
    _write_seed_log(replay_log, n_creds=10)

    monkeypatch.setattr(
        _filer,
        "file_threshold_trip",
        lambda *a, **kw: pytest.fail("replay must not call filer by default"),
    )

    last_tick_path = tmp_path / "last-tick.json"
    ledger_path = tmp_path / "ledger.jsonl"
    state_dir = tmp_path / "state"

    rc = run_cycle(
        config_path=config_path,
        state_dir=state_dir,
        last_tick_path=last_tick_path,
        ledger_path=ledger_path,
        now_utc=_NOW,
        # ``main()`` would set dry_run=True when replay_log is given
        # without --no-dry-run-with-replay. Here we model that.
        dry_run=True,
        replay_log=replay_log,
    )
    assert rc == 0
    payload = _read_last_tick(last_tick_path)
    sig = payload["signals_evaluated"][0]
    assert sig["count_cycle"] == 10


def test_replay_log_with_filing_enabled_alone_does_NOT_call_filer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """filing_enabled=True alone is NOT enough to enable live filing during replay.

    Regression test for codex WP02 cycle-2 finding: previously a direct
    caller could bypass the replay-safety guard by explicitly passing
    ``filing_enabled=True`` (the cycle-1 fix only forced ``dry_run=True``;
    it left an explicit ``filing_enabled`` override intact, and
    ``_process_signal`` gates filing on ``filing_enabled`` not ``dry_run``).

    The cycle-2 fix makes the replay-safety guard override BOTH
    ``dry_run`` (force True) AND ``filing_enabled`` (force False) when
    ``replay_log`` is set without ``force_replay_filing=True``.
    ``force_replay_filing=True`` is now the only key that unlocks live
    filing in replay mode.
    """
    config_path = tmp_path / "config.toml"
    _write_config(config_path, tmp_path / "does-not-exist.log")
    replay_log = tmp_path / "replay.log"
    # n_creds=10 is above both cycle_threshold (3) and rolling (5).
    _write_seed_log(replay_log, n_creds=10)

    monkeypatch.setattr(
        _filer,
        "file_threshold_trip",
        lambda *a, **kw: pytest.fail(
            "filing_enabled=True must NOT bypass the replay-safety guard; "
            "only force_replay_filing=True unlocks live filing in replay mode"
        ),
    )
    monkeypatch.setattr(
        _filer,
        "check_existing_issue_open",
        lambda *a, **kw: pytest.fail(
            "gh dedup check must NOT run when replay-safety guard is active"
        ),
    )

    last_tick_path = tmp_path / "last-tick.json"

    # Caller passes filing_enabled=True but NO force_replay_filing.
    # The replay-safety guard must override filing_enabled to False and
    # force dry_run=True regardless of the caller's filing_enabled value.
    rc = run_cycle(
        config_path=config_path,
        state_dir=tmp_path / "state",
        last_tick_path=last_tick_path,
        ledger_path=tmp_path / "ledger.jsonl",
        now_utc=_NOW,
        dry_run=False,
        replay_log=replay_log,
        filing_enabled=True,
    )
    assert rc == 0
    payload = _read_last_tick(last_tick_path)
    # The cycle record must show dry_run=True (forced by replay-safe guard).
    assert payload["dry_run"] is True
    # And the signal must still have been evaluated (above threshold).
    sig = payload["signals_evaluated"][0]
    assert sig["count_cycle"] == 10


def test_replay_function_call_forces_dry_run_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Calling run_cycle(replay_log=<path>) without force_replay_filing must NOT invoke the filer.

    Regression test for codex WP02 cycle-1 finding: replay-safe default
    at function-call layer. Previously, run_cycle(replay_log=X) with the
    default dry_run=False allowed filing_enabled to default to True, so
    a stray direct call could invoke the live filer. The fix forces
    dry_run=True at the top of run_cycle when replay_log is set and
    force_replay_filing is not explicitly opted in.
    """
    config_path = tmp_path / "config.toml"
    _write_config(config_path, tmp_path / "does-not-exist.log")
    replay_log = tmp_path / "replay.log"
    # n_creds=10 is above both cycle_threshold (3) and rolling (5).
    _write_seed_log(replay_log, n_creds=10)

    monkeypatch.setattr(
        _filer,
        "file_threshold_trip",
        lambda *a, **kw: pytest.fail(
            "run_cycle(replay_log=...) must force dry_run by default; "
            "filer must NOT be invoked without force_replay_filing=True"
        ),
    )
    monkeypatch.setattr(
        _filer,
        "check_existing_issue_open",
        lambda *a, **kw: pytest.fail(
            "gh dedup check must NOT run in default-dry replay"
        ),
    )

    last_tick_path = tmp_path / "last-tick.json"
    ledger_path = tmp_path / "ledger.jsonl"
    state_dir = tmp_path / "state"

    # Note: NO dry_run argument (defaults to False) and NO
    # force_replay_filing argument (defaults to False). The replay-safe
    # guard inside run_cycle must force dry_run=True.
    rc = run_cycle(
        config_path=config_path,
        state_dir=state_dir,
        last_tick_path=last_tick_path,
        ledger_path=ledger_path,
        now_utc=_NOW,
        replay_log=replay_log,
    )
    assert rc == 0
    payload = _read_last_tick(last_tick_path)
    # The cycle record must show dry_run=True (forced by replay-safe default).
    assert payload["dry_run"] is True
    # And the signal must have been evaluated (above threshold).
    sig = payload["signals_evaluated"][0]
    assert sig["count_cycle"] == 10


def test_replay_function_call_with_force_replay_filing_invokes_filer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Explicit force_replay_filing=True allows live filing during replay.

    The escape hatch must be honored at the function-call layer for
    direct Python callers (the CLI's --no-dry-run-with-replay flag is
    the canonical user-facing equivalent).
    """
    config_path = tmp_path / "config.toml"
    _write_config(config_path, tmp_path / "does-not-exist.log")
    replay_log = tmp_path / "replay.log"
    _write_seed_log(replay_log, n_creds=10)

    called: dict = {}

    def fake_filer(signal_def, extraction, state, now_utc, **kw):
        called["yes"] = True
        return FilingResult(
            issue_number=601, issue_url=None, error=None
        )

    monkeypatch.setattr(_filer, "file_threshold_trip", fake_filer)
    monkeypatch.setattr(
        _filer, "check_existing_issue_open", lambda *a, **kw: False
    )

    rc = run_cycle(
        config_path=config_path,
        state_dir=tmp_path / "state",
        last_tick_path=tmp_path / "last-tick.json",
        ledger_path=tmp_path / "ledger.jsonl",
        now_utc=_NOW,
        replay_log=replay_log,
        force_replay_filing=True,
    )
    assert rc == 0
    assert called.get("yes") is True


def test_replay_log_with_filing_enabled_AND_force_replay_filing_invokes_filer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """When BOTH filing_enabled=True AND force_replay_filing=True are set,
    live filing proceeds.

    Defense-in-depth test for the cycle-2 override hierarchy:
    ``force_replay_filing=True`` is the only key that unlocks live filing
    in replay mode. ``filing_enabled=True`` is honored only when paired
    with ``force_replay_filing=True`` (or in non-replay scenarios).
    """
    config_path = tmp_path / "config.toml"
    _write_config(config_path, tmp_path / "does-not-exist.log")
    replay_log = tmp_path / "replay.log"
    _write_seed_log(replay_log, n_creds=10)

    called: dict = {}

    def fake_filer(signal_def, extraction, state, now_utc, **kw):
        called["yes"] = True
        return FilingResult(
            issue_number=602, issue_url=None, error=None
        )

    monkeypatch.setattr(_filer, "file_threshold_trip", fake_filer)
    monkeypatch.setattr(
        _filer, "check_existing_issue_open", lambda *a, **kw: False
    )

    rc = run_cycle(
        config_path=config_path,
        state_dir=tmp_path / "state",
        last_tick_path=tmp_path / "last-tick.json",
        ledger_path=tmp_path / "ledger.jsonl",
        now_utc=_NOW,
        replay_log=replay_log,
        filing_enabled=True,
        force_replay_filing=True,
    )
    assert rc == 0
    assert called.get("yes") is True


# ---------------------------------------------------------------------------
# Partial / failure exit-status semantics
# ---------------------------------------------------------------------------


def test_extractor_failure_records_partial_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    log_path = tmp_path / "openclaw-2026-06-01.log"
    _write_seed_log(log_path, n_creds=10)
    config_path = tmp_path / "config.toml"
    _write_config(config_path, log_path)

    def broken(*args, **kwargs):
        raise RuntimeError("extractor exploded")

    dispatch = {"whatsapp_creds_restore": broken}
    monkeypatch.setattr(
        _filer,
        "file_threshold_trip",
        lambda *a, **kw: pytest.fail("filer must not run when extractor failed"),
    )

    last_tick_path = tmp_path / "last-tick.json"
    ledger_path = tmp_path / "ledger.jsonl"

    rc = run_cycle(
        config_path=config_path,
        state_dir=tmp_path / "state",
        last_tick_path=last_tick_path,
        ledger_path=ledger_path,
        now_utc=_NOW,
        dispatch=dispatch,
    )
    assert rc == 0  # cycle didn't abort; per-signal failure → "partial".
    payload = _read_last_tick(last_tick_path)
    assert payload["exit_status"] == "partial"
    assert len(payload["errors"]) == 1
    assert payload["errors"][0]["error_type"] == "extractor_failed"


def test_filer_failure_records_partial_and_does_not_update_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Filer subprocess fail mid-cycle → partial status, state ref untouched."""
    log_path = tmp_path / "openclaw-2026-06-01.log"
    _write_seed_log(log_path, n_creds=10)
    config_path = tmp_path / "config.toml"
    _write_config(config_path, log_path)

    monkeypatch.setattr(
        _filer,
        "file_threshold_trip",
        lambda *a, **kw: FilingResult(
            issue_number=None,
            issue_url=None,
            error=FilingError(
                error_type="filer_subprocess_failed",
                error_message="gh rate limit",
            ),
        ),
    )

    state_dir = tmp_path / "state"
    last_tick_path = tmp_path / "last-tick.json"

    rc = run_cycle(
        config_path=config_path,
        state_dir=state_dir,
        last_tick_path=last_tick_path,
        ledger_path=tmp_path / "ledger.jsonl",
        now_utc=_NOW,
    )
    assert rc == 0
    payload = _read_last_tick(last_tick_path)
    assert payload["exit_status"] == "partial"
    assert payload["issues_filed"] == []
    assert any(
        e["error_type"] == "filer_subprocess_failed"
        for e in payload["errors"]
    )
    # State file was written (we still want cursor + buckets persisted),
    # but ``last_filed_issue_ref`` is still None.
    state = load_state(state_dir, "whatsapp_creds_restore")
    assert state is not None
    assert state.last_filed_issue_ref is None


def test_config_load_failure_aborts_cycle_with_failure_status(
    tmp_path: Path,
):
    bogus_config = tmp_path / "does-not-exist.toml"
    last_tick_path = tmp_path / "last-tick.json"
    rc = run_cycle(
        config_path=bogus_config,
        state_dir=tmp_path / "state",
        last_tick_path=last_tick_path,
        ledger_path=tmp_path / "ledger.jsonl",
        now_utc=_NOW,
    )
    assert rc == 1
    payload = _read_last_tick(last_tick_path)
    assert payload["exit_status"] == "failure"
    assert payload["errors"][0]["error_type"] == "config_load_failed"


# ---------------------------------------------------------------------------
# Unknown-signal dispatch
# ---------------------------------------------------------------------------


def test_unknown_signal_id_records_error_does_not_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    log_path = tmp_path / "openclaw-2026-06-01.log"
    _write_seed_log(log_path, n_creds=10)
    config_path = tmp_path / "config.toml"
    _write_config(config_path, log_path)

    # Empty dispatch → no extractor registered for the configured signal.
    rc = run_cycle(
        config_path=config_path,
        state_dir=tmp_path / "state",
        last_tick_path=tmp_path / "last-tick.json",
        ledger_path=tmp_path / "ledger.jsonl",
        now_utc=_NOW,
        dispatch={},
    )
    assert rc == 0
    payload = _read_last_tick(tmp_path / "last-tick.json")
    assert payload["exit_status"] == "partial"
    assert payload["errors"][0]["error_type"] == "unknown_signal_id"


# ---------------------------------------------------------------------------
# Naive datetime guard
# ---------------------------------------------------------------------------


def test_run_cycle_rejects_naive_now_utc(tmp_path: Path):
    with pytest.raises(ValueError):
        run_cycle(
            config_path=tmp_path / "config.toml",
            state_dir=tmp_path / "state",
            last_tick_path=tmp_path / "last-tick.json",
            ledger_path=tmp_path / "ledger.jsonl",
            now_utc=datetime(2026, 6, 1, 18, 0, 0),  # naive!
        )


# ---------------------------------------------------------------------------
# Atomic-write helper
# ---------------------------------------------------------------------------


def test_atomic_write_json_creates_parent_dirs(tmp_path: Path):
    target = tmp_path / "nested" / "dir" / "last-tick.json"
    _atomic_write_json(target, {"hello": "world"})
    assert json.loads(target.read_text()) == {"hello": "world"}


def test_atomic_write_json_overwrites_existing(tmp_path: Path):
    target = tmp_path / "last-tick.json"
    target.write_text('{"old":true}')
    _atomic_write_json(target, {"new": True})
    assert json.loads(target.read_text()) == {"new": True}


# ---------------------------------------------------------------------------
# Ledger append behavior
# ---------------------------------------------------------------------------


def test_ledger_grows_one_line_per_cycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    log_path = tmp_path / "openclaw-2026-06-01.log"
    _write_seed_log(log_path, n_creds=2)
    config_path = tmp_path / "config.toml"
    _write_config(config_path, log_path)

    ledger_path = tmp_path / "ledger.jsonl"
    for _ in range(3):
        run_cycle(
            config_path=config_path,
            state_dir=tmp_path / "state",
            last_tick_path=tmp_path / "last-tick.json",
            ledger_path=ledger_path,
            now_utc=_NOW,
        )

    lines = ledger_path.read_text().splitlines()
    assert len(lines) == 3
    for line in lines:
        parsed = json.loads(line)
        assert "cycle_id" in parsed
        assert "schema_version" in parsed


# ---------------------------------------------------------------------------
# main() CLI integration
# ---------------------------------------------------------------------------


def test_main_implies_dry_run_with_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """main(--replay-log X) without --no-dry-run-with-replay forces dry_run."""
    log_path = tmp_path / "replay.log"
    _write_seed_log(log_path, n_creds=10)
    config_path = tmp_path / "config.toml"
    _write_config(config_path, tmp_path / "irrelevant.log")

    # If main DIDN'T force dry_run, filer would be called — fail loudly.
    monkeypatch.setattr(
        _filer,
        "file_threshold_trip",
        lambda *a, **kw: pytest.fail(
            "main must force dry_run when --replay-log without escape hatch"
        ),
    )

    rc = tick.main(
        [
            "--config",
            str(config_path),
            "--state-dir",
            str(tmp_path / "state"),
            "--last-tick",
            str(tmp_path / "last-tick.json"),
            "--ledger",
            str(tmp_path / "ledger.jsonl"),
            "--replay-log",
            str(log_path),
        ]
    )
    assert rc == 0
    payload = _read_last_tick(tmp_path / "last-tick.json")
    assert payload["dry_run"] is True


# ---------------------------------------------------------------------------
# _threshold_status — quiet-cycle gate (mission signal-trip-cycle-floor-01KT4NHJ)
# ---------------------------------------------------------------------------


def _threshold_def(
    *, cycle_threshold: int, rolling_threshold: int
) -> SignalDefinition:
    """Minimal SignalDefinition for predicate testing.

    Only ``cycle_threshold`` and ``rolling_threshold`` are exercised by
    ``_threshold_status``; remaining fields use realistic defaults.
    """
    return SignalDefinition(
        signal_id="whatsapp_creds_restore",
        source_kind="openclaw_log",
        source_path_pattern="/tmp/openclaw/openclaw-*.log",
        match_pattern="restored corrupted WhatsApp creds.json from backup",
        match_kind="substring",
        cycle_threshold=cycle_threshold,
        rolling_window_minutes=60,
        rolling_threshold=rolling_threshold,
        dedup_strategy="open_issue_present",
        dedup_window_hours=24,
        priority="P2",
        area_label="felix-core",
        tier_hypothesis="3",
        excerpt_lines=5,
        enabled=True,
    )


def _threshold_extraction(
    *, count_cycle: int, count_rolling: int
) -> SignalExtraction:
    """Minimal SignalExtraction for predicate testing."""
    return SignalExtraction(
        signal_id="whatsapp_creds_restore",
        count_cycle=count_cycle,
        count_rolling=count_rolling,
        excerpts=[],
        last_event_at_utc=None,
        new_cursor=None,
    )


@pytest.mark.parametrize(
    "name,count_cycle,count_rolling,cycle_threshold,rolling_threshold,expected",
    [
        ("quiet_below",           0,    0, 5, 15, "below"),
        # Regression guard against #502/#503/#504: pre-fix this case
        # returned "tripped_rolling" and re-filed the noise of a resolved
        # transient burst once the prior anchor was closed.
        ("quiet_hot_rolling",     0,  999, 5, 15, "below"),
        ("one_event_below",       1,    0, 5, 15, "below"),
        ("one_event_rolling_hit", 1,   15, 5, 15, "tripped_rolling"),
        ("cycle_only",            5,    0, 5, 15, "tripped_cycle"),
        ("cycle_just_above",      6,   14, 5, 15, "tripped_cycle"),
        ("both",                  5,   15, 5, 15, "tripped_both"),
        ("huge_both",           100, 1000, 5, 15, "tripped_both"),
    ],
)
def test_threshold_status_named_cases(
    name: str,
    count_cycle: int,
    count_rolling: int,
    cycle_threshold: int,
    rolling_threshold: int,
    expected: str,
) -> None:
    """Cover every named case from trip-predicate.contract.md § Test obligations."""
    extraction = _threshold_extraction(
        count_cycle=count_cycle, count_rolling=count_rolling
    )
    signal_def = _threshold_def(
        cycle_threshold=cycle_threshold,
        rolling_threshold=rolling_threshold,
    )
    assert _threshold_status(extraction, signal_def) == expected, name
