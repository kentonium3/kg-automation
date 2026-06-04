"""Tests for scripts/sync/classify.py (WP03 / T012).

Pure tests — no I/O. Exhaustive classification matrix + UC-4 inversion.
"""
from __future__ import annotations

from scripts.sync import classify as c
from scripts.sync.diff import DivergenceCandidate


TS = "2026-06-04T19:25:30Z"


def _candidate(field: str = "title", entity_id: int = 14) -> DivergenceCandidate:
    return DivergenceCandidate(
        vikunja_entity_id=entity_id,
        field=field,
        vikunja_value="new",
        felix_cached_value="old",
        vikunja_updated_at="2026-06-04T18:32:00Z",
        ts_observed_utc=TS,
    )


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

    def test_override_title_prefix_literal(self):
        assert c.MANUAL_OVERRIDE_TITLE_PREFIX == "[NO FELIX]"

    def test_class_labels(self):
        assert c.CLASS_AUTO_RESOLVED == "auto_resolved"
        assert c.CLASS_UNSAFE == "unsafe_to_auto_resolve"


# ===========================================================================
# Group 2 — has_override_signal
# ===========================================================================


class TestHasOverrideSignal:
    def test_no_labels_no_title_prefix_returns_false(self):
        task = {"title": "Wake at 5", "labels": []}
        assert c.has_override_signal(task) is False

    def test_label_match_returns_true(self):
        task = {
            "title": "Wake at 5",
            "labels": [{"id": 1, "title": "felix:ignore"}],
        }
        assert c.has_override_signal(task) is True

    def test_title_prefix_match_returns_true(self):
        task = {"title": "[NO FELIX] sensitive task"}
        assert c.has_override_signal(task) is True

    def test_title_substring_not_prefix_returns_false(self):
        task = {"title": "this has [NO FELIX] mid-string"}
        assert c.has_override_signal(task) is False

    def test_missing_labels_field_treated_as_no_labels(self):
        task = {"title": "x"}
        assert c.has_override_signal(task) is False

    def test_non_list_labels_treated_as_no_labels(self):
        task = {"title": "x", "labels": "not-a-list"}
        assert c.has_override_signal(task) is False

    def test_non_dict_label_item_skipped(self):
        task = {"title": "x", "labels": ["not-a-dict", {"id": 1, "title": "felix:ignore"}]}
        assert c.has_override_signal(task) is True


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
        task = {"title": "x", "labels": [{"id": 1, "title": "felix:ignore"}]}
        result = c.classify(_candidate(field="title"), task=task)
        assert result.class_ == c.CLASS_AUTO_RESOLVED
        assert "uc4_manual_override" in result.unsafe_reasons

    def test_uc4_title_prefix_inverts(self):
        task = {"title": "[NO FELIX] sensitive thing"}
        result = c.classify(_candidate(field="title"), task=task)
        assert result.class_ == c.CLASS_AUTO_RESOLVED
        assert "uc4_manual_override" in result.unsafe_reasons

    def test_uc4_dominates_uc3(self):
        # ``due_date`` is downstream-affecting; UC-3 would fire — but UC-4 wins.
        task = {"title": "x", "labels": [{"id": 1, "title": "felix:ignore"}]}
        result = c.classify(_candidate(field="due_date"), task=task)
        assert result.class_ == c.CLASS_AUTO_RESOLVED
        # All three reasons present.
        assert result.unsafe_reasons == (
            "uc1_uc2_divergence",
            "uc3_downstream_behavior",
            "uc4_manual_override",
        )


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
