"""Seen-findings state + alert cadence (WP04, felix-truthful-reporting-01KX6MN5).

Tracks findings across scan ticks so alert cadence is correct
(data-model.md "State & idempotency"):

- **First observation** of a finding -> alert immediately.
- While a finding **persists** -> re-alert every 24h (so persistent
  unapproved infra is not silently hidden after the first alert).
- When a previously-seen finding **disappears** -> emit a low-priority
  ``drift_resolved`` event and drop it from state.

**Baseline-versioned fingerprints** (data-model.md "Baseline-versioned
fingerprints"): the finding fingerprint folds in ``baseline_hash`` (WP02) so
a baseline edit re-evaluates every finding rather than letting stale
seen-state suppress a now-legitimate (or newly-illegitimate) cron.

State is a small JSON map ``fingerprint -> {first_seen, last_seen,
last_alerted}`` (ISO-8601 UTC strings), written atomically (temp file in the
same directory + ``os.replace``) so a crash mid-write never leaves a
partial/corrupt file. A missing or corrupt state file loads as empty
(fail-safe) — never a crash.

Deterministic: :func:`reconcile` takes ``now`` as an injected parameter; it
never calls ``datetime.now()`` itself, so tests can drive the 24h boundary
exactly.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.trust.assertion_verifier import AssertionFinding
from scripts.trust.cron_drift_detector import CronDriftFinding

__all__ = [
    "DEFAULT_STATE_PATH",
    "RE_ALERT_INTERVAL",
    "ResolvedEvent",
    "fingerprint_finding",
    "load_state",
    "save_state",
    "reconcile",
]

logger = logging.getLogger(__name__)

# Home for the seen-findings state file (module constant, injectable for
# tests via the `path` parameter on load_state/save_state/reconcile).
DEFAULT_STATE_PATH = Path("/data/services/trust/state/seen-findings.json")

# Re-alert cadence for a persisting finding.
RE_ALERT_INTERVAL = timedelta(hours=24)

_ISO_FMT_NOTE = "ISO-8601 UTC, e.g. 2026-07-10T12:00:00+00:00"


@dataclass(frozen=True)
class ResolvedEvent:
    """A finding that was previously seen but is absent from the current scan."""

    fingerprint: str
    name: str
    first_seen: str
    cleared_at: str


def _utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _cron_identity(finding: CronDriftFinding) -> tuple[str, ...]:
    return ("cron", finding.kind, finding.name, finding.agent_id)


def _assertion_identity(finding: AssertionFinding) -> tuple[str, ...]:
    return (
        "assertion",
        finding.kind,
        finding.agent,
        finding.artifact_kind,
        finding.artifact_id,
    )


def _finding_name(finding: CronDriftFinding | AssertionFinding) -> str:
    """Human-readable name for the finding, used in drift_resolved rendering."""
    if isinstance(finding, CronDriftFinding):
        return finding.name
    return f"{finding.artifact_kind}:{finding.artifact_id}"


def fingerprint_finding(
    finding: CronDriftFinding | AssertionFinding, baseline_hash: str
) -> str:
    """Return a stable fingerprint for *finding*, versioned by *baseline_hash*.

    Fingerprint = sha256 of the finding's identity tuple (kind + name +
    agent_id for cron; kind + agent + artifact_kind + artifact_id for
    assertion) combined with ``baseline_hash`` (data-model.md
    "Baseline-versioned fingerprints") so a baseline update re-evaluates
    findings rather than letting stale seen-state suppress a now-legitimate
    (or newly-illegitimate) cron.
    """
    if isinstance(finding, CronDriftFinding):
        identity = _cron_identity(finding)
    elif isinstance(finding, AssertionFinding):
        identity = _assertion_identity(finding)
    else:
        raise TypeError(f"fingerprint_finding: unsupported finding type {type(finding)!r}")

    canonical = "|".join((*identity, baseline_hash))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_state(path: Path | str = DEFAULT_STATE_PATH) -> dict[str, dict[str, str]]:
    """Load the seen-findings state map; fail-safe (missing/corrupt -> ``{}``).

    A missing file is the expected first-run state. A corrupt/unreadable
    file is logged and treated as empty rather than raised — a state-file
    problem must never break the scan (NFR-001); worst case is a spurious
    "first observation" re-alert, never a crash.
    """
    target = Path(path)
    try:
        raw_text = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as exc:
        logger.warning("state.load_state: unreadable state file %s (%s); loading empty", target, exc)
        return {}

    try:
        document = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.warning("state.load_state: corrupt state file %s (%s); loading empty", target, exc)
        return {}

    if not isinstance(document, dict):
        logger.warning("state.load_state: state file %s is not a JSON object; loading empty", target)
        return {}

    # Defensive: only keep entries that look like the expected shape.
    cleaned: dict[str, dict[str, str]] = {}
    for fingerprint, entry in document.items():
        if isinstance(entry, dict) and all(
            isinstance(entry.get(key), str)
            for key in ("first_seen", "last_seen", "last_alerted")
        ):
            cleaned[fingerprint] = {
                "first_seen": entry["first_seen"],
                "last_seen": entry["last_seen"],
                "last_alerted": entry["last_alerted"],
                # Preserve name for readability/debugging; optional field.
                "name": entry.get("name", ""),
            }
    return cleaned


def save_state(state: dict[str, dict[str, str]], path: Path | str = DEFAULT_STATE_PATH) -> None:
    """Atomically write *state* to *path* (temp file in the same dir + ``os.replace``).

    Never partially writes the state file: the temp file is written and
    fsync'd, then atomically renamed over the target. Raises on failure
    (e.g. unwritable directory) — the caller (the scan runner) is
    responsible for catching this and degrading to "state not persisted
    this tick" rather than crashing the whole scan.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, sort_keys=True, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, target)
    except Exception:
        # Clean up the temp file on any failure so we never leak stray
        # `.tmp` files into the state directory.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def reconcile(
    current_findings: list[tuple[CronDriftFinding | AssertionFinding, str]],
    now: datetime,
    state: dict[str, dict[str, str]] | None = None,
) -> tuple[
    list[CronDriftFinding | AssertionFinding],
    list[ResolvedEvent],
    dict[str, dict[str, str]],
]:
    """Reconcile *current_findings* against *state*; return (to_alert, resolved, new_state).

    ``current_findings`` is a list of ``(finding, baseline_hash)`` pairs —
    the caller supplies the baseline_hash alongside each finding so this
    function stays a pure, injectable-``now`` function with no baseline
    loading of its own.

    Cadence (data-model.md "State & idempotency"):

    - fingerprint **not in** state -> first observation -> include in
      ``to_alert``; ``first_seen = last_seen = last_alerted = now``.
    - fingerprint **in** state and ``now - last_alerted >= 24h`` -> re-alert
      -> include in ``to_alert``; update ``last_alerted = now``; always
      update ``last_seen = now``.
    - fingerprint **in** state and **not** re-alert-due -> not included in
      ``to_alert``, but ``last_seen`` is still refreshed.
    - fingerprint in state but **absent** from ``current_findings`` ->
      produce a :class:`ResolvedEvent` (``first_seen`` + ``cleared_at =
      now``) and drop the entry.

    Returns ``(to_alert, resolved_events, new_state)`` — the caller is
    responsible for persisting ``new_state`` via :func:`save_state` (this
    function performs no I/O).
    """
    current_state = dict(state) if state is not None else {}
    now_str = _utc_iso(now)

    seen_fingerprints: set[str] = set()
    to_alert: list[CronDriftFinding | AssertionFinding] = []
    new_state: dict[str, dict[str, str]] = {}

    for finding, baseline_hash in current_findings:
        fingerprint = fingerprint_finding(finding, baseline_hash)
        seen_fingerprints.add(fingerprint)
        name = _finding_name(finding)

        existing = current_state.get(fingerprint)
        if existing is None:
            # First observation.
            new_state[fingerprint] = {
                "first_seen": now_str,
                "last_seen": now_str,
                "last_alerted": now_str,
                "name": name,
            }
            to_alert.append(finding)
            continue

        first_seen = existing.get("first_seen", now_str)
        last_alerted_str = existing.get("last_alerted", now_str)
        try:
            last_alerted = _parse_iso(last_alerted_str)
            due_for_re_alert = (now - last_alerted) >= RE_ALERT_INTERVAL
        except ValueError:
            # Corrupt timestamp on this entry only -> treat conservatively
            # as due for re-alert rather than silently never re-alerting.
            due_for_re_alert = True

        if due_for_re_alert:
            new_state[fingerprint] = {
                "first_seen": first_seen,
                "last_seen": now_str,
                "last_alerted": now_str,
                "name": name,
            }
            to_alert.append(finding)
        else:
            new_state[fingerprint] = {
                "first_seen": first_seen,
                "last_seen": now_str,
                "last_alerted": last_alerted_str,
                "name": name,
            }

    resolved_events: list[ResolvedEvent] = []
    for fingerprint, entry in current_state.items():
        if fingerprint in seen_fingerprints:
            continue
        resolved_events.append(
            ResolvedEvent(
                fingerprint=fingerprint,
                name=entry.get("name", ""),
                first_seen=entry.get("first_seen", now_str),
                cleared_at=now_str,
            )
        )
        # Dropped from new_state by simply not carrying it forward.

    return to_alert, resolved_events, new_state
