"""Unit tests for the approved-cron baseline loader (WP02, #683).

Covers the happy path (loading the real seeded baseline plus a small
in-memory fixture), every malformed-input branch (each must raise
``BaselineError`` — never a silent empty list, per the fail-safe rule), and
the order-independence + change-sensitivity of ``baseline_hash``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.trust.cron_baseline import (
    ApprovedCron,
    BaselineError,
    DEFAULT_BASELINE_PATH,
    baseline_hash,
    load_baseline,
)

_VALID_ENTRY = {
    "name": "inbox-5pm",
    "agent_id": "felix-admin-capture",
    "schedule_expr": "0 17 * * *",
    "tz": "America/New_York",
    "purpose": "Scheduled inbox processing run.",
    "approved_by": "kent",
    "approved_at": "2026-07-10",
}


def _write_baseline(tmp_path: Path, document: dict) -> Path:
    path = tmp_path / "approved-crons.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _valid_document(entries: list[dict]) -> dict:
    return {"schema_version": 1, "crons": entries}


# --- Happy path -------------------------------------------------------------


def test_load_baseline_seeded_repo_file_has_seven_crons() -> None:
    """The real committed baseline seeds all 7 known legitimate crons."""
    entries = load_baseline(DEFAULT_BASELINE_PATH)

    assert len(entries) == 7
    names = {entry.name for entry in entries}
    assert names == {
        "inbox-5pm",
        "inbox-10pm",
        "inbox-7am",
        "inbox-noon",
        "habits-morning-checkin",
        "habits-weekly-report",
        "escalation-daily",
    }
    for entry in entries:
        assert isinstance(entry, ApprovedCron)
        assert entry.approved_by == "kent"


def test_load_baseline_valid_fixture(tmp_path: Path) -> None:
    path = _write_baseline(tmp_path, _valid_document([_VALID_ENTRY]))

    entries = load_baseline(path)

    assert entries == [ApprovedCron(**_VALID_ENTRY)]


def test_load_baseline_accepts_str_path(tmp_path: Path) -> None:
    path = _write_baseline(tmp_path, _valid_document([_VALID_ENTRY]))

    entries = load_baseline(str(path))

    assert len(entries) == 1


# --- Malformed input: each raises BaselineError, never [] -------------------


def test_load_baseline_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.json"

    with pytest.raises(BaselineError):
        load_baseline(missing)


def test_load_baseline_unreadable_file_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-FileNotFoundError OSError (e.g. permission denied) must also
    raise BaselineError, not propagate as a raw OSError."""
    path = _write_baseline(tmp_path, _valid_document([_VALID_ENTRY]))

    import scripts.trust.cron_baseline as cron_baseline_module

    def _raise_permission_error(self: Path, *args: object, **kwargs: object) -> str:
        raise PermissionError("permission denied")

    monkeypatch.setattr(
        cron_baseline_module.Path, "read_text", _raise_permission_error
    )

    with pytest.raises(BaselineError):
        load_baseline(path)


def test_load_baseline_bad_json(tmp_path: Path) -> None:
    path = tmp_path / "approved-crons.json"
    path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(BaselineError):
        load_baseline(path)


def test_load_baseline_not_a_json_object(tmp_path: Path) -> None:
    path = tmp_path / "approved-crons.json"
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    with pytest.raises(BaselineError):
        load_baseline(path)


def test_load_baseline_missing_schema_version(tmp_path: Path) -> None:
    path = _write_baseline(tmp_path, {"crons": [_VALID_ENTRY]})

    with pytest.raises(BaselineError):
        load_baseline(path)


def test_load_baseline_missing_crons_key(tmp_path: Path) -> None:
    path = _write_baseline(tmp_path, {"schema_version": 1})

    with pytest.raises(BaselineError):
        load_baseline(path)


def test_load_baseline_crons_not_a_list(tmp_path: Path) -> None:
    path = _write_baseline(tmp_path, {"schema_version": 1, "crons": {"oops": True}})

    with pytest.raises(BaselineError):
        load_baseline(path)


def test_load_baseline_entry_not_an_object(tmp_path: Path) -> None:
    path = _write_baseline(tmp_path, _valid_document(["not-a-dict"]))

    with pytest.raises(BaselineError):
        load_baseline(path)


# tz is optional (host default-timezone crons omit it) — see the positive test
# below; all other fields remain required.
@pytest.mark.parametrize("missing_field", sorted(k for k in _VALID_ENTRY if k != "tz"))
def test_load_baseline_missing_required_field(tmp_path: Path, missing_field: str) -> None:
    entry = dict(_VALID_ENTRY)
    del entry[missing_field]
    path = _write_baseline(tmp_path, _valid_document([entry]))

    with pytest.raises(BaselineError):
        load_baseline(path)


@pytest.mark.parametrize("tz_variant", ["absent", "empty"])
def test_load_baseline_tz_optional_defaults_empty(tmp_path: Path, tz_variant: str) -> None:
    # A host default-timezone cron omits schedule.tz in the live payload, so the
    # baseline must accept an absent or empty tz and normalize it to "" (a
    # non-empty sentinel would produce a spurious schedule_mismatch — #683 deploy).
    entry = dict(_VALID_ENTRY)
    if tz_variant == "absent":
        del entry["tz"]
    else:
        entry["tz"] = ""
    path = _write_baseline(tmp_path, _valid_document([entry]))

    crons = load_baseline(path)
    assert len(crons) == 1
    assert crons[0].tz == ""


def test_load_baseline_blank_required_field(tmp_path: Path) -> None:
    entry = dict(_VALID_ENTRY)
    entry["purpose"] = "   "
    path = _write_baseline(tmp_path, _valid_document([entry]))

    with pytest.raises(BaselineError):
        load_baseline(path)


def test_load_baseline_duplicate_name(tmp_path: Path) -> None:
    second = dict(_VALID_ENTRY)
    second["agent_id"] = "some-other-agent"
    path = _write_baseline(tmp_path, _valid_document([_VALID_ENTRY, second]))

    with pytest.raises(BaselineError):
        load_baseline(path)


# --- baseline_hash: order-independent, change-sensitive ---------------------


def test_baseline_hash_stable_across_reordering() -> None:
    entry_a = ApprovedCron(**_VALID_ENTRY)
    entry_b = ApprovedCron(
        **{
            **_VALID_ENTRY,
            "name": "inbox-10pm",
            "schedule_expr": "0 22 * * *",
        }
    )

    hash_forward = baseline_hash([entry_a, entry_b])
    hash_reversed = baseline_hash([entry_b, entry_a])

    assert hash_forward == hash_reversed


def test_baseline_hash_changes_when_field_changes() -> None:
    entry = ApprovedCron(**_VALID_ENTRY)
    changed = ApprovedCron(**{**_VALID_ENTRY, "schedule_expr": "0 18 * * *"})

    assert baseline_hash([entry]) != baseline_hash([changed])


def test_baseline_hash_deterministic_same_input() -> None:
    entry = ApprovedCron(**_VALID_ENTRY)

    assert baseline_hash([entry]) == baseline_hash([entry])


def test_baseline_hash_empty_list_is_stable() -> None:
    assert baseline_hash([]) == baseline_hash([])
