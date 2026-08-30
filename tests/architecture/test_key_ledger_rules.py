"""Structural rules for ``health_check.key_ledger`` (pointer-key-ledger-01M189P6 WP02).

``contracts/key-ledger.md`` defines the ``key_ledger`` shape and eight
structural rules, enforced by ``tooling/scripts/validate_architecture_data.py``.
This module is red-first: each rule below gets a failing case (a fixture that
violates exactly that rule) plus, where the contract specifies it, a passing
case that must NOT be flagged.

Two negative cases matter as much as the positive ones, and are asserted
first: a component with no ``key_ledger`` validates clean, and a well-formed
ledger validates clean. These are what stop an over-broad rule from
reddening the 16 ledger-free pointer-emitting components.

Loaded the same way as ``tests/tooling/test_validate_architecture_data.py``
(the module is a standalone script, not an importable package).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "tooling" / "scripts" / "validate_architecture_data.py"

_spec = importlib.util.spec_from_file_location("validate_architecture_data", _SCRIPT)
vad = importlib.util.module_from_spec(_spec)
sys.modules["validate_architecture_data"] = vad
assert _spec.loader is not None
_spec.loader.exec_module(vad)


def _rules(findings) -> list[str]:
    return sorted(f.rule for f in findings)


def _validate(doc: dict):
    return vad.validate_document(doc, "test.json")


# A path that genuinely exists in this repo, used as the "reconciliation
# harness exists" fixture value — the point under test is the ledger
# structure, not the real restic reconciliation test.
_EXISTING_PATH = "tooling/scripts/validate_architecture_data.py"
_NONEXISTENT_PATH = "tests/office2/restic_backup/does_not_exist_at_all.py"

# A ledger that satisfies all eight structural rules, mirroring the shape in
# contracts/key-ledger.md § Shape (trimmed to a few representative keys —
# the full fourteen-key restic-backup ledger is authored in T009, not here).
WELL_FORMED_LEDGER = {
    "reconciliation_harness": _EXISTING_PATH,
    "adjudicated": {
        "schema_version": {"good_values": [2]},
        "restic_exit_code": {"good_values": [0, 3]},
        "prune_exit_code": {"good_values": [0]},
        "integrity_check_passed": {"good_values": [True, None]},
        "snapshot_timestamp_utc": {"freshness": True, "anchor": True},
        "last_integrity_check_utc": {"freshness": True, "max_age_seconds": 777600},
        "snapshot_count": {"minimum": 2, "unmeasured_is_unknown": True},
        "repo_fs_free_bytes": {"minimum": 53687091200},
    },
    "diagnostic_only": {
        "snapshot_id": {"reason": "Identifier for investigation; carries no health meaning."},
        "script_finished_at_utc": {
            "reason": "Separate cron-finished witness. Deliberately NOT a freshness "
            "fallback: a run producing no snapshot once read fresh through it (#902/FR-009)."
        },
    },
}


def _entry(key_ledger, *, method="state-file", **hc_extra):
    """A minimal service entry carrying the given key_ledger on its health_check.

    Carries a ``max_age_seconds`` by default so the unrelated
    ``max-age-missing`` advisory rule (alert-eligible freshness checks
    without a bound) doesn't pollute exact-equality assertions in these
    tests — that rule is outside this WP's scope.
    """
    hc = {"method": method, "key_ledger": key_ledger, "max_age_seconds": 100800}
    hc.update(hc_extra)
    return {
        "last_updated": "2026-08-30",
        "services": [
            {
                "name": "fixture-component",
                "type": "cron",
                "status": "active",
                "health_check": hc,
            }
        ],
    }


def _doc(entry_dict):
    """Wrap a bare entry dict (already carrying last_updated/services) as a doc."""
    return entry_dict


# --------------------------------------------------------------------------- #
# Negative cases first: absence stays legal, and a well-formed ledger is clean.
# These are the over-broad-rule guard.
# --------------------------------------------------------------------------- #

def test_component_with_no_key_ledger_validates_clean():
    doc = {
        "last_updated": "2026-08-30",
        "services": [
            {
                "name": "ledger-free-component",
                "type": "cron",
                "status": "active",
                "health_check": {
                    "method": "state-file",
                    "state_path": "/data/services/x/state/last.json",
                    "max_age_seconds": 100800,
                },
            }
        ],
    }
    assert _validate(doc) == []


# --------------------------------------------------------------------------- #
# Regression (review cycle 1): `hc.get("key_ledger")` returns None for both
# "absent" (legal) and "present but null" (malformed) — collapsing those two
# via an early return on None made `"key_ledger": null` validate clean. The
# fix distinguishes them with `"key_ledger" not in hc`. A present-but-empty
# declaration is exactly the shape this mission exists to make impossible, so
# it must not be writable; absence, by contrast, must keep validating clean
# for the 16 components with no ledger at all.
# --------------------------------------------------------------------------- #

def test_null_key_ledger_is_flagged():
    doc = _doc(_entry(None))
    assert "key-ledger-shape" in _rules(_validate(doc))


def test_string_key_ledger_is_flagged():
    doc = _doc(_entry("not a ledger"))
    assert "key-ledger-shape" in _rules(_validate(doc))


def test_list_key_ledger_is_flagged():
    doc = _doc(_entry([]))
    assert "key-ledger-shape" in _rules(_validate(doc))


def test_absent_key_ledger_still_validates_clean():
    # Must not regress: this is the guard 16 ledger-free components depend on.
    doc = {
        "last_updated": "2026-08-30",
        "services": [
            {
                "name": "still-ledger-free",
                "type": "cron",
                "status": "active",
                "health_check": {
                    "method": "state-file",
                    "state_path": "/data/services/y/state/last.json",
                    "max_age_seconds": 100800,
                },
            }
        ],
    }
    assert _validate(doc) == []


def test_well_formed_ledger_validates_clean():
    doc = _doc(_entry(WELL_FORMED_LEDGER))
    assert _validate(doc) == []


def test_nested_predicate_object_alone_does_not_trigger_a_finding():
    """The validator walks every nested dict (_iter_objects), so a per-key
    predicate object like {"good_values": [0, 3]} is yielded as its own
    "entry". It carries no health_check field, so the key-ledger rule must
    not fire on it directly — only entries that carry a health_check are
    examined. This is the central over-broad-gating trap named in the WP.
    """
    doc = {
        "last_updated": "2026-08-30",
        # A bare predicate-shaped fragment with no owning health_check.
        "scratch": {"good_values": [0, 3]},
    }
    assert _validate(doc) == []


# --------------------------------------------------------------------------- #
# Rule 1 — key_ledger contains only adjudicated / diagnostic_only /
# reconciliation_harness.
# --------------------------------------------------------------------------- #

def test_unknown_member_key_is_flagged():
    ledger = dict(WELL_FORMED_LEDGER)
    ledger["extra_field"] = "not allowed"
    doc = _doc(_entry(ledger))
    assert "key-ledger-unknown-member" in _rules(_validate(doc))


# --------------------------------------------------------------------------- #
# Rule 2 — adjudicated is an object; diagnostic_only entries carry a
# non-empty reason.
# --------------------------------------------------------------------------- #

def test_adjudicated_not_an_object_is_flagged():
    ledger = dict(WELL_FORMED_LEDGER)
    ledger["adjudicated"] = ["not", "a", "dict"]
    doc = _doc(_entry(ledger))
    assert "key-ledger-adjudicated-shape" in _rules(_validate(doc))


def test_diagnostic_only_entry_missing_reason_is_flagged():
    ledger = dict(WELL_FORMED_LEDGER)
    ledger["diagnostic_only"] = dict(WELL_FORMED_LEDGER["diagnostic_only"])
    ledger["diagnostic_only"]["repo_size_bytes"] = {}  # no "reason"
    doc = _doc(_entry(ledger))
    assert "key-ledger-diagnostic-missing-reason" in _rules(_validate(doc))


def test_diagnostic_only_entry_with_empty_reason_is_flagged():
    ledger = dict(WELL_FORMED_LEDGER)
    ledger["diagnostic_only"] = dict(WELL_FORMED_LEDGER["diagnostic_only"])
    ledger["diagnostic_only"]["repo_size_bytes"] = {"reason": "   "}
    doc = _doc(_entry(ledger))
    assert "key-ledger-diagnostic-missing-reason" in _rules(_validate(doc))


# --------------------------------------------------------------------------- #
# Rule 3 — a key in both adjudicated and diagnostic_only is a hard error,
# never resolved by precedence.
# --------------------------------------------------------------------------- #

def test_key_in_both_adjudicated_and_diagnostic_only_is_a_hard_error():
    ledger = {
        "reconciliation_harness": _EXISTING_PATH,
        "adjudicated": {"restic_exit_code": {"good_values": [0, 3]}},
        "diagnostic_only": {"restic_exit_code": {"reason": "duplicated on purpose"}},
    }
    doc = _doc(_entry(ledger))
    findings = _validate(doc)
    assert "key-ledger-key-in-both-lists" in _rules(findings)
    dupe = next(f for f in findings if f.rule == "key-ledger-key-in-both-lists")
    assert "restic_exit_code" in dupe.detail


# --------------------------------------------------------------------------- #
# Rule 4 — exactly one predicate field per adjudicated key; modifiers are
# permitted only from that predicate's allow-list.
# --------------------------------------------------------------------------- #

def test_zero_predicates_on_an_adjudicated_key_is_flagged():
    ledger = {
        "reconciliation_harness": _EXISTING_PATH,
        "adjudicated": {"restic_exit_code": {}},
    }
    doc = _doc(_entry(ledger))
    assert "key-ledger-predicate-count" in _rules(_validate(doc))


def test_two_predicates_on_one_key_is_flagged():
    ledger = {
        "reconciliation_harness": _EXISTING_PATH,
        "adjudicated": {"restic_exit_code": {"good_values": [0, 3], "minimum": 0}},
    }
    doc = _doc(_entry(ledger))
    assert "key-ledger-predicate-count" in _rules(_validate(doc))


def test_modifier_field_outside_its_predicates_allowlist_is_flagged():
    # "anchor" is a freshness modifier; it is not on good_values' allow-list
    # (which is empty), so declaring it there is a structural error.
    ledger = {
        "reconciliation_harness": _EXISTING_PATH,
        "adjudicated": {"restic_exit_code": {"good_values": [0, 3], "anchor": True}},
    }
    doc = _doc(_entry(ledger))
    assert "key-ledger-unrecognised-modifier" in _rules(_validate(doc))


def test_allowlisted_modifiers_do_not_trigger_a_finding():
    # unmeasured_is_unknown/suppress_until_utc for minimum, anchor/
    # max_age_seconds for freshness — all on their predicate's allow-list.
    ledger = {
        "reconciliation_harness": _EXISTING_PATH,
        "adjudicated": {
            "snapshot_count": {
                "minimum": 2,
                "unmeasured_is_unknown": True,
                "suppress_until_utc": "2026-09-30T00:00:00Z",
            },
            "snapshot_timestamp_utc": {"freshness": True, "anchor": True},
            "last_integrity_check_utc": {"freshness": True, "max_age_seconds": 777600},
        },
    }
    doc = _doc(_entry(ledger))
    assert _validate(doc) == []


# --------------------------------------------------------------------------- #
# Rule 5 — good_values is a non-empty array of scalars/null; minimum is a
# number.
# --------------------------------------------------------------------------- #

def test_empty_good_values_array_is_flagged():
    ledger = {
        "reconciliation_harness": _EXISTING_PATH,
        "adjudicated": {"restic_exit_code": {"good_values": []}},
    }
    doc = _doc(_entry(ledger))
    assert "key-ledger-good-values-malformed" in _rules(_validate(doc))


def test_non_numeric_minimum_is_flagged():
    ledger = {
        "reconciliation_harness": _EXISTING_PATH,
        "adjudicated": {"snapshot_count": {"minimum": "two"}},
    }
    doc = _doc(_entry(ledger))
    assert "key-ledger-minimum-malformed" in _rules(_validate(doc))


# --------------------------------------------------------------------------- #
# Rule 6 — a ledger may only appear on a health_check whose method reads a
# JSON document.
# --------------------------------------------------------------------------- #

def test_ledger_on_non_pointer_method_is_flagged():
    doc = _doc(_entry(WELL_FORMED_LEDGER, method="http"))
    assert "key-ledger-ineligible-method" in _rules(_validate(doc))


def test_ledger_on_each_pointer_method_is_not_flagged_for_method():
    for method in ("state-file", "tick-signal-file", "signal-file"):
        doc = _doc(_entry(WELL_FORMED_LEDGER, method=method))
        rules = _rules(_validate(doc))
        assert "key-ledger-ineligible-method" not in rules


# --------------------------------------------------------------------------- #
# Rule 7 — at most one key declares freshness with anchor: true. Other
# freshness keys with their own max_age_seconds and no anchor are legal —
# v1 of the contract forbade more than one freshness key outright and
# contradicted its own ledger; that was caught in post-plan review and fixed.
# --------------------------------------------------------------------------- #

def test_two_anchors_is_flagged():
    ledger = {
        "reconciliation_harness": _EXISTING_PATH,
        "adjudicated": {
            "snapshot_timestamp_utc": {"freshness": True, "anchor": True},
            "last_integrity_check_utc": {"freshness": True, "anchor": True},
        },
    }
    doc = _doc(_entry(ledger))
    assert "key-ledger-multiple-anchors" in _rules(_validate(doc))


def test_one_anchor_plus_a_non_anchor_freshness_key_is_not_flagged():
    ledger = {
        "reconciliation_harness": _EXISTING_PATH,
        "adjudicated": {
            "snapshot_timestamp_utc": {"freshness": True, "anchor": True},
            "last_integrity_check_utc": {"freshness": True, "max_age_seconds": 777600},
        },
    }
    doc = _doc(_entry(ledger))
    assert _validate(doc) == []


# --------------------------------------------------------------------------- #
# Rule 8 — reconciliation_harness is required when key_ledger is present, and
# must be a non-empty, repo-relative path string.
#
# Presence and SHAPE only — the validator does not check that the file
# exists. Revised 2026-08-30 (contract e9df2666) after this exact rule, in an
# earlier existence-checking form, deadlocked WP02: the harness is WP05's to
# create, WP05 depends on WP02, and the harness must reconcile against a
# ledger that already exists, so the window can't be closed by reordering.
# The validator also runs whole-tree in the pre-commit hook, so an existence
# check would fail every commit for the entire window between the ledger
# landing and its harness landing. The existence-and-binding assertion moved
# to WP05's reconciliation (Obligation 2), which can prove the harness
# actually produced the document being reconciled — strictly stronger than a
# validator merely confirming a path resolves.
# --------------------------------------------------------------------------- #

def test_missing_reconciliation_harness_is_flagged():
    ledger = {"adjudicated": {"restic_exit_code": {"good_values": [0, 3]}}}
    doc = _doc(_entry(ledger))
    assert "key-ledger-missing-harness" in _rules(_validate(doc))


def test_empty_string_reconciliation_harness_is_flagged():
    ledger = {
        "reconciliation_harness": "   ",
        "adjudicated": {"restic_exit_code": {"good_values": [0, 3]}},
    }
    doc = _doc(_entry(ledger))
    assert "key-ledger-missing-harness" in _rules(_validate(doc))


def test_non_string_reconciliation_harness_is_flagged():
    ledger = {
        "reconciliation_harness": 42,
        "adjudicated": {"restic_exit_code": {"good_values": [0, 3]}},
    }
    doc = _doc(_entry(ledger))
    assert "key-ledger-missing-harness" in _rules(_validate(doc))


def test_absolute_path_reconciliation_harness_is_flagged():
    # "repo-relative" is part of rule 8's shape requirement; an absolute path
    # is well-formed as a string but not repo-relative.
    ledger = {
        "reconciliation_harness": "/etc/passwd",
        "adjudicated": {"restic_exit_code": {"good_values": [0, 3]}},
    }
    doc = _doc(_entry(ledger))
    assert "key-ledger-missing-harness" in _rules(_validate(doc))


def test_well_formed_reconciliation_harness_naming_a_nonexistent_path_is_not_flagged():
    # This is the point of the 2026-08-30 change: a well-formed, repo-relative
    # path that does not (yet) exist on disk must NOT be flagged. restic-backup's
    # real declared harness (tests/office2/restic_backup/test_ledger_reconciliation.py)
    # is exactly this shape until WP05 creates it.
    ledger = {
        "reconciliation_harness": _NONEXISTENT_PATH,
        "adjudicated": {"restic_exit_code": {"good_values": [0, 3]}},
    }
    doc = _doc(_entry(ledger))
    assert _rules(_validate(doc)) == []


def test_well_formed_reconciliation_harness_naming_an_existing_path_is_not_flagged():
    ledger = {
        "reconciliation_harness": _EXISTING_PATH,
        "adjudicated": {"restic_exit_code": {"good_values": [0, 3]}},
    }
    doc = _doc(_entry(ledger))
    assert _rules(_validate(doc)) == []


# --------------------------------------------------------------------------- #
# Post-merge review of #934, Finding 1 — the validator must check predicate
# MODIFIER VALUES, not just their names. A malformed value (e.g.
# `"anchor": "true"`, a string) previously passed a name-only allow-list
# check, then read as "no anchor" at runtime — a freshness obligation with no
# bound that silently accepts any parseable timestamp.
# --------------------------------------------------------------------------- #

def _entry_without_hc_bound(key_ledger, *, method="state-file"):
    """Like ``_entry``, but the health_check carries NO max_age_seconds of its
    own — used to test the "no effective bound anywhere" case, which ``_entry``'s
    default 100800s hc-level bound would otherwise mask.
    """
    return {
        "last_updated": "2026-08-30",
        "services": [
            {
                "name": "fixture-component-no-hc-bound",
                "type": "cron",
                "status": "active",
                "health_check": {"method": method, "key_ledger": key_ledger},
            }
        ],
    }


def test_anchor_string_true_is_flagged():
    # The exact case from the finding: "true" (a JSON string), not the
    # literal boolean, so the validator must check the VALUE's type.
    ledger = {
        "reconciliation_harness": _EXISTING_PATH,
        "adjudicated": {"snapshot_timestamp_utc": {"freshness": True, "anchor": "true"}},
    }
    doc = _doc(_entry(ledger))
    assert "key-ledger-anchor-malformed" in _rules(_validate(doc))


def test_anchor_boolean_true_is_not_flagged():
    ledger = {
        "reconciliation_harness": _EXISTING_PATH,
        "adjudicated": {"snapshot_timestamp_utc": {"freshness": True, "anchor": True}},
    }
    doc = _doc(_entry(ledger))
    assert "key-ledger-anchor-malformed" not in _rules(_validate(doc))


def test_freshness_field_string_value_is_flagged():
    ledger = {
        "reconciliation_harness": _EXISTING_PATH,
        "adjudicated": {"snapshot_timestamp_utc": {"freshness": "true", "anchor": True}},
    }
    doc = _doc(_entry(ledger))
    assert "key-ledger-freshness-malformed" in _rules(_validate(doc))


def test_freshness_field_boolean_true_is_not_flagged():
    ledger = {
        "reconciliation_harness": _EXISTING_PATH,
        "adjudicated": {"snapshot_timestamp_utc": {"freshness": True, "anchor": True}},
    }
    doc = _doc(_entry(ledger))
    assert "key-ledger-freshness-malformed" not in _rules(_validate(doc))


def test_freshness_max_age_seconds_bool_is_flagged():
    ledger = {
        "reconciliation_harness": _EXISTING_PATH,
        "adjudicated": {
            "last_integrity_check_utc": {"freshness": True, "max_age_seconds": True},
        },
    }
    doc = _doc(_entry(ledger))
    assert "key-ledger-freshness-max-age-malformed" in _rules(_validate(doc))


def test_freshness_max_age_seconds_non_number_is_flagged():
    ledger = {
        "reconciliation_harness": _EXISTING_PATH,
        "adjudicated": {
            "last_integrity_check_utc": {"freshness": True, "max_age_seconds": "777600"},
        },
    }
    doc = _doc(_entry(ledger))
    assert "key-ledger-freshness-max-age-malformed" in _rules(_validate(doc))


def test_freshness_max_age_seconds_negative_is_flagged():
    ledger = {
        "reconciliation_harness": _EXISTING_PATH,
        "adjudicated": {
            "last_integrity_check_utc": {"freshness": True, "max_age_seconds": -1},
        },
    }
    doc = _doc(_entry(ledger))
    assert "key-ledger-freshness-max-age-malformed" in _rules(_validate(doc))


def test_freshness_max_age_seconds_valid_is_not_flagged():
    ledger = {
        "reconciliation_harness": _EXISTING_PATH,
        "adjudicated": {
            "last_integrity_check_utc": {"freshness": True, "max_age_seconds": 777600},
        },
    }
    doc = _doc(_entry(ledger))
    assert "key-ledger-freshness-max-age-malformed" not in _rules(_validate(doc))


def test_unmeasured_is_unknown_non_bool_is_flagged():
    ledger = {
        "reconciliation_harness": _EXISTING_PATH,
        "adjudicated": {
            "snapshot_count": {"minimum": 2, "unmeasured_is_unknown": "true"},
        },
    }
    doc = _doc(_entry(ledger))
    assert "key-ledger-unmeasured-is-unknown-malformed" in _rules(_validate(doc))


def test_unmeasured_is_unknown_bool_is_not_flagged():
    ledger = {
        "reconciliation_harness": _EXISTING_PATH,
        "adjudicated": {
            "snapshot_count": {"minimum": 2, "unmeasured_is_unknown": True},
        },
    }
    doc = _doc(_entry(ledger))
    assert "key-ledger-unmeasured-is-unknown-malformed" not in _rules(_validate(doc))


def test_suppress_until_utc_non_string_is_flagged():
    ledger = {
        "reconciliation_harness": _EXISTING_PATH,
        "adjudicated": {
            "snapshot_count": {"minimum": 2, "suppress_until_utc": 20260930},
        },
    }
    doc = _doc(_entry(ledger))
    assert "key-ledger-suppress-until-malformed" in _rules(_validate(doc))


def test_suppress_until_utc_unparseable_string_is_flagged():
    ledger = {
        "reconciliation_harness": _EXISTING_PATH,
        "adjudicated": {
            "snapshot_count": {"minimum": 2, "suppress_until_utc": "not-a-timestamp"},
        },
    }
    doc = _doc(_entry(ledger))
    assert "key-ledger-suppress-until-malformed" in _rules(_validate(doc))


def test_suppress_until_utc_well_formed_is_not_flagged():
    ledger = {
        "reconciliation_harness": _EXISTING_PATH,
        "adjudicated": {
            "snapshot_count": {"minimum": 2, "suppress_until_utc": "2026-09-30T00:00:00Z"},
        },
    }
    doc = _doc(_entry(ledger))
    assert "key-ledger-suppress-until-malformed" not in _rules(_validate(doc))


def test_freshness_predicate_with_no_bound_anywhere_is_flagged():
    # No key-level max_age_seconds AND no hc-level max_age_seconds (the
    # anchor case: even the anchor must resolve to a bound — the runtime
    # "no freshness anchor declared" / unbounded-obligation path silently
    # accepts any parseable timestamp).
    ledger = {
        "reconciliation_harness": _EXISTING_PATH,
        "adjudicated": {"snapshot_timestamp_utc": {"freshness": True, "anchor": True}},
    }
    doc = _doc(_entry_without_hc_bound(ledger))
    assert "key-ledger-freshness-no-bound" in _rules(_validate(doc))


def test_non_anchor_freshness_predicate_with_no_bound_anywhere_is_flagged():
    ledger = {
        "reconciliation_harness": _EXISTING_PATH,
        "adjudicated": {"last_integrity_check_utc": {"freshness": True}},
    }
    doc = _doc(_entry_without_hc_bound(ledger))
    assert "key-ledger-freshness-no-bound" in _rules(_validate(doc))


def test_freshness_predicate_bound_by_hc_level_max_age_is_not_flagged():
    # No own max_age_seconds, but the health_check's covers it — legal
    # (contract: "uses the health_check's max_age_seconds unless the
    # predicate carries its own").
    ledger = {
        "reconciliation_harness": _EXISTING_PATH,
        "adjudicated": {"snapshot_timestamp_utc": {"freshness": True, "anchor": True}},
    }
    doc = _doc(_entry(ledger))  # _entry supplies hc.max_age_seconds=100800
    assert "key-ledger-freshness-no-bound" not in _rules(_validate(doc))


def test_freshness_predicate_bound_by_own_max_age_is_not_flagged():
    ledger = {
        "reconciliation_harness": _EXISTING_PATH,
        "adjudicated": {
            "last_integrity_check_utc": {"freshness": True, "max_age_seconds": 777600},
        },
    }
    doc = _doc(_entry_without_hc_bound(ledger))
    assert "key-ledger-freshness-no-bound" not in _rules(_validate(doc))
