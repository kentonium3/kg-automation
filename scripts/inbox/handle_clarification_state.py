#!/usr/bin/env python3
"""Manage felix-admin-capture's pending calendar clarification state.

Three subcommands:

  add    Append a PendingClarification to the state file.
  sweep  Delete entries with `created_at` >= 8h old (relative to now UTC).
         Safe on absent state file (exit 0, no error).
  match  Find the most-recent PendingClarification whose
         `partial_payload.title` substring appears (case-insensitive) in
         `--reply-content`. Prints the matched entry as JSON, or `null`
         if no match. Does NOT delete the entry.

State file (default): `/data/services/openclaw/state/pending-calendar-clarifications.json`
Layout: JSON array of PendingClarification objects:
    {"note_filename": str, "partial_payload": dict, "created_at": ISO 8601 Z}

Invocation form (MANDATORY per NFR-004 / [[feedback_helper_m_invocation_form]]):
    python3 -m scripts.inbox.handle_clarification_state add ...
    python3 -m scripts.inbox.handle_clarification_state sweep
    python3 -m scripts.inbox.handle_clarification_state match ...

Exit codes:
    0 = success
    1 = validation error (e.g. invalid --partial-payload JSON)
    2 = runtime error (reserved; not currently emitted)

Atomic write: write-temp + os.replace in the state file's parent directory.
Mirrors the pattern in `scripts/inbox/inject_parse_error_marker.py`.

8h aging semantic (#780, C-006): entries with `now - created_at >= 8h` are
removed. The boundary is inclusive of 8h exactly. This single `SWEEP_MAX_AGE`
governs the **whole** clarification lifecycle — both the #780 all-day fallback
trigger (an eligible aged-out record) and the delete-and-release / re-ask aging
for ineligible records. Reduced from the original 24h (operator decision
2026-07-18: 24h is too long to sit on an open-ended calendar question).
Documented here so callers don't need to read tests to confirm the semantic.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

STATE_PATH_DEFAULT = Path("/data/services/openclaw/state/pending-calendar-clarifications.json")

SWEEP_MAX_AGE = timedelta(hours=8)


# --------------------------------------------------------------------------
# state I/O
# --------------------------------------------------------------------------


def load_state(path: Path) -> list:
    """Return the list of PendingClarification entries; `[]` if file absent."""
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return []
    data = json.loads(raw)
    if not isinstance(data, list):  # pragma: no cover - defensive
        raise ValueError(
            f"state file is not a JSON array: {path}"
        )
    return data


def save_state(path: Path, entries: list) -> None:
    """Atomically rewrite the state file with `entries`.

    Creates the parent directory if absent. Writes to a tempfile in the
    target directory then `os.replace`s it into place.
    """
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    payload = json.dumps(entries, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        # FR-012/SC-9: state files must be group-readable (0640), not the 0600
        # that mkstemp creates (and os.replace preserves). Best-effort.
        try:
            os.chmod(tmp_name, 0o640)
        except OSError:  # pragma: no cover - best-effort
            pass
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:  # pragma: no cover - cleanup best-effort
            pass
        raise


# --------------------------------------------------------------------------
# subcommands
# --------------------------------------------------------------------------


def subcommand_add(
    path: Path, note_filename: str, partial_payload_json: str, now_utc: datetime
) -> int:
    """Append one PendingClarification entry to the state file."""
    try:
        payload = json.loads(partial_payload_json)
    except json.JSONDecodeError as exc:
        print(
            json.dumps({"error": "invalid_payload", "detail": str(exc)}),
            file=sys.stderr,
        )
        return 1

    entries = load_state(path)
    entries.append(
        {
            "note_filename": note_filename,
            "partial_payload": payload,
            "created_at": _iso_z(now_utc),
        }
    )
    save_state(path, entries)
    print(f"added={note_filename}")
    return 0


def subcommand_sweep(path: Path, now_utc: datetime) -> int:
    """Remove entries with `created_at` >= 8h old. Safe on absent file."""
    if not path.exists():
        print("removed=0")
        return 0
    entries = load_state(path)
    if not entries:
        print("removed=0")
        return 0
    kept: list = []
    removed = 0
    for entry in entries:
        created_raw = entry.get("created_at")
        if not _is_aged_out(created_raw, now_utc):
            kept.append(entry)
        else:
            removed += 1
    if removed:
        save_state(path, kept)
    print(f"removed={removed}")
    return 0


def subcommand_remove(path: Path, note_filename: str) -> int:
    """Remove all pending entries for a resolved note (#763, Directive 6).

    Deletes every entry whose ``note_filename`` matches ``note_filename`` by
    basename. The calendar agent calls this once a clarification is resolved,
    instead of hand-rolling a JSON rewrite of the store (which could drop or
    malform a surviving entry). Deterministic and atomic (``save_state`` RMW),
    idempotent (a filename with no entry prints ``removed=0``, no error),
    basename-normalized (a path-form key still matches the stored basename), and
    safe on an absent file.
    """
    target = os.path.basename(note_filename)
    if not path.exists():
        print("removed=0")
        return 0
    entries = load_state(path)
    kept = [
        e
        for e in entries
        if os.path.basename(str(e.get("note_filename", ""))) != target
    ]
    removed = len(entries) - len(kept)
    if removed:
        save_state(path, kept)
    print(f"removed={removed}")
    return 0


def pending_filenames(path: Path, now_utc: datetime) -> set[str]:
    """Return the set of note **basenames** with a live pending-clarification entry.

    "Live" == a well-formed ``created_at`` in the past and within
    :data:`SWEEP_MAX_AGE`. This is the WITHHOLD consumer (``prescan`` drops these
    notes from the tick), so it must fail **open**: an entry with a missing,
    non-string, unparseable, or future ``created_at`` is treated as NOT live so
    the note is *released*, never stranded — the opposite doubt-direction from
    ``sweep``'s :func:`_is_aged_out` ("keep on doubt"). See :func:`_is_live`.
    Because release is decided here at read time (not by the physical sweep), a
    note is guaranteed to re-enter the scan once its entry ages out, bounding the
    re-ask loop to once per window (#740).

    Filenames are normalized to their basename so a path-form and a basename-form
    key both match the inbox note's ``Path.name`` (the deterministic contract is
    a basename — ``classify_content`` emits ``path.name`` — but this is defensive
    against the agent ever passing a path). Deduped, so accumulated duplicate
    entries for the same note collapse.
    """
    out: set[str] = set()
    for entry in load_state(path):
        name = entry.get("note_filename")
        if not isinstance(name, str) or not name:
            continue
        if _is_live(entry.get("created_at"), now_utc):
            out.add(os.path.basename(name))
    return out


def subcommand_pending(path: Path, note_filename: str, now_utc: datetime) -> int:
    """Print ``pending=true``/``pending=false`` for one note filename (#740).

    True iff a live (non-aged-out) PendingClarification entry exists for
    ``note_filename``. Gives the capture agent the deterministic "is this note
    already awaiting Kent?" check its ``AGENTS.md`` re-dispatch rule needs but
    previously lacked; ``prescan.py`` uses :func:`pending_filenames` directly to
    filter such notes out of the tick before the agent ever sees them.
    """
    is_pending = note_filename in pending_filenames(path, now_utc)
    print(f"pending={'true' if is_pending else 'false'}")
    return 0


def subcommand_match(path: Path, reply_content: str) -> int:
    """Print the most-recent matching entry as JSON, or `null`.

    Heuristic: case-insensitive token match. The title is tokenized
    (alphanumeric words, lowercased) and stripped of stopwords; the entry
    matches if at least one of the remaining significant tokens appears as
    a substring of the lowercased reply. This handles natural
    rephrasings — e.g. title "Meet with Rob" matches reply
    "3pm works for the rob meeting" via the token "rob".
    """
    entries = load_state(path)
    haystack = reply_content.lower()
    matches: list = []
    for entry in entries:
        title = (entry.get("partial_payload") or {}).get("title")
        if not isinstance(title, str) or not title:
            continue
        tokens = _significant_tokens(title)
        if not tokens:
            continue
        if any(tok in haystack for tok in tokens):
            matches.append(entry)
    if not matches:
        print("null")
        return 0
    # Most recent by `created_at` (ISO Z strings sort chronologically).
    matches.sort(key=lambda e: e.get("created_at", ""), reverse=True)
    print(json.dumps(matches[0]))
    return 0


# Common English stopwords likely to appear in calendar event titles.
# Kept intentionally small; the goal is to drop noise words that would
# false-positive across unrelated replies, not to do full NLP.
_STOPWORDS = frozenset(
    {
        "a", "an", "and", "at", "by", "for", "from", "in", "of", "on",
        "or", "the", "to", "with",
    }
)


def _significant_tokens(title: str) -> list[str]:
    """Return lowercased alphanumeric tokens with stopwords removed."""
    tokens = re.findall(r"[a-z0-9]+", title.lower())
    return [t for t in tokens if t not in _STOPWORDS]


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _iso_z(dt: datetime) -> str:
    """Format `dt` as ISO 8601 with `Z` suffix (UTC), second-precision."""
    return dt.astimezone(timezone.utc).replace(microsecond=0).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _parse_iso_z(value: str) -> datetime:
    """Parse the `Z`-suffixed UTC ISO 8601 strings the helper writes.

    Accepts both `...Z` and `...+00:00` forms (the latter is what
    `datetime.isoformat()` emits for UTC).
    """
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _is_aged_out(created_raw: object, now_utc: datetime) -> bool:
    """True iff `created_raw` is a valid timestamp >= SWEEP_MAX_AGE old."""
    if not isinstance(created_raw, str):
        return False
    try:
        created = _parse_iso_z(created_raw)
    except ValueError:
        return False
    return (now_utc - created) >= SWEEP_MAX_AGE


def _is_live(created_raw: object, now_utc: datetime) -> bool:
    """True iff `created_raw` is a well-formed, non-future, within-window stamp.

    This is the WITHHOLD predicate (see :func:`pending_filenames`) and must fail
    **open** — the opposite doubt-direction from :func:`_is_aged_out`. A missing,
    non-string, unparseable, or FUTURE `created_at` returns ``False`` (not live →
    do not withhold → release the note), so a bad timestamp can never strand a
    note indefinitely (the #746/D9 silent-loss class). "Live" is strictly a
    non-negative age below :data:`SWEEP_MAX_AGE`; anything else releases.

    Note `_is_live` and `_is_aged_out` are deliberately NOT complements: a future
    stamp is neither aged-out (sweep keeps it) nor live (withhold releases it).
    """
    if not isinstance(created_raw, str):
        return False
    try:
        created = _parse_iso_z(created_raw)
    except ValueError:
        return False
    age = now_utc - created
    return timedelta(0) <= age < SWEEP_MAX_AGE


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _add_state_file_arg(p: argparse.ArgumentParser) -> None:
    """Attach `--state-file` to a (sub)parser with the common default + help."""
    p.add_argument(
        "--state-file",
        default=str(STATE_PATH_DEFAULT),
        help=(
            "Path to the JSON state file. Defaults to "
            "/data/services/openclaw/state/pending-calendar-clarifications.json."
        ),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="handle_clarification_state",
        description=(
            "Manage felix-admin-capture's pending calendar clarification state."
        ),
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    add_p = sub.add_parser("add", help="Append a PendingClarification.")
    add_p.add_argument("--note-filename", required=True)
    add_p.add_argument(
        "--partial-payload",
        required=True,
        help="JSON string of partial CalendarPayload.",
    )
    _add_state_file_arg(add_p)

    sweep_p = sub.add_parser("sweep", help="Delete entries older than 8h.")
    _add_state_file_arg(sweep_p)

    remove_p = sub.add_parser(
        "remove",
        help="Remove all pending entries for a resolved note filename (#763).",
    )
    remove_p.add_argument("--note-filename", required=True)
    _add_state_file_arg(remove_p)

    pending_p = sub.add_parser(
        "pending",
        help="Print whether a note filename has a live pending entry (#740).",
    )
    pending_p.add_argument("--note-filename", required=True)
    _add_state_file_arg(pending_p)

    match_p = sub.add_parser(
        "match",
        help="Find the most-recent PendingClarification matching a reply.",
    )
    match_p.add_argument("--reply-content", required=True)
    _add_state_file_arg(match_p)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    state_path = Path(args.state_file)
    now_utc = datetime.now(timezone.utc)

    if args.subcommand == "add":
        return subcommand_add(
            state_path, args.note_filename, args.partial_payload, now_utc
        )
    if args.subcommand == "sweep":
        return subcommand_sweep(state_path, now_utc)
    if args.subcommand == "remove":
        return subcommand_remove(state_path, args.note_filename)
    if args.subcommand == "pending":
        return subcommand_pending(state_path, args.note_filename, now_utc)
    if args.subcommand == "match":  # pragma: no branch - argparse enforces
        return subcommand_match(state_path, args.reply_content)
    return 2  # pragma: no cover - argparse rejects unknown subcommands


if __name__ == "__main__":
    sys.exit(main())
