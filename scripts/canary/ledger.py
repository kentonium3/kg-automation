"""Pure key-ledger evaluator (WP03) — adjudicate a state document against a
declared ledger.

A "ledger" is a ``key_ledger`` object from a component's ``health_check``
(contract ``docs/design/architecture/data/service-inventory.json`` §
``health_check.key_ledger``; see ``kitty-specs/pointer-key-ledger-01M189P6/
contracts/key-ledger.md`` for the authoritative predicate semantics — the
invariants there, P1-P5 in ``data-model.md``, are the specification this
module implements). It declares which top-level keys of a producer's state
document decide the component's health, and how.

This module exists to be the **one** place that decides "does this value
satisfy this predicate" — reused, unmodified, by every producer that adopts a
ledger. It contains **no component name, no host name, and no
producer-specific key name**: genericity here is what lets a second producer
adopt the contract by declaring data, not by editing code (contract §"Reuse
by a second producer").

:func:`evaluate` is pure and total: no I/O (the evaluation instant is passed
in as ``now``, never read from the system clock), no network, no filesystem,
and it never raises — every input, however malformed, produces a decided
:class:`LedgerResult` (NFR-006). It **iterates the declaration** (the
ledger's ``adjudicated`` map), not the document: iterating the document is
how an adjudicated key that stopped being emitted goes unnoticed, which is
the exact defect this mission exists to close.

Freshness (the ``freshness`` predicate) is *recognised* here — presence is
still enforced (see the absence rule below) — but not resolved: timestamp
parsing and bound-checking need the probe's ``now`` plus its existing
resolution helpers, and belong to WP04 (``scripts/canary/probes.py``), not
here. A present freshness key is collected into
:attr:`LedgerResult.freshness_pending` as a :class:`FreshnessObligation` for
the probe layer to finish.

Three traps this module exists to close (each has already reintroduced the
defect once, in a previous work package of this same mission — see the
comments at each site below for the concrete fix):

1. A type guard that *skips* an unexpected-type value, which reads it as
   healthy by default (the fail-open shape). See :func:`_type_identity_matches`
   and the good_values / minimum handling below — an unexpected type is
   unhealthy, never skipped.
2. Bool/number collision, in **both** directions (Python: ``False in [0, 3]``
   and ``1 in [True, None]`` are both ``True``). See
   :func:`_type_identity_matches`.
3. Raising. See :func:`evaluate`'s outer guard — no branch below is trusted
   to be exception-free on its own; the module is *proven* total by wrapping
   the whole evaluation, the same fail-safe shape ``run_probe`` in the
   neighbouring module uses.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

#: The three decided outcomes an evaluation can produce. ``unknown`` is a
#: distinct member here (not, say, a sentinel evidence string on ``ok``) —
#: making "we could not decide" structurally indistinguishable from "healthy"
#: is the exact hazard this mission diagnoses (a first-seen ``unknown`` is
#: recorded WITHOUT alerting upstream, so silently downgrading unknown to ok
#: would convert a detected problem into silence).
LedgerOutcome = Literal["ok", "unhealthy", "unknown"]

#: The recognised predicate field names. Exactly one must be present on a
#: predicate object (contract structural rule 4); modifier fields (e.g.
#: ``unmeasured_is_unknown``, ``suppress_until_utc``, ``anchor``,
#: ``max_age_seconds``) live alongside without changing the predicate kind.
_PREDICATE_FIELDS: tuple[str, ...] = ("good_values", "minimum", "freshness")


@dataclass(frozen=True)
class FreshnessObligation:
    """A single ``freshness`` predicate this module recognised but did not
    resolve.

    Presence of the key in the document has already been enforced by
    :func:`evaluate` (absence is unhealthy for every predicate form, freshness
    included) by the time this is constructed — ``value`` is always the
    document's raw, unparsed value for ``key``. This module does not parse or
    bound-check it: that needs the evaluation instant plus the probe layer's
    existing timestamp-resolution machinery (WP04), which in turn needs probe
    context this module deliberately does not have.
    """

    key: str
    value: Any
    anchor: bool
    max_age_seconds: float | None


@dataclass(frozen=True)
class LedgerResult:
    """The decided outcome of evaluating a document against a ledger.

    ``evidence`` names the responsible key and value whenever the outcome is
    not ``ok`` (NFR-004). ``freshness_pending`` carries every ``freshness``
    predicate this evaluation recognised but deferred — only meaningful when
    ``outcome == "ok"``: a non-``ok`` outcome already decided the verdict and
    the probe layer has nothing further to combine it with.
    """

    outcome: LedgerOutcome
    evidence: str
    freshness_pending: tuple[FreshnessObligation, ...] = field(default_factory=tuple)


def _unknown(evidence: str) -> LedgerResult:
    return LedgerResult(outcome="unknown", evidence=evidence)


def _unhealthy(evidence: str) -> LedgerResult:
    return LedgerResult(outcome="unhealthy", evidence=evidence)


def _type_identity_matches(value: Any, candidate: Any) -> bool:
    """Membership test for a single ``good_values`` candidate.

    TRAP 2 (bool/number collision, both directions). Python's numeric tower
    makes ``False == 0`` and ``True == 1`` true, so plain ``in`` / ``==`` gets
    this wrong in both directions at once::

        False in [0, 3]        # True  -> a bool document value would satisfy
                                #          an int good-set
        1     in [True, None]  # True  -> an int document value would satisfy
                                #          a bool good-set

    and the producer builds this document by shell interpolation, so a value
    landing with the wrong type is realistic drift, not a hypothetical.

    ``type(x) is type(y)`` already rejects every one of these on its own —
    ``bool`` is a *subclass* of ``int`` but is never the *same type as* int,
    so ``type(True) is type(1)`` is ``False`` even though ``True == 1``. No
    separate bool special-case is needed; requiring type identity AND value
    equality closes the hole in both directions at once. Do not "simplify"
    this back to bare ``==``/``in`` — that is precisely the defect.
    """
    return type(value) is type(candidate) and value == candidate


def _predicate_kind(predicate: Any) -> str | None:
    """Return which predicate field is declared, or ``None`` if the predicate
    object is not a dict, or does not declare exactly one recognised
    predicate field (zero is undecidable, two is ambiguous — structural rule
    4). Callers treat ``None`` as "malformed; cannot evaluate" -> ``unknown``.
    """
    if not isinstance(predicate, dict):
        return None
    present = [name for name in _PREDICATE_FIELDS if name in predicate]
    if len(present) != 1:
        return None
    return present[0]


def _eval_good_values(key: str, predicate: dict[str, Any], value: Any) -> LedgerResult | None:
    """Evaluate a ``good_values`` predicate. ``None`` means "satisfied,
    continue"; otherwise the decided (non-ok) result.

    TRAP 1 (type guard that skips). There is deliberately no ``isinstance``
    pre-filter here of the shape the neighbouring module uses for its own
    (unrelated, historical) purposes — ``if isinstance(code, int) and code
    not in _OK_CODES:``. That shape *skips* evaluation for an unexpected type
    and falls through to healthy. Here, a value of any type that is not
    matched by :func:`_type_identity_matches` against some candidate is
    unhealthy — regardless of its type (P2/contract "Membership matching").
    """
    good_values = predicate.get("good_values")
    if not isinstance(good_values, list) or not good_values:
        return _unknown(f"malformed good_values for {key}: {good_values!r}")
    for candidate in good_values:
        # No type pre-filter (TRAP 1) and no hashing (list membership, not set
        # membership) -- so a hostile/unhashable candidate (e.g. a list or
        # dict that survived validation) is compared, never skipped or raised
        # on.
        if _type_identity_matches(value, candidate):
            return None
    return _unhealthy(f"{key}={value!r} not in good_values {good_values!r}")


def _eval_minimum(
    key: str, predicate: dict[str, Any], value: Any, now: datetime
) -> LedgerResult | None:
    """Evaluate a ``minimum`` predicate (+ optional ``unmeasured_is_unknown``,
    ``suppress_until_utc``). ``None`` means "satisfied, continue".
    """
    # Suppression is an operator's deliberate, dated exemption (FR-019 T016).
    # Anything that is not a VALID one is not an exemption at all -- so an
    # absent, non-string, or unparseable `suppress_until_utc` must fall
    # through to the ordinary `minimum` verdict below, exactly as if no
    # modifier were declared. It must NEVER decide `unknown` on its own:
    # `unknown` is not a neutral outcome (a first-seen `unknown` is recorded
    # WITHOUT alerting -- test_first_seen_unknown_is_ledgered_not_paged), so
    # treating a malformed modifier as "unknown" would let a single typo in a
    # ledger's `suppress_until_utc` silently switch off a live health rule,
    # indistinguishable from health. This is this mission's own defect class,
    # reached through the contract's own escape hatch (review cycle 1).
    suppress_until = predicate.get("suppress_until_utc")
    if isinstance(suppress_until, str):
        suppressed_until_dt = _parse_iso(suppress_until)
        if suppressed_until_dt is not None and now < suppressed_until_dt:
            # FR-019 first-run exemption. Before the declared instant the
            # predicate is NOT EVALUATED -- it contributes nothing to the
            # verdict, it is not treated as healthy. An established repo that
            # keeps reporting the same low value after its exemption expires
            # falls straight through to the normal check below, which is what
            # keeps this rule catching a wiped-and-reinitialised repository
            # (contract "Predicate modifiers" — the exemption is a dated,
            # declarative opt-in specifically because every signal a new
            # repository produces, a wiped one can also produce).
            return None
        # Present but unparseable -- falls through below, same as absent.
    # Present but non-string, or absent, or null -- falls through below.
    if value is None:
        if predicate.get("unmeasured_is_unknown") is True:
            return _unknown(f"{key} is null (unmeasured)")
        return _unhealthy(f"{key} is null")
    minimum = predicate.get("minimum")
    if isinstance(minimum, bool) or not isinstance(minimum, (int, float)):
        return _unknown(f"malformed minimum for {key}: {minimum!r}")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _unhealthy(f"{key}={value!r} is not a real number (minimum {minimum!r})")
    if value >= minimum:
        return None
    return _unhealthy(f"{key}={value!r} below minimum {minimum!r}")


def _eval_freshness(
    key: str, predicate: dict[str, Any], value: Any
) -> tuple[LedgerResult | None, FreshnessObligation | None]:
    """Recognise a ``freshness`` predicate and defer it. Never parses
    ``value`` -- timestamp resolution belongs to the probe layer (WP04),
    which has the ``now`` + candidate-key machinery this module deliberately
    does not duplicate. Returns ``(decided_result, None)`` only for a
    malformed modifier; otherwise ``(None, obligation)``.
    """
    max_age = predicate.get("max_age_seconds")
    if max_age is not None and (isinstance(max_age, bool) or not isinstance(max_age, (int, float))):
        return _unknown(f"malformed max_age_seconds for {key}: {max_age!r}"), None
    anchor = predicate.get("anchor") is True
    return None, FreshnessObligation(key=key, value=value, anchor=anchor, max_age_seconds=max_age)


def _parse_iso(value: str) -> datetime | None:
    """Parse an ISO-8601 instant; ``None`` on anything unparseable.

    Reimplemented locally rather than imported from the probe module so this
    module stays standalone and dependency-free (WP04 wires the probe layer
    to this module, never the reverse). A trailing ``Z`` is normalized to
    ``+00:00`` for consistency with the neighbouring module's own parser.
    """
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _evaluate(document: Any, ledger: dict[str, Any], now: datetime) -> LedgerResult:
    if not isinstance(document, dict):
        return _unknown("document is not a JSON object")
    if not isinstance(ledger, dict):
        return _unknown("ledger is not a JSON object")

    adjudicated = ledger.get("adjudicated")
    if adjudicated is None:
        return LedgerResult(outcome="ok", evidence="ledger declares no adjudicated keys")
    if not isinstance(adjudicated, dict):
        return _unknown("ledger 'adjudicated' is not an object")

    deferred: list[FreshnessObligation] = []

    # Iterate the DECLARATION, not the document. A key the document stopped
    # emitting is invisible if you only walk `document` -- that is the exact
    # mechanism this mission exists to close.
    for key, predicate in adjudicated.items():
        kind = _predicate_kind(predicate)
        if kind is None:
            return _unknown(f"malformed predicate for adjudicated key {key!r}: {predicate!r}")

        # P4 (absence, unconditional): an adjudicated key absent from the
        # document is unhealthy, whatever its predicate -- checked here,
        # before any predicate-specific logic, so it applies identically to
        # good_values / minimum / freshness alike. `null` in `good_values`
        # licenses only a PRESENT null; this is the "the producer stopped
        # speaking" case, which is a different condition.
        if key not in document:
            return _unhealthy(f"adjudicated key {key} not emitted")

        value = document[key]

        if kind == "good_values":
            result = _eval_good_values(key, predicate, value)
            if result is not None:
                return result
            continue

        if kind == "minimum":
            result = _eval_minimum(key, predicate, value, now)
            if result is not None:
                return result
            continue

        # kind == "freshness"
        result, obligation = _eval_freshness(key, predicate, value)
        if result is not None:
            return result
        assert obligation is not None  # invariant of _eval_freshness's contract
        deferred.append(obligation)

    return LedgerResult(
        outcome="ok",
        evidence="all adjudicated keys satisfied",
        freshness_pending=tuple(deferred),
    )


def evaluate(document: Any, ledger: dict[str, Any], *, now: datetime) -> LedgerResult:
    """Adjudicate ``document`` against ``ledger`` and return a decided
    :class:`LedgerResult`.

    Pure and total (NFR-006, TRAP 3): no I/O, no network, no filesystem, and
    it never raises. ``document`` and ``ledger`` are typed loosely (``Any`` /
    permissive ``dict``) on purpose -- both arrive as decoded JSON from a
    document built by shell interpolation, so *any* shape is a realistic
    input, not just a well-formed one, and this function must decide rather
    than crash on all of them.

    TRAP 3 (raising). Every branch below is already defensive on its own
    (isinstance guards throughout :func:`_evaluate` and its helpers), but
    this wrapper is the actual proof of totality: nothing below is trusted to
    be exception-free by inspection alone. This mirrors the fail-safe shape
    the neighbouring probe dispatcher uses (``run_probe`` wraps its handler
    call in ``except Exception`` for the same reason) -- upstream, a raised
    exception is caught and mapped to ``unknown``, and a *first-seen*
    ``unknown`` is recorded WITHOUT alerting. So an evaluator that raises on
    a document carrying an explicit failure value produces silence, not an
    alert -- converting the bug this mission fixes into a differently-shaped
    one. Catching here, at the true boundary, is what keeps that from
    happening one layer up.
    """
    try:
        return _evaluate(document, ledger, now)
    except Exception as exc:  # noqa: BLE001 -- fail-safe boundary (NFR-006/TRAP 3)
        return _unknown(f"{type(exc).__name__}: {exc}")
