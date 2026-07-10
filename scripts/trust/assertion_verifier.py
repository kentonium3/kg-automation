"""Completion-assertion verifier (#683, mission
felix-truthful-reporting-01KX6MN5, WP03).

Deterministically grounds each artifact id in a recorded ``CompletionAssertion``
(see ``scripts.trust.completion_assertion``) against its owning system,
producing zero or more ``AssertionFinding`` records. This is the "verification
half" of FR-005 / FR-006(a): it does not decide whether a claim is *true* in
some general sense — only whether the specific artifact ids the assertion
names can be corroborated to exist.

Contract: C5 in
``kitty-specs/felix-truthful-reporting-01KX6MN5/contracts/detector-cli.md``;
schema: ``AssertionFinding`` in ``data-model.md``.

- **Per-id independence.** Each id in ``artifact_ids`` is checked on its own;
  a mixed present/missing assertion yields findings only for the missing ids.
- **`vikunja_task`** → looked up via the shared Vikunja client
  (``scripts.common.vikunja_client.VikunjaClient``, the same client-builder
  pattern as ``scripts/vikunja/create_task.py``). A missing id →
  ``artifact_missing`` (error). A transient/unexpected client error is handled
  conservatively — logged, treated as *not* a finding — so a Vikunja outage
  never fabricates a false ``artifact_missing`` alert storm.
- **`calendar_event` / `vault_note` / `other`** → no cheap existence check
  today → one ``unverifiable_kind`` (warn) finding per id, never a false
  ``artifact_missing``.
- **No LLM anywhere.** Verification is deterministic existence-checking only.

Also exposes a clean reader (:func:`read_assertions` / :func:`iter_recent_assertions`)
over the assertion JSONL so WP04's scan runner can consume recorded
assertions and advance its own watermark; the watermark/state concern itself
lives in WP04, not here.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator

from scripts.trust.completion_assertion import assertions_dir

__all__ = [
    "AssertionFinding",
    "VerificationResult",
    "verify_assertion",
    "verify_assertion_detailed",
    "verify_vikunja_id_present",
    "read_assertions",
    "iter_recent_assertions",
]

logger = logging.getLogger(__name__)

# Kinds with no cheap existence check today (Codex finding — false
# `artifact_missing` avoidance). `vikunja_task` is deliberately absent: it has
# a real existence check below.
_UNVERIFIABLE_KINDS = frozenset({"calendar_event", "vault_note", "other"})


@dataclass(frozen=True)
class AssertionFinding:
    """One verification finding for a single asserted artifact id."""

    kind: str  # "artifact_missing" | "unverifiable_kind"
    agent: str
    artifact_kind: str
    artifact_id: str
    claim: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of verifying one ``CompletionAssertion`` (F1 lifecycle).

    Distinguishes a **conclusive** verification (every id was resolved to
    *present* or *missing*) from an **indeterminate** one (at least one id
    hit a transient/unexpected fault — e.g. a Vikunja outage — so its
    existence could not be established this scan).

    - ``findings`` — zero or more :class:`AssertionFinding` for the ids that
      were conclusively *missing* / *unverifiable*.
    - ``indeterminate`` — ``True`` iff at least one id could not be
      conclusively checked. The scan runner uses this to hold the watermark
      so the record is re-read (and re-verified) on the next scan rather than
      being silently consumed after a transient failure (Codex F1).

    A record is safe to advance the watermark past **only** when
    ``indeterminate`` is ``False``.
    """

    findings: list[AssertionFinding] = field(default_factory=list)
    indeterminate: bool = False


def _build_client() -> Any:
    from scripts.common.vikunja_client import VikunjaClient

    return VikunjaClient()


def _verify_vikunja_task_id(client: Any, artifact_id: str) -> bool | None:
    """Return True if found, False if confirmed missing, None if indeterminate.

    ``None`` signals a transient/unexpected error — the caller must not treat
    that as ``artifact_missing`` (a Vikunja outage is not a missing artifact).
    """
    try:
        from scripts.common.vikunja_client import VikunjaNotFoundError
    except ImportError:  # pragma: no cover - defensive; module always present
        VikunjaNotFoundError = ()  # type: ignore[assignment]

    try:
        result = client.get(f"/tasks/{artifact_id}")
    except VikunjaNotFoundError:
        return False
    except Exception:  # noqa: BLE001 - conservative: transient error, not "missing"
        logger.warning(
            "assertion_verifier: transient error checking vikunja_task id=%s; "
            "treating as indeterminate (no finding)",
            artifact_id,
        )
        return None

    if not result:
        # A falsey-but-non-raising response (e.g. None/{}) — conservatively
        # treat as "not found" rather than fabricating a false positive later.
        return False
    return True


def verify_assertion_detailed(
    a: dict[str, Any], *, client: Any | None = None
) -> VerificationResult:
    """Verify a ``CompletionAssertion`` and report conclusiveness (F1).

    Like :func:`verify_assertion` but returns a :class:`VerificationResult`
    so the caller can tell a *conclusive* verification (every id resolved to
    present or missing) apart from an *indeterminate* one (a transient
    Vikunja fault on at least one id). The scan runner needs this to avoid
    advancing its watermark past a record it could not conclusively verify
    (a genuinely-missing artifact after a Vikunja outage must be retried,
    not silently consumed).

    Deterministic; no LLM.
    """
    agent = str(a.get("agent", ""))
    artifact_kind = str(a.get("artifact_kind", ""))
    artifact_ids = a.get("artifact_ids") or []
    claim = str(a.get("claim", ""))

    findings: list[AssertionFinding] = []

    if artifact_kind != "vikunja_task":
        # calendar_event / vault_note / other / unknown kinds: no cheap
        # existence check today -> warn, one per id, never artifact_missing.
        # These are always conclusive (there is no external call to fail).
        for artifact_id in artifact_ids:
            findings.append(
                AssertionFinding(
                    kind="unverifiable_kind",
                    agent=agent,
                    artifact_kind=artifact_kind,
                    artifact_id=str(artifact_id),
                    claim=claim,
                )
            )
        return VerificationResult(findings=findings, indeterminate=False)

    active_client = client if client is not None else _build_client()
    indeterminate = False
    for artifact_id in artifact_ids:
        found = _verify_vikunja_task_id(active_client, str(artifact_id))
        if found is False:
            findings.append(
                AssertionFinding(
                    kind="artifact_missing",
                    agent=agent,
                    artifact_kind=artifact_kind,
                    artifact_id=str(artifact_id),
                    claim=claim,
                )
            )
        elif found is None:
            # Transient error on this id -> the record is not conclusively
            # verified. Deliberately no finding (avoid a false artifact_missing
            # on outage); flag the whole record indeterminate so the runner
            # holds the watermark and retries next scan.
            indeterminate = True
        # found is True -> present, no finding.
    return VerificationResult(findings=findings, indeterminate=indeterminate)


def verify_assertion(a: dict[str, Any], *, client: Any | None = None) -> list[AssertionFinding]:
    """Verify each id in a ``CompletionAssertion`` independently.

    ``a`` is a ``CompletionAssertion`` (dict, e.g. as read back from the
    ledger JSONL). Returns zero or more ``AssertionFinding`` — one per
    missing/unverifiable id. Deterministic; no LLM. Thin wrapper over
    :func:`verify_assertion_detailed` for callers that don't need the
    conclusiveness signal.
    """
    return verify_assertion_detailed(a, client=client).findings


def verify_vikunja_id_present(artifact_id: str, *, client: Any | None = None) -> bool | None:
    """Re-check a single ``vikunja_task`` id's existence (F2 re-verify path).

    Returns ``True`` if the task is present, ``False`` if confirmed missing,
    ``None`` if indeterminate (transient error). Used by the scan runner to
    re-verify an outstanding ``artifact_missing`` assertion each scan —
    independent of the watermark — so the finding persists (24h re-alert)
    while the artifact is still missing and only resolves when it reappears.
    """
    active_client = client if client is not None else _build_client()
    return _verify_vikunja_task_id(active_client, str(artifact_id))


def read_assertions(path: Path) -> Iterator[dict[str, Any]]:
    """Yield each assertion record from a single JSONL file.

    Tolerant of blank lines and partial/corrupt trailing lines (best-effort
    read; a malformed line is skipped rather than raising).
    """
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("assertion_verifier: skipping malformed line in %s", path)
                    continue
    except FileNotFoundError:
        return


def iter_recent_assertions(
    *, base_dir: Path | None = None, since_offset: int | None = None
) -> Iterator[dict[str, Any]]:
    """Yield assertion records from the date-partitioned ledger, most-recent-file-last.

    ``base_dir`` defaults to :func:`scripts.trust.completion_assertion.assertions_dir`.
    ``since_offset``, if given, limits the read to the last N date-partition
    files (by filename sort) — a simple recency window. Callers that need a
    stateful watermark (e.g. WP04's scan runner) build that on top of this;
    this function itself is stateless.
    """
    base = base_dir if base_dir is not None else assertions_dir()
    if not base.exists():
        return
    files = sorted(base.glob("*.jsonl"))
    if since_offset is not None and since_offset >= 0:
        files = files[-since_offset:] if since_offset > 0 else []
    for file_path in files:
        yield from read_assertions(file_path)
