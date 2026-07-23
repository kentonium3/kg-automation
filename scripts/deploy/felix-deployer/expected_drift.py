#!/usr/bin/env python3
"""Which baselines have FRESH, EXPECTED in-flight drift? (kentonium3/kg-automation#862)

Read-only bridge from the security-monitor audit (``audit.sh``) to felix-deployer's
pending-rebaseline token. The audit calls this once, at push time, to learn which
drifted baselines belong to an in-flight deploy that felix-deployer is already
rebaselining, so it can withhold the *push* for those (never the detection) while
still paging for everything else.

Design (see kitty-specs/drift-alert-rebaseline-suppression-01KY7GZZ/):

- **Single source of truth for the token**: reuse ``rebaseline.read_token`` — we never
  reparse or redefine the token schema (C-002). ``read_token`` already treats an
  absent or malformed token as ``None``.
- **Dedicated SHORT suppression window**: ``AUDIT_SUPPRESS_WINDOW_SECONDS`` (~15 min),
  deliberately NOT felix-deployer's 24 h ``MAX_AGE_SECONDS`` stale threshold. A
  lingering or maliciously planted token must never mute the security push for a day
  (post-plan Codex F3). In practice the token clears within ~10 s.
- **Fail-safe by construction**: ANY error (import failure, missing/malformed token,
  unparseable timestamp, future timestamp) yields an EMPTY set and exit 0, so the
  audit pages exactly as it does today (FR-004/FR-005/NFR-002/NFR-003).

Usage:
    expected_drift.py --list            # print fresh expected baseline names, one per line
    expected_drift.py --filter-alerts   # read an audit alert file on stdin, write to stdout
                                        # only the alert records to PUSH (expected-baseline
                                        # drift records — header AND their multi-line diff
                                        # body — are dropped; IOC and unexpected records kept)

Env:
    EXPECTED_DRIFT_TOKEN_PATH    # override the token path (tests / live-verify);
                                 # unset -> felix-deployer's default token path.
"""
from __future__ import annotations

import datetime as _dt
import os
import pathlib
import re
import sys

# A baseline-drift alert record header, as emitted by audit.sh's alert():
#   "[ALERT] <name> changed since baseline: <first diff line>"
# The diff body continues on the following lines (which do NOT start with "[ALERT]").
_BASELINE_ALERT_RE = re.compile(r"^\[ALERT\] (\S+) changed since baseline:")

# Dedicated SHORT suppression window (#862, Codex F3): ~15 min = a small multiple of
# the felix-deployer ~5-min deploy tick. NOT rebaseline.MAX_AGE_SECONDS (24 h).
AUDIT_SUPPRESS_WINDOW_SECONDS = 900


def _override_token_path() -> "pathlib.Path | None":
    """Return the env-overridden token path, or ``None`` to use the default.

    ``EXPECTED_DRIFT_TOKEN_PATH`` lets tests and live-verify point at a temp token
    so felix-deployer's real state is never read/raced (Codex F4).
    """
    override = os.environ.get("EXPECTED_DRIFT_TOKEN_PATH")
    return pathlib.Path(override) if override else None


def fresh_expected_baselines(now: "_dt.datetime | None" = None) -> "set[str]":
    """Return baseline names with fresh, expected in-flight drift.

    Never raises. Returns an empty set on any error, or when the token is absent,
    malformed, stale (age > ``AUDIT_SUPPRESS_WINDOW_SECONDS``), or has a bad/future
    ``pending_since_utc``.
    """
    try:
        # Lazy import so an import failure degrades to an empty set (fail-safe).
        # A sibling of rebaseline.py: its own dir on sys.path[0] resolves the import
        # when run as a script; insert defensively for the imported-in-tests case.
        here = str(pathlib.Path(__file__).resolve().parent)
        if here not in sys.path:
            sys.path.insert(0, here)
        import rebaseline  # type: ignore[import-not-found]

        token = rebaseline.read_token(_override_token_path())
        if not token:
            return set()

        expected = token.get("expected_baselines") or []
        pending_since = token.get("pending_since_utc")
        if not expected or not pending_since:
            return set()

        now_dt = now if now is not None else _dt.datetime.now(tz=_dt.timezone.utc)
        since_dt = _dt.datetime.fromisoformat(str(pending_since).replace("Z", "+00:00"))
        age_seconds = (now_dt - since_dt).total_seconds()
        # Reject stale (older than the short window) AND future-dated tokens.
        if age_seconds < 0 or age_seconds > AUDIT_SUPPRESS_WINDOW_SECONDS:
            return set()

        return {str(b) for b in expected if b}
    except Exception:  # noqa: BLE001 - fail-safe: any error -> empty (page as usual)
        return set()


def filter_alert_lines(lines: "list[str]", expected: "set[str]") -> "list[str]":
    """Return the alert lines to PUSH, dropping whole records for expected baselines.

    An audit alert *record* is a ``[ALERT] …`` header line followed by zero or more
    continuation lines (the multi-line ``diff`` body, which do not start with
    ``[ALERT]``). When a baseline-drift header names an *expected* baseline, the header
    **and its whole diff body** are dropped. IOC records (``[ALERT] IOC: …`` etc., which
    do not match "changed since baseline:") and unexpected-drift records are kept in
    full. Pure function — no I/O; trivially testable.
    """
    out: list[str] = []
    suppress = False
    for line in lines:
        if line.startswith("[ALERT]"):
            m = _BASELINE_ALERT_RE.match(line)
            name = m.group(1) if m else None
            if name is not None and name in expected:
                suppress = True  # drop this header and its following diff body
                continue
            suppress = False
            out.append(line)
        elif not suppress:
            out.append(line)
    return out


def _run_filter_alerts() -> int:
    """stdin (audit alert file) -> stdout (lines to push). Fail-safe: on ANY error,
    pass the input through unchanged so the audit pushes everything."""
    raw = sys.stdin.read()
    try:
        lines = raw.splitlines()
        kept = filter_alert_lines(lines, fresh_expected_baselines())
        sys.stdout.write("\n".join(kept) + ("\n" if kept else ""))
    except Exception:  # noqa: BLE001 - fail-safe: emit original input, push everything
        sys.stdout.write(raw)
    return 0


def main(argv: "list[str] | None" = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--filter-alerts" in args:
        return _run_filter_alerts()
    if "--list" in args:
        for name in sorted(fresh_expected_baselines()):
            print(name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
