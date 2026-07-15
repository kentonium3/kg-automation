"""Tests for scripts/sync/classify.py (WP03 / T012).

Pure tests — no I/O. Exhaustive classification matrix + UC-4 inversion.
"""
from __future__ import annotations

import pytest

from scripts.common import vikunja_refs
from scripts.common.vikunja_refs import VikunjaRefError
from scripts.sync import classify as c
from scripts.sync.diff import DivergenceCandidate


TS = "2026-06-04T19:25:30Z"

# felix:ignore's id when we model it as PROVISIONED in an injected registry.
IGNORE_ID = 42


def _candidate(field: str = "title", entity_id: int = 14) -> DivergenceCandidate:
    return DivergenceCandidate(
        vikunja_entity_id=entity_id,
        field=field,
        vikunja_value="new",
        felix_cached_value="old",
        vikunja_updated_at="2026-06-04T18:32:00Z",
        ts_observed_utc=TS,
    )


# ---------------------------------------------------------------------------
# Registry fixtures (WP04 / T017) — model the felix:ignore label's provisioning
# state via the WP01 injectable seam. Every test resets the override afterwards
# so no injected state leaks into the next test (or the real-registry default).
# ---------------------------------------------------------------------------


def _registry(*, felix_ignore_selector: dict | None, include_felix_ignore: bool = True) -> dict:
    """Build a raw registry mapping for injection.

    ``include_felix_ignore=False`` omits the label entirely (models a
    deleted/undeclared reference — the SC-002 fail-loud case).
    """
    labels: list[dict] = []
    if include_felix_ignore:
        labels.append(
            {
                "name": "felix:ignore",
                "selector": felix_ignore_selector,
                "title": "felix:ignore",
                "owner_token": "kent",
            }
        )
    return {
        "schema_version": 1,
        "source_of_truth": "test",
        "last_verified_utc": "2026-07-15T00:00:00Z",
        "projects": [],
        "labels": labels,
        "private_projects": [],
    }


def _install_provisioned() -> None:
    vikunja_refs.set_registry_for_test(
        _registry(felix_ignore_selector={"kind": "label", "value": IGNORE_ID})
    )


def _install_unprovisioned() -> None:
    vikunja_refs.set_registry_for_test(
        _registry(felix_ignore_selector={"kind": "label", "value": None})
    )


def _install_deleted() -> None:
    vikunja_refs.set_registry_for_test(_registry(felix_ignore_selector=None, include_felix_ignore=False))


@pytest.fixture(autouse=True)
def _reset_registry_override():
    """Clear any injected registry after every test (prevents cross-test leak)."""
    yield
    vikunja_refs.set_registry_for_test(None)


# ===========================================================================
# Group 1 — Constants
# ===========================================================================


class TestConstants:
    def test_reason_codes_tuple(self):
        assert c.REASON_CODES == (
            "uc1_uc2_divergence",
            "uc3_downstream_behavior",
            "uc4_manual_override",
        )

    def test_downstream_set_is_frozenset(self):
        assert isinstance(c.DOWNSTREAM_AFFECTING_FIELDS, frozenset)

    def test_downstream_set_contains_expected_fields(self):
        for name in ("due_date", "project_id", "done", "repeat_after", "repeat_mode", "title"):
            assert name in c.DOWNSTREAM_AFFECTING_FIELDS

    def test_override_label_literal(self):
        assert c.MANUAL_OVERRIDE_LABEL == "felix:ignore"

    def test_override_label_token_literal(self):
        # felix:ignore is resolved in kent's namespace (#715).
        assert c.MANUAL_OVERRIDE_LABEL_TOKEN == "kent"

    def test_override_title_prefix_literal(self):
        assert c.MANUAL_OVERRIDE_TITLE_PREFIX == "[NO FELIX]"

    def test_class_labels(self):
        assert c.CLASS_AUTO_RESOLVED == "auto_resolved"
        assert c.CLASS_UNSAFE == "unsafe_to_auto_resolve"


# ===========================================================================
# Group 2 — has_override_signal
# ===========================================================================


class TestHasOverrideSignal:
    # --- Title-prefix path (independent of label provisioning) ---

    def test_title_prefix_match_returns_true(self):
        task = {"title": "[NO FELIX] sensitive task"}
        assert c.has_override_signal(task) is True

    def test_title_substring_not_prefix_returns_false(self):
        _install_provisioned()
        task = {"title": "this has [NO FELIX] mid-string"}
        assert c.has_override_signal(task) is False

    # --- Variant 1: felix:ignore UNPROVISIONED -> graceful, no label override ---

    def test_unprovisioned_label_degrades_gracefully_no_crash(self):
        _install_unprovisioned()
        # A task carrying *some* label id (title even says felix:ignore) must NOT
        # be treated as an override while the label is unprovisioned — and must
        # not crash. The [NO FELIX] title path is the only live override.
        task = {"title": "Wake at 5", "labels": [{"id": 1, "title": "felix:ignore"}]}
        assert c.has_override_signal(task) is False

    def test_unprovisioned_label_title_prefix_still_works(self):
        _install_unprovisioned()
        task = {"title": "[NO FELIX] still overrides", "labels": []}
        assert c.has_override_signal(task) is True

    # --- Variant 2: felix:ignore PROVISIONED + matching id -> override ---

    def test_provisioned_label_matching_id_returns_true(self):
        _install_provisioned()
        task = {"title": "Wake at 5", "labels": [{"id": IGNORE_ID, "title": "felix:ignore"}]}
        assert c.has_override_signal(task) is True

    def test_provisioned_non_dict_label_item_skipped(self):
        _install_provisioned()
        task = {"title": "x", "labels": ["not-a-dict", {"id": IGNORE_ID, "title": "felix:ignore"}]}
        assert c.has_override_signal(task) is True

    # --- Variant 3: PROVISIONED but task id does NOT match -> no override
    #     (rename-proof: id comparison, not title) ---

    def test_provisioned_label_non_matching_id_returns_false(self):
        _install_provisioned()
        # Title claims felix:ignore, but the id differs from the resolved id.
        # Id-based resolution correctly does NOT treat this as an override.
        task = {"title": "x", "labels": [{"id": 999, "title": "felix:ignore"}]}
        assert c.has_override_signal(task) is False

    def test_provisioned_no_labels_no_prefix_returns_false(self):
        _install_provisioned()
        task = {"title": "Wake at 5", "labels": []}
        assert c.has_override_signal(task) is False

    def test_provisioned_missing_labels_field_treated_as_no_labels(self):
        _install_provisioned()
        task = {"title": "x"}
        assert c.has_override_signal(task) is False

    def test_provisioned_non_list_labels_treated_as_no_labels(self):
        _install_provisioned()
        task = {"title": "x", "labels": "not-a-list"}
        assert c.has_override_signal(task) is False

    # --- Variant 4: DELETED/undeclared reference -> fail loud (SC-002 / #743) ---

    def test_deleted_reference_raises_loudly(self):
        _install_deleted()
        task = {"title": "x", "labels": [{"id": IGNORE_ID, "title": "felix:ignore"}]}
        with pytest.raises(VikunjaRefError):
            c.has_override_signal(task)


# ===========================================================================
# Group 3 — Classification rule 1: uc1_uc2_divergence always fires
# ===========================================================================


class TestUc1Uc2Always:
    def test_unsafe_no_uc3_no_uc4(self):
        # ``labels`` is NOT in DOWNSTREAM_AFFECTING_FIELDS — no UC-3.
        result = c.classify(_candidate(field="labels"), task={"title": "x"})
        assert result.class_ == c.CLASS_UNSAFE
        assert result.unsafe_reasons == ("uc1_uc2_divergence",)

    def test_unsafe_with_uc3_due_date(self):
        result = c.classify(_candidate(field="due_date"), task={"title": "x"})
        assert result.class_ == c.CLASS_UNSAFE
        assert result.unsafe_reasons == ("uc1_uc2_divergence", "uc3_downstream_behavior")

    def test_unsafe_with_uc3_project_id(self):
        result = c.classify(_candidate(field="project_id"), task={"title": "x"})
        assert result.class_ == c.CLASS_UNSAFE
        assert "uc3_downstream_behavior" in result.unsafe_reasons

    def test_uc1_uc2_always_first_in_tuple(self):
        result = c.classify(_candidate(field="done"), task={"title": "x"})
        assert result.unsafe_reasons[0] == "uc1_uc2_divergence"


# ===========================================================================
# Group 4 — UC-4 inversion
# ===========================================================================


class TestUc4Inverts:
    def test_uc4_label_inverts_to_auto_resolved(self):
        _install_provisioned()
        task = {"title": "x", "labels": [{"id": IGNORE_ID, "title": "felix:ignore"}]}
        result = c.classify(_candidate(field="title"), task=task)
        assert result.class_ == c.CLASS_AUTO_RESOLVED
        assert "uc4_manual_override" in result.unsafe_reasons

    def test_uc4_title_prefix_inverts(self):
        task = {"title": "[NO FELIX] sensitive thing"}
        result = c.classify(_candidate(field="title"), task=task)
        assert result.class_ == c.CLASS_AUTO_RESOLVED
        assert "uc4_manual_override" in result.unsafe_reasons

    def test_uc4_dominates_uc3(self):
        _install_provisioned()
        # ``due_date`` is downstream-affecting; UC-3 would fire — but UC-4 wins.
        task = {"title": "x", "labels": [{"id": IGNORE_ID, "title": "felix:ignore"}]}
        result = c.classify(_candidate(field="due_date"), task=task)
        assert result.class_ == c.CLASS_AUTO_RESOLVED
        # All three reasons present.
        assert result.unsafe_reasons == (
            "uc1_uc2_divergence",
            "uc3_downstream_behavior",
            "uc4_manual_override",
        )

    def test_uc4_unprovisioned_label_does_not_invert(self):
        # Unprovisioned felix:ignore -> label override dormant. A divergence with
        # only a felix:ignore label (no title prefix) stays unsafe, gracefully.
        _install_unprovisioned()
        task = {"title": "x", "labels": [{"id": IGNORE_ID, "title": "felix:ignore"}]}
        result = c.classify(_candidate(field="title"), task=task)
        assert result.class_ == c.CLASS_UNSAFE
        assert "uc4_manual_override" not in result.unsafe_reasons

    def test_classify_fails_loud_on_deleted_reference(self):
        # SC-002 / #743: a broken (deleted/undeclared) felix:ignore reference must
        # NOT silently classify as "not overridden" — it propagates loudly.
        _install_deleted()
        task = {"title": "x", "labels": [{"id": IGNORE_ID, "title": "felix:ignore"}]}
        with pytest.raises(VikunjaRefError):
            c.classify(_candidate(field="title"), task=task)


# ===========================================================================
# Group 5 — Determinism
# ===========================================================================


class TestDeterminism:
    def test_same_inputs_same_output(self):
        candidate = _candidate(field="title")
        task = {"title": "x"}
        r1 = c.classify(candidate, task)
        r2 = c.classify(candidate, task)
        assert r1 == r2

    def test_classification_no_io_no_side_effects(self):
        # Just call classify many times with identical args; observed via
        # equality (frozen dataclass) — no global state mutation.
        candidate = _candidate(field="due_date")
        task = {"title": "x"}
        results = [c.classify(candidate, task) for _ in range(5)]
        assert all(r == results[0] for r in results)
