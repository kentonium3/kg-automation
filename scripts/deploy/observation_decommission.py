"""Phase-2 (destructive) observation stray-tree decommission logic.

Mission: observation-digest-repoint-01KWS2E2 (fast-follow of #656 → #659)

This module holds ALL logic for the **irreversible** removal of the stray
second-brain clone at ``/home/claude/second-brain`` (WP03 / FR-003..FR-005).
The hyphenated executable ``decommission-observation-stray-tree.py`` is a thin
``sys.path``-shim wrapper that calls :func:`main` here (hyphenated filenames are
not importable, so the logic lives in this underscore module and is unit-tested
via ``import``).

Why this is dangerous
---------------------
``/home/claude/second-brain`` is a git clone containing a March vault snapshot,
old digest/state, live observation logs, and a ``_private`` growth directory.
Kent authorized full deletion (``DM-01KWS4F986PVHTJRSHZPQACDM7``) for this tree
*only*.  The delete is a **single root-level** ``shutil.rmtree(source_root)`` —
descendants are NEVER enumerated, walked, copied, or logged (C-008).  No
``rglob`` / ``os.walk`` / ``iterdir`` / ``git status --ignored`` anywhere; no
per-file ``onerror`` callback that could echo a child path; and the ``_private``
subtree is never read or referenced.

Hard precondition gate (FR-004) — ALL must pass or the caller aborts non-zero
WITHOUT any destructive action:

  (a) SNAPSHOT + COVERAGE — a fresh Restic snapshot (``verify_restic_recent``)
      AND proof ``source_root`` is in the backup set.  Recency alone is
      insufficient; coverage is proven by a ``restic snapshots`` include-path
      check OR the explicit ``--attest-backup-coverage`` operator override.
  (b) ORIGIN recoverability — ``git -C <root> branch -r --contains HEAD`` shows
      the clone's HEAD is present on an ``origin/*`` branch.  We never push.
  (c) QUIESCE + no live writer — stop ``felix-core-digest.timer`` (user unit),
      then confirm no ``summarize.py`` / ``log_action.py`` process is running
      (bounded ``pgrep`` wait).  An active writer aborts.
  (d) INBOX-PRESCAN mtime — no top-level
      ``agents/logs/inbox-prescan-*.md`` newer than the #656 cutover
      (:data:`INBOX_PRESCAN_CUTOFF`).

``check_preconditions`` references ONLY ``source_root`` and the specific
``source_root/agents/logs/inbox-prescan-*.md`` glob — it never walks the tree.

Output discipline
------------------
stdout carries exactly one JSON object (the plan in dry-run; the result on
apply).  All progress / errors go to stderr via :func:`_emit`.  No descendant
path ever appears in stdout or stderr — only ``source_root`` itself.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

# Reuse the Phase-1 helpers (union-merge / migrate flow) and shared defaults.
from scripts.deploy.observation_migration import (
    DEFAULT_SOURCE_ROOT,
    DEFAULT_VAULT_LOGS_DIR,
    _emit,
    migrate_logs,
)
from scripts.deploy.lib.snapshot import verify_restic_recent

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
#: The #656 ``0007`` migration manifest was applied 2026-07-04 and repointed the
#: inbox-prescan output to ``/home/kgale``. Any top-level ``inbox-prescan-*.md``
#: in the stray tree newer than this cutover means a writer targeted the stray
#: tree after cutover — abort and require operator disposition (FR-004e).
INBOX_PRESCAN_CUTOFF = date(2026, 7, 4)

#: The user-scoped systemd timer that drives the digest/observation writers.
DIGEST_TIMER = "felix-core-digest.timer"

#: Writer processes that must not be running before we delete (FR-004c).
WRITER_PROCESS_PATTERNS = ("summarize.py", "log_action.py")

#: Bounded quiesce wait: poll pgrep for up to this long for writers to exit.
DEFAULT_QUIESCE_WAIT_S = 30.0
DEFAULT_POLL_INTERVAL_S = 2.0

_PRESCAN_GLOB = "inbox-prescan-*.md"


# ---------------------------------------------------------------------------
# Low-level command wrappers (single choke points so tests can monkeypatch)
# ---------------------------------------------------------------------------

def _run_cmd(cmd: list[str], timeout: float | None = 30.0) -> subprocess.CompletedProcess:
    """Run *cmd* capturing text output. Never raises — a timeout or OS error is
    mapped to a synthetic non-zero result (returncode 124) so callers treat
    "could not run" fail-safe. Critical: an exception escaping here after the
    digest timer is stopped would skip the timer-restart in decommission()'s
    finally (post-merge Codex finding)."""
    try:
        return subprocess.run(  # noqa: S603 - fixed argv, no shell
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return subprocess.CompletedProcess(cmd, 124, stdout="", stderr=str(exc))


def stop_digest_timer() -> subprocess.CompletedProcess:
    """``systemctl --user stop felix-core-digest.timer``."""
    return _run_cmd(["systemctl", "--user", "stop", DIGEST_TIMER])


def start_digest_timer() -> subprocess.CompletedProcess:
    """``systemctl --user start felix-core-digest.timer``."""
    return _run_cmd(["systemctl", "--user", "start", DIGEST_TIMER])


def _writer_active() -> bool:
    """True if any known observation writer process is running, OR if the check
    could not be completed. pgrep exit codes: 0=match, 1=no match, >=2=error.
    An error/timeout (incl. the synthetic 124 from _run_cmd) is treated fail-safe
    as "active" so an unconfirmable quiesce aborts before any deletion rather
    than proceeding on a false "no writer"."""
    for pattern in WRITER_PROCESS_PATTERNS:
        proc = _run_cmd(["pgrep", "-f", pattern], timeout=10.0)
        if proc.returncode == 0 and proc.stdout.strip():
            return True
        if proc.returncode not in (0, 1):
            return True
    return False


# ---------------------------------------------------------------------------
# Gate (a): fresh snapshot + coverage proof
# ---------------------------------------------------------------------------

def _verify_backup_coverage(source_root: Path) -> tuple[bool, dict[str, Any]]:
    """Prove ``source_root`` is inside the Restic backup set.

    Queries ``restic snapshots --json`` and checks whether any snapshot's
    ``paths`` covers ``source_root``.  The ``claude`` user frequently cannot
    query Restic directly, so callers that know coverage holds pass
    ``--attest-backup-coverage`` instead; this check is the automatable path
    and fails closed (no coverage proven → gate fails) when Restic is
    unavailable.
    """
    source_root = Path(source_root)
    try:
        proc = _run_cmd(["restic", "snapshots", "--json"], timeout=60.0)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, {"coverage": "restic_unavailable", "error": type(exc).__name__}

    if proc.returncode != 0:
        return False, {"coverage": "restic_query_failed", "returncode": proc.returncode}

    try:
        snapshots = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return False, {"coverage": "restic_output_unparseable"}

    target = str(source_root)
    for snap in snapshots:
        for path in snap.get("paths", []) or []:
            # Covered if a backed-up path is source_root or an ancestor of it.
            if target == path or target.startswith(path.rstrip("/") + "/"):
                return True, {"coverage": "restic_snapshot_paths"}
    return False, {"coverage": "source_root_not_in_backup_set"}


def check_snapshot_coverage(
    source_root: Path,
    attest_backup_coverage: bool = False,
    snapshot_log_dir: Path | None = None,
) -> tuple[bool, dict[str, Any]]:
    """Gate (a): recency AND coverage (or an explicit attestation)."""
    detail: dict[str, Any] = {"gate": "snapshot_coverage"}

    kwargs: dict[str, Any] = {}
    if snapshot_log_dir is not None:
        kwargs["log_dir"] = snapshot_log_dir
    recent = verify_restic_recent(**kwargs)
    detail["recent_ok"] = bool(recent.ok)
    detail["recent_summary"] = recent.summary
    if not recent.ok:
        detail["reason"] = "no_recent_snapshot"
        return False, detail

    if attest_backup_coverage:
        detail["coverage"] = "operator_attested"
        return True, detail

    covered, cov_detail = _verify_backup_coverage(source_root)
    detail.update(cov_detail)
    if not covered:
        detail["reason"] = "backup_coverage_unproven"
        return False, detail
    return True, detail


# ---------------------------------------------------------------------------
# Gate (b): origin recoverability
# ---------------------------------------------------------------------------

def check_origin_recoverable(source_root: Path) -> tuple[bool, dict[str, Any]]:
    """Gate (b): the clone's HEAD is present on an ``origin/*`` branch.

    Read-only: ``git branch -r --contains HEAD``. We never push.
    """
    detail: dict[str, Any] = {"gate": "origin"}
    proc = _run_cmd(
        ["git", "-C", str(source_root), "branch", "-r", "--contains", "HEAD"]
    )
    if proc.returncode != 0:
        detail["reason"] = "git_query_failed"
        detail["returncode"] = proc.returncode
        return False, detail

    origin_refs = [
        line.strip()
        for line in proc.stdout.splitlines()
        if line.strip().startswith("origin/")
    ]
    detail["origin_ref_count"] = len(origin_refs)
    if not origin_refs:
        detail["reason"] = "head_not_on_origin"
        return False, detail
    return True, detail


# ---------------------------------------------------------------------------
# Gate (c): quiesce the timer + confirm no live writer
# ---------------------------------------------------------------------------

def check_quiesce(
    *,
    stop_timer: bool = True,
    wait_s: float = DEFAULT_QUIESCE_WAIT_S,
    poll_interval: float = DEFAULT_POLL_INTERVAL_S,
) -> tuple[bool, dict[str, Any]]:
    """Gate (c): stop the digest timer, then wait for writers to quiesce.

    When ``stop_timer`` is False (dry-run) the timer is NOT touched — the gate
    only reports what it *would* do and still performs the read-only writer
    check.  ``timer_stopped`` records whether a stop was actually issued so the
    caller can guarantee a restart in its ``finally``.
    """
    detail: dict[str, Any] = {"gate": "quiesce", "timer_stopped": False}

    if stop_timer:
        proc = stop_digest_timer()
        if proc.returncode != 0:
            detail["reason"] = "timer_stop_failed"
            detail["returncode"] = proc.returncode
            return False, detail
        detail["timer_stopped"] = True
    else:
        detail["plan_only"] = True

    deadline = time.monotonic() + max(wait_s, 0.0)
    while True:
        if not _writer_active():
            detail["writer_active"] = False
            return True, detail
        if time.monotonic() >= deadline:
            detail["writer_active"] = True
            detail["reason"] = "writer_still_active"
            return False, detail
        time.sleep(poll_interval)


# ---------------------------------------------------------------------------
# Gate (d): inbox-prescan mtime cutover
# ---------------------------------------------------------------------------

def check_inbox_prescan_mtime(source_root: Path) -> tuple[bool, dict[str, Any]]:
    """Gate (d): no top-level ``agents/logs/inbox-prescan-*.md`` past cutover.

    References ONLY ``source_root/agents/logs/inbox-prescan-*.md`` — a single
    non-recursive glob.  Never walks the tree; never touches ``_private``.
    """
    detail: dict[str, Any] = {"gate": "inbox_prescan", "cutoff": INBOX_PRESCAN_CUTOFF.isoformat()}
    logs_dir = Path(source_root) / "agents" / "logs"

    newer_count = 0
    # Path.glob on a missing dir yields nothing (no error). Non-recursive.
    for prescan in logs_dir.glob(_PRESCAN_GLOB):
        try:
            mtime_date = datetime.fromtimestamp(prescan.stat().st_mtime).date()
        except OSError:
            # Cannot stat — treat as suspicious and abort (fail closed).
            detail["reason"] = "prescan_stat_failed"
            return False, detail
        if mtime_date > INBOX_PRESCAN_CUTOFF:
            newer_count += 1

    detail["files_newer_than_cutoff"] = newer_count
    if newer_count:
        detail["reason"] = "prescan_written_after_cutover"
        return False, detail
    return True, detail


# ---------------------------------------------------------------------------
# Precondition gate — ALL must pass (FR-004)
# ---------------------------------------------------------------------------

def check_preconditions(
    source_root: Path,
    vault_logs_dir: Path,
    attest_backup_coverage: bool = False,
    *,
    stop_timer: bool = True,
    wait_s: float = DEFAULT_QUIESCE_WAIT_S,
    poll_interval: float = DEFAULT_POLL_INTERVAL_S,
    snapshot_log_dir: Path | None = None,
) -> dict[str, Any]:
    """Evaluate ALL destructive-safety gates; return a structured result.

    The read-only gates (a snapshot+coverage, b origin, d inbox-prescan) run
    first.  The quiesce gate (c) — the only one with a side effect — runs LAST,
    and only after the read-only gates pass, so the timer is never stopped for a
    request that was going to abort anyway.  ``ok`` is the AND of every gate.

    The returned dict is JSON-serializable and names ONLY ``source_root``; no
    descendant path is ever included.
    """
    source_root = Path(source_root)
    gates: dict[str, Any] = {}

    ok_a, gates["snapshot_coverage"] = check_snapshot_coverage(
        source_root, attest_backup_coverage, snapshot_log_dir
    )
    ok_b, gates["origin"] = check_origin_recoverable(source_root)
    ok_d, gates["inbox_prescan"] = check_inbox_prescan_mtime(source_root)

    # Only quiesce (a mutation) once the read-only gates are green. If any
    # read-only gate failed, report quiesce as skipped and never stop the timer.
    if ok_a and ok_b and ok_d:
        ok_c, gates["quiesce"] = check_quiesce(
            stop_timer=stop_timer, wait_s=wait_s, poll_interval=poll_interval
        )
    else:
        ok_c = False
        gates["quiesce"] = {
            "gate": "quiesce",
            "timer_stopped": False,
            "skipped": True,
            "reason": "read_only_gate_failed",
        }

    all_ok = bool(ok_a and ok_b and ok_c and ok_d)
    for label, ok in (
        ("snapshot_coverage", ok_a),
        ("origin", ok_b),
        ("inbox_prescan", ok_d),
        ("quiesce", ok_c),
    ):
        if not ok:
            _emit("GATE-FAIL", f"{label}: {gates[label].get('reason', 'failed')}")
    return {"ok": all_ok, "gates": gates}


# ---------------------------------------------------------------------------
# Decommission flow — dry-run plan OR gated destructive apply (FR-003/FR-005)
# ---------------------------------------------------------------------------

def decommission(
    source_root: Path,
    vault_logs_dir: Path,
    dry_run: bool,
    attest_backup_coverage: bool = False,
    *,
    wait_s: float = DEFAULT_QUIESCE_WAIT_S,
    poll_interval: float = DEFAULT_POLL_INTERVAL_S,
    snapshot_log_dir: Path | None = None,
) -> dict[str, Any]:
    """Plan (dry-run) or execute the gated destructive decommission.

    Dry-run: evaluate preconditions read-only (the timer is NOT stopped),
    collect the final-merge plan, mutate nothing, and report.  Apply: run the
    gate; if ANY gate fails, return failure WITHOUT deleting; else do the final
    ``migrate_logs`` under quiesce, a single root-level ``shutil.rmtree`` of
    ``source_root``, restart the timer, and assert the root is gone.  The timer
    restart is always attempted in a ``finally`` if it was stopped.
    """
    source_root = Path(source_root)
    vault_logs_dir = Path(vault_logs_dir)

    result: dict[str, Any] = {
        "source_root": str(source_root),
        "vault_logs_dir": str(vault_logs_dir),
        "dry_run": bool(dry_run),
        "deleted": False,
        "ok": False,
    }

    # ── Dry-run: read-only preconditions + migrate plan; mutate nothing. ──
    if dry_run:
        pre = check_preconditions(
            source_root,
            vault_logs_dir,
            attest_backup_coverage,
            stop_timer=False,  # NEVER stop the timer in a dry-run
            wait_s=wait_s,
            poll_interval=poll_interval,
            snapshot_log_dir=snapshot_log_dir,
        )
        migrate_plan = migrate_logs(source_root, vault_logs_dir, dry_run=True)
        result["plan_only"] = True
        result["preconditions"] = pre
        result["migrate"] = migrate_plan
        result["ok"] = bool(pre["ok"])
        _emit("INFO", "DRY-RUN: no deletion performed; timer untouched.")
        return result

    # ── Apply: hard gate → final merge → root-only delete → restart. ──
    timer_stopped = False
    result["plan_only"] = False
    try:
        pre = check_preconditions(
            source_root,
            vault_logs_dir,
            attest_backup_coverage,
            stop_timer=True,
            wait_s=wait_s,
            poll_interval=poll_interval,
            snapshot_log_dir=snapshot_log_dir,
        )
        timer_stopped = bool(pre["gates"]["quiesce"].get("timer_stopped", False))
        result["preconditions"] = pre

        if not pre["ok"]:
            _emit("ABORT", "Precondition gate failed — no deletion performed.")
            return result

        # Final straggler merge under quiesce (reuse WP02).
        result["migrate"] = migrate_logs(source_root, vault_logs_dir, dry_run=False)

        # SINGLE root-level delete. No onerror callback (a callback could echo a
        # child path); no tree walk. Names ONLY source_root.
        _emit("INFO", f"Removing decommissioned tree: {source_root}")
        shutil.rmtree(source_root)

        # Post-check: the root must be gone.
        if source_root.exists():
            _emit("ERROR", f"Post-delete check failed: {source_root} still present.")
            return result

        _emit("DONE", f"Decommission complete: {source_root} removed.")
        result["deleted"] = True
        result["ok"] = True
        return result
    finally:
        if timer_stopped:
            proc = start_digest_timer()
            if proc.returncode != 0:
                _emit("WARN", f"Timer restart returned non-zero: {DIGEST_TIMER}")
            else:
                _emit("INFO", f"Timer restarted: {DIGEST_TIMER}")


# ---------------------------------------------------------------------------
# Entry point (argparse lives here so the hyphenated wrapper stays thin)
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="decommission-observation-stray-tree",
        description="Phase-2 (destructive) decommission of the observation stray tree.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true", help="Print plan; no mutation (default).")
    parser.add_argument("--apply", action="store_true", help="Execute the gated destructive decommission.")
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--vault-logs-dir", type=Path, default=DEFAULT_VAULT_LOGS_DIR)
    parser.add_argument(
        "--attest-backup-coverage",
        action="store_true",
        help="Operator attestation that source_root is in the Restic backup set (gate a override).",
    )
    parser.add_argument(
        "--snapshot-log-dir",
        type=Path,
        default=None,
        help="Override the Restic backup log dir (for testing).",
    )

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    # --dry-run is the default; --apply flips it.
    dry_run: bool = not args.apply
    source_root: Path = args.source_root
    vault_logs_dir: Path = args.vault_logs_dir

    _emit("INFO", f"Observation decommission start  dry_run={dry_run}")
    _emit("INFO", f"  source_root    = {source_root}")
    _emit("INFO", f"  vault_logs_dir = {vault_logs_dir}")

    try:
        result = decommission(
            source_root,
            vault_logs_dir,
            dry_run=dry_run,
            attest_backup_coverage=args.attest_backup_coverage,
            snapshot_log_dir=args.snapshot_log_dir,
        )
    except (RuntimeError, OSError) as exc:
        _emit("ERROR", str(exc))
        _emit("ABORT", "Decommission aborted — see ERROR above.")
        return 1

    # Exactly one JSON object to stdout.
    sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
    sys.stdout.flush()

    if result.get("ok"):
        return 0
    # Dry-run whose preconditions are not (yet) satisfied is still a successful
    # *plan* run (mutated nothing, exit 0) — only an apply failure is non-zero.
    if dry_run:
        return 0
    return 1


if __name__ == "__main__":  # pragma: no cover — use python3 -m or the wrapper
    sys.exit(main())
