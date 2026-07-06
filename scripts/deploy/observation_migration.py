"""Phase-1 (non-destructive) observation-log migration logic.

Mission: observation-digest-repoint-01KWS2E2 (fast-follow of #656 → #659)

This module holds ALL logic for migrating the per-agent observation runtime
logs out of the stray tree (``/home/claude/second-brain``) into the vault
(``/home/kgale/second-brain/agents/logs``).  The hyphenated executable
``migrate-observation-logs.py`` is a thin ``sys.path``-shim wrapper that calls
:func:`main` here (Codex Major 4: hyphenated filenames are not importable, so
the logic lives in this underscore module and is unit-tested via ``import``).

Phase 1 is **strictly non-destructive** — it copies / union-merges only.  No
deletion, ``rm``, ``rmtree``, or quarantine happens anywhere in this module;
the destructive decommission is a separate Phase-2 entrypoint (WP03 / #659).

Safety / constraint highlights
------------------------------
* **Atomic union-merge (NFR-005)** — :func:`union_merge_jsonl` builds the merged
  content, writes it to a temp file in the destination dir, ``fsync``s, then
  ``os.replace``s it onto the destination.  A concurrent append can never see a
  partial file, and the merge is crash-safe.
* **Bounded traversal (C-008)** — :func:`iter_source_log_files` globs ONLY
  ``source_root/agents/logs/*/*.jsonl``.  It never ``rglob``/``os.walk``/
  ``iterdir``s the tree root, never touches top-level ``.md`` files, and never
  walks toward a ``_private`` path.  Emitted results contain only relative
  ``<agent>/<file>.jsonl`` identifiers — never a path outside ``agents/logs``.
* **Vault writability post-check (C-011)** — :func:`check_vault_writable`
  appends+removes a temp ``.jsonl`` under the target and raises a clear error
  if the deploying service user cannot write there.

CLI shape (see contracts/migrate-observation-logs-cli.md)
---------------------------------------------------------
  --dry-run   (default on)  Print the JSON plan to stdout; mutate nothing; exit 0.
  --apply                    Snapshot gate → union-merge → vault writability check.
  --source-root DIR          Override the stray-tree root.
  --vault-logs-dir DIR       Override the migration target.
  --snapshot-log-dir DIR     Override the Restic backup log dir (testing).
  --skip-snapshot-gate       Skip the Restic gate (testing only — unsafe in prod).

stdout carries exactly one JSON object (the plan in dry-run, the result summary
on apply).  Structured progress / errors go to stderr via :func:`_emit`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Production defaults (real office2 paths)
# ---------------------------------------------------------------------------
DEFAULT_SOURCE_ROOT = Path("/home/claude/second-brain")
DEFAULT_VAULT_LOGS_DIR = Path("/home/kgale/second-brain/agents/logs")

# Only per-agent JSONL directly under agents/logs/<agent>/ is in scope.
_LOGS_GLOB = "*/*.jsonl"
_PRIVATE_PART = "_private"


# ---------------------------------------------------------------------------
# Output — progress/errors to stderr (stdout is reserved for the JSON object)
# ---------------------------------------------------------------------------

def _emit(label: str, msg: str, details: dict[str, Any] | None = None) -> None:
    sys.stderr.write(f"{label}: {msg}\n")
    if details:
        sys.stderr.write(json.dumps(details, sort_keys=True) + "\n")
    sys.stderr.flush()


# ---------------------------------------------------------------------------
# T004 — atomic union-merge + bounded source discovery
# ---------------------------------------------------------------------------

def union_merge_jsonl(src_file: Path, dst_file: Path) -> int:
    """Union-merge JSONL ``src_file`` into ``dst_file`` atomically.

    The merged content is the union of the non-empty lines of the existing
    destination followed by any source-only lines (existing destination order
    is preserved; identical lines are deduplicated).  The result is written to
    a temp file in the destination directory, ``fsync``ed, then ``os.replace``d
    onto ``dst_file`` so no reader/appender can ever observe a partial file
    (NFR-005).  Idempotent: re-running with the same inputs rewrites identical
    content and reports zero new lines.

    Returns the count of source-only lines added to the destination.
    """
    src_file = Path(src_file)
    dst_file = Path(dst_file)

    def _nonempty_lines(path: Path) -> list[str]:
        if not path.exists():
            return []
        return [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    dst_lines = _nonempty_lines(dst_file)
    src_lines = _nonempty_lines(src_file)

    seen = set(dst_lines)
    merged = list(dst_lines)
    new_count = 0
    for line in src_lines:
        if line not in seen:
            seen.add(line)
            merged.append(line)
            new_count += 1

    content = "".join(line + "\n" for line in merged)

    dst_dir = dst_file.parent
    dst_dir.mkdir(parents=True, exist_ok=True)

    # Temp file in the SAME directory as the destination so os.replace is an
    # atomic same-filesystem rename.
    fd, tmp_name = tempfile.mkstemp(
        prefix=dst_file.name + ".", suffix=".tmp", dir=str(dst_dir)
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, dst_file)
    except BaseException:
        # Never leave a partial temp file behind on failure.
        if tmp_path.exists():
            tmp_path.unlink()
        raise

    return new_count


def iter_source_log_files(source_root: Path) -> list[Path]:
    """Return the in-scope per-agent JSONL logs under ``source_root``.

    Globs ONLY ``source_root/agents/logs/*/*.jsonl`` (C-008).  This deliberately
    does not ``rglob``/``os.walk``/``iterdir`` the tree root, never matches
    top-level ``.md`` files, and never descends into non-``agents/logs``
    directories — so it can never walk toward a ``_private`` path.  A defensive
    filter additionally drops any path containing a ``_private`` component.
    """
    source_root = Path(source_root)
    logs_root = source_root / "agents" / "logs"

    files: list[Path] = []
    # Path.glob on a non-existent directory yields nothing (no error).
    for path in sorted(logs_root.glob(_LOGS_GLOB)):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(source_root).parts
        if any(part == _PRIVATE_PART for part in rel_parts):
            continue  # defence in depth — should never match under agents/logs
        files.append(path)
    return files


# ---------------------------------------------------------------------------
# T005 — migrate flow + vault writability
# ---------------------------------------------------------------------------

def migrate_logs(
    source_root: Path,
    vault_logs_dir: Path,
    dry_run: bool,
) -> dict[str, Any]:
    """Union-merge each per-agent JSONL log from the stray tree into the vault.

    For every ``agents/logs/<agent>/<date>.jsonl`` under ``source_root`` this
    ensures ``vault_logs_dir/<agent>/`` exists and atomically union-merges the
    source file into ``vault_logs_dir/<agent>/<date>.jsonl``.  In dry-run mode
    the plan is collected and returned but nothing is mutated.

    Returns a JSON-serializable ``{"migrated": [...], "plan_only": bool}``.
    Each ``migrated`` entry is a relative ``<agent>/<file>.jsonl`` identifier —
    NEVER an absolute path and NEVER a path outside ``agents/logs/*``.
    """
    source_root = Path(source_root)
    vault_logs_dir = Path(vault_logs_dir)

    migrated: list[str] = []
    for src in iter_source_log_files(source_root):
        agent = src.parent.name
        entry = f"{agent}/{src.name}"
        migrated.append(entry)

        if dry_run:
            _emit("DRY-RUN", f"Would union-merge {entry} → {vault_logs_dir}/{entry}")
            continue

        agent_dir = vault_logs_dir / agent
        agent_dir.mkdir(parents=True, exist_ok=True)
        dst = agent_dir / src.name
        new_lines = union_merge_jsonl(src, dst)
        _emit(
            "MERGED",
            f"{entry}: {new_lines} new line(s)",
            {"new_lines_merged": new_lines},
        )

    return {"migrated": migrated, "plan_only": bool(dry_run)}


def check_vault_writable(vault_logs_dir: Path) -> None:
    """Confirm the current user can append+remove a temp JSONL under the target.

    Raises ``RuntimeError`` with a clear message if the vault log dir cannot be
    created or is not writable by the deploying service user (C-011).
    """
    vault_logs_dir = Path(vault_logs_dir)
    try:
        vault_logs_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(
            f"Vault log dir is not creatable by the current user: "
            f"{vault_logs_dir}: {exc}"
        ) from exc

    try:
        fd, probe_name = tempfile.mkstemp(
            prefix=".writability-probe.", suffix=".jsonl", dir=str(vault_logs_dir)
        )
    except OSError as exc:
        raise RuntimeError(
            f"Vault log dir is not writable by the current user: "
            f"{vault_logs_dir}: {exc}"
        ) from exc

    probe_path = Path(probe_name)
    try:
        with os.fdopen(fd, "a", encoding="utf-8") as fh:
            fh.write("{}\n")
            fh.flush()
    except OSError as exc:
        probe_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"Vault log dir is not writable by the current user: "
            f"{vault_logs_dir}: {exc}"
        ) from exc
    finally:
        probe_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Snapshot gate (Tier-2) — enforced on --apply only
# ---------------------------------------------------------------------------

def run_snapshot_gate(snapshot_log_dir: Path | None = None) -> bool:
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
# Entry point (argparse lives here so the hyphenated wrapper stays thin)
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="migrate-observation-logs",
        description="Phase-1 (non-destructive) observation-log migration.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # --dry-run is the default; --apply flips it. Kept as an explicit flag for
    # documentation and parity with the sibling #656 migrator.
    parser.add_argument("--dry-run", action="store_true", help="Print plan; no mutation (default).")
    parser.add_argument("--apply", action="store_true", help="Execute the migration.")
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
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
        help="Skip the Restic snapshot check (testing only — NOT safe in production).",
    )

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    # --apply overrides the dry-run default.
    dry_run: bool = not args.apply
    source_root: Path = args.source_root
    vault_logs_dir: Path = args.vault_logs_dir

    _emit("INFO", f"Observation-log migration start  dry_run={dry_run}")
    _emit("INFO", f"  source_root    = {source_root}")
    _emit("INFO", f"  vault_logs_dir = {vault_logs_dir}")

    # ── Snapshot gate (Tier-2) — apply only. A dry-run mutates nothing, so it
    # must not require a recent snapshot and must exit 0 for felix-deployer's
    # dry-run→apply gate.
    if dry_run:
        _emit("INFO", "DRY-RUN: snapshot gate would be enforced on --apply (Tier-2).")
    elif not args.skip_snapshot_gate:
        if not run_snapshot_gate(args.snapshot_log_dir):
            _emit("ABORT", "Refusing to proceed: no recent Restic snapshot (Tier-2 gate).")
            return 1
    else:
        _emit("WARN", "--skip-snapshot-gate active — TESTING ONLY, not safe for production.")

    try:
        result = migrate_logs(source_root, vault_logs_dir, dry_run=dry_run)
        if not dry_run:
            check_vault_writable(vault_logs_dir)
    except (RuntimeError, OSError) as exc:
        _emit("ERROR", str(exc))
        _emit("ABORT", "Migration aborted — see ERROR above.")
        return 1

    # Exactly one JSON object to stdout (the plan in dry-run; the result on apply).
    sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
    sys.stdout.flush()

    if dry_run:
        _emit("INFO", "Dry-run complete. No files were modified.")
    else:
        _emit("DONE", "Observation-log migration complete.")
    return 0


if __name__ == "__main__":  # pragma: no cover — use python3 -m or the wrapper
    sys.exit(main())
