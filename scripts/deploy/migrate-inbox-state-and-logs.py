#!/usr/bin/env python3
"""One-time Tier-2 inbox state & log migration entrypoint (narrowed scope).

Mission: felix-admin-cron-path-fix-01KWQTY3 (kentonium3/kg-automation#656)
Fast-follow: full /home/claude/second-brain decommission → #659

Moves:
  State files:
    /home/claude/second-brain/agents/state/{inbox-routing.jsonl,
                                            pending-calendar-clarifications.*}
    → /data/services/openclaw/state/  (claude:secondbrain, 0640)

  Inbox forensic logs (top-level only):
    /home/claude/second-brain/agents/logs/inbox-prescan-*.md
    → /home/kgale/second-brain/agents/logs/  (skip-if-exists)

  NOTE: per-agent observation subdirs (enrichment/, felix-admin-*, …) are
  intentionally NOT copied — they belong to the observation-digest subsystem
  which is still active. Full decommission of /home/claude/second-brain is
  deferred to #659 once those writers are repointed.

  The /home/claude/second-brain tree is LEFT IN PLACE by this migration.

Safety requirements:
  - Tier-2 snapshot gate via scripts.deploy.lib.snapshot.verify_restic_recent
  - --dry-run prints the full plan and mutates nothing (tested)
  - Idempotent: a second --apply is a safe no-op (tested)
  - Atomic copy-before-cutover: state files at new path before readers rely on them (H1)
  - Convergent: ownership and mode ALWAYS enforced on target dir/files, even when
    content copy is skipped (pre-existing identical file or partial prior run).

CLI usage
---------
  --dry-run               Print plan; no mutations.
  --apply                 Execute the migration.

  # Path overrides (for testing — defaults are the real office2 paths)
  --source-root DIR        Override /home/claude/second-brain
  --target-state-dir DIR   Override /data/services/openclaw/state
  --vault-logs-dir DIR     Override /home/kgale/second-brain/agents/logs
  --snapshot-log-dir DIR   Override Restic backup log dir
  --skip-snapshot-gate     Skip the Restic check (testing only — NOT safe in production)
  --skip-chown             Skip chown calls entirely (testing only on dev machines
                           where the service user/group do not exist — NOT safe
                           in production).

Exit codes
----------
  0   success (dry-run plan printed, or apply completed / already done)
  1   refused (snapshot gate failed, ownership error, or other error)
  2   usage error
"""
from __future__ import annotations

import argparse
import filecmp
import json
import os
import shutil
import stat as _stat
import sys
from pathlib import Path
from typing import Any

# sys.path shim — felix-deployer runs this entrypoint via its shebang, so the
# script dir (scripts/deploy/) is on sys.path but the repo root is NOT. Add the
# repo root so the lazy `from scripts.deploy.lib...` imports resolve regardless of
# how the entrypoint is invoked (matches the convention in the other deploy
# entrypoints, e.g. verify-felix-deployer-auto-rebaseline.py).
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ---------------------------------------------------------------------------
# Production defaults (real office2 paths)
# ---------------------------------------------------------------------------
DEFAULT_SOURCE_ROOT = Path("/home/claude/second-brain")
DEFAULT_TARGET_STATE_DIR = Path("/data/services/openclaw/state")
DEFAULT_VAULT_LOGS_DIR = Path("/home/kgale/second-brain/agents/logs")

TARGET_STATE_OWNER = "claude"
TARGET_STATE_GROUP = "secondbrain"
TARGET_STATE_DIR_MODE = 0o750
TARGET_STATE_FILE_MODE = 0o640

# ---------------------------------------------------------------------------
# State file classification constants
# In-scope state file names under agents/state/.
# ---------------------------------------------------------------------------
_STATE_FILENAMES_EXACT: frozenset[str] = frozenset({"inbox-routing.jsonl"})
_STATE_FILENAME_PREFIX = "pending-calendar-clarifications"


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _emit(label: str, msg: str, details: dict[str, Any] | None = None) -> None:
    sys.stdout.write(f"{label}: {msg}\n")
    if details:
        sys.stdout.write(json.dumps(details, sort_keys=True) + "\n")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

def _set_permissions(
    path: Path,
    mode: int,
    user: str | None = None,
    group: str | None = None,
    skip_chown: bool = False,
) -> None:
    """Apply *mode* and optionally set ownership.

    In production (``skip_chown=False``, the default), failure to set the
    requested owner/group is a **hard error**: a ``RuntimeError`` is raised
    and the caller should propagate it to abort the migration with exit 1.
    This ensures office2 never silently ends with files in the wrong ownership
    state.

    Pass ``skip_chown=True`` **only** in tests running on dev machines where
    the service user/group (``claude``/``secondbrain``) do not exist.  The
    flag is deliberately not the default so production paths fail loudly on
    misconfiguration.
    """
    os.chmod(path, mode)
    if skip_chown:
        return
    if user is not None or group is not None:
        try:
            shutil.chown(path, user=user, group=group)
        except (LookupError, PermissionError, OSError) as exc:
            raise RuntimeError(
                f"Cannot enforce {user}:{group} on {path}: {exc}. "
                "Ownership compliance is mandatory on office2. "
                "Pass --skip-chown only in tests."
            ) from exc


# ---------------------------------------------------------------------------
# Step 1 — ensure target state directory
# ---------------------------------------------------------------------------

def _ensure_target_state_dir(
    target_state_dir: Path,
    dry_run: bool,
    skip_chown: bool,
) -> None:
    """Ensure target state dir exists with correct ownership and mode.

    Convergent: ownership and mode are ALWAYS enforced — even when the
    directory already exists — so a partial prior run or a pre-existing
    directory with wrong permissions is repaired on rerun.
    """
    if target_state_dir.exists():
        _emit("INFO", f"Target state dir already exists: {target_state_dir}")
        if not dry_run:
            # Repair ownership/mode unconditionally (convergent).
            _set_permissions(
                target_state_dir,
                TARGET_STATE_DIR_MODE,
                user=TARGET_STATE_OWNER,
                group=TARGET_STATE_GROUP,
                skip_chown=skip_chown,
            )
            _emit(
                "INFO",
                f"  Enforced mode {oct(TARGET_STATE_DIR_MODE)}"
                f" owner={TARGET_STATE_OWNER}:{TARGET_STATE_GROUP} on existing dir.",
            )
        return
    if dry_run:
        _emit(
            "DRY-RUN",
            f"Would mkdir {target_state_dir}"
            f"  [mode={oct(TARGET_STATE_DIR_MODE)}"
            f" owner={TARGET_STATE_OWNER}:{TARGET_STATE_GROUP}]",
        )
        return
    target_state_dir.mkdir(parents=True, exist_ok=True)
    _set_permissions(
        target_state_dir,
        TARGET_STATE_DIR_MODE,
        user=TARGET_STATE_OWNER,
        group=TARGET_STATE_GROUP,
        skip_chown=skip_chown,
    )
    _emit("DONE", f"Created target state dir: {target_state_dir}")


# ---------------------------------------------------------------------------
# Step 2 — copy state files (atomic-before-cutover, H1)
# ---------------------------------------------------------------------------

def _files_identical(a: Path, b: Path) -> bool:
    try:
        return filecmp.cmp(str(a), str(b), shallow=False)
    except OSError:
        return False


def _union_merge_jsonl_files(src: Path, dst: Path) -> int:
    """Append source JSONL lines not already present in *dst*.

    Dedup key: full stripped text of each non-empty line.  Existing target
    lines are preserved in-place; unique source-only lines are appended at the
    end.  This preserves the append-only ledger invariant: no entry from either
    source or target is ever lost.

    Returns the count of new lines appended.
    """

    def _nonempty_lines(text: str) -> list[str]:
        return [line.strip() for line in text.splitlines() if line.strip()]

    src_lines = _nonempty_lines(src.read_text(encoding="utf-8"))
    dst_lines = _nonempty_lines(dst.read_text(encoding="utf-8"))
    dst_set = set(dst_lines)

    new_lines = [line for line in src_lines if line not in dst_set]

    if new_lines:
        with dst.open("a", encoding="utf-8") as f:
            for line in new_lines:
                f.write(line + "\n")

    return len(new_lines)


def _copy_state_files(
    source_root: Path,
    target_state_dir: Path,
    dry_run: bool,
    skip_chown: bool,
) -> list[Path]:
    """Copy in-scope state files to *target_state_dir*.

    Content copy is skipped when the target already exists and is identical
    (idempotency).  Ownership and mode are ALWAYS enforced on the target file,
    regardless of whether content was copied or skipped — even for a
    pre-existing identical file.  This makes the apply path convergent.

    Returns the list of source paths that were in scope (copied, skipped, or
    warned).
    """
    state_dir = source_root / "agents" / "state"
    handled: list[Path] = []

    if not state_dir.exists():
        _emit("INFO", f"No state dir at {state_dir}; nothing to copy.")
        return handled

    for src in sorted(state_dir.iterdir()):
        if not src.is_file():
            continue
        name = src.name
        if name not in _STATE_FILENAMES_EXACT and not name.startswith(
            _STATE_FILENAME_PREFIX
        ):
            # Not a file we own — skip silently.
            continue

        dst = target_state_dir / name

        if dst.exists():
            if _files_identical(src, dst):
                _emit("SKIP", f"State file already at target (identical): {dst}")
                # Enforce perms on pre-existing target file (convergent, always).
                if not dry_run:
                    _set_permissions(
                        dst,
                        TARGET_STATE_FILE_MODE,
                        user=TARGET_STATE_OWNER,
                        group=TARGET_STATE_GROUP,
                        skip_chown=skip_chown,
                    )
                handled.append(src)
                continue

            # Content differs — strategy is determined by file type.
            if src.suffix == ".jsonl":
                # UNION-MERGE: append-only ledger — no entry may ever be lost.
                # Append any source lines not already present in the target so
                # that both sets of entries survive in the target.
                if dry_run:
                    _emit(
                        "DRY-RUN",
                        f"Would union-merge JSONL ledger (divergent target): "
                        f"{src} → {dst}",
                        {
                            "src_size": src.stat().st_size,
                            "dst_size": dst.stat().st_size,
                        },
                    )
                else:
                    merged_count = _union_merge_jsonl_files(src, dst)
                    _emit(
                        "MERGED",
                        f"Union-merged {merged_count} new line(s) from {src} into {dst}",
                        {"new_lines_merged": merged_count},
                    )
                    _set_permissions(
                        dst,
                        TARGET_STATE_FILE_MODE,
                        user=TARGET_STATE_OWNER,
                        group=TARGET_STATE_GROUP,
                        skip_chown=skip_chown,
                    )
                handled.append(src)
                continue

            # Non-JSONL file with divergent content — not safely auto-mergeable.
            # Abort rather than silently drop entries from either side.
            raise RuntimeError(
                f"CONFLICT: target state file exists with different content and "
                f"cannot be safely auto-merged: {dst}  "
                f"(src={src.stat().st_size}B, dst={dst.stat().st_size}B). "
                f"Resolve the conflict manually, then re-run. "
                f"Source has NOT been quarantined."
            )

        if dry_run:
            _emit(
                "DRY-RUN",
                f"Would copy {src} → {dst}"
                f"  [{src.stat().st_size}B"
                f" mode={oct(TARGET_STATE_FILE_MODE)}"
                f" owner={TARGET_STATE_OWNER}:{TARGET_STATE_GROUP}]",
            )
            handled.append(src)
            continue

        shutil.copy2(str(src), str(dst))
        _set_permissions(
            dst,
            TARGET_STATE_FILE_MODE,
            user=TARGET_STATE_OWNER,
            group=TARGET_STATE_GROUP,
            skip_chown=skip_chown,
        )
        _emit("DONE", f"Copied state file: {src} → {dst}  [{dst.stat().st_size}B]")
        handled.append(src)

    return handled


# ---------------------------------------------------------------------------
# Step 3 — preserve inbox forensic logs (top-level only, no overwrite)
# ---------------------------------------------------------------------------

def _copy_inbox_logs(
    source_root: Path,
    vault_logs_dir: Path,
    dry_run: bool,
) -> int:
    """Copy top-level agents/logs/inbox-prescan-*.md files to *vault_logs_dir*.

    Only files at the direct level of agents/logs/ matching ``inbox-prescan-*.md``
    are copied.  Per-agent observation subdirs (enrichment/, felix-admin-*, …)
    are intentionally skipped — they belong to the observation-digest subsystem
    and will be handled by #659.

    Existing destination files are skipped (no overwrite — idempotent).

    Returns the count of files that were (or would be) copied.
    """
    src_logs = source_root / "agents" / "logs"
    if not src_logs.exists():
        _emit("INFO", f"No logs dir at {src_logs}; nothing to preserve.")
        return 0

    inbox_logs = sorted(src_logs.glob("inbox-prescan-*.md"))
    if not inbox_logs:
        _emit("INFO", f"No inbox-prescan-*.md files in {src_logs}; nothing to preserve.")
        return 0

    if not vault_logs_dir.exists():
        if dry_run:
            _emit("DRY-RUN", f"Would mkdir {vault_logs_dir}")
        else:
            vault_logs_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    for src_file in inbox_logs:
        dst_file = vault_logs_dir / src_file.name
        if dst_file.exists():
            _emit("SKIP", f"Inbox log already in vault: {dst_file}")
            continue
        if dry_run:
            _emit("DRY-RUN", f"Would copy inbox log: {src_file} → {dst_file}")
            copied += 1
            continue
        shutil.copy2(str(src_file), str(dst_file))
        _emit("DONE", f"Preserved inbox log: {src_file} → {dst_file}")
        copied += 1

    return copied


# ---------------------------------------------------------------------------
# Snapshot gate
# ---------------------------------------------------------------------------

def _run_snapshot_gate(snapshot_log_dir: Path | None) -> bool:
    """Return True if the Tier-2 Restic snapshot gate passes."""
    from scripts.deploy.lib.snapshot import verify_restic_recent

    kwargs: dict[str, Any] = {}
    if snapshot_log_dir is not None:
        kwargs["log_dir"] = snapshot_log_dir

    result = verify_restic_recent(**kwargs)
    if result.ok:
        _emit("INFO", f"Snapshot gate passed: {result.summary}")
    else:
        _emit(
            "ERROR",
            f"Snapshot gate FAILED: {result.summary}",
            dict(result.details),
        )
    return result.ok


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:  # noqa: C901 — linear flow, readable
    parser = argparse.ArgumentParser(
        prog="migrate-inbox-state-and-logs",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--dry-run", action="store_true")
    mode_group.add_argument("--apply", action="store_true")

    # Path overrides for testing
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--target-state-dir", type=Path, default=DEFAULT_TARGET_STATE_DIR)
    parser.add_argument("--vault-logs-dir", type=Path, default=DEFAULT_VAULT_LOGS_DIR)
    parser.add_argument(
        "--snapshot-log-dir",
        type=Path,
        default=None,
        help="Override Restic backup log dir (for testing).",
    )
    parser.add_argument(
        "--skip-snapshot-gate",
        action="store_true",
        help="Skip Restic snapshot check (for testing only — NOT safe in production).",
    )
    parser.add_argument(
        "--skip-chown",
        action="store_true",
        help=(
            "Skip chown calls entirely (for testing on dev machines where the "
            "service user/group do not exist — NOT safe in production)."
        ),
    )

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    dry_run: bool = args.dry_run
    skip_chown: bool = args.skip_chown
    source_root: Path = args.source_root
    target_state_dir: Path = args.target_state_dir
    vault_logs_dir: Path = args.vault_logs_dir

    _emit("INFO", f"Migration start  dry_run={dry_run}")
    _emit("INFO", f"  source_root      = {source_root}")
    _emit("INFO", f"  target_state_dir = {target_state_dir}")
    _emit("INFO", f"  vault_logs_dir   = {vault_logs_dir}")
    if skip_chown:
        _emit(
            "WARN",
            "--skip-chown active — TESTING ONLY, ownership enforcement skipped.",
        )

    # ── 1. Snapshot gate (Tier-2 requirement) ─────────────────────────────
    # Enforced on --apply ONLY: a --dry-run mutates nothing, so it must not
    # require a recent snapshot and must exit 0 for felix-deployer's
    # dry-run→apply gate (apply.py runs `<entrypoint> --dry-run` first and
    # aborts the whole deploy if it is non-zero).
    if dry_run:
        _emit(
            "INFO",
            "DRY-RUN: snapshot gate would be enforced on --apply (Tier-2, C-003).",
        )
    elif not args.skip_snapshot_gate:
        if not _run_snapshot_gate(args.snapshot_log_dir):
            _emit(
                "ABORT",
                "Refusing to proceed: no recent Restic snapshot (Tier-2 gate, C-003).",
            )
            return 1
    else:
        _emit(
            "WARN",
            "--skip-snapshot-gate active — TESTING ONLY, not safe for production.",
        )

    # ── 2. Ensure target state dir ────────────────────────────────────────
    # ── 3. Copy state files (atomic-before-cutover, H1) ───────────────────
    # Both steps enforce ownership/mode strictly; catch hard errors here.
    try:
        _ensure_target_state_dir(target_state_dir, dry_run, skip_chown)
        _copy_state_files(source_root, target_state_dir, dry_run, skip_chown)
    except RuntimeError as exc:
        _emit("ERROR", str(exc))
        _emit("ABORT", "Migration aborted — see ERROR above.")
        return 1

    # ── 4. Copy inbox forensic logs (top-level inbox-prescan-*.md only) ───
    # Per-agent observation subdirs are intentionally left in place (#659).
    log_count = _copy_inbox_logs(source_root, vault_logs_dir, dry_run)
    _emit(
        "INFO",
        f"Inbox logs: {log_count} file(s) "
        f"{'would be copied' if dry_run else 'copied'} to vault.",
    )

    # NOTE: /home/claude/second-brain is LEFT IN PLACE.
    # Full inventory + classify + quarantine/decommission is deferred to #659,
    # after the observation-digest subsystem writers are repointed.

    if dry_run:
        _emit("INFO", "Dry-run complete. No files were modified.")
    else:
        _emit("DONE", "Migration complete.")
    return 0


if __name__ == "__main__":  # pragma: no cover — use python3 -m or direct call
    sys.exit(main())
