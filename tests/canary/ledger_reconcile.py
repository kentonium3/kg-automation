"""Reconcile a producer's actually-emitted key set against its declared
``health_check.key_ledger`` (contract:
``kitty-specs/pointer-key-ledger-01M189P6/contracts/key-ledger.md``
§ "Obligation 2 — Test").

The generative rule this module exists to make true: *a test enumerates the
keys a producer **actually emits** and fails if any key is in neither list*.
Comparing against a key list written in the test that calls this module
would relocate that defect, not fix it — every function here takes the
emitted set and the ledger as data, never a hardcoded key list.

**What this module guarantees**:

* :func:`load_ledgers` finds every component in a service-inventory document
  that declares a ``key_ledger`` — by walking the document itself, never a
  hand-maintained name list, so a newly-ledgered component is discovered
  automatically rather than requiring an edit here.
* :func:`declared_keys` is the union of a ledger's ``adjudicated`` and
  ``diagnostic_only`` key names: the full set a producer is permitted to
  emit.
* :func:`assert_reconciles` proves, for one (harness-observed emission,
  ledger) pair, both that the harness actually produced something worth
  reconciling (process outcome, document present, parses as an object,
  non-empty key set — each a distinct failure) and that the emitted key set
  and the declared key set are the *same* set, in both directions.
* :func:`assert_selection_matches` proves a reconciliation suite's component
  selection is non-empty and equals the full set of ledger-declaring
  components — not a subset. A component that grows a ledger and is
  silently not reconciled is the #913 failure mode this exists to catch.
* :func:`assert_harness_paths_exist` proves every declared
  ``reconciliation_harness`` path exists on disk. This moved here from the
  structural validator (contract "Structural rules" rule 8, revised
  2026-08-30): an existence check there deadlocks whole-tree in the
  pre-commit hook between a ledger landing and its harness landing — a
  window that cannot be closed by reordering, since a harness must
  reconcile against a ledger that already exists. Here it fails loudly, in
  the one place that can also prove the harness actually reconciled
  something, not merely that a path resolves.

**What this module does NOT guarantee**: it binds a ledger to *the repo
copy* of a producer — whichever script or command the calling harness
actually executed to build the ``EmissionResult`` it hands to
:func:`assert_reconciles`. Whether that repo copy matches what is deployed
and running elsewhere is a separate, weaker guarantee, held by a daily
observe-only drift comparator (see the contract and
``kitty-specs/pointer-key-ledger-01M189P6/research.md`` R4), not by
anything in this module.

This module contains **no component name, no host name, and no
producer-specific key name** (contract "Reuse by a second producer") — it
is the piece #913 reuses, and a single such reference here would defeat
FR-010. A second producer adopts the contract by declaring a ledger and
registering a harness, never by editing this file; that property is itself
tested, in ``tests/canary/test_ledger_reuse.py``, by driving a fictitious
producer through this module unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


def load_ledgers(inventory: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every component in ``inventory`` that declares a
    ``health_check.key_ledger``, keyed by component name.

    Walks ``inventory["services"]`` — the one place components live in
    ``service-inventory.json`` — rather than consulting a hand-maintained
    name list, so a component that grows a ledger is picked up
    automatically. :func:`assert_selection_matches` exists to enforce that a
    reconciliation suite's selection actually tracks this, rather than
    drifting from it.
    """
    ledgers: dict[str, dict[str, Any]] = {}
    for component in inventory.get("services", []):
        if not isinstance(component, dict):
            continue
        name = component.get("name")
        health_check = component.get("health_check")
        if not isinstance(health_check, dict):
            continue
        ledger = health_check.get("key_ledger")
        if isinstance(ledger, dict) and isinstance(name, str) and name:
            ledgers[name] = ledger
    return ledgers


def declared_keys(ledger: dict[str, Any]) -> set[str]:
    """The full set of keys ``ledger`` accounts for: every ``adjudicated``
    key plus every ``diagnostic_only`` key. A key outside this union is
    undeclared, whichever list it should have lived in.
    """
    adjudicated = ledger.get("adjudicated")
    diagnostic_only = ledger.get("diagnostic_only")
    keys: set[str] = set()
    if isinstance(adjudicated, dict):
        keys |= set(adjudicated)
    if isinstance(diagnostic_only, dict):
        keys |= set(diagnostic_only)
    return keys


@dataclass(frozen=True)
class EmissionResult:
    """What a harness observed when it drove a producer under controlled
    effects (contract Obligation 2.6). Built entirely by the calling
    harness — this module never executes anything itself, and never reads a
    filesystem or a subprocess on its own.

    ``process_ok`` / ``process_detail``: whether the harness considers the
    producer's process outcome acceptable for the scenario it drove, and
    why. Deciding "acceptable" is the harness's job — only it knows whether
    a non-zero exit was the point of the run it just made; this module only
    enforces that the question was answered explicitly rather than skipped.

    ``document_text``: the raw text the harness read from wherever the
    producer writes its document, or ``None`` if there was nothing to read
    (the harness must not substitute ``"{}"`` or any other stand-in — a
    missing document reconciling against ``{}`` is vacuous, since an empty
    key set can never disagree with anything).

    ``document``: ``document_text`` decoded, or ``None`` if it was absent,
    or present but did not decode as JSON *at all* (a syntax error — not
    merely the wrong shape; "wrong shape" is ``document``'s own job to
    represent, by being something other than a ``dict``).
    """

    process_ok: bool
    process_detail: str
    document_text: str | None
    document: Any


def assert_reconciles(emitted: EmissionResult, ledger: dict[str, Any], component: str) -> None:
    """Assert ``emitted`` reconciles against ``ledger`` for ``component``.

    Four floors (contract Obligation 2.6), each raising a distinct,
    actionable :class:`AssertionError` so the evidence names which one was
    hit — then both reconciliation directions (Obligation 2.2-2.3):

    1. the harness's own judgement of the process outcome
    2. a document was produced at all (not absent)
    3. it parses as a JSON object — covers both "did not decode as JSON at
       all" and "decoded, but to something other than an object", as two
       distinct failures
    4. it has a non-empty key set — a harness that treated an absent
       document as ``{}`` would pass this vacuously; the absence floor
       above is what actually closes that hole
    5. no key the document emits is undeclared by the ledger (neither
       ``adjudicated`` nor ``diagnostic_only``)
    6. no key the ledger declares goes unemitted by the document (a stale
       declaration)
    """
    if not emitted.process_ok:
        raise AssertionError(
            f"{component}: producer process outcome unacceptable: {emitted.process_detail}"
        )
    if emitted.document_text is None:
        raise AssertionError(f"{component}: no document was produced (state absent)")
    if emitted.document is None:
        raise AssertionError(f"{component}: document did not decode as JSON at all")
    if not isinstance(emitted.document, dict):
        # This is a test-contract violation, not a Python type error --
        # AssertionError is the correct signal for pytest, hence the
        # suppression below.
        raise AssertionError(  # noqa: TRY004
            f"{component}: document decoded but is not a JSON object "
            f"(got {type(emitted.document).__name__})"
        )
    emitted_keys = set(emitted.document)
    if not emitted_keys:
        raise AssertionError(f"{component}: document parsed but emitted zero keys")

    ledger_keys = declared_keys(ledger)

    undeclared = sorted(emitted_keys - ledger_keys)
    if undeclared:
        raise AssertionError(
            f"{component}: producer emits undeclared key(s) {undeclared} — "
            "add each to the ledger's adjudicated or diagnostic_only, or stop emitting it"
        )

    stale = sorted(ledger_keys - emitted_keys)
    if stale:
        raise AssertionError(
            f"{component}: ledger declares key(s) {stale} the producer no longer emits — "
            "remove the stale declaration or restore emission"
        )


def assert_selection_matches(selected: set[str] | frozenset[str], inventory: dict[str, Any]) -> None:
    """Assert a reconciliation suite's ``selected`` component set is
    non-empty and equals — not a subset of — the full set of
    ledger-declaring components in ``inventory`` (contract Obligation 2.4).

    A ``selected`` set assembled by hand, rather than derived from
    :func:`load_ledgers`, is exactly how a component that grows a ledger
    goes silently unreconciled — the #913 failure mode this floor exists to
    catch. An empty ``selected`` set is a green suite with zero assertions
    executed, which is worse than no suite at all: it would certify the
    contract while enforcing nothing.
    """
    if not selected:
        raise AssertionError(
            "no ledgers selected for reconciliation — the reconciliation is not running"
        )
    declared = set(load_ledgers(inventory))
    missing = sorted(declared - selected)
    extra = sorted(selected - declared)
    if missing or extra:
        raise AssertionError(
            "reconciliation selection does not equal the ledger-declaring component set: "
            f"missing {missing}, unexpected {extra}"
        )


def assert_harness_paths_exist(ledgers: dict[str, dict[str, Any]], repo_root: Path) -> None:
    """Assert every declared ``reconciliation_harness`` path in ``ledgers``
    exists on disk, resolved relative to ``repo_root``.

    Moved here from the structural validator (contract "Structural rules"
    rule 8): a whole-tree existence check in the validator's pre-commit hook
    would fail every commit in the window between a ledger landing and its
    harness landing, since a harness must reconcile against a ledger that
    already exists — a window that cannot be reordered away. Here the check
    runs only when this suite runs, and (via :func:`assert_reconciles`,
    exercised alongside it) proves something the validator never could: not
    merely that the file exists, but that it reconciled.
    """
    for component, ledger in ledgers.items():
        harness = ledger.get("reconciliation_harness")
        if not isinstance(harness, str) or not harness.strip():
            raise AssertionError(f"{component}: reconciliation_harness is missing or not a string")
        path = repo_root / harness
        if not path.is_file():
            raise AssertionError(
                f"{component}: reconciliation_harness {harness!r} does not exist at {path}"
            )
