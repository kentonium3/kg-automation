"""Seen-findings state + alert cadence (WP04, felix-truthful-reporting-01KX6MN5).

Tracks findings across scan ticks so alert cadence is correct
(data-model.md "State & idempotency"):

- **First observation** of a finding -> alert immediately.
- While a finding **persists** -> re-alert every 24h (so persistent
  unapproved infra is not silently hidden after the first alert).
- When a previously-seen finding **disappears** -> emit a low-priority
  ``drift_resolved`` event and drop it from state — but only if the sub-scan
  that owns it completed this tick. A finding whose sub-scan failed is
  carried forward unchanged (#1129).

**Baseline-versioned fingerprints** (data-model.md "Baseline-versioned
fingerprints"): a **cron** finding's fingerprint folds in ``baseline_hash``
(WP02) so a baseline edit re-evaluates every cron finding rather than letting
stale seen-state suppress a now-legitimate (or newly-illegitimate) cron.
#1130 narrowed this to cron findings, superseding the mission data-model's
"every finding": assertion and unit-drift callers pass ``""``, so their
fingerprints do not depend on the baseline. The per-type rule lives in
``run_trust_scan._finding_baseline_hash``.

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
from scripts.trust.cron_drift_detector import KIND_DUPLICATE_PRESENT, CronDriftFinding
from scripts.trust.unit_drift_detector import UnitDriftFinding

__all__ = [
    "ALL_SOURCES",
    "DEFAULT_STATE_PATH",
    "RE_ALERT_INTERVAL",
    "ResolvedEvent",
    "SOURCE_ASSERTION",
    "SOURCE_CRON",
    "SOURCE_UNIT",
    "fingerprint_finding",
    "load_state",
    "save_state",
    "reconcile",
    "keep_due",
    "outstanding_assertion_findings",
    "undelivered_assertion_findings",
]

logger = logging.getLogger(__name__)

# Home for the seen-findings state file (module constant, injectable for
# tests via the `path` parameter on load_state/save_state/reconcile).
DEFAULT_STATE_PATH = Path("/data/services/trust/state/seen-findings.json")

# Re-alert cadence for a persisting finding.
RE_ALERT_INTERVAL = timedelta(hours=24)

_ISO_FMT_NOTE = "ISO-8601 UTC, e.g. 2026-07-10T12:00:00+00:00"

# Source tags: which sub-scan produced a finding. Persisted as each state
# entry's ``source`` field, so the VALUES must never change (a rename would
# orphan every stored entry). They route drift_resolved copy and decide which
# entries a tick may resolve (#1129). They are NOT the fingerprint identity
# tags: those are ``"cron"`` / ``"assertion"`` / ``"unit"`` (see
# ``_unit_identity``) and are pinned by the fingerprint goldens.
SOURCE_CRON = "cron"
SOURCE_ASSERTION = "assertion"
SOURCE_UNIT = "unit-drift"
ALL_SOURCES: frozenset[str] = frozenset({SOURCE_CRON, SOURCE_ASSERTION, SOURCE_UNIT})


@dataclass(frozen=True)
class ResolvedEvent:
    """A finding that was previously seen but is absent from the current scan.

    ``source`` distinguishes a cron-drift resolution (``"cron"``) from an
    assertion resolution (``"assertion"``) so the runner renders the correct
    alert copy — an ``artifact_missing`` that clears must NOT render as
    "Cron drift cleared" (Codex F2).
    """

    fingerprint: str
    name: str
    first_seen: str
    cleared_at: str
    source: str = SOURCE_CRON


def _utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# Identity encoding for a cron with no owning agent (``agent_id is None`` —
# OpenClaw plugin-managed crons, #1124). A NUL can never appear in a real
# OpenClaw agent id, so this cannot collide with any real agent (nor with
# ``""``). A str agent_id is encoded as itself, so every pre-existing
# fingerprint is byte-identical (no spurious re-alert of persisted findings).
_NO_AGENT_SENTINEL = "\x00none"

# Identity encoding for an id-less ``duplicate_present`` copy (#1126). NUL-
# prefixed, so no real OpenClaw cron id can equal it. Deliberately NO ordinal:
# an ordinal shifts when a sibling copy is removed, which would churn alerts;
# id-less copies of one key therefore collapse to one identity (a degraded
# shape OpenClaw does not emit).
_NO_CRON_ID_SENTINEL = "\x00noid"


def _cron_identity(finding: CronDriftFinding) -> tuple[str, ...]:
    """4-field ``(source, kind, name, agent)`` identity; 5 fields only for
    ``duplicate_present``, which adds the copy's cron id so each extra copy is
    tracked and resolves independently (#1126). Every other kind ignores
    ``cron_id`` (pinned by tests/trust/test_fingerprint_goldens.py)."""
    agent = _NO_AGENT_SENTINEL if finding.agent_id is None else finding.agent_id
    if finding.kind == KIND_DUPLICATE_PRESENT:
        cron_id = _NO_CRON_ID_SENTINEL if finding.cron_id is None else finding.cron_id
        return ("cron", finding.kind, finding.name, agent, cron_id)
    return ("cron", finding.kind, finding.name, agent)


def _assertion_identity(finding: AssertionFinding) -> tuple[str, ...]:
    return (
        "assertion",
        finding.kind,
        finding.agent,
        finding.artifact_kind,
        finding.artifact_id,
    )


def _unit_identity(finding: UnitDriftFinding) -> tuple[str, ...]:
    return ("unit", finding.kind, finding.name)


def _finding_name(finding: CronDriftFinding | AssertionFinding | UnitDriftFinding) -> str:
    """Human-readable name for the finding, used in drift_resolved rendering."""
    if isinstance(finding, CronDriftFinding):
        if finding.kind == KIND_DUPLICATE_PRESENT:
            # Display only (drift_resolved copy), not fingerprinted.
            return f"{finding.name} (duplicate {finding.cron_id or 'no-id'})"
        return finding.name
    if isinstance(finding, UnitDriftFinding):
        return finding.name
    return f"{finding.artifact_kind}:{finding.artifact_id}"


def _finding_source(finding: CronDriftFinding | AssertionFinding | UnitDriftFinding) -> str:
    """Return the source tag (one of :data:`ALL_SOURCES`) for a finding (F2
    resolution routing — selects the drift_resolved copy)."""
    if isinstance(finding, CronDriftFinding):
        return SOURCE_CRON
    if isinstance(finding, UnitDriftFinding):
        return SOURCE_UNIT
    return SOURCE_ASSERTION


def _entry_source(entry: dict[str, str]) -> str:
    """The source a stored entry belongs to: its ``source`` tag when that is a
    known tag, else :data:`SOURCE_CRON` (the pre-F2 missing-source default).

    The single rule for both the #1129 completion test and
    ``ResolvedEvent.source``, so an unknown tag behaves exactly like cron and
    can never be orphaned (carried forever because no source "owns" it).
    """
    source = entry.get("source")
    return source if source in ALL_SOURCES else SOURCE_CRON


def _is_reverifiable_assertion(entry: dict[str, str]) -> bool:
    """True iff *entry* is an assertion the runner re-verifies every scan (F2).

    Only an ``artifact_missing`` claim about a ``vikunja_task`` with a
    non-empty id has a re-verify path, so only such an entry's absence means
    "the artifact reappeared". Every other assertion entry is never
    re-produced after its first tick, so its absence means nothing (#1137).
    ``assertion_verifier`` owns which kinds are verifiable; block (b)'s
    ``verify_vikunja_id_present`` in ``run_trust_scan`` is the co-change site.
    """
    return (
        _entry_source(entry) == SOURCE_ASSERTION
        and entry.get("assertion_kind") == "artifact_missing"
        and entry.get("artifact_kind") == "vikunja_task"
        and bool(entry.get("artifact_id"))
    )


def _assertion_identity_fields(finding: AssertionFinding) -> dict[str, str]:
    """Identity fields persisted for an ``artifact_missing`` assertion (F2).

    These let the scan runner re-verify an outstanding ``artifact_missing``
    finding each scan (re-checking the artifact's existence) independent of
    the once-only assertion watermark, so the finding persists (24h re-alert)
    while the artifact is still missing and only resolves when it reappears.
    """
    return {
        "assertion_kind": finding.kind,
        "artifact_kind": finding.artifact_kind,
        "artifact_id": finding.artifact_id,
        "agent": finding.agent,
        "claim": finding.claim,
    }


_FIELD_SEPARATOR = "|"
_V2_PREFIX = "v2:"


def _canonical(parts: tuple[str, ...]) -> str:
    """Encode a fingerprint's ``(*identity, baseline_hash)`` parts injectively (#1128).

    - **Legacy** (no part contains ``|`` and every part is UTF-8 encodable):
      ``"|".join(parts)``, byte-identical to every fingerprint written before
      #1128, so persisted seen-state is not orphaned.
    - **v2** (any part contains ``|``, or cannot be UTF-8 encoded — e.g. a
      lone surrogate from a ``\\ud800`` JSON escape):
      ``"v2:" + json.dumps(list(parts))``.

    Injectivity invariant (distinct part tuples never share a canonical):

    - legacy vs legacy: no part contains ``|``, and the part count is fixed by
      the first two parts (source tag + kind: cron 4, or 5 for
      ``duplicate_present``; assertion 5; unit 3; plus ``baseline_hash``), so
      splitting on ``|`` recovers the tuple uniquely;
    - v2 vs v2: ``json.dumps`` of a list of str is injective;
    - legacy vs v2: a legacy canonical starts with a source tag (``cron|``,
      ``assertion|``, ``unit|``), a code constant that is never ``v2:[``.
      Routing an unencodable tuple to v2 keeps this: the branch is a pure
      function of the parts, and v2 is injective on every tuple of str.

    ``ensure_ascii=True`` (the default) escapes non-ASCII, so a lone surrogate
    cannot raise ``UnicodeEncodeError`` when the canonical is UTF-8 encoded.
    """
    if not any(_FIELD_SEPARATOR in part or not _utf8_encodable(part) for part in parts):
        return _FIELD_SEPARATOR.join(parts)
    return _V2_PREFIX + json.dumps(list(parts))


def _utf8_encodable(part: str) -> bool:
    try:
        part.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def fingerprint_finding(
    finding: CronDriftFinding | AssertionFinding | UnitDriftFinding, baseline_hash: str
) -> str:
    """Return a stable fingerprint for *finding*, versioned by *baseline_hash*.

    Fingerprint = sha256 of the finding's identity tuple (kind + name +
    agent_id for cron; kind + agent + artifact_kind + artifact_id for
    assertion) combined with ``baseline_hash`` (data-model.md
    "Baseline-versioned fingerprints") so a baseline update re-evaluates
    cron findings rather than letting stale seen-state suppress a
    now-legitimate (or newly-illegitimate) cron. Only cron findings are
    baseline-versioned (#1130): callers pass ``""`` for assertion and
    unit-drift findings. This function applies whatever hash it is given;
    the per-type rule is ``run_trust_scan._finding_baseline_hash``.

    A cron finding with ``agent_id is None`` (plugin-managed, #1124) encodes
    its agent as a NUL-prefixed sentinel that no real agent id can equal; a
    str agent_id is encoded as itself, so existing fingerprints are unchanged.
    The parts are encoded by :func:`_canonical` (injective, #1128).
    """
    if isinstance(finding, CronDriftFinding):
        identity = _cron_identity(finding)
    elif isinstance(finding, AssertionFinding):
        identity = _assertion_identity(finding)
    elif isinstance(finding, UnitDriftFinding):
        identity = _unit_identity(finding)
    else:
        raise TypeError(f"fingerprint_finding: unsupported finding type {type(finding)!r}")

    canonical = _canonical((*identity, baseline_hash))
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
    # Optional string fields carried through verbatim when present: `name`
    # (readability), `source` ("cron"/"assertion" — F2 resolution routing),
    # and the assertion-identity fields used to re-verify an outstanding
    # artifact_missing finding each scan (F2).
    _OPTIONAL_STR_FIELDS = (
        "name",
        "source",
        "assertion_kind",
        "artifact_kind",
        "artifact_id",
        "agent",
        "claim",
    )
    for fingerprint, entry in document.items():
        if isinstance(entry, dict) and all(
            isinstance(entry.get(key), str)
            for key in ("first_seen", "last_seen", "last_alerted")
        ):
            cleaned_entry = {
                "first_seen": entry["first_seen"],
                "last_seen": entry["last_seen"],
                "last_alerted": entry["last_alerted"],
            }
            for opt_key in _OPTIONAL_STR_FIELDS:
                value = entry.get(opt_key)
                if isinstance(value, str):
                    cleaned_entry[opt_key] = value
            cleaned_entry.setdefault("name", "")
            cleaned[fingerprint] = cleaned_entry
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
    current_findings: list[tuple[CronDriftFinding | AssertionFinding | UnitDriftFinding, str]],
    now: datetime,
    state: dict[str, dict[str, str]] | None = None,
    completed_sources: frozenset[str] | None = None,
) -> tuple[
    list[CronDriftFinding | AssertionFinding | UnitDriftFinding],
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
    - fingerprint in state but **absent** from ``current_findings``, and its
      source is in ``completed_sources`` -> produce a :class:`ResolvedEvent`
      (``first_seen`` + ``cleared_at = now``) and drop the entry.
    - fingerprint in state, **absent**, and its source is **not** in
      ``completed_sources`` -> **carried forward unchanged** (#1129): no
      event, no ``last_seen`` refresh. A sub-scan that could not run says
      nothing about its findings ("could not check" is not "verified false",
      engineering principle 14).

    ``completed_sources`` names the sub-scans that ran to completion this
    tick. ``None`` means all of them (:data:`ALL_SOURCES`), for tests and
    legacy callers; the scan runner always passes an explicit set. A value
    that is not a subset of :data:`ALL_SOURCES` raises :class:`ValueError`.
    A stored entry's source is read by :func:`_entry_source`, so a missing or
    unknown tag is treated as cron. Entries that ARE present in the current
    findings are processed the same whether or not their source completed: a
    partial result is still real evidence of presence.

    Returns ``(to_alert, resolved_events, new_state)`` — the caller is
    responsible for persisting ``new_state`` via :func:`save_state` (this
    function performs no I/O).
    """
    completed = ALL_SOURCES if completed_sources is None else frozenset(completed_sources)
    if not completed <= ALL_SOURCES:
        raise ValueError(
            f"reconcile: unknown completed_sources {sorted(completed - ALL_SOURCES)!r}; "
            f"expected a subset of {sorted(ALL_SOURCES)!r}"
        )
    current_state = dict(state) if state is not None else {}
    now_str = _utc_iso(now)

    seen_fingerprints: set[str] = set()
    to_alert: list[CronDriftFinding | AssertionFinding | UnitDriftFinding] = []
    new_state: dict[str, dict[str, str]] = {}

    for finding, baseline_hash in current_findings:
        fingerprint = fingerprint_finding(finding, baseline_hash)
        seen_fingerprints.add(fingerprint)
        name = _finding_name(finding)
        source = _finding_source(finding)
        # Persist assertion identity so an outstanding artifact_missing can be
        # re-verified next scan independent of the watermark (F2).
        identity_fields = (
            _assertion_identity_fields(finding)
            if isinstance(finding, AssertionFinding)
            else {}
        )

        existing = current_state.get(fingerprint)
        if existing is None:
            # First observation.
            new_state[fingerprint] = {
                "first_seen": now_str,
                "last_seen": now_str,
                "last_alerted": now_str,
                "name": name,
                "source": source,
                **identity_fields,
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

        base_entry = {
            "first_seen": first_seen,
            "last_seen": now_str,
            "name": name,
            "source": source,
            **identity_fields,
        }
        if due_for_re_alert:
            new_state[fingerprint] = {**base_entry, "last_alerted": now_str}
            to_alert.append(finding)
        else:
            new_state[fingerprint] = {**base_entry, "last_alerted": last_alerted_str}

    resolved_events: list[ResolvedEvent] = []
    for fingerprint, entry in current_state.items():
        if fingerprint in seen_fingerprints:
            continue
        source = _entry_source(entry)
        if source not in completed:
            # Its sub-scan did not complete: carry the entry forward as loaded
            # (a copy, so keep_due on new_state can never alias prior state).
            new_state[fingerprint] = dict(entry)
            continue
        if source == SOURCE_ASSERTION and not _is_reverifiable_assertion(entry):
            # Never re-produced after its first tick, so its absence is not
            # evidence the claim is grounded: drop it silently (#1137).
            continue
        resolved_events.append(
            ResolvedEvent(
                fingerprint=fingerprint,
                name=entry.get("name", ""),
                first_seen=entry.get("first_seen", now_str),
                cleared_at=now_str,
                source=source,
            )
        )
        # Dropped from new_state by simply not carrying it forward.

    return to_alert, resolved_events, new_state


# Sentinel `last_alerted` value that always parses as "long ago", forcing the
# next scan to treat the finding as due for re-alert. Used by :func:`keep_due`
# when an emit fails on a *first observation* (there is no prior last_alerted
# to fall back to).
_ALWAYS_DUE_SENTINEL = "1970-01-01T00:00:00+00:00"


def _never_delivered(entry: dict[str, str]) -> bool:
    """True iff *entry*'s alert has never reached Kent (``keep_due`` stamped the
    sentinel on a failed first emit and no later emit has succeeded)."""
    return entry.get("last_alerted") == _ALWAYS_DUE_SENTINEL


def keep_due(
    new_state: dict[str, dict[str, str]],
    fingerprint: str,
    prior_state: dict[str, dict[str, str]] | None,
) -> None:
    """Revert an entry's ``last_alerted`` so a failed emit stays DUE (F3).

    :func:`reconcile` optimistically bumps ``last_alerted`` to *now* for every
    finding it puts in ``to_alert``. But an alert that never reached Kent (the
    ``#701`` bus returned ``ok=False``) must NOT be treated as delivered — the
    finding has to remain due on the very next scan, not wait out the 24h
    cadence. The runner calls this for each finding whose emit failed:

    - if the finding existed in ``prior_state``, restore that entry's original
      ``last_alerted`` (so the pre-existing cadence is unchanged — no spurious
      reset of a still-valid 24h window);
    - if it was a first observation (absent from ``prior_state``), stamp an
      always-due sentinel so the immediate retry fires next scan.

    Mutates ``new_state`` in place. Idempotent and fail-safe (a missing
    fingerprint is a no-op).
    """
    entry = new_state.get(fingerprint)
    if entry is None:
        return
    prior = (prior_state or {}).get(fingerprint)
    if prior is not None and isinstance(prior.get("last_alerted"), str):
        entry["last_alerted"] = prior["last_alerted"]
    else:
        entry["last_alerted"] = _ALWAYS_DUE_SENTINEL


def outstanding_assertion_findings(
    state: dict[str, dict[str, str]] | None,
) -> list[AssertionFinding]:
    """Reconstruct the ``artifact_missing`` assertion findings still in *state* (F2).

    Returns one :class:`AssertionFinding` per state entry that was recorded as
    an outstanding ``artifact_missing`` assertion (``source == "assertion"``
    and ``assertion_kind == "artifact_missing"`` with a ``vikunja_task``
    artifact_kind, the only re-verifiable kind). The scan runner re-verifies
    each of these against Vikunja every scan — independent of the once-only
    assertion watermark — so a still-missing artifact keeps producing its
    finding (persisting the 24h re-alert cadence) and only clears when the
    artifact reappears.
    """
    return [
        AssertionFinding(
            kind="artifact_missing",
            agent=entry.get("agent", ""),
            artifact_kind="vikunja_task",
            artifact_id=entry["artifact_id"],
            claim=entry.get("claim", ""),
        )
        for entry in (state or {}).values()
        if _is_reverifiable_assertion(entry)
    ]


def undelivered_assertion_findings(
    state: dict[str, dict[str, str]] | None,
) -> list[AssertionFinding]:
    """Rebuild the never-delivered, non-re-verifiable assertion findings in *state* (#1137).

    A non-re-verifiable assertion (e.g. an ``unverifiable_kind`` warning about
    a calendar event) is produced once, when its record is read; nothing
    re-produces it later, and :func:`reconcile` drops it silently once it is
    absent. If its first emit failed, ``keep_due`` stamped it never-delivered
    (:func:`_never_delivered`), so without help the warning would be lost.

    Returns one :class:`AssertionFinding` per assertion entry that is NOT
    re-verifiable (the complement of :func:`outstanding_assertion_findings`),
    is never-delivered, and has a stored ``assertion_kind``. Each is rebuilt
    from the entry's stored identity fields, so it fingerprints to the same key
    (assertion fingerprints are baseline-independent, #1130). The runner adds
    these to the tick's assertion findings with no external call: reconcile
    then sees each present and due, so it is emitted; on success it is dropped
    the next tick, on another failure ``keep_due`` keeps it never-delivered and
    it is retried again. A legacy entry without ``assertion_kind`` cannot be
    rebuilt and is simply dropped.
    """
    return [
        AssertionFinding(
            kind=entry["assertion_kind"],
            agent=entry.get("agent", ""),
            artifact_kind=entry.get("artifact_kind", ""),
            artifact_id=entry.get("artifact_id", ""),
            claim=entry.get("claim", ""),
        )
        for entry in (state or {}).values()
        if _entry_source(entry) == SOURCE_ASSERTION
        and not _is_reverifiable_assertion(entry)
        and _never_delivered(entry)
        and "assertion_kind" in entry
    ]
