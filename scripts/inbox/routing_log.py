"""Routing log helper module for felix-admin-capture inbox dedup.

The routing log is the load-bearing dedup substrate for the inbox-capture
agent (per #185). It lives at /data/services/openclaw/state/inbox-routing.jsonl
as an append-only JSONL file. Each line records one successful route
(filename, GitHub issue#, Vikunja task ID, routed_at, note excerpt).

See kitty-specs/inbox-capture-dedup-and-parser-hardening-01KREZJ8/contracts/
routing-log.md for the authoritative contract.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


DEFAULT_ROUTING_LOG_PATH = Path("/data/services/openclaw/state/inbox-routing.jsonl")


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
    """

    filename: str
    issue_number: Optional[int]
    vikunja_task_id: Optional[int]
    routed_at: str  # ISO-8601 UTC, with trailing Z
    note_excerpt: str = ""
    kind: str = "issue_task"
    destination: str = ""

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
        self._cache: Optional[set[str]] = None

    def routed_filenames(self) -> set[str]:
        """Return the set of filenames present in the log.

        - Missing file → empty set (fail-safe).
        - Malformed lines → skipped with a warning to stderr; valid lines
          still returned.
        - Result is cached for the lifetime of this reader instance.
        """
        if self._cache is not None:
            return self._cache
        names: set[str] = set()
        if not self._path.exists():
            self._cache = names
            return names
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
                    name = entry.get("filename")
                    if not isinstance(name, str) or not name:
                        print(
                            f"[routing_log] line {lineno}: missing/invalid "
                            "filename, skipping",
                            file=sys.stderr,
                        )
                        continue
                    names.add(name)
        except OSError as exc:
            print(
                f"[routing_log] could not read {self._path}: {exc}",
                file=sys.stderr,
            )
        self._cache = names
        return names

    def has(self, filename: str) -> bool:
        """True if `filename` appears in any routing-log entry."""
        return filename in self.routed_filenames()


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
    ) -> RoutingEntry:
        """Append one entry. Creates the parent directory if absent.

        `routed_at` is set automatically to UTC now (ISO-8601 with trailing Z).
        `note_excerpt` is truncated to 120 characters per the contract.
        `kind`/`destination` (#737) record the route class and a kind-specific
        id (e.g. a calendar ``event_id``); ``issue_number`` defaults to ``None``
        so calendar routes — which have no GitHub issue — need not supply it.
        """
        entry = RoutingEntry(
            filename=filename,
            issue_number=issue_number,
            vikunja_task_id=vikunja_task_id,
            routed_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            note_excerpt=(note_excerpt or "")[:120],
            kind=kind,
            destination=destination,
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
