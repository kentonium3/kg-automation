"""Replay integration test against the 2026-06-01 captured log (T014).

Validates NFR-004 (filing accuracy within ±2 of ground truth) and
NFR-006 (time-to-action ≤30 min from event onset given 15-min cadence)
by simulating the orchestrator across the captured fixture's full
18-hour window in 15-minute cycles.

Ground truth (counted at test setup time from the captured fixture
``openclaw-2026-06-01.log``):

- 198 ``whatsapp_creds_restore`` events
- 153 ``web_watchdog_reconnect`` events
- 6 ``openclaw_unhandled_error`` events

These differ slightly from research.md §OD-2's earlier 193/149/6
because the captured fixture (WP-01 T006) is a slightly longer window
than the original calibration capture. The numbers were re-verified
by WP-01's signal-extraction primitives; the burst windows are
unchanged. See WP-02 implementer notes.

Approach:

1. Parse the captured fixture once and bucket events into 15-minute
   cycle windows.
2. For each cycle, write a per-cycle sliced log file containing ONLY
   lines whose ``time`` falls in ``[cycle_start, cycle_start + 15min)``.
3. Run ``tick.run_cycle(replay_log=sliced, dry_run=True, ...)`` with
   ``now_utc = cycle_start + 15min`` so the orchestrator sees exactly
   that cycle's events.
4. Each cycle uses a FRESH ``state_dir`` (no dedup carryover) so every
   tripped cycle records a "would file" in ``issues_skipped_dedup``
   with ``reason: dry_run``. This isolates threshold evaluation from
   the dedup machinery — the dedup behavior is exercised in
   ``test_tick_orchestrator.py``.
5. Assert NFR-004 (per-cycle counts within ±2 of ground truth) and
   NFR-006 (the very first cycle of the first burst at 00:00 trips
   and would-file within that cycle).

The test runs ``run_cycle`` as a Python function call (not a
subprocess) so coverage instrumentation captures it.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.openclaw.observation import filer as _filer  # noqa: E402
from scripts.openclaw.observation.signals.openclaw_log import (  # noqa: E402
    extract_event_time,
)
from scripts.openclaw.observation.tick import run_cycle  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture + ground-truth scan
# ---------------------------------------------------------------------------


_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "captured"
    / "openclaw-2026-06-01.log"
)

# Match patterns mirror ``signals/config.toml`` — keep in sync if the
# config ever changes (test will fail loudly if not).
_CREDS_NEEDLE = "restored corrupted WhatsApp creds.json from backup"
_WATCH_NEEDLE = "web reconnect: connection closed"
_ERROR_NEEDLE = '"logLevelName":"ERROR"'


def _signal_matches(raw_line: str, parsed: dict) -> dict[str, bool]:
    """Classify one log line by which signals it would match.

    Mirrors the extractor's match logic so the test ground truth is
    derived from the same shape the production code sees.
    """
    body_parts = []
    for k in sorted(parsed.keys()):
        if k.isdigit() and isinstance(parsed[k], str):
            body_parts.append(parsed[k])
    body = " ".join(body_parts)
    return {
        "creds": _CREDS_NEEDLE in body,
        "watch": _WATCH_NEEDLE in body,
        "error": _ERROR_NEEDLE in raw_line,
    }


def _cycle_floor(t: datetime) -> datetime:
    """Round ``t`` down to the nearest 15-minute cycle boundary."""
    return t.replace(
        minute=(t.minute // 15) * 15, second=0, microsecond=0
    )


def _parse_fixture() -> list[tuple[datetime, str, dict, dict[str, bool]]]:
    """Read the captured fixture once; return parsed records.

    Each tuple is (event_time_utc, raw_line, parsed_dict, matches_dict).
    Used by both the ground-truth bucket pass and the per-cycle log
    slicer.
    """
    records = []
    text = _FIXTURE_PATH.read_text(encoding="utf-8")
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        t = extract_event_time(parsed)
        if t is None:
            continue
        matches = _signal_matches(stripped, parsed)
        records.append((t, stripped, parsed, matches))
    return records


@pytest.fixture(scope="module")
def fixture_records():
    return _parse_fixture()


@pytest.fixture(scope="module")
def ground_truth(fixture_records):
    """Per-cycle (creds, watch, error) counts derived from the fixture."""
    buckets: dict[datetime, dict[str, int]] = {}
    for t, _raw, _parsed, matches in fixture_records:
        cycle = _cycle_floor(t)
        bucket = buckets.setdefault(
            cycle, {"creds": 0, "watch": 0, "error": 0}
        )
        if matches["creds"]:
            bucket["creds"] += 1
        if matches["watch"]:
            bucket["watch"] += 1
        if matches["error"]:
            bucket["error"] += 1
    return buckets


# ---------------------------------------------------------------------------
# Slicing helper
# ---------------------------------------------------------------------------


def _slice_log(
    records, cycle_start: datetime, cycle_end: datetime, out_path: Path
) -> int:
    """Write the lines whose ``time`` is in ``[cycle_start, cycle_end)``.

    Returns the number of lines written.
    """
    out_lines: list[str] = []
    for t, raw, _parsed, _matches in records:
        if cycle_start <= t < cycle_end:
            out_lines.append(raw)
    out_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return len(out_lines)


# ---------------------------------------------------------------------------
# Config writer (mirrors signals/config.toml thresholds)
# ---------------------------------------------------------------------------


def _write_config(path: Path, log_path: Path) -> None:
    """Write a config matching signals/config.toml seed thresholds."""
    path.write_text(
        f"""[meta]
schema_version = 1

[signals.whatsapp_creds_restore]
source_kind             = "openclaw_log"
source_path_pattern     = "{log_path}"
match_pattern           = "restored corrupted WhatsApp creds.json from backup"
match_kind              = "substring"
cycle_threshold         = 6
rolling_window_minutes  = 60
rolling_threshold       = 18
dedup_strategy          = "open_issue_present"
priority                = "P2"
area_label              = "felix-core"
tier_hypothesis         = "3"
excerpt_lines           = 5
enabled                 = true

[signals.web_watchdog_reconnect]
source_kind             = "openclaw_log"
source_path_pattern     = "{log_path}"
match_pattern           = "web reconnect: connection closed"
match_kind              = "substring"
cycle_threshold         = 10
rolling_window_minutes  = 60
rolling_threshold       = 25
dedup_strategy          = "open_issue_present"
priority                = "P2"
area_label              = "felix-core"
tier_hypothesis         = "3"
excerpt_lines           = 5
enabled                 = true

[signals.openclaw_unhandled_error]
source_kind             = "openclaw_log"
source_path_pattern     = "{log_path}"
match_pattern           = '"logLevelName":"ERROR"'
match_kind              = "substring"
cycle_threshold         = 3
rolling_window_minutes  = 60
rolling_threshold       = 5
dedup_strategy          = "open_issue_present"
priority                = "P2"
area_label              = "felix-core"
tier_hypothesis         = "3"
excerpt_lines           = 8
enabled                 = true
""",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Cycle simulation driver
# ---------------------------------------------------------------------------


def _simulate_cycles(
    tmp_path: Path,
    fixture_records,
    monkeypatch: pytest.MonkeyPatch,
) -> list[dict]:
    """Run one cycle per 15-minute slice of the fixture; collect last_tick payloads.

    Returns the list of last-tick.json dicts, one per cycle, in
    chronological order.
    """
    # Fail loudly if the filer is ever invoked — the test runs with
    # dry_run=True (replay forces it) so no shell-out should occur.
    monkeypatch.setattr(
        _filer,
        "file_threshold_trip",
        lambda *a, **kw: pytest.fail("replay test must not invoke filer"),
    )
    monkeypatch.setattr(
        _filer,
        "check_existing_issue_open",
        lambda *a, **kw: pytest.fail("replay test must not invoke gh CLI"),
    )

    # Window: first event's cycle floor → last event's cycle floor + 15min.
    first_t = min(r[0] for r in fixture_records)
    last_t = max(r[0] for r in fixture_records)
    window_start = _cycle_floor(first_t)
    window_end = _cycle_floor(last_t) + timedelta(minutes=15)

    cycle_payloads: list[dict] = []
    cycle_start = window_start
    while cycle_start < window_end:
        cycle_end = cycle_start + timedelta(minutes=15)
        sliced_log = (
            tmp_path
            / f"slice-{cycle_start.strftime('%H%M')}.log"
        )
        line_count = _slice_log(
            fixture_records, cycle_start, cycle_end, sliced_log
        )

        last_tick = (
            tmp_path / f"last-tick-{cycle_start.strftime('%H%M')}.json"
        )
        config = tmp_path / f"config-{cycle_start.strftime('%H%M')}.toml"
        # The config's source_path_pattern is overridden by --replay-log,
        # so the slice_log path is the one that actually matters.
        _write_config(config, sliced_log)

        # Fresh state-dir per cycle so dedup never suppresses; we're
        # testing extraction accuracy, not dedup (which has its own
        # tests in test_tick_orchestrator.py).
        state_dir = (
            tmp_path / f"state-{cycle_start.strftime('%H%M')}"
        )

        # Run the cycle. Replay implies dry_run; filing_enabled stays
        # at the default (None → False because dry_run=True).
        rc = run_cycle(
            config_path=config,
            state_dir=state_dir,
            last_tick_path=last_tick,
            ledger_path=tmp_path / "ledger.jsonl",
            now_utc=cycle_end,
            dry_run=True,
            replay_log=sliced_log,
        )
        # rc 0 — replay should never hit config-load failure since we
        # write the config inline above.
        assert rc == 0, (
            f"replay cycle {cycle_start} returned rc={rc}"
        )

        payload = json.loads(last_tick.read_text(encoding="utf-8"))
        payload["_cycle_start"] = cycle_start.isoformat()
        payload["_line_count"] = line_count
        cycle_payloads.append(payload)
        cycle_start = cycle_end

    return cycle_payloads


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_ground_truth_matches_known_totals(fixture_records, ground_truth):
    """Sanity: the fixture has the totals WP-01 verified."""
    totals = {"creds": 0, "watch": 0, "error": 0}
    for bucket in ground_truth.values():
        totals["creds"] += bucket["creds"]
        totals["watch"] += bucket["watch"]
        totals["error"] += bucket["error"]
    assert totals == {"creds": 198, "watch": 153, "error": 6}


def test_nfr_004_per_cycle_counts_match_ground_truth(
    tmp_path, fixture_records, ground_truth, monkeypatch
):
    """NFR-004 accuracy: every cycle's reported count is within ±2 of ground truth.

    The signal-extraction loop is deterministic — there should be NO
    drift (delta ≤ 2 is the spec's slack, but in practice we observe 0).
    A failure here means either the extractor is mis-counting or the
    test's slicing logic doesn't match the extractor's match logic.
    """
    payloads = _simulate_cycles(tmp_path, fixture_records, monkeypatch)

    # Build per-cycle observed counts keyed by cycle_start ISO string.
    observed: dict[str, dict[str, int]] = {}
    for payload in payloads:
        cycle_iso = payload["_cycle_start"]
        observed[cycle_iso] = {}
        for sig in payload["signals_evaluated"]:
            short = {
                "whatsapp_creds_restore": "creds",
                "web_watchdog_reconnect": "watch",
                "openclaw_unhandled_error": "error",
            }.get(sig["signal_id"])
            if short is not None:
                observed[cycle_iso][short] = sig["count_cycle"]

    drifts: list[tuple[str, str, int, int]] = []
    for cycle_start_dt, expected in ground_truth.items():
        cycle_iso = cycle_start_dt.isoformat()
        actual = observed.get(cycle_iso, {"creds": 0, "watch": 0, "error": 0})
        for key in ("creds", "watch", "error"):
            delta = abs(actual.get(key, 0) - expected[key])
            if delta > 2:
                drifts.append(
                    (cycle_iso, key, expected[key], actual.get(key, 0))
                )
    assert not drifts, f"NFR-004 violated: cycles outside ±2: {drifts}"


def test_nfr_004_burst_cycles_trip_threshold(
    tmp_path, fixture_records, monkeypatch
):
    """NFR-004 filing scope: at least 3 cycles trip the creds threshold.

    Per the WP prompt: ≥3 filings for ``whatsapp_creds_restore``
    correspond to the burst windows. Each tripped cycle records a
    ``issues_skipped_dedup`` entry with ``reason: dry_run`` (the
    "would file" record under replay dry-run semantics).
    """
    payloads = _simulate_cycles(tmp_path, fixture_records, monkeypatch)

    creds_trip_cycles = []
    for payload in payloads:
        for sig in payload["signals_evaluated"]:
            if (
                sig["signal_id"] == "whatsapp_creds_restore"
                and sig["threshold_status"] != "below"
            ):
                creds_trip_cycles.append(payload["_cycle_start"])
                break

    assert len(creds_trip_cycles) >= 3, (
        f"NFR-004: expected ≥3 creds_restore trip cycles, "
        f"got {creds_trip_cycles}"
    )


def test_nfr_004_quiet_hours_do_not_trip_threshold(
    tmp_path, fixture_records, monkeypatch
):
    """During quiet hours (background rate ~1-2/15min) creds threshold stays below.

    Hour 04-10 UTC is the documented quiet stretch; per the bucket
    pass at the top of this module, each cycle there has 0-1 events,
    well under cycle_threshold=6. We use 06:00 and 09:00 cycles as
    representatives.
    """
    payloads = _simulate_cycles(tmp_path, fixture_records, monkeypatch)
    by_cycle = {p["_cycle_start"]: p for p in payloads}

    quiet_cycle_starts = [
        "2026-06-01T06:00:00+00:00",
        "2026-06-01T09:00:00+00:00",
        "2026-06-01T13:00:00+00:00",
    ]
    for cs in quiet_cycle_starts:
        payload = by_cycle.get(cs)
        if payload is None:
            continue  # cycle had zero events — skipped by simulator.
        for sig in payload["signals_evaluated"]:
            if sig["signal_id"] == "whatsapp_creds_restore":
                assert sig["threshold_status"] == "below", (
                    f"quiet hour {cs} should not trip creds, "
                    f"got {sig}"
                )


def test_nfr_006_first_burst_files_in_first_cycle(
    tmp_path, fixture_records, monkeypatch
):
    """NFR-006 latency: the 00:00 cycle (burst onset) trips immediately.

    "Files within ≤1 cycle of onset" — in this fixture the very first
    cycle 00:00–00:15 already has 14 creds_restore events, well above
    cycle_threshold=6. So the burst is detected the same cycle it
    starts (zero-cycle latency); the test asserts this is true so any
    regression that pushed first-trip to the second cycle would fail.
    """
    payloads = _simulate_cycles(tmp_path, fixture_records, monkeypatch)
    # First chronological payload should be the 00:00–00:15 cycle.
    first = payloads[0]
    assert first["_cycle_start"] == "2026-06-01T00:00:00+00:00"

    creds_sig = next(
        s
        for s in first["signals_evaluated"]
        if s["signal_id"] == "whatsapp_creds_restore"
    )
    assert creds_sig["threshold_status"] != "below", (
        f"NFR-006 violated: 00:00 burst did not trip first cycle: {creds_sig}"
    )
    # And: the "would file" record exists in issues_skipped_dedup
    # (dry-run replay records "would file" there).
    skipped_signals = {
        s["signal_id"] for s in first["issues_skipped_dedup"]
    }
    assert "whatsapp_creds_restore" in skipped_signals, (
        f"NFR-006: expected creds_restore in issues_skipped_dedup "
        f"(would-file record), got {first['issues_skipped_dedup']}"
    )


def test_replay_does_not_invoke_filer_or_gh(
    tmp_path, fixture_records, monkeypatch
):
    """Replay mode (dry_run) must never shell out — the monkeypatch
    fixtures in ``_simulate_cycles`` already fail-on-call. This test
    runs the simulation just to confirm the assertion structure
    succeeds end-to-end."""
    payloads = _simulate_cycles(tmp_path, fixture_records, monkeypatch)
    assert all(p["dry_run"] is True for p in payloads)
    assert all(p["issues_filed"] == [] for p in payloads)
