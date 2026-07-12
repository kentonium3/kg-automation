"""Felix agent-prompt deploy pipeline helper (WP01 + #667 WP05).

Pull-based sync: each tick (every 5 min via systemd) advances the shared
checkout at /home/claude/kg-automation and, for each Felix agent declared under
services[openclaw].agents.* in service-inventory.json, MD5-compares each
in-scope prompt file in the agent's source_in_repo against the deployed file
at workspace/<filename>, and atomically copies any drifted file. Audit log
at /data/services/openclaw/deploy/agent-prompt-sync.jsonl.

Race-immune advance + shared lock (#667):
    The checkout advance goes through scripts.deploy.lib.gitsync.advance_checkout,
    which fetches then fast-forwards the atomic remote-tracking ref origin/main
    (never .git/FETCH_HEAD), structurally eliminating the historical
    "Cannot fast-forward to multiple branches" race. The whole checkout-touching
    critical section (the advance AND the per-agent prompt-copy loop) runs inside
    the shared scripts.deploy.lib.deploylock so it never races felix-deployer's
    concurrent checkout mutation. If the lock is contended the tick defers cleanly
    (git_pull_skipped audit record, exit 0 — prompts are NOT copied outside the
    lock). A per-actor health watermark (scripts.deploy.lib.health) fires at most
    one ntfy alert per confirmed-failure streak so a silent multi-week stall is
    impossible.

Invocation form (mandatory per NFR-005):

    python3 -m scripts.openclaw.deploy.deploy_agent_prompts [--dry-run] [--agent SLUG]

Exit codes (per contracts/helper-cli.md):
    0: success (no drift OR all copies succeeded; also a benign lock defer)
    1: partial failure (advance succeeded, one or more per-file copies failed)
    2: git advance failed (fetch/merge/diverged — no copies attempted)
    3: validation error (missing .git/, missing service-inventory.json, unknown --agent slug)

Stdlib only for the core sync path; the shared deploy primitives
(gitsync/deploylock/health) and the generic ntfy notifier are imported from
scripts.deploy.* — no requests, httpx, pydantic, or other third-party imports.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List, Optional

from scripts.deploy.lib import health as _health
from scripts.deploy.lib.deploylock import LockUnavailable, deploylock
from scripts.deploy.lib.gitsync import AdvanceResult, advance_checkout


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

IN_SCOPE_FILENAMES = frozenset({"AGENTS.md", "IDENTITY.md", "SOUL.md", "TOOLS.md", "USER.md"})
EXCLUDED_GOVERNANCE = "GOVERNANCE.md"
EXCLUDED_HEARTBEAT_PREFIX = "HEARTBEAT.md"

REPO_ROOT_DEFAULT = Path("/home/claude/kg-automation")
AUDIT_PATH_DEFAULT = Path("/data/services/openclaw/deploy/agent-prompt-sync.jsonl")
SERVICE_INVENTORY_RELATIVE = Path("docs/design/architecture/data/service-inventory.json")

# Per-tick freshness signal (#721). A flat JSON pointer the canary reads —
# written beside the append-only audit log because the JSONL itself is
# shape-unevaluable to the freshness probe (it is not a flat JSON object). See
# scripts/canary/probes.py and the felix-deployer last-tick.json precedent (#720).
LAST_TICK_FILENAME = "last-tick.json"

# Per-actor git-advance health watermark (#667, WP05). Lives beside the audit
# log so the prompt-sync deploy state is co-located.
HEALTH_STATE_PATH_DEFAULT = Path("/data/services/openclaw/deploy/git-health.json")

# This actor's identity for the health watermark. ``HEALTH_TOPIC_ENV`` is now
# vestigial (WP02 / #701): the felix-alert bus resolves the single
# FELIX_ALERT_NTFY_TOPIC, so the old per-actor topic env is no longer read for
# delivery. The constant + the topic_env kwarg are retained only so the notify
# call site stays signature-compatible.
HEALTH_ACTOR = "agent-prompt-sync"
HEALTH_TOPIC_ENV = "AGENT_PROMPT_SYNC_NTFY_TOPIC"

MD5_CHUNK_BYTES = 65536


# ---------------------------------------------------------------------------
# Cross-package notify loader
# ---------------------------------------------------------------------------
#
# The generic ntfy health notifier lives in scripts/deploy/felix-deployer/notify.py.
# That directory name contains a hyphen, so it is NOT importable via a dotted
# path (``import scripts.deploy.felix_deployer.notify`` → ModuleNotFoundError).
# The repo convention for reaching it (see tests/deploy/test_notify.py and
# felix-deployer's own _tick.py path bootstrap) is an ``importlib`` load from the
# on-disk path. We wrap that in a lazily-cached accessor so importing this module
# stays side-effect-free and cheap.

_FELIX_DEPLOYER_DIR = Path(__file__).resolve().parents[2] / "deploy" / "felix-deployer"
_notify_module = None


def _load_notify():
    """Load and cache the felix-deployer ``notify`` module from its on-disk path.

    Mirrors the ``importlib.util.spec_from_file_location`` mechanism used by the
    existing felix-deployer tests, because the hyphenated ``felix-deployer/``
    directory is not importable as a dotted package path.
    """
    global _notify_module
    if _notify_module is None:
        repo_root = _FELIX_DEPLOYER_DIR.parents[2]
        for extra in (str(repo_root), str(_FELIX_DEPLOYER_DIR)):
            if extra not in sys.path:
                sys.path.insert(0, extra)
        spec = importlib.util.spec_from_file_location(
            "felix_deployer_notify_for_prompt_sync",
            _FELIX_DEPLOYER_DIR / "notify.py",
        )
        if spec is None or spec.loader is None:
            raise ImportError(
                f"could not load felix-deployer notify module from "
                f"{_FELIX_DEPLOYER_DIR / 'notify.py'}"
            )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _notify_module = module
    return _notify_module


def _health_notifier(title: str, body: str) -> bool:
    """Notifier seam passed to :func:`scripts.deploy.lib.health.record`.

    Dispatches a best-effort health alert for this actor via the generic
    ``dispatch_health_notification`` in the felix-deployer notify module (now
    backed by the felix-alert bus — WP02) and returns its delivery ``bool``
    (True iff the alert was actually delivered) so ``health.record`` only stamps
    ``last_alert_ts`` on a delivered alert. The notifier never raises into the
    tick — the underlying bus swallows every failure mode and returns False.
    ``topic_env`` is passed for signature compatibility but is vestigial (the
    bus resolves FELIX_ALERT_NTFY_TOPIC).
    """
    notify = _load_notify()
    return notify.dispatch_health_notification(
        HEALTH_ACTOR,
        title,
        body,
        topic_env=HEALTH_TOPIC_ENV,
    )


# Exit codes
EXIT_SUCCESS = 0
EXIT_PARTIAL_FAILURE = 1
EXIT_GIT_PULL_FAILED = 2
EXIT_VALIDATION_ERROR = 3


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentInventoryEntry:
    """Minimal projection of services[openclaw].agents.<slug> used by the helper."""

    slug: str
    source_in_repo: Path
    workspace: Path


@dataclass(frozen=True)
class GitPullResult:
    """Result of git_pull(): success + post-pull HEAD SHA, or failure + stage + stderr.

    Public field contract (``success``, ``head_sha``, ``stderr``, ``stage``) is
    frozen — downstream code and existing tests depend on these names and order.
    ``advance`` is an additive, optional companion field carrying the underlying
    :class:`~scripts.deploy.lib.gitsync.AdvanceResult` so ``run_tick`` can enrich
    the failure audit record with ref-state and feed the health watermark; it
    defaults to ``None`` and never displaces the four public fields.
    """

    success: bool
    head_sha: Optional[str]
    stderr: str
    stage: Optional[str]
    advance: Optional[AdvanceResult] = None


# ---------------------------------------------------------------------------
# Filename filtering
# ---------------------------------------------------------------------------


def is_in_scope(filename: str) -> bool:
    """True iff filename matches the in-scope allowlist AND no exclusion pattern.

    Exclusions checked first:
      - HEARTBEAT.md and HEARTBEAT.md.* (runtime state owned by another process)
      - GOVERNANCE.md (manually maintained, no repo source for the main agent)
      - *.tmpl (templates)
      - *.bak* (backups; matches both '.bak' and '.bak.pre-mission-490' style)
    Then check membership in IN_SCOPE_FILENAMES.
    """
    if filename.startswith(EXCLUDED_HEARTBEAT_PREFIX):
        return False
    if filename == EXCLUDED_GOVERNANCE:
        return False
    if filename.endswith(".tmpl"):
        return False
    if ".bak" in filename:
        return False
    return filename in IN_SCOPE_FILENAMES


# ---------------------------------------------------------------------------
# Inventory discovery
# ---------------------------------------------------------------------------


OPENCLAW_SERVICE_NAMES = frozenset({"openclaw", "openclaw-gateway"})


def iter_agents(inventory_path: Path) -> Iterator[AgentInventoryEntry]:
    """Yield each Felix agent under the openclaw service's agents map.

    The openclaw service entry has been named both "openclaw" and
    "openclaw-gateway" over time. The canonical name in the production
    inventory is "openclaw-gateway"; the helper accepts either to remain
    robust across renames. Final fallback: pick the first service that
    has a non-empty `agents` dict (there is only one such service by Felix
    convention).

    Skips agents missing source_in_repo or workspace; caller may emit a
    warning audit record on the skip.
    """
    with open(inventory_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    services = data.get("services", [])
    openclaw_entry = None
    for svc in services:
        if svc.get("name") in OPENCLAW_SERVICE_NAMES:
            openclaw_entry = svc
            break
    if openclaw_entry is None:
        for svc in services:
            agents_candidate = svc.get("agents")
            if isinstance(agents_candidate, dict) and agents_candidate:
                openclaw_entry = svc
                break
    if openclaw_entry is None:
        return
    agents = openclaw_entry.get("agents") or {}
    if not isinstance(agents, dict):
        agents = openclaw_entry.get("config", {}).get("agents", {})
    for slug, meta in agents.items():
        if not isinstance(meta, dict):
            continue
        source_in_repo_raw = meta.get("source_in_repo")
        workspace_raw = meta.get("workspace")
        if not source_in_repo_raw or not workspace_raw:
            continue
        yield AgentInventoryEntry(
            slug=slug,
            source_in_repo=Path(str(source_in_repo_raw)),
            workspace=Path(str(workspace_raw)),
        )


# ---------------------------------------------------------------------------
# MD5 + atomic copy
# ---------------------------------------------------------------------------


def compute_md5(path: Path) -> str:
    """Return hex MD5 of the file at path. 64KB chunked reads."""
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(MD5_CHUNK_BYTES), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_copy(src: Path, dst: Path) -> None:
    """Atomically copy src bytes to dst. Preserve dst's prior mode if it existed.

    Implementation:
        1. Read src bytes
        2. Write to dst.parent / '<name>.tmp.<pid>'
        3. fsync the file descriptor
        4. If dst exists, capture its mode and chmod the temp to match
        5. os.replace temp -> dst (atomic POSIX rename)

    On any exception, the temp file is unlinked and the exception re-raised.
    """
    src_bytes = src.read_bytes()
    temp_path = dst.parent / f"{dst.name}.tmp.{os.getpid()}"
    try:
        with open(temp_path, "wb") as fh:
            fh.write(src_bytes)
            fh.flush()
            os.fsync(fh.fileno())
        if dst.exists():
            mode = dst.stat().st_mode & 0o777
            os.chmod(temp_path, mode)
        os.replace(temp_path, dst)
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:  # pragma: no cover
            pass
        raise


# ---------------------------------------------------------------------------
# Git pull wrapper
# ---------------------------------------------------------------------------


def git_pull(repo_root: Path) -> GitPullResult:
    """Race-immune fast-forward of *repo_root* to origin/main (#667).

    Delegates to :func:`scripts.deploy.lib.gitsync.advance_checkout` with
    ``assume_locked=True`` — the caller (:func:`run_tick`) already holds the
    shared ``deploylock`` around the whole checkout-mutating critical section
    (fetch/merge + prompt-copy). ``advance_checkout`` fetches, then fast-forwards
    the atomic remote-tracking **ref** ``origin/main`` (never ``.git/FETCH_HEAD``),
    structurally eliminating the ``Cannot fast-forward to multiple branches`` race.

    The :class:`AdvanceResult` is adapted onto the frozen public ``GitPullResult``
    shape (unchanged field names): a clean no-op (``behind == 0``) and a real
    fast-forward both map to ``success=True``; ``diverged``/``fetch_failed``/
    ``merge_failed``/``lock_unavailable`` map to ``success=False`` with ``stage``
    carrying the ``reason``. The underlying result is preserved on ``.advance``
    for the enriched audit record + health watermark.

    Never raises; git failures are surfaced via ``advance_checkout``'s reason.
    """
    result = advance_checkout(repo_root, assume_locked=True)
    success = result.ok and (result.advanced or result.behind == 0)
    head_sha = result.post_head or None
    stage = None if success else result.reason
    return GitPullResult(
        success=success,
        head_sha=head_sha,
        stderr=result.stderr,
        stage=stage,
        advance=result,
    )


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


def _utc_now_iso() -> str:
    """Return current UTC time as 'YYYY-MM-DDTHH:MM:SSZ' for audit records."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_last_tick(signal_dir: Path, *, status: str, exit_code: int = 0) -> None:
    """Atomically write the per-tick freshness signal the canary reads (#721).

    The agent-prompt-sync ``health_check`` in ``service-inventory.json`` points at
    ``last-tick.json`` beside the audit log; the canary freshness probe reads it
    and judges staleness against ``max_age_seconds``. ``completed_at_utc`` is the
    canary-recognized timestamp key and ``exit_code=0`` is the good signal.

    Written on EVERY real (non-dry-run) tick — including a benign lock-defer — so
    the pointer reflects *timer liveness*, not deploy-work outcome. Git-advance
    failures escalate through the ``git-health.json`` watermark (streak-based
    ntfy) and per-file copy failures land in the JSONL audit log, never this
    pointer, so it stays ``exit_code=0`` while the timer runs. ``status`` carries
    the tick disposition for human debugging only (it is NOT one of the canary's
    failure values, so it never flips the probe). Best-effort: a write failure
    must not crash the tick (mirrors felix-deployer ``_tick.py``).
    """
    payload = {
        "status": status,
        "exit_code": exit_code,
        "completed_at_utc": _utc_now_iso(),
    }
    path = signal_dir / LAST_TICK_FILENAME
    try:
        signal_dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        # Freshness-signal loss is preferable to crashing the tick.
        pass


def audit_record(kind: str, tick_id: str, **fields) -> dict:
    """Build an audit record dict with timestamp, tick_id, kind, and arbitrary extra fields."""
    record = {"timestamp": _utc_now_iso(), "tick_id": tick_id, "kind": kind}
    record.update(fields)
    return record


def audit_append(log_path: Path, record: dict) -> None:
    """Append one JSON line to log_path. Creates parent dir on first run."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, separators=(",", ":")) + "\n"
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(line)


def audit_tick_summary(
    log_path: Path,
    tick_id: str,
    agents_processed: int,
    files_copied: int,
    files_skipped: int,
    files_errored: int,
    git_head_after_pull: Optional[str],
    exit_code: int,
    duration_ms: int,
) -> None:
    """Append the tick_summary record at end of tick (per audit-log-jsonl contract)."""
    record = audit_record(
        kind="tick_summary",
        tick_id=tick_id,
        agents_processed=agents_processed,
        files_copied=files_copied,
        files_skipped=files_skipped,
        files_errored=files_errored,
        git_head_after_pull=git_head_after_pull,
        exit_code=exit_code,
        duration_ms=duration_ms,
    )
    audit_append(log_path, record)


# ---------------------------------------------------------------------------
# Per-agent sync
# ---------------------------------------------------------------------------


@dataclass
class AgentSyncCounts:
    """Per-agent counts of per-file actions emitted this tick."""

    copied: int = 0
    skipped: int = 0
    errored: int = 0


def sync_agent(
    agent: AgentInventoryEntry,
    repo_root: Path,
    log_path: Path,
    tick_id: str,
    dry_run: bool,
    dry_run_sink: Optional[List[str]] = None,
) -> AgentSyncCounts:
    """Sync one agent: iterate in-scope source files, MD5-compare, atomic-copy on drift.

    If dry_run is True, no audit records are written; instead a 'DRIFT' line is
    appended to dry_run_sink (if provided) for each drift-candidate file.

    Returns per-agent counts (copy/skip/error).
    """
    counts = AgentSyncCounts()
    source_dir = repo_root / agent.source_in_repo
    if not source_dir.exists():
        if not dry_run:
            audit_append(
                log_path,
                audit_record(
                    kind="warning",
                    tick_id=tick_id,
                    agent_slug=agent.slug,
                    error=f"source directory does not exist: {source_dir}",
                ),
            )
        return counts
    for entry in sorted(source_dir.iterdir()):
        if not entry.is_file():
            continue
        if not is_in_scope(entry.name):
            continue
        dst_path = agent.workspace / entry.name
        src_md5 = compute_md5(entry)
        dst_md5_before: Optional[str] = None
        if dst_path.exists():
            dst_md5_before = compute_md5(dst_path)
        drift = (dst_md5_before != src_md5)
        if drift:
            if dry_run:
                if dry_run_sink is not None:
                    dry_run_sink.append(
                        f"DRIFT {agent.slug} {entry.name} src_md5={src_md5} "
                        f"dst_md5={dst_md5_before or 'absent'}"
                    )
                counts.copied += 1
                continue
            try:
                agent.workspace.mkdir(parents=True, exist_ok=True)
                atomic_copy(entry, dst_path)
                audit_append(
                    log_path,
                    audit_record(
                        kind="copy",
                        tick_id=tick_id,
                        agent_slug=agent.slug,
                        filename=entry.name,
                        src_md5=src_md5,
                        dst_md5_before=dst_md5_before,
                        dst_path=str(dst_path),
                    ),
                )
                counts.copied += 1
            except OSError as exc:
                audit_append(
                    log_path,
                    audit_record(
                        kind="error",
                        tick_id=tick_id,
                        agent_slug=agent.slug,
                        filename=entry.name,
                        error=str(exc),
                        error_class=type(exc).__name__,
                    ),
                )
                counts.errored += 1
        else:
            if not dry_run:
                audit_append(
                    log_path,
                    audit_record(
                        kind="skip",
                        tick_id=tick_id,
                        agent_slug=agent.slug,
                        filename=entry.name,
                        src_md5=src_md5,
                        dst_md5_before=dst_md5_before,
                    ),
                )
            counts.skipped += 1
    return counts


# ---------------------------------------------------------------------------
# CLI orchestration
# ---------------------------------------------------------------------------


def parse_args(argv: List[str]) -> argparse.Namespace:
    """Parse argv into a Namespace with .dry_run (bool) and .agent (Optional[str])."""
    parser = argparse.ArgumentParser(
        prog="deploy_agent_prompts",
        description="Sync Felix agent prompts from repo to deployed location.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute drift; print DRIFT lines to stdout; no audit log writes; no file modifications.",
    )
    parser.add_argument(
        "--agent",
        type=str,
        default=None,
        metavar="SLUG",
        help="Restrict iteration to one agent slug.",
    )
    return parser.parse_args(argv)


def _validate(repo_root: Path, agent_filter: Optional[str]) -> Optional[str]:
    """Return None if validation passes, else a human-readable error string (exit 3)."""
    if not (repo_root / ".git").exists():
        return f"not a git checkout: {repo_root} has no .git/ directory"
    inventory_path = repo_root / SERVICE_INVENTORY_RELATIVE
    if not inventory_path.exists():
        return f"service-inventory.json not found at {inventory_path}"
    try:
        with open(inventory_path, "r", encoding="utf-8") as fh:
            json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        return f"service-inventory.json failed to parse: {exc}"
    if agent_filter is not None:
        known_slugs = {a.slug for a in iter_agents(inventory_path)}
        if agent_filter not in known_slugs:
            return f"unknown agent slug: {agent_filter} (known: {sorted(known_slugs)})"
    return None


def _sync_all_agents(
    inventory_path: Path,
    repo_root: Path,
    audit_path: Path,
    tick_id: str,
    agent_filter: Optional[str],
    dry_run: bool,
    dry_run_sink: List[str],
) -> tuple[int, int, int, int]:
    """Iterate agents and sync each; return (processed, copied, skipped, errored)."""
    total_copied = 0
    total_skipped = 0
    total_errored = 0
    agents_processed = 0
    for agent in iter_agents(inventory_path):
        if agent_filter is not None and agent.slug != agent_filter:
            continue
        agents_processed += 1
        counts = sync_agent(
            agent=agent,
            repo_root=repo_root,
            log_path=audit_path,
            tick_id=tick_id,
            dry_run=dry_run,
            dry_run_sink=dry_run_sink if dry_run else None,
        )
        total_copied += counts.copied
        total_skipped += counts.skipped
        total_errored += counts.errored
    return agents_processed, total_copied, total_skipped, total_errored


def run_tick(
    args: argparse.Namespace,
    repo_root: Path,
    audit_path: Path,
    health_state_path: Optional[Path] = None,
) -> int:
    """Run one tick: validate, git_pull, iterate agents, return exit code.

    The checkout-touching critical section (the ``git_pull`` fetch/merge AND the
    per-agent prompt-copy loop) runs inside the shared ``deploylock`` so it never
    races felix-deployer's concurrent checkout mutation (#667). If the lock is
    contended past its bounded retry, the tick defers cleanly: a
    ``git_pull_skipped`` audit record is written and the tick returns success —
    prompts are NOT copied outside the lock.
    """
    tick_id = str(uuid.uuid4())
    start = time.monotonic()
    if health_state_path is None:
        health_state_path = HEALTH_STATE_PATH_DEFAULT

    validation_error = _validate(repo_root, args.agent)
    if validation_error is not None:
        sys.stderr.write(validation_error + "\n")
        return EXIT_VALIDATION_ERROR

    inventory_path = repo_root / SERVICE_INVENTORY_RELATIVE
    dry_run_sink: List[str] = []

    # --dry-run is read-only (no fetch/merge, no copy) — it takes no lock so it
    # can never block, and mirrors the existing dry-run contract.
    if args.dry_run:
        _sync_all_agents(
            inventory_path,
            repo_root,
            audit_path,
            tick_id,
            args.agent,
            dry_run=True,
            dry_run_sink=dry_run_sink,
        )
        for line in dry_run_sink:
            sys.stdout.write(line + "\n")
        return EXIT_SUCCESS

    # Real tick: hold the shared checkout lock across fetch/merge + copy. The
    # per-tick freshness signal (last-tick.json, read by the canary) is written
    # in the finally so it reflects timer liveness on EVERY real tick — the
    # locked path AND a benign lock-defer (#721).
    status = "success"
    try:
        try:
            with deploylock():
                rc = _run_locked_tick(
                    inventory_path=inventory_path,
                    repo_root=repo_root,
                    audit_path=audit_path,
                    health_state_path=health_state_path,
                    tick_id=tick_id,
                    start=start,
                    agent_filter=args.agent,
                )
                if rc == EXIT_GIT_PULL_FAILED:
                    status = "git_pull_failed"
                elif rc == EXIT_PARTIAL_FAILURE:
                    status = "partial"
                return rc
        except LockUnavailable:
            # Benign defer: the other actor held the lock. Record it and retry
            # next tick. NOT a git failure and NOT a health failure — no prompts
            # copied.
            status = "deferred"
            audit_append(
                audit_path,
                audit_record(
                    kind="git_pull_skipped",
                    tick_id=tick_id,
                    stage="lock",
                    reason="lock_unavailable",
                ),
            )
            return EXIT_SUCCESS
    finally:
        # exit_code=0 always: the pointer is timer-liveness, not deploy outcome
        # (failures escalate via git-health.json + the audit log).
        write_last_tick(audit_path.parent, status=status)


def _run_locked_tick(
    *,
    inventory_path: Path,
    repo_root: Path,
    audit_path: Path,
    health_state_path: Path,
    tick_id: str,
    start: float,
    agent_filter: Optional[str],
) -> int:
    """The fetch/merge + copy body — runs with the shared deploylock held."""
    pull_result = git_pull(repo_root)
    advance = pull_result.advance

    # Update the health watermark from the advance outcome (fires at most one
    # ntfy alert per confirmed-failure streak; lock_unavailable never reaches
    # here since the lock is held). Best-effort — the notifier never raises, and
    # the whole call is failure-contained: a health-store or notify-import error
    # must never crash the prompt-sync tick (mirrors felix-deployer _tick.py).
    if advance is not None:
        try:
            _health.record(
                HEALTH_ACTOR,
                advance,
                state_path=health_state_path,
                notifier=_health_notifier,
            )
        except Exception as exc:  # noqa: BLE001 - health is escalation, never fatal
            audit_append(
                audit_path,
                audit_record(
                    kind="health_record_error",
                    tick_id=tick_id,
                    error=str(exc)[:200],
                    error_class=type(exc).__name__,
                ),
            )

    if not pull_result.success:
        audit_append(
            audit_path,
            audit_record(
                kind="git_pull_failed",
                tick_id=tick_id,
                stage=pull_result.stage or "unknown",
                git_exit_code=1,
                error=pull_result.stderr[:2000],
                local_head=(advance.pre_head if advance else None),
                origin_head=(advance.origin_head if advance else None),
                behind=(advance.behind if advance else None),
                ahead=(advance.ahead if advance else None),
                reason=(advance.reason if advance else pull_result.stage),
            ),
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        audit_tick_summary(
            audit_path,
            tick_id=tick_id,
            agents_processed=0,
            files_copied=0,
            files_skipped=0,
            files_errored=0,
            git_head_after_pull=None,
            exit_code=EXIT_GIT_PULL_FAILED,
            duration_ms=duration_ms,
        )
        return EXIT_GIT_PULL_FAILED

    git_head = pull_result.head_sha

    (
        agents_processed,
        total_copied,
        total_skipped,
        total_errored,
    ) = _sync_all_agents(
        inventory_path,
        repo_root,
        audit_path,
        tick_id,
        agent_filter,
        dry_run=False,
        dry_run_sink=[],
    )

    exit_code = EXIT_PARTIAL_FAILURE if total_errored > 0 else EXIT_SUCCESS
    duration_ms = int((time.monotonic() - start) * 1000)
    audit_tick_summary(
        audit_path,
        tick_id=tick_id,
        agents_processed=agents_processed,
        files_copied=total_copied,
        files_skipped=total_skipped,
        files_errored=total_errored,
        git_head_after_pull=git_head,
        exit_code=exit_code,
        duration_ms=duration_ms,
    )
    return exit_code


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point. Parses argv, runs one tick, returns the exit code."""
    if argv is None:
        argv = sys.argv[1:]
    args = parse_args(argv)
    return run_tick(args, repo_root=Path.cwd(), audit_path=AUDIT_PATH_DEFAULT)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
