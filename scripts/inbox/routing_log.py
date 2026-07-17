"""Routing log helper module for felix-admin-capture inbox dedup.

The routing log is the load-bearing dedup substrate for the inbox-capture
agent (per #185). It lives at /data/services/openclaw/state/inbox-routing.jsonl
as an append-only JSONL file. Each line records one successful route
(filename, GitHub issue#, Vikunja task ID, routed_at, note excerpt).

See kitty-specs/inbox-capture-dedup-and-parser-hardening-01KREZJ8/contracts/
routing-log.md for the authoritative contract.
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


DEFAULT_ROUTING_LOG_PATH = Path("/data/services/openclaw/state/inbox-routing.jsonl")

# The permissive ``kind`` vocabulary. The field stays a ``str`` (old on-disk
# rows and forward-compat callers are never rejected), but these are the values
# the current writers emit:
#   - ``issue_task``  — original GitHub-issue / Vikunja-task route (pre-#737).
#   - ``calendar``    — Google Calendar event (#737); destination = event id.
#   - ``someday``     — Someday/Maybe Vikunja task; destination = task id.
#   - ``journal``     — appended journal section; destination = file path.
#   - ``vikunja_task`` — tasker-delegated Vikunja task; destination = task id.
#   - ``github_issue`` — filed GitHub issue; destination = issue number.
#   - ``empty``       — verified-empty note, no route; destination = "".
KNOWN_KINDS: frozenset[str] = frozenset(
    {
        "issue_task",
        "calendar",
        "someday",
        "journal",
        "vikunja_task",
        "github_issue",
        "empty",
    }
)


def block_hash(block_text: str) -> str:
    """Return a stable content hash for one routed block.

    The text is normalized (leading/trailing whitespace stripped) before
    hashing so an unchanged block re-hashes identically across cron ticks —
    the property the per-block idempotency key (D10) relies on. Returns the
    sha256 hexdigest of the UTF-8 encoded normalized text.
    """
    normalized = (block_text or "").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RoutingEntry:
    """One row in the routing log. Append-only; values never mutate after write.

    ``kind`` records the route class (``issue_task`` for the original
    GitHub-issue / Vikunja-task routes, ``calendar`` for Google Calendar
    events, etc.) and ``destination`` carries a kind-specific identifier
    (e.g. a calendar ``event_id``). Both were added in #737 so calendar
    routes — which have neither a GitHub issue nor a Vikunja task — can be
    represented. Old on-disk rows predate these fields; the reader only keys
    on ``filename`` so their absence is harmless.

    ``block_index`` / ``block_hash`` (D10, this mission) extend the key from
    filename alone to (``filename``, ``block_index``, ``block_hash``) so one
    routed block in a multi-block note never masks another. Both default to
    ``None``; legacy rows (and note-level routes that have no meaningful block)
    omit them and fall back to filename-only dedup.
    """

    filename: str
    issue_number: Optional[int]
    vikunja_task_id: Optional[int]
    routed_at: str  # ISO-8601 UTC, with trailing Z
    note_excerpt: str = ""
    kind: str = "issue_task"
    destination: str = ""
    block_index: Optional[int] = None
    block_hash: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class RoutingLogReader:
    """Read-only view of the routing log.

    Reads the file once on first call to `routed_filenames()` and caches the
    resulting set. Safe to instantiate and reuse across a single cron tick.
    """

    def __init__(self, path: Optional[Path] = None):
        # Resolve default at call time (not at function-definition time) so
        # tests can monkeypatch `routing_log.DEFAULT_ROUTING_LOG_PATH`.
        if path is None:
            import sys as _sys
            path = _sys.modules[__name__].DEFAULT_ROUTING_LOG_PATH
        self._path = Path(path)
        self._records: Optional[list[dict]] = None
        self._cache: Optional[set[str]] = None

    def _read_records(self) -> list[dict]:
        """Parse the log once into a list of valid entry dicts (read-once).

        A "valid" record is any JSON object with a non-empty string
        ``filename``. Malformed lines and missing/invalid-filename lines are
        skipped with a warning to stderr (unchanged behavior). The parsed
        records feed both `routed_filenames()` and `has_block()`, so the file
        is read at most once per reader instance.
        """
        if self._records is not None:
            return self._records
        records: list[dict] = []
        if not self._path.exists():
            self._records = records
            return records
        try:
            with self._path.open("r", encoding="utf-8") as fh:
                for lineno, raw in enumerate(fh, start=1):
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        entry = json.loads(raw)
                    except json.JSONDecodeError as exc:
                        print(
                            f"[routing_log] line {lineno}: malformed JSON, "
                            f"skipping: {exc}",
                            file=sys.stderr,
                        )
                        continue
                    name = entry.get("filename") if isinstance(entry, dict) else None
                    if not isinstance(name, str) or not name:
                        print(
                            f"[routing_log] line {lineno}: missing/invalid "
                            "filename, skipping",
                            file=sys.stderr,
                        )
                        continue
                    records.append(entry)
        except OSError as exc:
            print(
                f"[routing_log] could not read {self._path}: {exc}",
                file=sys.stderr,
            )
        self._records = records
        return records

    def routed_filenames(self) -> set[str]:
        """Return the set of filenames present in the log.

        - Missing file → empty set (fail-safe).
        - Malformed lines → skipped with a warning to stderr; valid lines
          still returned.
        - Result is cached for the lifetime of this reader instance.
        """
        if self._cache is not None:
            return self._cache
        names = {rec["filename"] for rec in self._read_records()}
        self._cache = names
        return names

    def has(self, filename: str) -> bool:
        """True if `filename` appears in any routing-log entry.

        Note-level check retained for the health rail: any routing-log entry
        for ``filename`` (block-keyed or legacy) satisfies it.
        """
        return filename in self.routed_filenames()

    def has_block(
        self, filename: str, block_index: int, block_hash: str
    ) -> bool:
        """True if this specific block has already been routed.

        Matches when a logged entry carries the same ``filename``,
        ``block_index``, and ``block_hash`` — the D10 per-block idempotency
        key. **Legacy fallback**: a matching-``filename`` entry that carries no
        ``block_index`` (a pre-WP01 row, e.g. the #737 calendar dedup) is
        treated as satisfying the filename, so legacy rows still dedup and
        never force a double-route.
        """
        for rec in self._read_records():
            if rec.get("filename") != filename:
                continue
            rec_index = rec.get("block_index")
            if rec_index is None:
                # Legacy / note-level row: filename match is sufficient.
                return True
            if rec_index == block_index and rec.get("block_hash") == block_hash:
                return True
        return False


class RoutingLogWriter:
    """Append-only writer for the routing log."""

    def __init__(self, path: Optional[Path] = None):
        if path is None:
            import sys as _sys
            path = _sys.modules[__name__].DEFAULT_ROUTING_LOG_PATH
        self._path = Path(path)

    def append(
        self,
        filename: str,
        issue_number: Optional[int] = None,
        vikunja_task_id: Optional[int] = None,
        note_excerpt: str = "",
        kind: str = "issue_task",
        destination: str = "",
        block_index: Optional[int] = None,
        block_hash: Optional[str] = None,
    ) -> RoutingEntry:
        """Append one entry. Creates the parent directory if absent.

        `routed_at` is set automatically to UTC now (ISO-8601 with trailing Z).
        `note_excerpt` is truncated to 120 characters per the contract.
        `kind`/`destination` (#737) record the route class and a kind-specific
        id (e.g. a calendar ``event_id``); ``issue_number`` defaults to ``None``
        so calendar routes — which have no GitHub issue — need not supply it.
        `block_index`/`block_hash` (D10) record the per-block idempotency key;
        both default to ``None`` for note-level / legacy call sites.
        """
        entry = RoutingEntry(
            filename=filename,
            issue_number=issue_number,
            vikunja_task_id=vikunja_task_id,
            routed_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            note_excerpt=(note_excerpt or "")[:120],
            kind=kind,
            destination=destination,
            block_index=block_index,
            block_hash=block_hash,
        )
        self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
        new_file = not self._path.exists()
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry.to_dict()) + "\n")
        # FR-012/SC-9: state files must be group-readable (0640), not umask-dependent.
        # Only enforce on first create so we don't fight an operator-set mode on an
        # existing file; best-effort (a chmod failure must not break routing).
        if new_file:
            try:
                self._path.chmod(0o640)
            except OSError:
                pass
        return entry
