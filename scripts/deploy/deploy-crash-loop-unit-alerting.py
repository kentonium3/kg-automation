#!/usr/bin/env python3
"""Deploy entrypoint: prove felix-canary's crash-loop stage is live and
complete on all three scopes (#1133).

Tier 3 (user-level code under the ``claude`` account; no unit content
changes; no Tier 0/1/2 action).

WHY. On 2026-11-23 obsidian-sync.service crash-looped 39 times and nothing
alerted: systemd restarted it each time, so every point-in-time check saw
``active (running)``. The fix is a crash-loop stage inside felix-canary that
compares restart counters across ticks. That code reaches office2 when
felix-deployer advances the checkout, because the canary runs from it. A
checkout pull cannot show the stage actually works, so this entrypoint does:

  0. Preflight: euid's passwd name is ``claude`` and ``Path.home()`` is
     ``/home/claude``; ``scripts/canary/crash_loop_config.json`` loads through
     ``crash_loop_model.load_config``.
  1. Record ``t0``, then run the canary once for real
     (``systemctl --user start felix-canary.service``; the oneshot blocks until
     the pass finishes).
  2. Prove the stage from the FRESH artifacts. Every check is individual, so a
     combined status cannot hide one scope's ``unknown``:
       (a) ``crash-loop.json`` ``updated_at_utc >= t0`` and ``schema_version``
           is 2 (the tick-counting state of Kent's 2026-11-24 ruling, R-16);
       (b) the canary ledger has ``crash-loop:system``, ``crash-loop:user`` and
           ``crash-loop:container`` lines with ``evaluated_at >= t0``, each
           ``healthy`` (the scope was read completely);
       (c) ``last-tick.json`` ``completed_at_utc >= t0`` and no ``errors``
           entry starts with ``crash_loop`` or ``ledger:crash-loop:`` (a failed
           crash-loop ledger append would hide an event from check (d));
       (d) every crash-loop event line from this run has ``delivered: true``.
     A genuine crash-loop alert at apply time, delivered, is a SUCCESSFUL
     deploy: Kent has been told. The first pass only records baselines, so none
     is expected.
  3. Joined-pass rule: the canary stamps its artifacts with the time its pass
     STARTED. If the timer had started a pass just before ``t0``, our start
     joins it and every artifact predates ``t0``. So if the only failures are
     freshness failures, start the unit once more and verify again. Still stale
     is a failure. The retry is bounded to one extra start.

Never wrap a command here in a remote shell to office2: this runs ON office2,
and loopback SSH fails.

Usage:
    scripts/deploy/deploy-crash-loop-unit-alerting.py --dry-run
    scripts/deploy/deploy-crash-loop-unit-alerting.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import pwd
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from scripts.canary import crash_loop_model, crash_loop_readers
from scripts.canary.crash_loop_model import (
    SCOPES,
    CrashLoopConfig,
    CrashLoopConfigError,
    ScopeReading,
)

_EXPECTED_USER = "claude"
_EXPECTED_HOME = Path("/home/claude")
SERVICE = "felix-canary.service"
START_TIMEOUT_S = 120
# Literal copies of the canary's paths, so --dry-run and --apply never import
# run.py's alert machinery; a test pins them to the canary modules' values.
STATE_PATH = Path("/data/services/felix-canary/state/crash-loop.json")
TICK_PATH = Path("/data/services/felix-canary/state/last-tick.json")
LEDGER_DIR = Path("/data/services/felix-canary/ledger")
# Literal copy of crash_loop_state.SCHEMA_VERSION; a test pins it.
STATE_SCHEMA_VERSION = 2
_EVENT_PREFIX = "crash-loop"
# Tick errors that void the proof. ``crash_loop`` covers stage faults, the
# held lock and ``crash_loop_state_save:``. A failed ledger append is recorded
# as ``ledger:<component_id>:...``; for a crash-loop scope or event line that
# means the ledger cannot be trusted to show every event (an undelivered alert
# whose line was never written would otherwise pass check (d)).
_TICK_ERROR_PREFIXES = ("crash_loop", "ledger:crash-loop:")

Runner = Callable[[list[str], float], "tuple[int, str, str]"]
ReadText = Callable[[Path], str]
ScopeReader = Callable[..., "tuple[list[ScopeReading], str | None]"]


# --------------------------------------------------------------------------- #
# Effects (defaults; every one is injectable).
# --------------------------------------------------------------------------- #
def _run(argv: list[str], timeout: float) -> tuple[int, str, str]:
    try:
        p = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout} s"
    except OSError as exc:
        return 127, "", f"{type(exc).__name__}: {exc}"
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def _now() -> datetime:
    return datetime.now(UTC)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _euid_name() -> str:
    return pwd.getpwuid(os.geteuid()).pw_name


def _load_config() -> CrashLoopConfig:
    return crash_loop_model.load_config(crash_loop_model.DEFAULT_CONFIG_PATH)


def _report(ok: bool, check: str, evidence: str) -> None:
    print(f"{'PASS' if ok else 'FAIL'} {check}: {evidence}", flush=True)


# --------------------------------------------------------------------------- #
# Pure verification (unit-tested).
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Check:
    """One verification result. ``stale`` marks a freshness-only failure."""

    name: str
    ok: bool
    evidence: str
    stale: bool = False


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def ledger_paths(t0: datetime, t1: datetime) -> list[Path]:
    """The ledger files a pass between *t0* and *t1* can have written to."""
    days = sorted({t.astimezone(UTC).date() for t in (t0, t1)})
    return [LEDGER_DIR / f"{d}.jsonl" for d in days]


def _read_json(read_text: ReadText, path: Path) -> tuple[object | None, str | None]:
    try:
        return json.loads(read_text(path)), None
    except FileNotFoundError:
        return None, "missing"
    except (OSError, ValueError) as exc:
        return None, f"unreadable: {type(exc).__name__}: {exc}"


def _check_state(read_text: ReadText, t0: datetime) -> Check:
    name = "state-fresh"
    doc, err = _read_json(read_text, STATE_PATH)
    if err == "missing":
        return Check(name, False, f"{STATE_PATH} missing", stale=True)
    if err or not isinstance(doc, dict):
        return Check(name, False, f"{STATE_PATH} {err or 'is not a JSON object'}")
    raw = doc.get("updated_at_utc")
    at = _parse_time(raw)
    if at is None:
        return Check(name, False, f"updated_at_utc={raw!r} is not a timestamp")
    if at < t0:
        return Check(name, False, f"updated_at_utc={raw} predates t0={t0.isoformat()}", stale=True)
    version = doc.get("schema_version")
    if isinstance(version, bool) or version != STATE_SCHEMA_VERSION:
        return Check(name, False, f"schema_version={version!r}, want {STATE_SCHEMA_VERSION}")
    return Check(name, True, f"updated_at_utc={raw} >= t0={t0.isoformat()} "
                             f"schema_version={version}")


def _fresh_ledger_lines(read_text: ReadText, paths: Sequence[Path], t0: datetime
                        ) -> tuple[list[dict], list[str]]:
    lines: list[dict] = []
    problems: list[str] = []
    for path in paths:
        try:
            text = read_text(path)
        except FileNotFoundError:
            continue
        except OSError as exc:
            problems.append(f"{path}: {type(exc).__name__}: {exc}")
            continue
        for raw in text.splitlines():
            if not raw.strip():
                continue
            try:
                rec = json.loads(raw)
            except ValueError:
                continue  # the canary writes whole lines; a torn line is not ours
            if not isinstance(rec, dict):
                continue
            at = _parse_time(rec.get("evaluated_at"))
            if at is not None and at >= t0:
                lines.append(rec)
    return lines, problems


def _check_scopes(lines: list[dict], read_problems: list[str]) -> list[Check]:
    checks: list[Check] = []
    for scope in SCOPES:
        name = f"scope-{scope}"
        if read_problems:
            checks.append(Check(name, False, "ledger unreadable: " + "; ".join(read_problems)))
            continue
        mine = [r for r in lines if r.get("component_id") == f"crash-loop:{scope}"]
        if not mine:
            checks.append(Check(name, False, f"no crash-loop:{scope} ledger line since t0",
                                stale=True))
            continue
        bad = [r for r in mine if r.get("outcome") != "healthy"]
        if bad:
            checks.append(Check(name, False, "; ".join(
                f"outcome={r.get('outcome')!r} evidence={r.get('evidence')!r}" for r in bad)))
        else:
            checks.append(Check(name, True, f"healthy x{len(mine)}: {mine[-1].get('evidence')}"))
    return checks


def _check_tick(read_text: ReadText, t0: datetime) -> list[Check]:
    doc, err = _read_json(read_text, TICK_PATH)
    if err or not isinstance(doc, dict):
        why = f"{TICK_PATH} {err or 'is not a JSON object'}"
        return [Check("tick-fresh", False, why), Check("tick-errors", False, why)]
    raw = doc.get("completed_at_utc")
    at = _parse_time(raw)
    if at is None:
        why = f"completed_at_utc={raw!r} is not a timestamp"
        return [Check("tick-fresh", False, why), Check("tick-errors", False, why)]
    if at < t0:
        why = f"completed_at_utc={raw} predates t0={t0.isoformat()}"
        return [Check("tick-fresh", False, why, stale=True),
                Check("tick-errors", False, "not evaluated: tick predates t0", stale=True)]
    fresh = Check("tick-fresh", True, f"completed_at_utc={raw} >= t0={t0.isoformat()}")
    errors = doc.get("errors")
    if not isinstance(errors, list):
        return [fresh, Check("tick-errors", False, f"errors={errors!r} is not a list")]
    hits = [e for e in errors if isinstance(e, str) and e.startswith(_TICK_ERROR_PREFIXES)]
    if hits:
        return [fresh, Check("tick-errors", False, f"crash-loop errors: {hits}")]
    return [fresh, Check("tick-errors", True,
                         f"no crash_loop or ledger:crash-loop entry in {len(errors)} errors")]


def _check_events(lines: list[dict]) -> Check:
    events = [r for r in lines
              if str(r.get("component_id", "")).startswith(f"{_EVENT_PREFIX}:")
              and str(r.get("outcome", "")).startswith(_EVENT_PREFIX)]
    undelivered = [r for r in events if r.get("delivered") is not True]
    if undelivered:
        return Check("events-delivered", False, "undelivered: " + "; ".join(
            f"{r.get('component_id')} {r.get('outcome')} delivered={r.get('delivered')!r}"
            for r in undelivered))
    return Check("events-delivered", True, f"{len(events)} event(s) since t0, all delivered")


def verify(read_text: ReadText, t0: datetime, t1: datetime) -> list[Check]:
    """Every R-11 check against the artifacts of a pass that started at or after *t0*."""
    lines, problems = _fresh_ledger_lines(read_text, ledger_paths(t0, t1), t0)
    return [_check_state(read_text, t0), *_check_scopes(lines, problems),
            *_check_tick(read_text, t0), _check_events(lines)]


# --------------------------------------------------------------------------- #
# Modes.
# --------------------------------------------------------------------------- #
def preflight(*, user_name: Callable[[], str] = _euid_name,
              home: Callable[[], Path] = Path.home,
              load_config: Callable[[], CrashLoopConfig] = _load_config) -> bool:
    actual_user, actual_home = user_name(), home()
    user_ok = actual_user == _EXPECTED_USER and actual_home == _EXPECTED_HOME
    _report(user_ok, "preflight-user",
            f"euid={actual_user} home={actual_home} (want {_EXPECTED_USER} {_EXPECTED_HOME})")
    if not user_ok:
        return False
    try:
        config = load_config()
    except CrashLoopConfigError as exc:
        _report(False, "preflight-config", str(exc))
        return False
    _report(True, "preflight-config",
            f"threshold={config.threshold} "
            f"consecutive_rise_ticks={config.consecutive_rise_ticks} "
            f"quiet_ticks_to_clear={config.quiet_ticks_to_clear} "
            f"reremind_ticks={config.reremind_ticks} "
            f"read_budget_seconds={config.read_budget_seconds} ignore={len(config.ignore)}")
    return True


def dry_run(*, read_scopes: ScopeReader = crash_loop_readers.read_all_scopes,
            preflight: Callable[[], bool] = preflight,
            load_config: Callable[[], CrashLoopConfig] = _load_config) -> int:
    """Read all three scopes once, read-only, and report. Writes nothing."""
    if not preflight():
        return 1
    config = load_config()
    readings, boot_id = read_scopes(budget_seconds=config.read_budget_seconds)
    ok = True
    for r in readings:
        ignored = sum(1 for o in r.observations if o.key in config.ignore)
        evidence = (f"complete={r.complete} watched={len(r.observations)} ignored={ignored} "
                    f"excluded={r.excluded} elapsed_ms={r.elapsed_ms}")
        if not r.complete:
            evidence += f" error={r.error}"
            ok = False
        _report(r.complete, f"scope-{r.scope}", evidence)
    total = sum(r.elapsed_ms for r in readings)
    print(f"boot_id={boot_id} total_elapsed_ms={total} "
          f"budget_ms={config.read_budget_seconds * 1000}", flush=True)
    print(f"would run: systemctl --user start {SERVICE}", flush=True)
    print("dry run complete" if ok else "dry run FAILED", flush=True)
    return 0 if ok else 1


def _start(run: Runner) -> bool:
    rc, _out, err = run(["systemctl", "--user", "start", SERVICE], START_TIMEOUT_S)
    _report(rc == 0, "start", f"systemctl --user start {SERVICE} rc={rc}"
            + (f" stderr={err}" if err else ""))
    return rc == 0


def apply(*, run: Runner = _run, now: Callable[[], datetime] = _now,
          read_text: ReadText = _read_text,
          preflight: Callable[[], bool] = preflight) -> int:
    if not preflight():
        return 1
    t0 = now()
    print(f"t0={t0.isoformat()}", flush=True)
    for attempt in (1, 2):
        if not _start(run):
            return 1
        checks = verify(read_text, t0, now())
        for c in checks:
            _report(c.ok, c.name, c.evidence + (" [stale]" if c.stale else ""))
        failed = [c for c in checks if not c.ok]
        if not failed:
            print(f"apply complete (attempt {attempt})", flush=True)
            return 0
        if attempt == 1 and all(c.stale for c in failed):
            print("artifacts predate t0: the start joined a pass already running; "
                  "starting once more", flush=True)
            continue
        break
    print("apply FAILED", flush=True)
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    return dry_run() if args.dry_run else apply()


if __name__ == "__main__":
    sys.exit(main())
