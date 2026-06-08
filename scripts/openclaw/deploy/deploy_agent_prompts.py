"""Felix agent-prompt deploy pipeline helper (WP01).

Pull-based sync: each tick (every 5 min via systemd) runs `git pull --ff-only`
inside /home/claude/kg-automation, then for each Felix agent declared under
services[openclaw].agents.* in service-inventory.json, MD5-compares each
in-scope prompt file in the agent's source_in_repo against the deployed file
at workspace/<filename>, and atomically copies any drifted file. Audit log
at /data/services/openclaw/deploy/agent-prompt-sync.jsonl.

Invocation form (mandatory per NFR-005):

    python3 -m scripts.openclaw.deploy.deploy_agent_prompts [--dry-run] [--agent SLUG]

Exit codes (per contracts/helper-cli.md):
    0: success (no drift OR all copies succeeded)
    1: partial failure (git pull succeeded, one or more per-file copies failed)
    2: git pull failed (no copies attempted)
    3: validation error (missing .git/, missing service-inventory.json, unknown --agent slug)

Stdlib only — no requests, httpx, pydantic, or other non-stdlib imports.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

IN_SCOPE_FILENAMES = frozenset({"AGENTS.md", "IDENTITY.md", "SOUL.md", "TOOLS.md", "USER.md"})
EXCLUDED_GOVERNANCE = "GOVERNANCE.md"
EXCLUDED_HEARTBEAT_PREFIX = "HEARTBEAT.md"

REPO_ROOT_DEFAULT = Path("/home/claude/kg-automation")
AUDIT_PATH_DEFAULT = Path("/data/services/openclaw/deploy/agent-prompt-sync.jsonl")
SERVICE_INVENTORY_RELATIVE = Path("docs/design/architecture/data/service-inventory.json")

MD5_CHUNK_BYTES = 65536


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
    """Result of git_pull(): success + post-pull HEAD SHA, or failure + stage + stderr."""

    success: bool
    head_sha: Optional[str]
    stderr: str
    stage: Optional[str]


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
    """Run `git fetch && git pull --ff-only origin main` inside repo_root.

    Returns a GitPullResult capturing success, post-pull HEAD SHA, and stage
    on failure (one of "fetch" or "pull"). Never raises; subprocess failures
    are surfaced via the GitPullResult.
    """
    fetch = subprocess.run(
        ["git", "fetch", "origin", "main"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if fetch.returncode != 0:
        return GitPullResult(success=False, head_sha=None, stderr=fetch.stderr.strip(), stage="fetch")
    pull = subprocess.run(
        ["git", "pull", "--ff-only", "origin", "main"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if pull.returncode != 0:
        return GitPullResult(success=False, head_sha=None, stderr=pull.stderr.strip(), stage="pull")
    rev_parse = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if rev_parse.returncode != 0:
        return GitPullResult(success=False, head_sha=None, stderr=rev_parse.stderr.strip(), stage="rev_parse")
    head_sha = rev_parse.stdout.strip()
    return GitPullResult(success=True, head_sha=head_sha, stderr="", stage=None)


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


def _utc_now_iso() -> str:
    """Return current UTC time as 'YYYY-MM-DDTHH:MM:SSZ' for audit records."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def run_tick(args: argparse.Namespace, repo_root: Path, audit_path: Path) -> int:
    """Run one tick: validate, git_pull, iterate agents, return exit code."""
    tick_id = str(uuid.uuid4())
    start = time.monotonic()

    validation_error = _validate(repo_root, args.agent)
    if validation_error is not None:
        sys.stderr.write(validation_error + "\n")
        return EXIT_VALIDATION_ERROR

    inventory_path = repo_root / SERVICE_INVENTORY_RELATIVE

    git_head: Optional[str] = None
    if not args.dry_run:
        pull_result = git_pull(repo_root)
        if not pull_result.success:
            audit_append(
                audit_path,
                audit_record(
                    kind="git_pull_failed",
                    tick_id=tick_id,
                    stage=pull_result.stage or "unknown",
                    git_exit_code=1,
                    error=pull_result.stderr[:2000],
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

    dry_run_sink: List[str] = []
    total_copied = 0
    total_skipped = 0
    total_errored = 0
    agents_processed = 0

    for agent in iter_agents(inventory_path):
        if args.agent is not None and agent.slug != args.agent:
            continue
        agents_processed += 1
        counts = sync_agent(
            agent=agent,
            repo_root=repo_root,
            log_path=audit_path,
            tick_id=tick_id,
            dry_run=args.dry_run,
            dry_run_sink=dry_run_sink if args.dry_run else None,
        )
        total_copied += counts.copied
        total_skipped += counts.skipped
        total_errored += counts.errored

    if args.dry_run:
        for line in dry_run_sink:
            sys.stdout.write(line + "\n")
        return EXIT_SUCCESS

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
