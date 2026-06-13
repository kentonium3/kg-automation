"""felix-deployer tick lifecycle.

One ``run_tick()`` call constitutes one applier tick. The systemd
``Type=oneshot`` service triggers this every 5 minutes via the
companion ``felix-deployer.timer`` unit.

Tick sequence (see ``data-model.md`` "Manifest lifecycle" + WP04 prompt):

1. ``git pull --ff-only`` from the canonical checkout. On non-zero exit,
   emit a ``tick_skip`` log entry and return 0 — the next tick retries.
2. Scan ``deploys/queued/*.yaml`` (alphabetical order).
3. For each manifest:

   a. Load + parse the YAML. On parse failure: write a failure record
      with ``phase="manifest_parse"`` and continue to the next manifest.
   b. Invoke :func:`scripts.deploy.lib.apply.dry_run_then_apply_gate`.
   c. On success: write the applied entry via
      :func:`scripts.deploy.lib.applied.write_applied`, ``git mv`` the
      queued path into ``deploys/applied/``, ``git commit + push``.
   d. On failure: write ``deploys/failed/<name>-<ts>.yaml`` and dispatch
      an ntfy.sh push notification via the sibling ``notify`` module.
      The manifest stays in ``deploys/queued/``.

The function ALWAYS returns 0 unless it crashes outright. Routine
failures (manifest parse, entrypoint exit non-zero, notification
dispatch errors) are observability events, not tick failures.

Tick log lines are appended to
``/data/services/felix-deployer/logs/<YYYY-MM-DD>.jsonl`` — one JSON
object per line, parseable independently. The log directory is
created on the first tick of each day.

Path discipline: this module is imported by the script-form
``deployer.py``. That entry point inserts the repo root onto
``sys.path`` (so ``scripts.deploy.lib`` resolves) and the felix-deployer
directory itself (so the sibling ``notify`` module resolves with a
plain ``import notify``). Tests reuse the same bootstrap helper.
"""

from __future__ import annotations

import datetime as _dt
import json
import pathlib
import subprocess
from typing import Any

from scripts.deploy.lib import apply as _apply
from scripts.deploy.lib import applied as _applied
from scripts.deploy.lib import manifest as _manifest

import notify as _notify  # type: ignore[import-not-found]

DEFAULT_REPO_ROOT = pathlib.Path("/home/claude/kg-automation")
DEFAULT_LOG_DIR = pathlib.Path("/data/services/felix-deployer/logs")

# Phase mapping from lib.apply's 7-value internal enum to the 4-value
# ntfy-notification-v1 enum. Drift here would silently break the operator's
# push-notification triage — keep these in lockstep with
# contracts/ntfy-notification-v1.md (felix-deployer-ntfy-failure-notifications
# mission).
PHASE_TO_NOTIFY_PHASE = {
    _apply.PHASE_TIER_GUARD: "tier_guard",
    _apply.PHASE_SNAPSHOT: "verification_pre",
    _apply.PHASE_VERIFICATION_PRE: "verification_pre",
    _apply.PHASE_ENTRYPOINT_DRY_RUN: "entrypoint",
    _apply.PHASE_ENTRYPOINT_APPLY: "entrypoint",
    _apply.PHASE_VERIFICATION_POST: "verification_post",
}


def _utc_now_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(log_path: pathlib.Path, entry: dict[str, Any]) -> None:
    """Append a single JSON line to *log_path*.

    Log writes are best-effort: if the directory or file is unwritable
    the tick still proceeds. Operator visibility loss is preferred over
    crashing the applier.
    """
    payload = dict(entry)
    payload.setdefault("ts", _utc_now_iso())
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, default=str) + "\n")
    except OSError:
        # Don't propagate log failures.
        pass


def _git(args: list[str], cwd: pathlib.Path) -> subprocess.CompletedProcess:
    """Thin wrapper around ``git`` so it can be uniformly mocked in tests."""
    return subprocess.run(  # noqa: S603 - argv list, no shell
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _resolve_head_sha(repo_root: pathlib.Path) -> str:
    r = _git(["rev-parse", "HEAD"], cwd=repo_root)
    if r.returncode != 0:
        return ""
    return r.stdout.strip()


def _write_failure_record(
    repo_root: pathlib.Path,
    manifest_name: str,
    *,
    phase: str,
    error_summary: str,
    exit_code: int | None = None,
    tick_log_excerpt: str | None = None,
) -> pathlib.Path | None:
    """Write ``deploys/failed/<name>-<ts>.yaml`` per data-model.md schema.

    Returns the written path on success, or ``None`` if the write failed.
    The manifest stays in the queue regardless.
    """
    failed_dir = repo_root / "deploys" / "failed"
    try:
        failed_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    ts = _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = failed_dir / f"{manifest_name}-{ts}.yaml"
    record: dict[str, Any] = {
        "manifest_name": manifest_name,
        "failed_at": _utc_now_iso(),
        "phase": phase,
        "error_summary": (error_summary or "")[:500],
    }
    if exit_code is not None:
        record["exit_code"] = exit_code
    if tick_log_excerpt:
        record["tick_log_excerpt"] = tick_log_excerpt
    try:
        import yaml  # local import keeps test setup minimal
        out_path.write_text(
            yaml.safe_dump(record, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )
    except Exception:  # pragma: no cover - extreme edge
        return None
    return out_path


def _record_success(
    repo_root: pathlib.Path,
    manifest_path: pathlib.Path,
    manifest_data: dict[str, Any],
    head_sha: str,
) -> tuple[bool, str]:
    """Write applied entry, git-mv queued→applied, commit+push.

    Returns ``(ok, summary)``. On any sub-step failure, returns
    ``(False, reason)`` so the caller can record a tick log entry. The
    manifest is NOT removed from the queue when this fails — the next
    tick re-attempts it.
    """
    applied_dir = repo_root / "deploys" / "applied"
    schema_path = repo_root / "deploys" / "schema" / "manifest-v1.schema.json"

    write_res = _applied.write_applied(
        manifest_data,
        apply_mode="manifest",
        applied_dir=applied_dir,
        schema_path=schema_path if schema_path.exists() else None,
    )
    if not write_res.ok:
        return False, f"write_applied failed: {write_res.summary}"

    applied_path = pathlib.Path(write_res.details["path"])

    # git rm the queued file (it's tracked); git add the applied entry.
    rm = _git(
        ["rm", str(manifest_path.relative_to(repo_root))],
        cwd=repo_root,
    )
    if rm.returncode != 0:
        # Fallback: try plain unlink so the manifest is not re-processed
        # by the next tick. Don't crash; operator visibility via tick log.
        try:
            manifest_path.unlink()
        except OSError:
            pass

    add = _git(
        ["add", str(applied_path.relative_to(repo_root))],
        cwd=repo_root,
    )
    if add.returncode != 0:
        return False, f"git add applied entry failed: {add.stderr[:200]}"

    commit_msg = (
        f"deploy(applied): {manifest_data.get('name', '<unknown>')}"
        + (f" @ {head_sha[:8]}" if head_sha else "")
    )
    commit = _git(["commit", "-m", commit_msg], cwd=repo_root)
    if commit.returncode != 0:
        return False, f"git commit failed: {commit.stderr[:200]}"

    push = _git(["push"], cwd=repo_root)
    if push.returncode != 0:
        # Commit succeeded but push failed — operator visibility, not
        # crash. Next tick's git pull will reconcile.
        return False, f"git push failed: {push.stderr[:200]}"

    return True, str(applied_path)


def run_tick(
    repo_root: pathlib.Path | None = None,
    log_dir: pathlib.Path | None = None,
) -> int:
    """Execute one applier tick. Always returns 0 unless the process crashes.

    Args:
        repo_root: override the canonical checkout (test fixtures).
        log_dir: override the tick log directory (test fixtures).
    """
    repo_root = pathlib.Path(repo_root) if repo_root else DEFAULT_REPO_ROOT
    log_dir = pathlib.Path(log_dir) if log_dir else DEFAULT_LOG_DIR
    log_path = log_dir / f"{_dt.date.today():%Y-%m-%d}.jsonl"

    import os as _os  # TEMP DEBUG: trace env for #595 smoke
    _log(log_path, {"event": "tick_start", "debug_ntfy_topic_present": bool(_os.environ.get("FELIX_DEPLOYER_NTFY_TOPIC", "").strip()), "debug_ntfy_topic_len": len(_os.environ.get("FELIX_DEPLOYER_NTFY_TOPIC", ""))})

    # 1. git pull --ff-only.
    pull = _git(["pull", "--ff-only"], cwd=repo_root)
    if pull.returncode != 0:
        _log(
            log_path,
            {
                "event": "tick_skip",
                "reason": "git_pull_failed",
                "stderr": (pull.stderr or "")[:200],
            },
        )
        return 0

    head_sha = _resolve_head_sha(repo_root)

    # 2. Scan deploys/queued/ in alphabetical order.
    queued_dir = repo_root / "deploys" / "queued"
    queue = sorted(queued_dir.glob("*.yaml")) if queued_dir.exists() else []
    _log(
        log_path,
        {
            "event": "queue_scanned",
            "count": len(queue),
            "head_sha": head_sha,
        },
    )

    # 3. Process each manifest in turn. One failure does NOT abort the
    #    remaining manifests in the queue.
    for manifest_path in queue:
        try:
            manifest_data = _manifest.load_manifest(manifest_path)
        except (FileNotFoundError, ValueError) as exc:
            # Parse failure: write a failure record with a synthetic
            # phase ("manifest_parse") and continue. No DM — we don't
            # have a usable tier or name for the payload.
            _write_failure_record(
                repo_root,
                manifest_path.stem,
                phase="manifest_parse",
                error_summary=str(exc),
            )
            _log(
                log_path,
                {
                    "event": "manifest_processed",
                    "manifest_path": str(manifest_path),
                    "outcome": "failed_manifest_parse",
                },
            )
            continue

        manifest_name = manifest_data.get("name") or manifest_path.stem
        result = _apply.dry_run_then_apply_gate(manifest_data, str(manifest_path))

        if result.ok:
            ok, summary = _record_success(
                repo_root, manifest_path, manifest_data, head_sha
            )
            if ok:
                _log(
                    log_path,
                    {
                        "event": "manifest_processed",
                        "manifest_name": manifest_name,
                        "outcome": "applied",
                        "applied_path": summary,
                    },
                )
            else:
                _log(
                    log_path,
                    {
                        "event": "manifest_processed",
                        "manifest_name": manifest_name,
                        "outcome": "applied_record_failed",
                        "reason": summary,
                    },
                )
            continue

        # Apply failed: write failure record + dispatch notification.
        # Manifest stays in the queue.
        phase = result.details.get("phase", "unknown")
        exit_code = result.details.get("returncode")
        record_path = _write_failure_record(
            repo_root,
            manifest_name,
            phase=phase,
            error_summary=result.summary,
            exit_code=exit_code if isinstance(exit_code, int) else None,
        )

        # Notification dispatch MUST NOT crash the tick — wrap broadly.
        try:
            _notify.dispatch_failure_notification(
                manifest=manifest_data,
                phase=phase,
                error_summary=result.summary,
                head_sha=head_sha,
            )
        except Exception as exc:  # pragma: no cover - defence in depth
            _log(
                log_path,
                {
                    "event": "notify_dispatch_error",
                    "manifest_name": manifest_name,
                    "error": str(exc)[:200],
                },
            )

        _log(
            log_path,
            {
                "event": "manifest_processed",
                "manifest_name": manifest_name,
                "outcome": f"failed_{phase}",
                "failure_record": str(record_path) if record_path else None,
            },
        )

    _log(log_path, {"event": "tick_complete"})
    return 0


__all__ = ["run_tick", "PHASE_TO_NOTIFY_PHASE"]
