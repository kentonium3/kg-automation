#!/usr/bin/env python3
"""Deploy entrypoint: prove felix-health-check's coverage checks live, then
retire the untracked host copy of health-check.sh (#1063).

Tier 3 (user-level scripts under the ``claude`` account; no unit content
changes; no Tier 0/1/2 action).

WHY. From 2026-09-27 to 2026-10-14 every nightly backup failed and nothing
alerted: felix-canary was dark (#1062) and felix-health-check reported
ALL_HEALTHY 34 times because its shell script, an untracked copy in
``~/helper-scripts/``, checked neither backups nor the canary. The code
change (coverage checks, the script moved into the repo) reaches office2 when
felix-deployer advances the checkout, because the unit runs from it. This
entrypoint does what a checkout pull cannot:

  0. Preflight: euid's passwd name is ``claude`` and ``Path.home()`` is
     ``/home/claude``. The repo copy of health-check.sh exists and is
     executable.
  1. Run the health check once for real (``systemctl --user start``; the
     oneshot blocks until it finishes).
  2. Prove from the FRESH run record that the new coverage is live and
     complete. Every check is individual (Codex post-plan finding 2), never
     just the combined status:
       - ``ran_at_utc`` is from this invocation;
       - ``script_path`` is the repo copy;
       - ``script_status`` is a recognised shell verdict;
       - ``exit_code`` is an int (the shell ran);
       - both coverage checks are present and neither is unknown;
       - if the run alerted, the alert was delivered.
     A genuine fault (``FAILURES_DETECTED`` with the alert delivered) is a
     SUCCESSFUL deploy, because Kent has been told.
  3. Only then move ``~/helper-scripts/health-check.sh`` to a dated file under
     the health check's state directory. A move, not a delete: reversible, and
     the 2026-04-07 original is kept. Re-applying after retirement is a no-op.

⚠ Never wrap a command here in ``ssh office2-claude '...'``: this runs ON
office2, and loopback SSH fails.

Usage:
    scripts/deploy/deploy-health-check-coverage.py --dry-run
    scripts/deploy/deploy-health-check-coverage.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import pwd
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

REPO_SCRIPT = _REPO_ROOT / "scripts/office2/felix_health_check/health-check.sh"
_EXPECTED_USER = "claude"
_EXPECTED_HOME = Path("/home/claude")
LEGACY_SCRIPT = _EXPECTED_HOME / "helper-scripts" / "health-check.sh"
STATE_DIR = Path("/data/services/openclaw/felix-health-check")
RUN_RECORD = STATE_DIR / "last-run.json"
RETIRED_DIR = STATE_DIR / "retired"
SERVICE = "felix-health-check.service"
COVERAGE_COMPONENTS = ("felix-canary", "restic-backup")
_RECOGNISED_SHELL = {"ALL_HEALTHY", "FAILURES_DETECTED"}
_ACCEPTABLE_STATUS = {"ALL_HEALTHY", "FAILURES_DETECTED"}
# The record stamps ran_at_utc at whole-second precision when the run starts.
_CLOCK_SLACK = timedelta(seconds=5)

Runner = Callable[[list[str]], "tuple[int, str, str]"]


def _emit(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True, default=str), flush=True)


def _run(argv: list[str]) -> tuple[int, str, str]:
    p = subprocess.run(argv, capture_output=True, text=True, check=False)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- pure checks (unit-tested) ----------------------------------------------

def record_problems(record: object, started: datetime, repo_script: Path = REPO_SCRIPT) -> list[str]:
    """Every reason the run record does not prove complete, live coverage."""
    if not isinstance(record, dict):
        return [f"run record is not a JSON object ({type(record).__name__})"]
    problems: list[str] = []
    ran = record.get("ran_at_utc")
    try:
        ran_at = datetime.fromisoformat(str(ran).replace("Z", "+00:00"))
        if ran_at.tzinfo is None:
            ran_at = ran_at.replace(tzinfo=timezone.utc)
        if ran_at < started - _CLOCK_SLACK:
            problems.append(f"ran_at_utc={ran!r} predates this apply ({started.isoformat()}): stale record")
    except ValueError:
        problems.append(f"ran_at_utc={ran!r} is not a timestamp")
    if record.get("script_path") != str(repo_script):
        problems.append(f"script_path={record.get('script_path')!r}, want {str(repo_script)!r}")
    if record.get("script_status") not in _RECOGNISED_SHELL:
        problems.append(f"script_status={record.get('script_status')!r}: shell checks did not complete")
    exit_code = record.get("exit_code")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        problems.append(f"exit_code={exit_code!r}: the shell script did not run")
    checks = record.get("coverage_checks")
    if not isinstance(checks, list):
        problems.append("coverage_checks missing")
    else:
        components = [c.get("component") if isinstance(c, dict) else None for c in checks]
        if components != list(COVERAGE_COMPONENTS):
            problems.append(f"coverage_checks components={components}, want {list(COVERAGE_COMPONENTS)}")
        for c in checks:
            if isinstance(c, dict) and c.get("finding") not in {"ok", "failure"}:
                problems.append(f"coverage {c.get('component')}: {c.get('finding')} ({c.get('outcome')}): "
                                f"{c.get('evidence')}")
    status = record.get("status")
    if status not in _ACCEPTABLE_STATUS:
        problems.append(f"status={status!r}")
    delivery = record.get("delivery")
    if not isinstance(delivery, dict):
        problems.append(f"delivery={delivery!r} is not an object")
    elif status != "ALL_HEALTHY" and delivery.get("sent") is not True:
        problems.append(f"status {status!r} needed an alert but delivery={delivery!r}")
    return problems


def retired_path(now: datetime) -> Path:
    return RETIRED_DIR / f"health-check.sh.{now.strftime('%Y%m%dT%H%M%SZ')}"


# --- steps -------------------------------------------------------------------

def _preflight(check_user: bool) -> bool:
    ok = True
    if check_user:
        actual = pwd.getpwuid(os.geteuid()).pw_name
        if actual != _EXPECTED_USER or Path.home() != _EXPECTED_HOME:
            _emit("preflight_failed", reason="must run as claude with HOME=/home/claude",
                  euid_user=actual, home=str(Path.home()))
            return False
    if not REPO_SCRIPT.is_file() or not os.access(REPO_SCRIPT, os.X_OK):
        _emit("preflight_failed", reason="repo health-check.sh missing or not executable",
              path=str(REPO_SCRIPT))
        ok = False
    if ok:
        _emit("preflight_ok", repo_script=str(REPO_SCRIPT))
    return ok


def _dry_run() -> int:
    ok = _preflight(check_user=False)
    try:
        from scripts.office2.felix_health_check import coverage

        findings = coverage.evaluate_coverage(_now())
        _emit("coverage_checks", checks=[f.to_record() for f in findings])
        blind = [f.component for f in findings if f.finding == "unknown"]
        if blind:
            # On office2 every pointer and declaration must be readable; an
            # unknown here means the apply's verification would fail too.
            _emit("coverage_unknown", components=blind)
            ok = False
    except Exception as exc:  # noqa: BLE001 - a dry run reports, never crashes
        _emit("coverage_checks_failed", error=f"{type(exc).__name__}: {exc}")
        ok = False
    _emit("would_run", argv=["systemctl", "--user", "start", SERVICE])
    if LEGACY_SCRIPT.exists():
        _emit("would_retire", src=str(LEGACY_SCRIPT), dst=str(retired_path(_now())))
    else:
        _emit("already_retired", path=str(LEGACY_SCRIPT))
    _emit("dry_run_complete" if ok else "dry_run_failed")
    return 0 if ok else 1


def _apply(run: Runner = _run, now: Callable[[], datetime] = _now,
           read_text: Callable[[Path], str] = lambda p: p.read_text(encoding="utf-8"),
           move: Callable[[str, str], object] = shutil.move,
           exists: Callable[[Path], bool] = lambda p: p.exists(),
           mkdir: Callable[[Path], None] = lambda p: p.mkdir(parents=True, exist_ok=True),
           check_user: bool = True) -> int:
    if not _preflight(check_user):
        return 1

    started = now()
    rc, _out, err = run(["systemctl", "--user", "start", SERVICE])
    if rc != 0:
        _emit("apply_failed", step="start", rc=rc, stderr=err)
        return 1

    try:
        record = json.loads(read_text(RUN_RECORD))
    except (OSError, ValueError) as exc:
        _emit("apply_failed", step="read_record", error=f"{type(exc).__name__}: {exc}")
        return 1
    problems = record_problems(record, started)
    if problems:
        _emit("apply_failed", step="verify", problems=problems)
        return 1
    _emit("verified", status=record["status"], script_status=record["script_status"],
          coverage={c["component"]: c["finding"] for c in record["coverage_checks"]},
          delivery_sent=record["delivery"].get("sent"))

    if exists(LEGACY_SCRIPT):
        dst = retired_path(now())
        if exists(dst):
            _emit("apply_failed", step="retire", error=f"{dst} already exists; refusing to overwrite")
            return 1
        try:
            mkdir(RETIRED_DIR)
            move(str(LEGACY_SCRIPT), str(dst))
        except OSError as exc:
            _emit("apply_failed", step="retire", error=f"{type(exc).__name__}: {exc}")
            return 1
        _emit("retired", src=str(LEGACY_SCRIPT), dst=str(dst))
    else:
        _emit("already_retired", path=str(LEGACY_SCRIPT))

    _emit("apply_complete", status=record["status"],
          duration_s=round((now() - started).total_seconds(), 1))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    return _dry_run() if args.dry_run else _apply()


if __name__ == "__main__":
    sys.exit(main())
