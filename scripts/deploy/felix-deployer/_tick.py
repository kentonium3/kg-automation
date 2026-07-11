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
import os
import pathlib
import subprocess
from typing import Any

from scripts.deploy.lib import apply as _apply
from scripts.deploy.lib import applied as _applied
from scripts.deploy.lib import health as _health
from scripts.deploy.lib import manifest as _manifest
from scripts.deploy.lib.deploylock import LockUnavailable, deploylock
from scripts.deploy.lib.gitsync import AdvanceResult, advance_checkout

import notify as _notify  # type: ignore[import-not-found]
import rebaseline as _rebaseline  # type: ignore[import-not-found]

DEFAULT_REPO_ROOT = pathlib.Path("/home/claude/kg-automation")
DEFAULT_LOG_DIR = pathlib.Path("/data/services/felix-deployer/logs")

#: Actor name for the shared per-actor git-advance health watermark (#667).
HEALTH_ACTOR = "felix-deployer"
#: Per-actor health-watermark state file (data drive on office2).
DEFAULT_STATE_DIR = pathlib.Path("/data/services/felix-deployer/state")
#: Env var naming felix-deployer's ntfy topic (reused for health alerts).
HEALTH_TOPIC_ENV = "FELIX_DEPLOYER_NTFY_TOPIC"

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


def _write_last_tick(
    state_dir: pathlib.Path, *, status: str, exit_code: int
) -> None:
    """Atomically write the per-tick freshness signal the canary reads.

    The felix-deployer ``health_check`` in ``service-inventory.json`` points at
    ``last-tick.json``; the canary freshness probe reads it and judges staleness
    against ``max_age_seconds``. ``completed_at_utc`` is the canary-recognized
    timestamp key and ``exit_code=0`` is the good signal.

    Written on EVERY tick — including a lock-defer — so the pointer reflects
    *timer liveness*, not deploy-work outcome. Deploy failures alert through
    ``git-health.json`` (consecutive-failure escalation) and ``deploys/failed/``,
    never this pointer, so it is always ``exit_code=0`` while the timer runs.
    Best-effort: a write failure must not crash the tick.
    """
    payload = {
        "status": status,
        "exit_code": exit_code,
        "completed_at_utc": _utc_now_iso(),
    }
    path = state_dir / "last-tick.json"
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        # Freshness-signal loss is preferable to crashing the applier.
        pass


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


def _advance_git_runner(repo_root: pathlib.Path):
    """Return a git runner bound to *repo_root* for :func:`advance_checkout`.

    Routing the fetch/merge through ``_tick._git`` keeps every git call in the
    tick uniformly mockable (the same seam the rebaseline engine uses).
    """

    def _runner(args: list[str]) -> subprocess.CompletedProcess:
        return _git(args, cwd=repo_root)

    return _runner


def _health_notifier(actor: str):
    """Return a health notifier that sends via the felix-deployer ntfy path.

    ``health.record`` calls the notifier with ``(title, body)`` and expects a
    delivery ``bool`` back; we route to
    :func:`notify.dispatch_health_notification` (best-effort, never raises into
    the tick) resolving the topic from ``FELIX_DEPLOYER_NTFY_TOPIC`` and return
    its delivery bool so ``health.record`` only stamps ``last_alert_ts`` on an
    actually-delivered alert.
    """

    def _notifier(title: str, body: str) -> bool:
        return _notify.dispatch_health_notification(
            actor, title, body, topic_env=HEALTH_TOPIC_ENV
        )

    return _notifier


def _rebaseline_git_runner(repo_root: pathlib.Path):
    """Return a git runner bound to *repo_root* for the rebaseline engine.

    The engine's ``classify_watermark`` takes a ``git_runner`` that runs from
    the deployer's checkout.  Routing through ``_tick._git`` keeps every git
    call uniformly mockable in the tick tests.
    """

    def _runner(args: list[str]) -> subprocess.CompletedProcess:
        return _git(args, cwd=repo_root)

    return _runner


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


class _RecordResult:
    """Structured outcome of :func:`_record_success` (C4 / Codex MED-1).

    ``commit_sha`` is captured immediately after a successful ``git commit``,
    **even when the subsequent push fails**, so the watermark advance can use
    the deployer's own commit SHA rather than a blind ``rev-parse HEAD``.
    ``ok`` is ``True`` only when both commit AND push succeed (queue-retry
    semantics unchanged); a commit-ok/push-fail still carries ``commit_sha``.

    Implemented as a plain class (not ``@dataclasses.dataclass``) because this
    module is loaded under synthetic names via ``spec_from_file_location`` in
    several test loaders; on Python 3.13 ``@dataclass`` resolves
    ``sys.modules[cls.__module__]`` at class-creation time, which is ``None``
    for a loader that does not register the module first.
    """

    __slots__ = ("ok", "commit_sha", "pushed", "applied_path", "error")

    def __init__(
        self,
        ok: bool,
        commit_sha: str | None = None,
        pushed: bool = False,
        applied_path: str | None = None,
        error: str | None = None,
    ) -> None:
        self.ok = ok
        self.commit_sha = commit_sha
        self.pushed = pushed
        self.applied_path = applied_path
        self.error = error

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return (
            f"_RecordResult(ok={self.ok!r}, commit_sha={self.commit_sha!r}, "
            f"pushed={self.pushed!r}, applied_path={self.applied_path!r}, "
            f"error={self.error!r})"
        )


def _record_success(
    repo_root: pathlib.Path,
    manifest_path: pathlib.Path,
    manifest_data: dict[str, Any],
    head_sha: str,
) -> _RecordResult:
    """Write applied entry, git-mv queued→applied, commit+push.

    Returns a :class:`_RecordResult`. On any sub-step failure ``ok`` is
    ``False`` so the caller can record a tick log entry. The manifest is NOT
    removed from the queue when this fails — the next tick re-attempts it.
    The deployer's own commit SHA is captured right after ``git commit`` even
    if push then fails.
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
        return _RecordResult(
            ok=False, error=f"write_applied failed: {write_res.summary}"
        )

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
        return _RecordResult(
            ok=False,
            applied_path=str(applied_path),
            error=f"git add applied entry failed: {add.stderr[:200]}",
        )

    commit_msg = (
        f"deploy(applied): {manifest_data.get('name', '<unknown>')}"
        + (f" @ {head_sha[:8]}" if head_sha else "")
    )
    commit = _git(["commit", "-m", commit_msg], cwd=repo_root)
    if commit.returncode != 0:
        return _RecordResult(
            ok=False,
            applied_path=str(applied_path),
            error=f"git commit failed: {commit.stderr[:200]}",
        )

    # Capture the deployer's own commit SHA NOW — before push — so the
    # watermark can advance to it even if the push fails (Codex MED-1 / C4).
    commit_sha = _resolve_head_sha(repo_root) or None

    push = _git(["push"], cwd=repo_root)
    if push.returncode != 0:
        # Commit succeeded but push failed — operator visibility, not
        # crash. Next tick's git pull will reconcile.  Carry commit_sha.
        return _RecordResult(
            ok=False,
            commit_sha=commit_sha,
            pushed=False,
            applied_path=str(applied_path),
            error=f"git push failed: {push.stderr[:200]}",
        )

    return _RecordResult(
        ok=True,
        commit_sha=commit_sha,
        pushed=True,
        applied_path=str(applied_path),
    )


def _coerce_record_result(res: Any) -> _RecordResult:
    """Normalize a ``_record_success`` return into a :class:`_RecordResult`.

    Accepts the structured result directly, or a legacy ``(ok, summary)``
    tuple (some tests monkeypatch ``_record_success`` to return a tuple).
    """
    if isinstance(res, _RecordResult):
        return res
    if isinstance(res, tuple) and len(res) == 2:
        ok, summary = res
        return _RecordResult(
            ok=bool(ok),
            pushed=bool(ok),
            applied_path=summary if ok else None,
            error=None if ok else summary,
        )
    # Unexpected shape — treat as failure without crashing.
    return _RecordResult(ok=False, error="unrecognized _record_success result")


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
    state_path = DEFAULT_STATE_DIR / "git-health.json"

    _log(log_path, {"event": "tick_start"})

    # T011 — Acquire the shared actor-level checkout lock around the ENTIRE
    # checkout-mutating critical section (Codex CRITICAL). felix-deployer keeps
    # mutating the same checkout/index long after the pull — the queue-apply
    # commits, applied-record commit/push, rebaseline stamp commit/push, and the
    # watermark write — so the lock MUST span all of it, not just the pull. The
    # only work OUTSIDE the lock is the pure-read setup above (path resolution +
    # the tick_start log), which touches nothing in the checkout.
    #
    # LockUnavailable is a benign defer: the other actor (agent-prompt-sync)
    # holds the lock this tick. Log tick_skip and return 0 — the next tick
    # retries. NOT a health failure (health.record is never called on defer).
    status = "success"
    rc = 0
    try:
        try:
            with deploylock():
                rc = _run_tick_locked(repo_root, log_path, state_path)
        except LockUnavailable:
            _log(
                log_path,
                {
                    "event": "tick_skip",
                    "reason": "lock_unavailable",
                },
            )
            status = "deferred"
            rc = 0
        return rc
    finally:
        # Freshness signal for the canary (service-inventory felix-deployer
        # health_check → last-tick.json). Written on EVERY tick, incl. a
        # lock-defer, so it reflects timer liveness, not deploy-work outcome.
        _write_last_tick(DEFAULT_STATE_DIR, status=status, exit_code=rc)


def _run_tick_locked(
    repo_root: pathlib.Path,
    log_path: pathlib.Path,
    state_path: pathlib.Path,
) -> int:
    """The checkout-mutating tick body — runs with the shared deploylock held.

    Spans pre-head capture → race-immune advance → queue-apply → applied-record
    commit/push → rebaseline observe/reconcile/stamp → watermark write. Every git
    mutation in the tick happens inside this function (i.e. inside the lock).
    """
    # 1. Race-immune fast-forward (T012). Replaces the historical bare
    # ``git pull --ff-only`` that read the shared .git/FETCH_HEAD and blew up with
    # "Cannot fast-forward to multiple branches" under the two-actor race.
    # ``advance_checkout`` fetches then merges the atomic ref ``origin/main``,
    # never FETCH_HEAD. assume_locked=True: we already hold the lock (above), so
    # advance_checkout must NOT re-acquire it. The git seam is routed through
    # ``_tick._git`` so every call stays uniformly mockable.
    #
    # Capture pre/post HEAD from the result so the rebaseline engine computes the
    # SAME pulled range (pre_pull_head..post_pull_head) as before — the #685/#688
    # rebaseline subsystem is byte-for-byte unchanged (result.pre_head →
    # pre_pull_head, result.post_head → post_pull_head).
    result = advance_checkout(
        repo_root,
        assume_locked=True,
        git_runner=_advance_git_runner(repo_root),
    )
    pre_pull_head = result.pre_head
    post_pull_head = result.post_head

    # T013 — record the advance outcome into the per-actor health watermark and
    # (on a confirmed-failure streak crossing the threshold) fire one ntfy alert.
    # lock_unavailable never reaches here (we hold the lock), so record() only
    # ever sees ok / diverged / fetch_failed / merge_failed. Best-effort: a
    # health-store error must never crash the tick.
    try:
        _health.record(
            HEALTH_ACTOR,
            result,
            state_path=state_path,
            notifier=_health_notifier(HEALTH_ACTOR),
        )
    except Exception as exc:  # noqa: BLE001 - health is escalation, never fatal
        _log(
            log_path,
            {
                "event": "health_record_error",
                "error": str(exc)[:200],
            },
        )

    if not result.ok:
        # T012/T013 — enriched fail-loud record (FR-005). diverged / fetch_failed
        # / merge_failed all carry the full ref state so a future incident is
        # self-diagnosing (the old log said only "Cannot fast-forward to multiple
        # branches" with no SHAs). Keep the git_pull_failed-shaped tick_skip
        # event, enriched with local_head/origin_head/behind/ahead/reason.
        _log(
            log_path,
            {
                "event": "tick_skip",
                "reason": result.reason,
                "local_head": result.pre_head,
                "origin_head": result.origin_head,
                "behind": result.behind,
                "ahead": result.ahead,
                "diverged": result.diverged,
                "stderr": (result.stderr or "")[:200],
            },
        )
        return 0

    head_sha = post_pull_head  # deployer bookkeeping commits reference this

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

    # Track applied manifest names so we can stamp the rebaseline outcome on
    # the deploy record (FR-003).  Populated inside the queue loop below;
    # consumed after reconcile.
    applied_this_tick: list[str] = []
    # Applied-record paths written this tick — the durable YAML artefacts the
    # reconcile outcome is stamped onto after reconcile (#688).
    applied_record_paths: list[str] = []
    # Baselines declared by manifests applied this tick — folded into the
    # pending token AFTER observe, BEFORE reconcile (T006 / FR-005/006).
    declared_baselines: set[str] = set()
    # Commit SHAs the deployer itself created this tick — used to advance the
    # watermark past our own bookkeeping commits (T004 / C4).
    own_commit_shas: list[str] = []

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

        # Pre-apply manifest validation (Codex HIGH-2): the
        # ``expected_baselines`` rules (known-baseline membership +
        # ``audited_surface: true`` coupling) MUST be enforced BEFORE the
        # entrypoint mutates office2 — a bogus/decoupled declaration should
        # reject the manifest with the office2 state untouched, not after the
        # apply already ran (which is when ``write_applied`` used to catch it).
        # Only the expected_baselines rules move earlier — we deliberately do
        # NOT add a full JSON-Schema pass here (the pipeline never schema-checked
        # pre-apply, so that would change apply behaviour for every manifest).
        validation = _manifest.validate_expected_baselines_only(manifest_data)
        if not validation.ok:
            _write_failure_record(
                repo_root,
                manifest_name,
                phase="manifest_validation",
                error_summary=validation.summary,
            )
            _log(
                log_path,
                {
                    "event": "manifest_processed",
                    "manifest_name": manifest_name,
                    "outcome": "failed_manifest_validation",
                    "reason": validation.summary,
                },
            )
            continue

        result = _apply.dry_run_then_apply_gate(manifest_data, str(manifest_path))

        if result.ok:
            rec = _coerce_record_result(
                _record_success(repo_root, manifest_path, manifest_data, head_sha)
            )
            # Capture the deployer's own commit SHA regardless of push outcome
            # (C4): a commit-ok/push-fail still advances the watermark past our
            # bookkeeping commit so we never re-observe it.
            if rec.commit_sha:
                own_commit_shas.append(rec.commit_sha)
            # Declared-baseline fold is gated on the APPLY success (result.ok),
            # NOT the record/push success (rec.ok) — Codex HIGH-1.  The office2
            # mutation already happened when apply succeeded, so its declared
            # rebaseline intent MUST be folded even if the applied-record commit
            # or push then fails; otherwise a push failure silently drops the
            # manifest-declared drift → NFR-001 / undetected drift.
            applied_this_tick.append(manifest_name)
            # Record the applied YAML path (when write_applied produced one) so
            # the reconcile outcome can be stamped onto it after reconcile
            # (#688). Present even when push failed, since the record file was
            # already written on disk.
            if rec.applied_path:
                applied_record_paths.append(rec.applied_path)
            for b in manifest_data.get("expected_baselines", []) or []:
                if b:
                    declared_baselines.add(b)
            if rec.ok:
                _log(
                    log_path,
                    {
                        "event": "manifest_processed",
                        "manifest_name": manifest_name,
                        "outcome": "applied",
                        "applied_path": rec.applied_path,
                    },
                )
            else:
                _log(
                    log_path,
                    {
                        "event": "manifest_processed",
                        "manifest_name": manifest_name,
                        "outcome": "applied_record_failed",
                        "reason": rec.error,
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
        # Thread the apply result's REAL captured error context into the alert
        # (#699 / SC-002): stderr/stdout excerpts, the failing argv/command, the
        # returncode and manifest_path all live in result.details from
        # scripts.deploy.lib.apply. Passing only result.summary is exactly how
        # the missing-exec-bit cause was lost in #699.
        failure_details = {
            key: result.details.get(key)
            for key in (
                "stderr_excerpt",
                "stdout_excerpt",
                "argv",
                "failed_command",
                "returncode",
                "manifest_path",
                "error_code",
            )
            if result.details.get(key) is not None
        }
        try:
            _notify.dispatch_failure_notification(
                manifest=manifest_data,
                phase=phase,
                error_summary=result.summary,
                head_sha=head_sha,
                details=failure_details,
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

    # 4. Rebaseline observe + reconcile (runs AFTER the queue loop so manifest
    #    application is never delayed — NFR-002).
    #
    # The entire rebaseline path is wrapped in a broad try/except that emits a
    # tick-log entry and lets the tick return 0.  This mirrors the pattern used
    # for notification dispatch above: the tick MUST NEVER crash on rebaseline
    # logic (no-crash discipline).
    watermark_class = _rebaseline.WATERMARK_FALLBACK
    try:
        # C3 — resolve the observe range base from the persisted watermark so
        # the range is complete regardless of which actor advanced HEAD (the
        # #685 out-of-band-pull defect).  The watermark is classified before
        # any self-heal so a transient git failure never advances past an
        # unverified range (FR-004 / Codex HIGH-1).
        watermark = _rebaseline.read_observed_head()
        watermark_class, range_base = _rebaseline.classify_watermark(
            watermark, post_pull_head, git_runner=_rebaseline_git_runner(repo_root)
        )
        if watermark_class == _rebaseline.WATERMARK_FALLBACK:
            observe_base = pre_pull_head
            range_source = "fallback"
        elif watermark_class == _rebaseline.WATERMARK_VALID:
            observe_base = range_base or pre_pull_head
            range_source = "watermark"
        elif watermark_class == _rebaseline.WATERMARK_SELF_HEAL:
            observe_base = range_base or post_pull_head
            range_source = "self_heal"
        else:  # WATERMARK_TRANSIENT — cannot determine range this tick.
            observe_base = post_pull_head  # empty range → not_required
            range_source = "transient"

        # C1 — observe the pulled range from the resolved base.
        obs_result = _rebaseline.observe(observe_base, post_pull_head)
        obs_outcome = obs_result.get("outcome", "not_required")
        obs_entry: dict[str, Any] = {
            "event": "rebaseline_observe",
            "outcome": obs_outcome,
            "pre_pull_head": pre_pull_head,
            "post_pull_head": post_pull_head,
            "base": observe_base,
            "range_source": range_source,
        }
        if obs_outcome == _rebaseline.OUTCOME_PENDING_SET:
            obs_entry["surface_ids"] = obs_result.get("surface_ids", [])
            obs_entry["matched_files"] = obs_result.get("matched_files", [])
        _log(log_path, obs_entry)

        # T006 — fold manifest-declared baselines into the token AFTER observe
        # and BEFORE reconcile (FR-005/006).  No-op when nothing was declared.
        if declared_baselines:
            fold_result = _rebaseline.fold_manifest_baselines(
                declared_baselines,
                observed_head_sha=post_pull_head,
                manifest_names=list(applied_this_tick),
            )
            _log(
                log_path,
                {
                    "event": "rebaseline_fold",
                    "outcome": fold_result.get("outcome"),
                    "expected_baselines": fold_result.get("expected_baselines", []),
                    "manifest_names": fold_result.get("manifest_names", []),
                },
            )

        # C2 — reconcile (only meaningful when a pending token exists, but
        # reconcile() is idempotent on no-token: returns not_required).
        rec_result = _rebaseline.reconcile()
        rec_outcome = rec_result.get("outcome", "not_required")
        rec_entry: dict[str, Any] = {
            "event": "rebaseline_reconcile",
            "outcome": rec_outcome,
        }
        if rec_outcome == _rebaseline.OUTCOME_COMPLETED:
            rec_entry["rebaselined_at_utc"] = rec_result.get("rebaselined_at_utc")
            rec_entry["baseline_count"] = rec_result.get("baseline_count")
        elif rec_outcome == _rebaseline.OUTCOME_FAILED:
            rec_entry["error_summary"] = rec_result.get("error_summary", "")
        elif rec_outcome == _rebaseline.OUTCOME_UNEXPECTED_DRIFT:
            rec_entry["drifted"] = rec_result.get("drifted", [])
            rec_entry["expected"] = rec_result.get("expected", [])
            rec_entry["unexpected"] = rec_result.get("unexpected", [])
        if rec_result.get("stale"):
            rec_entry["stale"] = True
        _log(log_path, rec_entry)

        # FR-003 — surface the rebaseline outcome on the applied deploy record.
        # When ≥1 manifest was applied this tick, emit a correlating
        # ``rebaseline_stamped`` log entry that links the applied manifest
        # names to the reconcile outcome and key details.  This gives operators
        # a single log line per tick that correlates deploys with the security
        # rebaseline state, satisfying the data-model.md "surfaced on the deploy
        # record" requirement.
        if applied_this_tick:
            stamp: dict[str, Any] = {
                "event": "rebaseline_stamped",
                "applied_manifests": applied_this_tick,
                "rebaseline_outcome": rec_outcome,
            }
            if rec_outcome == _rebaseline.OUTCOME_COMPLETED:
                stamp["rebaselined_at_utc"] = rec_result.get("rebaselined_at_utc")
                stamp["baseline_count"] = rec_result.get("baseline_count")
            elif rec_outcome == _rebaseline.OUTCOME_FAILED:
                stamp["error_summary"] = rec_result.get("error_summary", "")
            if rec_result.get("stale"):
                stamp["stale"] = True
            _log(log_path, stamp)

        # #688 — stamp the reconcile outcome onto the applied deploy record(s)
        # written this tick, so a deploy's rebaseline disposition is legible
        # from the durable YAML artefact (not only the tick-log stream). The
        # record was committed early in the queue loop (idempotency: a crash
        # must never re-run a non-idempotent entrypoint), so the outcome —
        # known only now, after reconcile — is written in a SECOND commit whose
        # SHA is appended to ``own_commit_shas`` BEFORE the watermark advance, so
        # the advance still lands on the deployer's last own commit (C4) and the
        # stamp commit is never re-observed next tick. Crash-safe: any failure is
        # logged and the tick proceeds (NFR-001).
        #
        # Gated on an outcome OTHER than ``not_required``: a ``not_required``
        # reconcile means no pending token existed (a non-audited deploy — the
        # common case), so there is no rebaseline disposition worth a second
        # commit. The applied record simply carries no ``rebaseline`` field then;
        # its absence means "no rebaseline was in play". Only audited deploys
        # (completed / cleared_clean / pending_clean / unexpected_drift /
        # failed / inconclusive) are stamped.
        if applied_record_paths and rec_outcome != _rebaseline.OUTCOME_NOT_REQUIRED:
            try:
                annotation = _build_rebaseline_annotation(rec_outcome, rec_result)
                stamped_rel: list[str] = []
                for rec_path in applied_record_paths:
                    if not pathlib.Path(rec_path).exists():
                        continue
                    res = _applied.stamp_rebaseline(rec_path, annotation)
                    if res.ok:
                        stamped_rel.append(
                            str(pathlib.Path(rec_path).relative_to(repo_root))
                        )
                    else:
                        _log(
                            log_path,
                            {
                                "event": "rebaseline_record_stamp_error",
                                "path": rec_path,
                                "reason": res.summary,
                            },
                        )
                if stamped_rel:
                    # On ANY git failure below, restore the stamped paths to HEAD
                    # (`git checkout HEAD -- <paths>` resets both index and
                    # working tree) so no dirty/staged record write leaks into
                    # the next tick's `deploy(applied)` commit or a later pull
                    # (Codex #688 MED-2).
                    add = _git(["add", *stamped_rel], cwd=repo_root)
                    if add.returncode != 0:
                        _git(["checkout", "HEAD", "--", *stamped_rel], cwd=repo_root)
                        _log(
                            log_path,
                            {
                                "event": "rebaseline_record_stamp_error",
                                "reason": f"git add failed: {add.stderr[:200]}",
                            },
                        )
                    else:
                        commit_msg = (
                            f"deploy(rebaseline): {rec_outcome} for "
                            f"{', '.join(applied_this_tick)}"
                        )
                        commit = _git(["commit", "-m", commit_msg], cwd=repo_root)
                        if commit.returncode != 0:
                            _git(["checkout", "HEAD", "--", *stamped_rel], cwd=repo_root)
                            _log(
                                log_path,
                                {
                                    "event": "rebaseline_record_stamp_error",
                                    "reason": f"git commit failed: {commit.stderr[:200]}",
                                },
                            )
                        else:
                            stamp_sha = _resolve_head_sha(repo_root)
                            if stamp_sha:
                                own_commit_shas.append(stamp_sha)
                            push = _git(["push"], cwd=repo_root)
                            _log(
                                log_path,
                                {
                                    "event": "rebaseline_record_stamped",
                                    "applied_records": stamped_rel,
                                    "outcome": rec_outcome,
                                    "commit_sha": stamp_sha,
                                    "pushed": push.returncode == 0,
                                },
                            )
            except Exception as exc:  # noqa: BLE001 - never crash the tick
                _log(
                    log_path,
                    {
                        "event": "rebaseline_record_stamp_error",
                        "error": str(exc)[:200],
                    },
                )

        # Dispatch ntfy alerts for off-happy-path events (C5).
        # Alert dispatch is best-effort: errors must NEVER propagate.
        _maybe_dispatch_rebaseline_alert(rec_outcome, rec_result, head_sha, log_path)

        # T004 / C4 — advance the observe watermark past our own bookkeeping
        # commit(s), crash-safe.  Skip on a TRANSIENT classification so we never
        # advance past an unverified range (Codex HIGH-1).  The new watermark is
        # the deployer's last own ``deploy(applied)`` commit that descends from
        # ``post_pull_head`` (deterministic "last own commit"), else
        # ``post_pull_head`` when we made no own commit this tick.
        if watermark_class != _rebaseline.WATERMARK_TRANSIENT:
            try:
                new_watermark = _select_watermark_advance(
                    repo_root, post_pull_head, own_commit_shas
                )
                _rebaseline.write_observed_head(new_watermark)
                _log(
                    log_path,
                    {
                        "event": "rebaseline_watermark",
                        "observed_head_sha": new_watermark,
                        "own_commits": own_commit_shas,
                    },
                )
            except Exception as exc:  # noqa: BLE001 - never crash the tick
                _log(
                    log_path,
                    {
                        "event": "rebaseline_watermark_error",
                        "error": str(exc)[:200],
                    },
                )

    except Exception as exc:  # pragma: no cover - defence in depth
        _log(
            log_path,
            {
                "event": "rebaseline_error",
                "error": str(exc)[:300],
            },
        )

    _log(log_path, {"event": "tick_complete"})
    return 0


def _build_rebaseline_annotation(
    rec_outcome: str, rec_result: dict[str, Any]
) -> dict[str, Any]:
    """Build the ``rebaseline`` annotation stamped onto an applied record (#688).

    Mirrors the fields in the ``rebaseline_stamped`` tick-log event so the
    durable record and the real-time log agree. ``at_utc`` timestamps the stamp
    so a non-terminal outcome's staleness is visible (a deploy whose drift lands
    in the grace window may be stamped ``pending_clean`` and is not re-stamped by
    a later tick in this MVP — see docs/runbooks/deployment.md).
    """
    annotation: dict[str, Any] = {
        "outcome": rec_outcome,
        "at_utc": _utc_now_iso(),
    }
    if rec_outcome == _rebaseline.OUTCOME_COMPLETED:
        bc = rec_result.get("baseline_count")
        if isinstance(bc, int):
            annotation["baseline_count"] = bc
    elif rec_outcome == _rebaseline.OUTCOME_FAILED:
        annotation["error_summary"] = (rec_result.get("error_summary") or "")[:500]
    elif rec_outcome == _rebaseline.OUTCOME_UNEXPECTED_DRIFT:
        unexpected = rec_result.get("unexpected") or []
        if unexpected:
            annotation["unexpected"] = list(unexpected)
    return annotation


def _select_watermark_advance(
    repo_root: pathlib.Path,
    post_pull_head: str,
    own_commit_shas: list[str],
) -> str:
    """Pick the new watermark value (C4).

    Returns the **last** captured own commit SHA that is a descendant of
    ``post_pull_head`` (verified with ``git merge-base --is-ancestor post
    <sha>``), or ``post_pull_head`` if we made no such commit this tick.
    Deterministic "last own commit" — never a blind ``rev-parse HEAD``.
    """
    for sha in reversed(own_commit_shas):
        if not sha:
            continue
        r = _git(["merge-base", "--is-ancestor", post_pull_head, sha], cwd=repo_root)
        if r.returncode == 0:
            return sha
    return post_pull_head


def _maybe_dispatch_rebaseline_alert(
    rec_outcome: str,
    rec_result: dict[str, Any],
    head_sha: str,
    log_path: pathlib.Path,
) -> None:
    """Dispatch ntfy alerts for off-happy-path rebaseline events (C5 / FR-006/009).

    Handles ``rebaseline_failed``, ``unexpected_drift``, and ``stale``
    outcomes.  Reads the pending token to check/update ``alerts_emitted``
    (dedupe).  Errors are caught and logged — NEVER raised.
    """
    # Map reconcile outcomes to the C5 event keys that require alerts.
    # ``stale`` may be co-emitted with ``unexpected_drift`` or ``inconclusive``.
    alert_events: list[str] = []
    if rec_outcome == _rebaseline.OUTCOME_FAILED:
        alert_events.append("rebaseline_failed")
    elif rec_outcome == _rebaseline.OUTCOME_UNEXPECTED_DRIFT:
        alert_events.append("unexpected_drift")
    if rec_result.get("stale"):
        # Use a DISTINCT dispatch key ("stale_ntfy") for the stale ntfy alert.
        # The engine's _maybe_stale pre-appends "stale" to token["alerts_emitted"]
        # before returning {"stale": True}, which would cause dispatch_rebaseline_alert
        # to dedupe (skip) the send if we used "stale" as the event_key here.
        # "stale_ntfy" is the WP03-layer dedupe key; "stale" remains the engine's
        # classification marker.  The two are intentionally decoupled.
        alert_events.append("stale_ntfy")

    if not alert_events:
        return

    # Load the current token (may have been updated by reconcile).
    token = _rebaseline.read_token()
    if token is None:
        # No token means nothing pending — alerts are not needed.
        return

    for event_key in alert_events:
        try:
            detail = _build_alert_detail(event_key, rec_result)
            _notify.dispatch_rebaseline_alert(
                event_key=event_key,
                token=token,
                detail=detail,
                head_sha=head_sha,
            )
            # Persist the updated alerts_emitted list (dispatch_rebaseline_alert
            # mutated ``token`` in place on successful send or dedupe).
            _rebaseline.write_token(token)
        except Exception as exc:  # noqa: BLE001 - defence in depth
            _log(
                log_path,
                {
                    "event": "rebaseline_alert_dispatch_error",
                    "event_key": event_key,
                    "error": str(exc)[:200],
                },
            )


def _build_alert_detail(event_key: str, rec_result: dict[str, Any]) -> str:
    """Build a short detail string for the ntfy alert body."""
    if event_key == "rebaseline_failed":
        return rec_result.get("error_summary", "rebaseline command failed")[:300]
    if event_key == "unexpected_drift":
        unexpected = rec_result.get("unexpected", [])
        return f"unexpected baselines: {', '.join(unexpected)}" if unexpected else "drift beyond expected set"
    if event_key in ("stale", "stale_ntfy"):
        # Accept both the canonical engine key ("stale") and the dispatch-layer
        # dedupe key ("stale_ntfy") so callers need not special-case either.
        return "token has exceeded max age; operator rebaseline required"
    return ""


__all__ = [
    "run_tick",
    "PHASE_TO_NOTIFY_PHASE",
    "_maybe_dispatch_rebaseline_alert",
    # Re-exported so the tick's git-advance primitive + result type are a single
    # import surface for tests/consumers of the felix-deployer tick (#667).
    "AdvanceResult",
    "advance_checkout",
    "deploylock",
    "LockUnavailable",
]
