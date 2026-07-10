"""Completion-assertion ledger — record helper + CLI (#683, mission
felix-truthful-reporting-01KX6MN5, WP03).

A **completion-assertion** is a deterministic, append-only record written by
an artifact-creation helper on the moment it successfully creates something on
an agent's behalf (e.g. ``scripts/vikunja/create_task.py`` writes one after a
successful Vikunja task create). It grounds a later completion claim
("created 7 reminder tasks") in specific artifact ids that the verifier
(``scripts.trust.assertion_verifier``) can independently check for existence.

Contract (mirrors the #706 alert-bus ledger in
``scripts/common/alert_bus/ledger.py``):

- **Best-effort + fail-safe.** :func:`record_assertion` catches every error and
  returns ``False`` on failure — a ledger-write problem must NEVER break the
  caller (NFR-001). It never raises.
- **Append-only JSONL, `fcntl.LOCK_EX`.** One JSON object per line, written
  under an exclusive lock (mirrors ``scripts/common/state_log.py`` and the
  #706 ledger pattern) so concurrent writers cannot tear a record.
  ``os.open(..., O_WRONLY | O_CREAT | O_APPEND, 0o600)``.
- **Date-partitioned, env-overridable home.** Files are named
  ``<YYYY-MM-DD>.jsonl`` under :func:`assertions_dir` (``FELIX_TRUST_ASSERTIONS_DIR``,
  default ``/data/services/trust/assertions/``). Tests point the env var at a
  tmpdir — no office2 calls.
- **Multi-artifact.** ``artifact_ids`` is a **list**, preserved verbatim — the
  motivating case created 7 Vikunja reminder tasks from one request; each id
  is verified independently by the verifier.
- **No LLM.** This module is pure record-keeping — no model calls, no judgment.

Schema: ``CompletionAssertion`` in
``kitty-specs/felix-truthful-reporting-01KX6MN5/data-model.md`` / contract C4
in ``contracts/detector-cli.md``.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = [
    "ASSERTIONS_DIR_ENV",
    "DEFAULT_ASSERTIONS_DIR",
    "assertions_dir",
    "build_record",
    "record_assertion",
    "main",
]

# Default ledger location on office2. Overridable via env (tests point it at a
# tmpdir; a different host can relocate it).
DEFAULT_ASSERTIONS_DIR = "/data/services/trust/assertions/"
ASSERTIONS_DIR_ENV = "FELIX_TRUST_ASSERTIONS_DIR"


def assertions_dir() -> Path:
    """Resolve the assertions directory (``FELIX_TRUST_ASSERTIONS_DIR`` or default)."""
    override = os.environ.get(ASSERTIONS_DIR_ENV, "").strip()
    return Path(override) if override else Path(DEFAULT_ASSERTIONS_DIR)


def _assertion_path(base: Path, day_utc: str) -> Path:
    return base / f"{day_utc}.jsonl"


def build_record(
    agent: str,
    artifact_kind: str,
    artifact_ids: list[str],
    claim: str,
    *,
    request_summary: str | None = None,
    request_ref: str | None = None,
) -> dict[str, Any]:
    """Build the JSON-serializable ``CompletionAssertion`` record."""
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "agent": agent,
        "request_summary": request_summary,
        "request_ref": request_ref,
        "artifact_kind": artifact_kind,
        "artifact_ids": list(artifact_ids),
        "claim": claim,
    }


def _append_line(path: Path, line: str) -> None:
    """Append *line* to *path* under an exclusive lock (torn-write-safe)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.write(fd, line.encode("utf-8"))
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def record_assertion(
    agent: str,
    artifact_kind: str,
    artifact_ids: list[str],
    claim: str,
    request_ref: str | None = None,
    *,
    request_summary: str | None = None,
) -> bool:
    """Append one completion-assertion record; never raises.

    Best-effort / fail-safe (NFR-001): on any failure (unwritable directory,
    serialization error, locking failure, ...) this returns ``False`` without
    raising, so a ledger problem never breaks the caller (e.g. Vikunja task
    creation). Returns ``True`` only on a successful write.
    """
    try:
        record = build_record(
            agent,
            artifact_kind,
            artifact_ids,
            claim,
            request_summary=request_summary,
            request_ref=request_ref,
        )
        base = assertions_dir()
        day_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        line = json.dumps(record, ensure_ascii=False) + "\n"
        _append_line(_assertion_path(base, day_utc), line)
    except Exception:  # noqa: BLE001 - fail-safe: must never raise into the caller
        return False
    return True


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scripts.trust.completion_assertion",
        description=(
            "Record a completion-assertion (manual/bypass path; the primary "
            "path is the artifact-creation helper auto-emitting on success)."
        ),
    )
    parser.add_argument("--agent", required=True, help="asserting/creating agent")
    parser.add_argument("--artifact-kind", required=True, help="vikunja_task | calendar_event | vault_note | other")
    parser.add_argument(
        "--artifact-id",
        dest="artifact_ids",
        action="append",
        default=[],
        help="artifact id (repeatable for multi-artifact assertions)",
    )
    parser.add_argument("--claim", required=True, help="the completion claim / summary")
    parser.add_argument("--request-ref", default=None, help="optional correlation ref")
    parser.add_argument("--request-summary", default=None, help="optional short paraphrase of the request")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint. Returns 0 on success, 1 on any handled failure.

    Guards its entire body so it never raises, mirroring
    :func:`record_assertion`'s fail-safe discipline.
    """
    try:
        args = _build_parser().parse_args(argv)
        ok = record_assertion(
            agent=args.agent,
            artifact_kind=args.artifact_kind,
            artifact_ids=args.artifact_ids,
            claim=args.claim,
            request_ref=args.request_ref,
            request_summary=args.request_summary,
        )
        if ok:
            print(f"RECORDED assertion agent={args.agent} artifact_kind={args.artifact_kind} "
                  f"artifact_ids={args.artifact_ids}")
            return 0
        print("ERROR: failed to record completion-assertion", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary: report, never raise
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
