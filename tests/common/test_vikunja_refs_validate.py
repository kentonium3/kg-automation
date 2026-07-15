"""Unit tests for ``scripts.common.vikunja_refs_validate.validate`` (WP02,
mission ``vikunja-reference-seam-01KXK68Z``, kentonium3/kg-automation#748/#745).

These lock the drift finding taxonomy defined in
``kitty-specs/vikunja-reference-seam-01KXK68Z/data-model.md`` and
``contracts/vikunja-refs.contract.md``: ``missing`` | ``id_drift`` |
``title_drift`` | ``unprovisioned`` (the ``unreachable`` kind is a CLI-only
state, covered in ``tests/vikunja/test_validate_refs.py``).

Every test drives the **pure** ``validate`` over injected live data and an
injected in-memory registry (WP01's ``set_registry_for_test`` seam) — never the
real registry file, never the network.
"""
from __future__ import annotations

from typing import Any

import pytest

from scripts.common import vikunja_refs
from scripts.common.vikunja_refs_validate import ValidationFinding, validate


def _registry(
    *,
    projects: list[dict[str, Any]] | None = None,
    labels: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a well-formed in-memory registry (same shape as the JSON file)."""
    return {
        "schema_version": 1,
        "source_of_truth": "docs/design/vikunja-configuration-design.md",
        "last_verified_utc": "2026-07-15T00:00:00Z",
        "projects": projects if projects is not None else [],
        "labels": labels if labels is not None else [],
        "private_projects": [],
    }


_INBOX = {
    "name": "inbox",
    "selector": {"kind": "project_id", "value": 1},
    "title": "Inbox",
    "owner": "kent",
    "provisioned": True,
}
_PERSONAL_UNPROVISIONED = {
    "name": "personal",
    "selector": {"kind": "project_id", "value": None},
    "title": "Personal",
    "owner": "kent",
    "provisioned": False,
}
_QSCHEDULE = {
    "name": "q:schedule",
    "selector": {"kind": "label", "value": 23},
    "title": "q:schedule",
    "owner_token": "kent",
}
_FELIX_IGNORE_UNPROVISIONED = {
    "name": "felix:ignore",
    "selector": {"kind": "label", "value": None},
    "title": "felix:ignore",
    "owner_token": "kent",
}


@pytest.fixture
def install_registry():
    """Install a raw registry for one test; clear the override afterwards."""

    def _install(raw: dict[str, Any]) -> None:
        vikunja_refs.set_registry_for_test(raw)

    yield _install
    vikunja_refs.set_registry_for_test(None)


def _kinds(findings: list[ValidationFinding]) -> list[str]:
    return [f.kind for f in findings]


# ---------------------------------------------------------------------------
# Clean
# ---------------------------------------------------------------------------


def test_all_provisioned_and_matching_is_clean(install_registry) -> None:
    install_registry(_registry(projects=[_INBOX], labels=[_QSCHEDULE]))
    findings = validate(
        [{"id": 1, "title": "Inbox"}],
        {"kent": [{"id": 23, "title": "q:schedule"}]},
    )
    assert findings == []


# ---------------------------------------------------------------------------
# Project findings
# ---------------------------------------------------------------------------


def test_missing_project_when_title_and_id_absent(install_registry) -> None:
    install_registry(_registry(projects=[_INBOX]))
    findings = validate([{"id": 999, "title": "Something Else"}], {})
    assert _kinds(findings) == ["missing"]
    assert findings[0].ref_type == "project"
    assert findings[0].name == "inbox"


def test_id_drift_project_when_title_present_id_changed(install_registry) -> None:
    install_registry(_registry(projects=[_INBOX]))
    findings = validate([{"id": 42, "title": "Inbox"}], {})
    assert _kinds(findings) == ["id_drift"]
    assert "42" in findings[0].detail


def test_title_drift_project_when_id_present_title_changed(install_registry) -> None:
    install_registry(_registry(projects=[_INBOX]))
    findings = validate([{"id": 1, "title": "Renamed Inbox"}], {})
    assert _kinds(findings) == ["title_drift"]
    assert "Renamed Inbox" in findings[0].detail


def test_unprovisioned_project_fires_regardless_of_live(install_registry) -> None:
    install_registry(_registry(projects=[_PERSONAL_UNPROVISIONED]))
    findings = validate([{"id": 20, "title": "Personal"}], {})
    assert _kinds(findings) == ["unprovisioned"]
    assert findings[0].ref_type == "project"
    assert findings[0].name == "personal"


# ---------------------------------------------------------------------------
# Label findings (within a token namespace)
# ---------------------------------------------------------------------------


def test_label_clean_within_token(install_registry) -> None:
    install_registry(_registry(labels=[_QSCHEDULE]))
    findings = validate([], {"kent": [{"id": 23, "title": "q:schedule"}]})
    assert findings == []


def test_label_id_drift_within_token(install_registry) -> None:
    install_registry(_registry(labels=[_QSCHEDULE]))
    findings = validate([], {"kent": [{"id": 77, "title": "q:schedule"}]})
    assert _kinds(findings) == ["id_drift"]
    assert findings[0].ref_type == "label"


def test_label_missing_when_token_namespace_empty(install_registry) -> None:
    # The label is declared for owner_token "kent"; live labels are provided only
    # under a different token, so kent's namespace is empty → missing (namespace
    # isolation, #715).
    install_registry(_registry(labels=[_QSCHEDULE]))
    findings = validate([], {"felix": [{"id": 23, "title": "q:schedule"}]})
    assert _kinds(findings) == ["missing"]
    assert findings[0].name == "q:schedule"


def test_felix_ignore_reports_unprovisioned_not_missing(install_registry) -> None:
    # WP01's live probe found felix:ignore does NOT exist in Vikunja → seeded
    # value:null. Against live data it must surface as `unprovisioned`, NOT
    # `missing` (FR-009 distinction). This is the live-data path the context flags.
    install_registry(_registry(labels=[_FELIX_IGNORE_UNPROVISIONED]))
    findings = validate([], {"kent": []})
    assert _kinds(findings) == ["unprovisioned"]
    assert findings[0].ref_type == "label"
    assert findings[0].name == "felix:ignore"


# ---------------------------------------------------------------------------
# All findings returned in one pass
# ---------------------------------------------------------------------------


def test_all_findings_returned_in_single_pass(install_registry) -> None:
    install_registry(
        _registry(
            projects=[_INBOX, _PERSONAL_UNPROVISIONED],
            labels=[_QSCHEDULE, _FELIX_IGNORE_UNPROVISIONED],
        )
    )
    findings = validate(
        [{"id": 42, "title": "Inbox"}],  # id_drift on inbox
        {"kent": [{"id": 77, "title": "q:schedule"}]},  # id_drift on q:schedule
    )
    kinds = sorted(_kinds(findings))
    # inbox id_drift, personal unprovisioned, q:schedule id_drift, felix:ignore unprovisioned
    assert kinds == ["id_drift", "id_drift", "unprovisioned", "unprovisioned"]


def test_validate_is_pure_tolerates_none_live(install_registry) -> None:
    # Vikunja returns null for an empty collection; validate must tolerate it and
    # not perform any I/O.
    install_registry(_registry(projects=[_INBOX]))
    findings = validate(None, {})
    assert _kinds(findings) == ["missing"]
