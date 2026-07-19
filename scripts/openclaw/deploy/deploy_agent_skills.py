"""Felix agent-skill deploy pipeline helper (#775).

Pull-based sync, sibling to ``deploy_agent_prompts.py`` (#567) but for the
**skills** surface. Each tick (every 5 min via systemd) advances the shared
checkout at /home/claude/kg-automation and, for each repo skill under
scripts/openclaw/skills/<skill>/, MD5-compares SKILL.md against the deployed
file at /home/claude/.openclaw/skills/<skill>/SKILL.md and atomically copies
any drifted file. Audit log at
/data/services/openclaw/deploy/agent-skill-sync.jsonl.

Why a parallel module (not extending deploy_agent_prompts): skills use a
different scope model (repo-dir enumeration, a single SKILL.md per dir, a
different dest base) than agent prompts (service-inventory agents map, a 5-file
allowlist, per-agent workspace). Keeping them separate leaves the load-bearing
prompt-sync guard untouched (DIRECTIVE_024, research D-1). The shared deploy
primitives (gitsync/deploylock/health) and the alert bus are reused as-is; the
two generic file primitives (compute_md5/atomic_copy) are duplicated locally —
two call sites is within the rule-of-three.

Design invariants (this mission's data-model.md):
  * Repo SKILL.md is the SOLE source of truth; dest converges to it.
  * Copy-only: never delete a dest-side file (FR-004). ``*.backup*`` sidecars
    are never a source or dest target (FR-010).
  * Atomic writes preserving dst mode; dest.parent is created first (FR-016).
  * A repo skill dir with files other than SKILL.md emits a warning-audit
    (multi-file guard, FR-015) — the payload stays SKILL.md only.
  * The checkout-touching critical section runs under the shared deploylock so
    it never races felix-deployer / prompt-sync; on contention the tick defers
    cleanly (exit 0, no copy).
  * A persistent git-advance OR copy failure fires at most one ntfy alert per
    confirmed-failure streak, via the felix-alert bus.

Invocation form (mandatory — the module imports scripts.* siblings, so a
script-path invocation fails ModuleNotFoundError; #668):

    python3 -m scripts.openclaw.deploy.deploy_agent_skills [--dry-run] [--skill NAME]

Exit codes:
    0: success (no drift OR all copies succeeded; also a benign lock defer; also --dry-run)
    1: partial failure (advance ok, one or more per-file copies failed)
    2: git advance failed (fetch/merge/diverged — no copies attempted)
    3: validation error (missing .git/, missing skills dir, unknown --skill)

Stdlib only for the core path; shared deploy primitives + the alert bus are
imported from scripts.* — no requests/httpx/pydantic.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List, Optional

from scripts.common.alert_bus import Alert, Severity, emit
from scripts.deploy.lib import health as _health
from scripts.deploy.lib.deploylock import LockUnavailable, deploylock
from scripts.deploy.lib.gitsync import AdvanceResult, advance_checkout


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SKILL_FILENAME = "SKILL.md"
BACKUP_MARKER = ".backup"

REPO_ROOT_DEFAULT = Path("/home/claude/kg-automation")
SKILLS_SOURCE_RELATIVE = Path("scripts/openclaw/skills")
SKILLS_DEST_BASE = Path("/home/claude/.openclaw/skills")

AUDIT_PATH_DEFAULT = Path("/data/services/openclaw/deploy/agent-skill-sync.jsonl")
LAST_TICK_FILENAME = "skills-last-tick.json"

# Per-actor git-advance health watermark (streak-dedup one-ntfy alert).
HEALTH_STATE_PATH_DEFAULT = Path("/data/services/openclaw/deploy/agent-skill-sync-git-health.json")
HEALTH_ACTOR = "agent-skill-sync"

# Copy-failure health watermark (a per-file copy failure happens AFTER a
# successful git advance, so it never reaches the git-advance watermark — a
# persistent copy failure is a deployed skill silently not updating, the #563
# class this service exists to prevent).
COPY_HEALTH_ACTOR = "agent-skill-sync-copy"
COPY_FAILED_REASON = "copy_failed"
COPY_CONFIRMED_REASONS = frozenset({COPY_FAILED_REASON})
COPY_HEALTH_FILENAME = "agent-skill-sync-copy-health.json"

MD5_CHUNK_BYTES = 65536

# Exit codes
EXIT_SUCCESS = 0
EXIT_PARTIAL_FAILURE = 1
EXIT_GIT_PULL_FAILED = 2
EXIT_VALIDATION_ERROR = 3


# ---------------------------------------------------------------------------
# Alert-bus health notifier
# ---------------------------------------------------------------------------


def _health_notifier(title: str, body: str) -> bool:
    """Notifier seam passed to :func:`scripts.deploy.lib.health.record`.

    Dispatches a best-effort alert via the unified felix-alert bus and returns
    the delivery bool so ``health.record`` only stamps ``last_alert_ts`` on a
    delivered alert. ``AlertResult`` exposes ``.ok`` (NOT ``.delivered``);
    ``emit`` never raises. The bus resolves FELIX_ALERT_NTFY_TOPIC.
    """
    result = emit(
        Alert(
            source=HEALTH_ACTOR,
            severity=Severity.ERROR,
            title=title,
            description=body,
        )
    )
    return result.ok


def _copy_render(state, result, threshold: int) -> tuple[str, str]:
    """Render seam for the copy-failure watermark — copy-accurate wording (the
    default health render says "git advance stalled", which is wrong here)."""
    title = f"{state.actor}: skill-copy failing ({state.consecutive_failures}x)"
    body = (
        f"Actor: {state.actor}\n"
        f"Consecutive ticks with per-file skill-copy failures: "
        f"{state.consecutive_failures} (threshold {threshold})\n"
        f"Streak started: {state.failure_streak_started_ts}\n"
        f"A deployed OpenClaw skill (SKILL.md) is not being updated on office2 — "
        f"inspect the agent-skill-sync audit log (agent-skill-sync.jsonl) for the "
        f"failing skill(s). This is the #563 silent-drift class for skills (#775)."
    )
    return title, body


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SkillSyncUnit:
    """One unit of sync work: a repo skill's SKILL.md → its deployed copy."""

    skill: str
    source: Path
    dest: Path
    extra_files: tuple = field(default_factory=tuple)  # non-SKILL.md files in the repo dir (FR-015)


@dataclass
class SkillSyncCounts:
    """Per-skill counts of per-file actions emitted this tick."""

    copied: int = 0
    skipped: int = 0
    errored: int = 0
    warned: int = 0


@dataclass(frozen=True)
class GitPullResult:
    """Result of git_pull(): success + post-pull HEAD SHA, or failure + stage + stderr."""

    success: bool
    head_sha: Optional[str]
    stderr: str
    stage: Optional[str]
    advance: Optional[AdvanceResult] = None


# ---------------------------------------------------------------------------
# Filename filtering
# ---------------------------------------------------------------------------


def is_backup(filename: str) -> bool:
    """True iff *filename* is an office2-side backup sidecar (e.g.
    ``SKILL.md.backup.2026-04-10``). Backups are never a sync/drift target."""
    return BACKUP_MARKER in filename


# ---------------------------------------------------------------------------
# MD5 + atomic copy  (duplicated from deploy_agent_prompts — rule-of-three ok)
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

    1. Read src bytes
    2. Write to dst.parent / '<name>.tmp.<pid>'
    3. fsync the file descriptor
    4. If dst exists, capture its mode and chmod the temp to match
    5. os.replace temp -> dst (atomic POSIX rename)

    On any exception, the temp file is unlinked and the exception re-raised.
    The caller is responsible for creating dst.parent (FR-016).
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
# Skill scope enumeration
# ---------------------------------------------------------------------------


def iter_skills(
    repo_root: Path,
    skill_filter: Optional[str] = None,
) -> Iterator[SkillSyncUnit]:
    """Yield one SkillSyncUnit per repo skill dir that contains a SKILL.md.

    Scope is DERIVED from the repo skills dir (FR-011): a newly-added skill dir
    is picked up with no code change. A dir with no SKILL.md is skipped (the
    caller writes a warning). Files other than SKILL.md (ignoring ``*.backup*``)
    are surfaced on ``extra_files`` for the multi-file guard (FR-015).

    ``skill_filter`` restricts to one skill by name; the caller validates an
    unknown name (exit 3).
    """
    skills_root = repo_root / SKILLS_SOURCE_RELATIVE
    if not skills_root.is_dir():
        return
    for skill_dir in sorted(skills_root.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill = skill_dir.name
        if skill_filter is not None and skill != skill_filter:
            continue
        source = skill_dir / SKILL_FILENAME
        if not source.is_file():
            # No SKILL.md — yield a marker unit with an empty source so the
            # caller can emit a warning. We signal this via extra_files carrying
            # a sentinel is overkill; instead skip here and let the caller detect
            # missing via a separate pass. Simpler: emit nothing; the presence
            # check below (skills_present) handles the warning.
            continue
        extra = tuple(
            sorted(
                p.name
                for p in skill_dir.iterdir()
                if p.is_file() and p.name != SKILL_FILENAME and not is_backup(p.name)
            )
        )
        yield SkillSyncUnit(
            skill=skill,
            source=source,
            dest=SKILLS_DEST_BASE / skill / SKILL_FILENAME,
            extra_files=extra,
        )


def iter_skill_dirs_missing_skillmd(
    repo_root: Path,
    skill_filter: Optional[str] = None,
) -> Iterator[str]:
    """Yield the name of each repo skill dir that has NO SKILL.md (warning source)."""
    skills_root = repo_root / SKILLS_SOURCE_RELATIVE
    if not skills_root.is_dir():
        return
    for skill_dir in sorted(skills_root.iterdir()):
        if not skill_dir.is_dir():
            continue
        if skill_filter is not None and skill_dir.name != skill_filter:
            continue
        if not (skill_dir / SKILL_FILENAME).is_file():
            yield skill_dir.name


# ---------------------------------------------------------------------------
# Git advance wrapper
# ---------------------------------------------------------------------------


def git_pull(repo_root: Path) -> GitPullResult:
    """Race-immune fast-forward of *repo_root* to origin/main (assumes lock held).

    Mirrors deploy_agent_prompts.git_pull: delegates to advance_checkout with
    ``assume_locked=True`` (the caller holds the shared deploylock across the
    whole checkout-mutating critical section). Never raises.
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
# Audit log + freshness signal
# ---------------------------------------------------------------------------


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def audit_record(kind: str, tick_id: str, **fields) -> dict:
    record = {"timestamp": _utc_now_iso(), "tick_id": tick_id, "kind": kind}
    record.update(fields)
    return record


def audit_append(log_path: Path, record: dict) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, separators=(",", ":")) + "\n"
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(line)


def write_last_tick(signal_dir: Path, *, status: str, exit_code: int = 0) -> None:
    """Atomically write the per-tick freshness signal the canary reads.

    Written on EVERY real (non-dry-run) tick — including a benign lock-defer —
    so the pointer reflects TIMER LIVENESS, not deploy-work outcome. ``exit_code``
    is always 0 here (git-advance failures escalate via the health watermark and
    per-file copy failures land in the JSONL audit log; neither flips this
    pointer). Best-effort: a write failure must not crash the tick.
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
        pass


def audit_tick_summary(
    log_path: Path,
    tick_id: str,
    skills_processed: int,
    files_copied: int,
    files_skipped: int,
    files_errored: int,
    files_warned: int,
    git_head_after_pull: Optional[str],
    exit_code: int,
    duration_ms: int,
) -> None:
    audit_append(
        log_path,
        audit_record(
            kind="tick_summary",
            tick_id=tick_id,
            skills_processed=skills_processed,
            files_copied=files_copied,
            files_skipped=files_skipped,
            files_errored=files_errored,
            files_warned=files_warned,
            git_head_after_pull=git_head_after_pull,
            exit_code=exit_code,
            duration_ms=duration_ms,
        ),
    )


# ---------------------------------------------------------------------------
# Per-skill sync
# ---------------------------------------------------------------------------


def sync_skill(
    unit: SkillSyncUnit,
    log_path: Path,
    tick_id: str,
    dry_run: bool,
    dry_run_sink: Optional[List[str]] = None,
) -> SkillSyncCounts:
    """Sync one skill's SKILL.md: MD5-compare, atomic-copy on drift, audit.

    Copy-only (FR-004), backup-ignore (FR-010), dest.parent created first
    (FR-016), multi-file warning (FR-015). If dry_run, no audit writes; a DRIFT
    line is appended to dry_run_sink for a drift-candidate file.
    """
    counts = SkillSyncCounts()

    # Multi-file guard (FR-015): a repo skill dir with files beyond SKILL.md is
    # surfaced (once per skill) — the payload stays SKILL.md only.
    if unit.extra_files:
        counts.warned += 1
        if not dry_run:
            audit_append(
                log_path,
                audit_record(
                    kind="warning",
                    tick_id=tick_id,
                    skill=unit.skill,
                    error=(
                        "repo skill dir contains files other than SKILL.md "
                        f"(not synced): {list(unit.extra_files)}"
                    ),
                ),
            )

    src_md5 = compute_md5(unit.source)
    dst_md5_before: Optional[str] = None
    if unit.dest.exists():
        dst_md5_before = compute_md5(unit.dest)
    drift = dst_md5_before != src_md5

    if not drift:
        if not dry_run:
            audit_append(
                log_path,
                audit_record(
                    kind="skip",
                    tick_id=tick_id,
                    skill=unit.skill,
                    filename=SKILL_FILENAME,
                    src_md5=src_md5,
                    dst_md5_before=dst_md5_before,
                ),
            )
        counts.skipped += 1
        return counts

    # Drift.
    if dry_run:
        if dry_run_sink is not None:
            dry_run_sink.append(
                f"DRIFT {unit.skill} {SKILL_FILENAME} src_md5={src_md5} "
                f"dst_md5={dst_md5_before or 'absent'}"
            )
        counts.copied += 1
        return counts

    try:
        unit.dest.parent.mkdir(parents=True, exist_ok=True)  # FR-016
        atomic_copy(unit.source, unit.dest)
        audit_append(
            log_path,
            audit_record(
                kind="copy",
                tick_id=tick_id,
                skill=unit.skill,
                filename=SKILL_FILENAME,
                src_md5=src_md5,
                dst_md5_before=dst_md5_before,
                dst_path=str(unit.dest),
            ),
        )
        counts.copied += 1
    except OSError as exc:
        audit_append(
            log_path,
            audit_record(
                kind="error",
                tick_id=tick_id,
                skill=unit.skill,
                filename=SKILL_FILENAME,
                error=str(exc),
                error_class=type(exc).__name__,
            ),
        )
        counts.errored += 1
    return counts


# ---------------------------------------------------------------------------
# CLI orchestration
# ---------------------------------------------------------------------------


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="deploy_agent_skills",
        description="Sync OpenClaw agent skills (SKILL.md) from repo to deployed location.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute drift; print DRIFT lines to stdout; no audit writes; no file modifications.",
    )
    parser.add_argument(
        "--skill",
        type=str,
        default=None,
        metavar="NAME",
        help="Restrict iteration to one skill name.",
    )
    return parser.parse_args(argv)


def _validate(repo_root: Path, skill_filter: Optional[str]) -> Optional[str]:
    """Return None if validation passes, else a human-readable error (exit 3)."""
    if not (repo_root / ".git").exists():
        return f"not a git checkout: {repo_root} has no .git/ directory"
    skills_root = repo_root / SKILLS_SOURCE_RELATIVE
    if not skills_root.is_dir():
        return f"skills source dir not found at {skills_root}"
    if skill_filter is not None:
        known = {u.skill for u in iter_skills(repo_root)}
        known |= set(iter_skill_dirs_missing_skillmd(repo_root))
        if skill_filter not in known:
            return f"unknown skill: {skill_filter} (known: {sorted(known)})"
    return None


def _sync_all_skills(
    repo_root: Path,
    audit_path: Path,
    tick_id: str,
    skill_filter: Optional[str],
    dry_run: bool,
    dry_run_sink: List[str],
) -> tuple[int, int, int, int, int]:
    """Iterate skills and sync each; return (processed, copied, skipped, errored, warned)."""
    total_copied = total_skipped = total_errored = total_warned = 0
    skills_processed = 0

    # Warn on repo skill dirs with no SKILL.md (missing-source signal).
    if not dry_run:
        for missing in iter_skill_dirs_missing_skillmd(repo_root, skill_filter):
            audit_append(
                audit_path,
                audit_record(
                    kind="warning",
                    tick_id=tick_id,
                    skill=missing,
                    error="repo skill dir has no SKILL.md (skipped)",
                ),
            )
            total_warned += 1

    for unit in iter_skills(repo_root, skill_filter):
        skills_processed += 1
        counts = sync_skill(
            unit=unit,
            log_path=audit_path,
            tick_id=tick_id,
            dry_run=dry_run,
            dry_run_sink=dry_run_sink if dry_run else None,
        )
        total_copied += counts.copied
        total_skipped += counts.skipped
        total_errored += counts.errored
        total_warned += counts.warned
    return skills_processed, total_copied, total_skipped, total_errored, total_warned


def run_tick(
    args: argparse.Namespace,
    repo_root: Path,
    audit_path: Path,
    health_state_path: Optional[Path] = None,
) -> int:
    """Run one tick: validate, git_pull, iterate skills, return exit code.

    The checkout-touching critical section (git_pull fetch/merge AND the
    per-skill copy loop) runs inside the shared deploylock so it never races
    felix-deployer / prompt-sync (#667). Lock contention → clean defer.
    """
    tick_id = str(uuid.uuid4())
    start = time.monotonic()
    if health_state_path is None:
        health_state_path = HEALTH_STATE_PATH_DEFAULT

    validation_error = _validate(repo_root, args.skill)
    if validation_error is not None:
        sys.stderr.write(validation_error + "\n")
        return EXIT_VALIDATION_ERROR

    dry_run_sink: List[str] = []

    # --dry-run is read-only (no fetch/merge, no copy) — takes no lock.
    if args.dry_run:
        _sync_all_skills(
            repo_root, audit_path, tick_id, args.skill, dry_run=True, dry_run_sink=dry_run_sink
        )
        for line in dry_run_sink:
            sys.stdout.write(line + "\n")
        return EXIT_SUCCESS

    status = "success"
    try:
        try:
            with deploylock():
                rc = _run_locked_tick(
                    repo_root=repo_root,
                    audit_path=audit_path,
                    health_state_path=health_state_path,
                    tick_id=tick_id,
                    start=start,
                    skill_filter=args.skill,
                )
                if rc == EXIT_GIT_PULL_FAILED:
                    status = "git_pull_failed"
                elif rc == EXIT_PARTIAL_FAILURE:
                    status = "partial"
                return rc
        except LockUnavailable:
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
        # exit_code=0 always: the pointer is timer-liveness, not deploy outcome.
        write_last_tick(audit_path.parent, status=status)


def _run_locked_tick(
    *,
    repo_root: Path,
    audit_path: Path,
    health_state_path: Path,
    tick_id: str,
    start: float,
    skill_filter: Optional[str],
) -> int:
    """The fetch/merge + copy body — runs with the shared deploylock held."""
    pull_result = git_pull(repo_root)
    advance = pull_result.advance

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
            audit_path, tick_id, 0, 0, 0, 0, 0, None, EXIT_GIT_PULL_FAILED, duration_ms
        )
        return EXIT_GIT_PULL_FAILED

    git_head = pull_result.head_sha

    (
        skills_processed,
        total_copied,
        total_skipped,
        total_errored,
        total_warned,
    ) = _sync_all_skills(
        repo_root, audit_path, tick_id, skill_filter, dry_run=False, dry_run_sink=[]
    )

    exit_code = EXIT_PARTIAL_FAILURE if total_errored > 0 else EXIT_SUCCESS

    # Record the per-file COPY outcome on a sibling health watermark so a
    # persistent copy failure alerts (the git-advance watermark can't see it —
    # the pull succeeded). Adapt the copy result onto the AdvanceResult contract.
    copy_ok = total_errored == 0
    copy_result = AdvanceResult(
        ok=copy_ok,
        advanced=False,
        pre_head=git_head or "",
        post_head=git_head or "",
        origin_head=git_head or "",
        behind=0,
        ahead=0,
        diverged=False,
        reason=None if copy_ok else COPY_FAILED_REASON,
    )
    try:
        _health.record(
            COPY_HEALTH_ACTOR,
            copy_result,
            state_path=health_state_path.with_name(COPY_HEALTH_FILENAME),
            notifier=_health_notifier,
            confirmed_reasons=COPY_CONFIRMED_REASONS,
            render=_copy_render,
        )
    except Exception as exc:  # noqa: BLE001 - copy-health is escalation, never fatal
        audit_append(
            audit_path,
            audit_record(
                kind="copy_health_record_error",
                tick_id=tick_id,
                error=str(exc)[:200],
                error_class=type(exc).__name__,
            ),
        )

    duration_ms = int((time.monotonic() - start) * 1000)
    audit_tick_summary(
        audit_path,
        tick_id,
        skills_processed,
        total_copied,
        total_skipped,
        total_errored,
        total_warned,
        git_head,
        exit_code,
        duration_ms,
    )
    return exit_code


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    args = parse_args(argv)
    return run_tick(args, repo_root=Path.cwd(), audit_path=AUDIT_PATH_DEFAULT)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
