"""Tick orchestrator for the signal-extraction pipeline (WP-02 T010-T012).

One-shot entrypoint: load config + state, run each enabled signal's
extractor against its source, evaluate thresholds, dedup against any
open GitHub issue, file via the deterministic filer, persist updated
state, write ``last-tick.json`` atomically, append the cycle record
to ``signals-ledger.jsonl``, and emit a stdout SUMMARY line.

Systemd (WP-03) invokes this script every 15 minutes via a timer.
There is no daemon loop — each invocation is one cycle.

CLI flags:

- ``--config <path>`` — path to ``signals/config.toml`` (default: the
  in-repo copy next to this file).
- ``--state-dir <path>`` — per-signal state directory (default:
  ``/data/services/openclaw/felix-core-digest-signals/state``).
- ``--last-tick <path>`` — atomic-write target for the latest-cycle JSON
  (default: ``/data/services/openclaw/felix-core-digest-signals/last-tick.json``).
- ``--ledger <path>`` — append-only JSONL of all cycles (default:
  ``/data/services/openclaw/felix-core-digest-signals/signals-ledger.jsonl``).
- ``--dry-run`` — read + evaluate + write last-tick.json but do NOT
  save per-signal state and do NOT shell out to the filer. The
  ``last-tick.json`` carries ``dry_run: true`` and the SUMMARY line is
  prefixed ``[DRY-RUN]``.
- ``--replay-log <path>`` — override the source resolution for any
  signal whose ``source_kind == "openclaw_log"``: use this single file
  from byte 0 (no cursor). Implies ``--dry-run`` unless
  ``--no-dry-run-with-replay`` is also passed.
- ``--no-dry-run-with-replay`` — escape hatch: with ``--replay-log`` and
  this flag, the filer DOES shell out. Use with care.

Architectural precedent: mirrors ``scripts/doc_audit/run.py``'s style
(argparse → run → SUMMARY line) and reuses the same atomic-write
pattern from ``scripts/openclaw/observation/state.py``.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import tempfile
import time as _time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

# sys.path bootstrap so the module is runnable directly via
# ``python3 scripts/openclaw/observation/tick.py``. WP-01 modules
# import via ``scripts.openclaw...`` package paths, which requires
# the REPO ROOT (parent of ``scripts/``) to be on sys.path. When
# the caller already has PYTHONPATH set (pytest with conftest), this
# is a no-op.
_REPO_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_FOR_IMPORTS))

from scripts.openclaw.observation import filer as _filer  # noqa: E402
from scripts.openclaw.observation.signals import (  # noqa: E402
    creds_restore as _creds_restore,
)
from scripts.openclaw.observation.signals import (  # noqa: E402
    unhandled_error as _unhandled_error,
)
from scripts.openclaw.observation.signals import (  # noqa: E402
    watchdog_reconnect as _watchdog_reconnect,
)
from scripts.openclaw.observation.signals.config_loader import (  # noqa: E402
    SignalDefinition,
    load_config,
)
from scripts.openclaw.observation.signals.openclaw_log import (  # noqa: E402
    LogCursor,
)
from scripts.openclaw.observation.signals.types import (  # noqa: E402
    SignalExtraction,
)
from scripts.openclaw.observation.state import (  # noqa: E402
    RollingBucket,
    SignalState,
    evict_old_buckets,
    load_state,
    save_state,
)

__all__ = [
    "CycleRecord",
    "DEFAULT_CONFIG_PATH",
    "DEFAULT_STATE_DIR",
    "DEFAULT_LAST_TICK_PATH",
    "DEFAULT_LEDGER_PATH",
    "SCHEMA_VERSION",
    "build_extractor_dispatch",
    "main",
    "run_cycle",
]


# Tick-signal JSON schema version (matches contracts/tick-signal.contract.md).
SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Defaults — used by argparse + tests
# ---------------------------------------------------------------------------


# In-repo seed config (deployment process copies to office2; the
# orchestrator falls back to this when --config is omitted, which is
# the common case for local smoke tests).
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "signals" / "config.toml"

DEFAULT_STATE_DIR = Path(
    "/data/services/openclaw/felix-core-digest-signals/state"
)
DEFAULT_LAST_TICK_PATH = Path(
    "/data/services/openclaw/felix-core-digest-signals/last-tick.json"
)
DEFAULT_LEDGER_PATH = Path(
    "/data/services/openclaw/felix-core-digest-signals/signals-ledger.jsonl"
)


# ---------------------------------------------------------------------------
# Cycle record (data-model.md §E3)
# ---------------------------------------------------------------------------


@dataclass
class CycleRecord:
    """E3 Cycle record — per-cycle execution summary.

    Mutable so :func:`run_cycle` can incrementally append signals,
    filings, and errors as it processes each signal. Serializes to
    the schema in ``contracts/tick-signal.contract.md`` via
    :meth:`to_signal_dict`.
    """

    cycle_id: str
    started_at_utc: str
    duration_ms: int = 0
    exit_status: str = "success"
    signals_evaluated: list[dict] = field(default_factory=list)
    issues_filed: list[dict] = field(default_factory=list)
    issues_skipped_dedup: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    dry_run: bool = False

    def to_signal_dict(self) -> dict[str, Any]:
        """Serialize to the ``last-tick.json`` schema (v1)."""
        return {
            "schema_version": SCHEMA_VERSION,
            "cycle_id": self.cycle_id,
            "started_at_utc": self.started_at_utc,
            "duration_ms": self.duration_ms,
            "exit_status": self.exit_status,
            "dry_run": self.dry_run,
            "signals_evaluated": self.signals_evaluated,
            "issues_filed": self.issues_filed,
            "issues_skipped_dedup": self.issues_skipped_dedup,
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Crockford Base32 alphabet (excludes I, L, O, U) — ULID spec §4.
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_cycle_id(now_utc: datetime) -> str:
    """Generate a 26-character ULID-shaped identifier.

    Stdlib-only ULID: 48-bit millisecond timestamp + 80 bits of random
    data, encoded in Crockford Base32. Sortable lexicographically by
    time, which matters because the ledger reads sort by cycle_id for
    debugging.

    Not a perfectly-canonical ULID (we don't enforce monotonicity
    within the same millisecond) but it's spec-shaped — same length,
    same alphabet, time-sortable to ms precision — so log greppers
    and future ULID-aware tooling treat it identically.
    """
    ts_ms = int(now_utc.timestamp() * 1000)
    rand_bytes = secrets.token_bytes(10)  # 80 bits
    rand_int = int.from_bytes(rand_bytes, "big")
    # Pack timestamp (48 bits) and randomness (80 bits) into 128 bits.
    value = (ts_ms << 80) | rand_int
    out = []
    for _ in range(26):
        out.append(_CROCKFORD[value & 0x1F])
        value >>= 5
    return "".join(reversed(out))


def _iso_z(dt: datetime) -> str:
    """Render a tz-aware datetime as ISO-8601 with ``Z`` suffix."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write_json(target: Path, payload: dict) -> None:
    """Atomically overwrite ``target`` with ``payload`` as JSON.

    Mirrors the pattern in ``state.save_state`` and
    ``scripts/doc_audit/output/tick_signal.py``: write a tempfile in
    the SAME directory (so ``os.rename`` is POSIX-atomic), fsync,
    rename, and clean up on rename failure.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=str(target.parent),
            prefix=target.name + ".",
            suffix=".tmp",
            delete=False,
            encoding="utf-8",
        ) as fp:
            json.dump(payload, fp, indent=2)
            fp.flush()
            os.fsync(fp.fileno())
            tmp_path = Path(fp.name)
        os.rename(tmp_path, target)
        tmp_path = None
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except OSError:  # pragma: no cover — best-effort cleanup
                pass


def _append_ledger(target: Path, payload: dict) -> None:
    """Append one JSON line to ``target`` (JSONL convention).

    Open-append-close per line keeps the writer simple and matches the
    doc_audit ledger idiom. Append is reasonably safe under low
    concurrency (only one tick runs at a time per host); no fcntl lock
    needed.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# Threshold evaluation
# ---------------------------------------------------------------------------


def _threshold_status(
    extraction: SignalExtraction, signal_def: SignalDefinition
) -> str:
    """Classify a signal's threshold posture for this cycle.

    Returns one of ``"below"``, ``"tripped_cycle"``, ``"tripped_rolling"``,
    ``"tripped_both"`` per ``contracts/tick-signal.contract.md``.
    """
    cycle_hit = extraction.count_cycle >= signal_def.cycle_threshold
    rolling_hit = extraction.count_rolling >= signal_def.rolling_threshold
    if cycle_hit and rolling_hit:
        return "tripped_both"
    if cycle_hit:
        return "tripped_cycle"
    if rolling_hit:
        return "tripped_rolling"
    return "below"


# ---------------------------------------------------------------------------
# Extractor dispatch
# ---------------------------------------------------------------------------


# Per-signal extractor function (state_dir, signal_def, now_utc,
# prior_cursor, prior_rolling_count) -> SignalExtraction.
ExtractorFn = Callable[
    [Any, SignalDefinition, datetime, Optional[LogCursor], int],
    SignalExtraction,
]


def build_extractor_dispatch() -> dict[str, ExtractorFn]:
    """Return the {signal_id → extractor function} table.

    Centralized so tests can patch the dispatch without monkey-patching
    individual modules. The orchestrator looks up by signal_id; if a
    signal isn't in the table the cycle records an error (not a crash).
    """
    return {
        "whatsapp_creds_restore": _creds_restore.extract,
        "web_watchdog_reconnect": _watchdog_reconnect.extract,
        "openclaw_unhandled_error": _unhandled_error.extract,
    }


# ---------------------------------------------------------------------------
# Replay-mode glob override
# ---------------------------------------------------------------------------


def _install_replay_override(replay_log: Path) -> Callable[[], None]:
    """Patch ``resolve_log_files`` to return a single static path.

    Used by ``--replay-log``. Returns a callable that reverts the patch
    so the orchestrator can restore the original behavior at end of
    cycle (defensive — the process exits anyway, but keeps tests clean).

    Replay mode also forces "no cursor" behavior at the call site
    (caller passes ``prior_cursor=None``); we don't override that here.
    """
    from scripts.openclaw.observation.signals import (
        _engine as _engine_mod,
    )
    from scripts.openclaw.observation.signals import (
        openclaw_log as _openclaw_log_mod,
    )

    original_engine = _engine_mod.resolve_log_files
    original_log = _openclaw_log_mod.resolve_log_files
    static = [Path(replay_log)]

    def fake_resolve(_pattern: str, _now_utc: datetime) -> list[Path]:
        return [p for p in static if p.is_file()]

    _engine_mod.resolve_log_files = fake_resolve  # type: ignore[assignment]
    _openclaw_log_mod.resolve_log_files = fake_resolve  # type: ignore[assignment]

    def restore() -> None:
        _engine_mod.resolve_log_files = original_engine  # type: ignore[assignment]
        _openclaw_log_mod.resolve_log_files = original_log  # type: ignore[assignment]

    return restore


# ---------------------------------------------------------------------------
# Core cycle
# ---------------------------------------------------------------------------


def _state_to_cursor(state: Optional[SignalState]) -> Optional[LogCursor]:
    """Reconstruct a :class:`LogCursor` from a persisted state dict."""
    if state is None or state.last_log_position is None:
        return None
    pos = state.last_log_position
    try:
        return LogCursor(
            path=str(pos["path"]),
            inode=int(pos["inode"]),
            byte_offset=int(pos["byte_offset"]),
            mtime=float(pos["mtime"]),
        )
    except (KeyError, TypeError, ValueError):
        # Malformed cursor — treat as cold start. The engine handles
        # ``None`` cursors by reading every resolved file from byte 0.
        return None


def _cursor_to_dict(cursor: Optional[LogCursor]) -> Optional[dict]:
    """Render a cursor for persistence in :class:`SignalState`."""
    if cursor is None:
        return None
    return {
        "path": cursor.path,
        "inode": cursor.inode,
        "byte_offset": cursor.byte_offset,
        "mtime": cursor.mtime,
    }


def _prior_rolling_count(state: Optional[SignalState]) -> int:
    """Sum the count from current rolling buckets (post-eviction)."""
    if state is None:
        return 0
    return sum(b.count for b in state.rolling_buckets)


def _update_state_after_extraction(
    state: Optional[SignalState],
    signal_def: SignalDefinition,
    extraction: SignalExtraction,
    cycle_id: str,
    now_utc: datetime,
) -> SignalState:
    """Return a new :class:`SignalState` with this cycle's data merged in.

    Adds a new rolling bucket for this cycle's count, refreshes the
    cursor, and updates ``last_event_at_utc``. Does NOT touch
    ``last_filed_issue_ref`` — only successful filings update that
    field, and the caller does it explicitly after the filer returns.
    """
    started_at = _iso_z(now_utc)
    new_bucket = RollingBucket(
        cycle_id=cycle_id,
        started_at=started_at,
        count=extraction.count_cycle,
    )
    if state is None:
        buckets = [new_bucket]
        last_filed_issue_ref: Optional[int] = None
        last_filed_at_utc: Optional[str] = None
    else:
        # Evict was already applied earlier; just append this cycle.
        buckets = list(state.rolling_buckets) + [new_bucket]
        last_filed_issue_ref = state.last_filed_issue_ref
        last_filed_at_utc = state.last_filed_at_utc

    last_event = (
        _iso_z(extraction.last_event_at_utc)
        if extraction.last_event_at_utc is not None
        else (state.last_event_at_utc if state is not None else None)
    )

    return SignalState(
        signal_id=signal_def.signal_id,
        cycle_id=cycle_id,
        last_cycle_count=extraction.count_cycle,
        rolling_buckets=buckets,
        last_event_at_utc=last_event,
        last_filed_issue_ref=last_filed_issue_ref,
        last_filed_at_utc=last_filed_at_utc,
        last_log_position=_cursor_to_dict(extraction.new_cursor),
    )


def _process_signal(
    signal_def: SignalDefinition,
    state_dir: Path,
    cycle_id: str,
    now_utc: datetime,
    dispatch: dict[str, ExtractorFn],
    *,
    dry_run: bool,
    replay_mode: bool,
    filing_enabled: bool,
    record: CycleRecord,
) -> None:
    """Run one signal end-to-end: extract → evaluate → file → persist.

    All errors are caught and recorded in ``record.errors``. The signal
    is appended to ``record.signals_evaluated`` either way so the
    operator can see which signals ran (vs which were entirely skipped).
    """
    extractor = dispatch.get(signal_def.signal_id)
    if extractor is None:
        record.errors.append(
            {
                "signal_id": signal_def.signal_id,
                "error_type": "unknown_signal_id",
                "error_message": (
                    f"No extractor registered for signal_id="
                    f"{signal_def.signal_id!r}"
                ),
            }
        )
        return

    # ---- Load + evict state ---------------------------------------
    try:
        loaded_state = load_state(state_dir, signal_def.signal_id)
    except (ValueError, OSError) as exc:
        record.errors.append(
            {
                "signal_id": signal_def.signal_id,
                "error_type": "state_corrupt",
                "error_message": str(exc),
            }
        )
        loaded_state = None

    if loaded_state is not None:
        loaded_state = evict_old_buckets(
            loaded_state, signal_def.rolling_window_minutes, now_utc
        )

    # In replay mode we always start from byte 0 (no cursor) so the
    # static fixture re-reads cleanly every cycle.
    prior_cursor = (
        None if replay_mode else _state_to_cursor(loaded_state)
    )
    prior_rolling = _prior_rolling_count(loaded_state)

    # ---- Extract ---------------------------------------------------
    try:
        extraction = extractor(
            state_dir,
            signal_def,
            now_utc,
            prior_cursor,
            prior_rolling,
        )
    except Exception as exc:  # noqa: BLE001 — extractor must not break the cycle
        record.errors.append(
            {
                "signal_id": signal_def.signal_id,
                "error_type": "extractor_failed",
                "error_message": f"{type(exc).__name__}: {exc}",
            }
        )
        record.signals_evaluated.append(
            {
                "signal_id": signal_def.signal_id,
                "count_cycle": 0,
                "count_rolling": prior_rolling,
                "threshold_status": "below",
            }
        )
        return

    status = _threshold_status(extraction, signal_def)
    record.signals_evaluated.append(
        {
            "signal_id": signal_def.signal_id,
            "count_cycle": extraction.count_cycle,
            "count_rolling": extraction.count_rolling,
            "threshold_status": status,
        }
    )

    new_state = _update_state_after_extraction(
        loaded_state, signal_def, extraction, cycle_id, now_utc
    )

    # ---- File (or not) --------------------------------------------
    tripped = status != "below"
    if tripped and filing_enabled:
        # Dedup: if prior filed issue is still OPEN, suppress filing.
        prior_ref = new_state.last_filed_issue_ref
        suppress = False
        if prior_ref is not None:
            try:
                suppress = _filer.check_existing_issue_open(prior_ref)
            except Exception as exc:  # noqa: BLE001 — defensive; check_existing_issue_open already swallows
                record.errors.append(
                    {
                        "signal_id": signal_def.signal_id,
                        "error_type": "dedup_check_failed",
                        "error_message": f"{type(exc).__name__}: {exc}",
                    }
                )
                suppress = False

        if suppress:
            record.issues_skipped_dedup.append(
                {
                    "signal_id": signal_def.signal_id,
                    "existing_issue_ref": prior_ref,
                }
            )
        else:
            filing = _filer.file_threshold_trip(
                signal_def, extraction, new_state, now_utc
            )
            if filing.error is not None:
                record.errors.append(
                    {
                        "signal_id": signal_def.signal_id,
                        "error_type": filing.error.error_type,
                        "error_message": filing.error.error_message,
                    }
                )
            else:
                record.issues_filed.append(
                    {
                        "signal_id": signal_def.signal_id,
                        "issue_number": filing.issue_number,
                        "issue_url": filing.issue_url,
                    }
                )
                new_state = SignalState(
                    signal_id=new_state.signal_id,
                    cycle_id=new_state.cycle_id,
                    last_cycle_count=new_state.last_cycle_count,
                    rolling_buckets=new_state.rolling_buckets,
                    last_event_at_utc=new_state.last_event_at_utc,
                    last_filed_issue_ref=filing.issue_number,
                    last_filed_at_utc=_iso_z(now_utc),
                    last_log_position=new_state.last_log_position,
                )
    elif tripped and not filing_enabled:
        # dry-run or replay-without-explicit-live: record what we WOULD file.
        record.issues_skipped_dedup.append(
            {
                "signal_id": signal_def.signal_id,
                "existing_issue_ref": new_state.last_filed_issue_ref,
                "reason": "dry_run",
            }
        )

    # ---- Persist state (skipped under dry-run) --------------------
    if not dry_run:
        try:
            save_state(state_dir, new_state)
        except OSError as exc:
            record.errors.append(
                {
                    "signal_id": signal_def.signal_id,
                    "error_type": "state_write_failed",
                    "error_message": str(exc),
                }
            )


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def run_cycle(
    *,
    config_path: Path,
    state_dir: Path,
    last_tick_path: Path,
    ledger_path: Path,
    now_utc: datetime,
    dry_run: bool = False,
    replay_log: Optional[Path] = None,
    filing_enabled: Optional[bool] = None,
    force_replay_filing: bool = False,
    dispatch: Optional[dict[str, ExtractorFn]] = None,
) -> int:
    """Run one observation cycle. Return the process exit code (0/1).

    Args:
        config_path: Path to the signal config TOML.
        state_dir: Per-signal state directory.
        last_tick_path: Atomic-write target for the cycle's tick signal.
        ledger_path: Append-only JSONL of all cycles.
        now_utc: Cycle clock. Must be timezone-aware UTC. Tests use
            this to deterministically simulate cycles in replay.
        dry_run: If True, skip state persistence and do not file. Note:
            when ``replay_log`` is provided, ``dry_run`` is forced to
            True regardless of the caller's value, unless
            ``force_replay_filing`` is also True. This makes
            ``run_cycle(replay_log=...)`` safe by default at the
            function-call layer, mirroring CLI behavior.
        replay_log: If provided, override source resolution to use this
            static file. Implies ``dry_run`` unless
            ``force_replay_filing`` is explicitly True (the
            ``--no-dry-run-with-replay`` flag at the CLI layer).
        filing_enabled: Explicit override of the filing path. Default
            is "file iff not dry_run". The CLI sets this to True when
            ``--no-dry-run-with-replay`` is passed in replay mode.
        force_replay_filing: When True, allows live filing during
            replay. Must be explicitly opted into. The
            ``--no-dry-run-with-replay`` CLI flag is the canonical
            caller; direct Python callers must also opt in explicitly.
            Without this flag, ``replay_log`` forces ``dry_run=True``
            so a stray function-call replay never triggers live filing.
        dispatch: Test-injection override for the extractor table.
    """
    if now_utc.tzinfo is None:
        raise ValueError("run_cycle: now_utc must be tz-aware UTC")

    # Replay-safe default at the function-call layer: a replay_log
    # without an explicit force_replay_filing opt-in forces BOTH
    # ``dry_run=True`` and ``filing_enabled=False``, regardless of what
    # the caller passed. This mirrors the CLI's --replay-log behavior and
    # prevents a stray Python caller from accidentally invoking the live
    # filer when replaying a historical log — including a caller who
    # explicitly sets ``filing_enabled=True``. ``force_replay_filing=True``
    # is the only key that unlocks live filing in replay mode.
    # See WP02 T012/T014 + cycle-1/cycle-2 review.
    if replay_log is not None and not force_replay_filing:
        dry_run = True
        filing_enabled = False

    cycle_id = new_cycle_id(now_utc)
    started_at = _iso_z(now_utc)
    start_perf = _time.perf_counter()
    record = CycleRecord(
        cycle_id=cycle_id,
        started_at_utc=started_at,
        dry_run=dry_run,
    )

    # Filing decision: explicit override wins; otherwise file iff not
    # dry_run. Replay mode forces dry_run + filing_enabled=False above
    # unless force_replay_filing is set, so this stays simple here.
    if filing_enabled is None:
        filing_enabled = not dry_run

    # ---- Replay-glob override (if any) ----------------------------
    restore_resolve: Optional[Callable[[], None]] = None
    if replay_log is not None:
        restore_resolve = _install_replay_override(replay_log)

    try:
        # ---- Load config ------------------------------------------
        try:
            signal_defs = load_config(config_path)
        except Exception as exc:  # noqa: BLE001 — config errors abort the cycle
            record.errors.append(
                {
                    "signal_id": None,
                    "error_type": "config_load_failed",
                    "error_message": f"{type(exc).__name__}: {exc}",
                }
            )
            record.exit_status = "failure"
            record.duration_ms = int(
                (_time.perf_counter() - start_perf) * 1000
            )
            _finalize_cycle(record, last_tick_path, ledger_path)
            return 1

        if dispatch is None:
            dispatch = build_extractor_dispatch()
        replay_mode = replay_log is not None

        # ---- Process each enabled signal --------------------------
        for signal_def in signal_defs:
            if not signal_def.enabled:
                continue
            _process_signal(
                signal_def,
                state_dir,
                cycle_id,
                now_utc,
                dispatch,
                dry_run=dry_run,
                replay_mode=replay_mode,
                filing_enabled=filing_enabled,
                record=record,
            )

        # ---- Status derivation ------------------------------------
        if record.errors:
            # Partial when extractor/filer/state errors happened but
            # the cycle ran to completion. ``failure`` is reserved for
            # cycle-aborting errors (config load, etc.).
            record.exit_status = "partial"

        record.duration_ms = int(
            (_time.perf_counter() - start_perf) * 1000
        )
        _finalize_cycle(record, last_tick_path, ledger_path)
        # Exit 0 on partial — operator inspects last-tick.json.errors.
        # The cycle ran; it just had per-signal issues. systemd
        # OnFailure= only fires on non-zero exit, and we don't want
        # an alarm storm from a single bad extractor.
        return 0
    finally:
        if restore_resolve is not None:
            restore_resolve()


def _finalize_cycle(
    record: CycleRecord, last_tick_path: Path, ledger_path: Path
) -> None:
    """Write last-tick.json + append the ledger + print SUMMARY.

    Split out of :func:`run_cycle` so the failure-fast path and the
    happy path share one finalization implementation.
    """
    payload = record.to_signal_dict()
    try:
        _atomic_write_json(last_tick_path, payload)
    except OSError as exc:
        # Log to stderr; the in-memory record already carries the
        # cycle's truth. Failing to write last-tick is a Tier 3
        # incident but we don't want to crash the orchestrator over
        # it — the next cycle's write will fix the state.
        print(
            f"WARN: tick: failed to write last-tick.json {last_tick_path}: "
            f"{exc}",
            file=sys.stderr,
        )
    try:
        _append_ledger(ledger_path, payload)
    except OSError as exc:
        print(
            f"WARN: tick: failed to append ledger {ledger_path}: {exc}",
            file=sys.stderr,
        )

    # SUMMARY line — operator-friendly, parseable by future tooling.
    prefix = "[DRY-RUN] " if record.dry_run else ""
    short_id = record.cycle_id[-8:] if record.cycle_id else "????????"
    print(
        f"{prefix}SUMMARY: cycle={short_id} "
        f"filed={len(record.issues_filed)} "
        f"skipped={len(record.issues_skipped_dedup)} "
        f"errors={len(record.errors)} "
        f"dur={record.duration_ms}ms"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: Optional[list[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="tick.py",
        description=(
            "Run one observation cycle of the felix-core-digest "
            "signal-extraction pipeline. Reads signal config, walks "
            "OpenClaw logs, evaluates thresholds, dedup-checks against "
            "existing GitHub issues, files via the deterministic "
            "filer, writes last-tick.json, and appends a row to the "
            "signals ledger. Designed for systemd-timer invocation "
            "every 15 minutes."
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=(
            "Path to signals/config.toml. Default: the in-repo seed "
            "next to this script."
        ),
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=DEFAULT_STATE_DIR,
        help="Per-signal state directory.",
    )
    parser.add_argument(
        "--last-tick",
        type=Path,
        default=DEFAULT_LAST_TICK_PATH,
        help="Path to write last-tick.json (atomic).",
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=DEFAULT_LEDGER_PATH,
        help="Path to the append-only signals-ledger.jsonl.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Evaluate signals + write last-tick.json, but do NOT save "
            "per-signal state and do NOT shell out to the filer."
        ),
    )
    parser.add_argument(
        "--replay-log",
        type=Path,
        default=None,
        help=(
            "Override source resolution: use this single static log "
            "file for all openclaw_log signals (read from byte 0; no "
            "cursor). Implies --dry-run unless "
            "--no-dry-run-with-replay is also passed."
        ),
    )
    parser.add_argument(
        "--no-dry-run-with-replay",
        action="store_true",
        help=(
            "Escape hatch: with --replay-log, file issues for real. "
            "Use only when intentionally replaying a captured incident "
            "to retroactively file."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entrypoint. Returns a shell-friendly exit code."""
    args = _parse_args(argv)

    # Replay mode forces dry-run unless the explicit escape hatch is set.
    dry_run = bool(args.dry_run)
    filing_enabled: Optional[bool] = None
    force_replay_filing = False
    if args.replay_log is not None and not args.no_dry_run_with_replay:
        dry_run = True
    if args.replay_log is not None and args.no_dry_run_with_replay:
        # Replay + filing: explicitly enable filing even though
        # dry_run might be False already. Also opt in to the
        # function-layer escape hatch so run_cycle() doesn't
        # re-force dry_run=True from its own replay-safe guard.
        filing_enabled = True
        force_replay_filing = True

    return run_cycle(
        config_path=args.config,
        state_dir=args.state_dir,
        last_tick_path=args.last_tick,
        ledger_path=args.ledger,
        now_utc=datetime.now(tz=timezone.utc),
        dry_run=dry_run,
        replay_log=args.replay_log,
        filing_enabled=filing_enabled,
        force_replay_filing=force_replay_filing,
    )


if __name__ == "__main__":  # pragma: no cover — CLI dispatch
    sys.exit(main())
