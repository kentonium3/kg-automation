"""Unit tests for ``scripts.common.vikunja_scope`` (WP01, mission
``deterministic-cron-hardening-01KXA4PX``, kentonium3/kg-automation#723).

Per DIRECTIVE_034 the test surface is authored alongside the
implementation. Pure module — no I/O, no network — so no fixtures needed.

Test groups
-----------
- Accessors return the current (project_id) values.
- ``get_habit_selector()`` returns a copy (no shared-mutable-state leak).
- ``habit_project_id()`` resolves the int for project_id form, ``None``
  for a label form.
- Unknown ``kind`` raises ``ValueError``.
"""
from __future__ import annotations

import pytest

from scripts.common import vikunja_scope


# ---------------------------------------------------------------------------
# get_escalation_excluded_project_ids
# ---------------------------------------------------------------------------


def test_get_escalation_excluded_project_ids_returns_current_values() -> None:
    # Goals (11) was deleted by #717; only Habits (13) remains excluded (SC-006).
    assert vikunja_scope.get_escalation_excluded_project_ids() == [13]


def test_get_escalation_excluded_project_ids_returns_a_copy() -> None:
    result = vikunja_scope.get_escalation_excluded_project_ids()
    result.append(999)
    assert vikunja_scope.get_escalation_excluded_project_ids() == [13]


# ---------------------------------------------------------------------------
# get_habit_selector
# ---------------------------------------------------------------------------


def test_get_habit_selector_returns_project_id_form() -> None:
    assert vikunja_scope.get_habit_selector() == {
        "kind": "project_id",
        "value": 13,
    }


def test_get_habit_selector_returns_a_copy() -> None:
    selector = vikunja_scope.get_habit_selector()
    selector["value"] = 999
    selector["kind"] = "label"
    # Module state is untouched by mutating the returned dict.
    assert vikunja_scope.get_habit_selector() == {
        "kind": "project_id",
        "value": 13,
    }


# ---------------------------------------------------------------------------
# habit_project_id
# ---------------------------------------------------------------------------


def test_habit_project_id_returns_int_for_project_id_form() -> None:
    assert vikunja_scope.habit_project_id() == 13


def test_habit_project_id_returns_none_for_label_form(monkeypatch) -> None:
    monkeypatch.setattr(
        vikunja_scope,
        "HABIT_SELECTOR",
        {"kind": "label", "value": "t:habit"},
    )
    assert vikunja_scope.habit_project_id() is None


def test_habit_project_id_label_form_round_trips_via_get_habit_selector(
    monkeypatch,
) -> None:
    """Proves the #714 swap is config-only: flipping HABIT_SELECTOR to a
    label form round-trips correctly through get_habit_selector() even
    though habit_project_id() can't fetch it (label fetch is #716)."""
    monkeypatch.setattr(
        vikunja_scope,
        "HABIT_SELECTOR",
        {"kind": "label", "value": "t:habit"},
    )
    assert vikunja_scope.get_habit_selector() == {
        "kind": "label",
        "value": "t:habit",
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_get_habit_selector_unknown_kind_raises_value_error(monkeypatch) -> None:
    monkeypatch.setattr(
        vikunja_scope,
        "HABIT_SELECTOR",
        {"kind": "bogus", "value": 1},
    )
    with pytest.raises(ValueError):
        vikunja_scope.get_habit_selector()
