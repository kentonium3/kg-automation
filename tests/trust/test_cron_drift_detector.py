"""Unit tests for the cron-drift detector (WP02, #683).

Feeds canned JSON dicts (the C1 shape from
``kitty-specs/felix-truthful-reporting-01KX6MN5/contracts/detector-cli.md``)
and small in-memory baselines to ``detect_cron_drift``, asserting the finding
set for each scenario: exact match, each of the four finding kinds
(including the owner-mismatch variant of ``unapproved_present``), tolerant
parsing of unknown/missing fields, and the ``enumerate_live_crons`` fail-safe
wrapper (mocked subprocess boundary — never calls office2/openclaw).
"""

from __future__ import annotations

import json
import subprocess
from itertools import permutations

import pytest

from scripts.trust import cron_drift_detector as detector_mod
from scripts.trust.cron_baseline import ApprovedCron
from scripts.trust.cron_drift_detector import (
    KIND_APPROVED_MISSING,
    KIND_ENABLED_MISMATCH,
    KIND_SCHEDULE_MISMATCH,
    KIND_UNAPPROVED_PRESENT,
    CronEnumerationError,
    detect_cron_drift,
    enumerate_live_crons,
)

BASELINE_ENTRY = ApprovedCron(
    name="inbox-5pm",
    agent_id="felix-admin-capture",
    schedule_expr="0 17 * * *",
    tz="America/New_York",
    purpose="Scheduled inbox processing run.",
    approved_by="kent",
    approved_at="2026-07-10",
)


def _live_job(**overrides: object) -> dict:
    job = {
        "id": "4ea46768-fac9-4620-825e-5d0f8214238b",
        "name": "inbox-5pm",
        "enabled": True,
        "createdAtMs": 1775153265189,
        "agentId": "felix-admin-capture",
        "schedule": {"kind": "cron", "expr": "0 17 * * *", "tz": "America/New_York"},
    }
    job.update(overrides)
    return job


# --- exact-match / no drift --------------------------------------------------


def test_exact_match_produces_no_findings() -> None:
    findings = detect_cron_drift([_live_job()], [BASELINE_ENTRY])

    assert findings == []


def test_empty_live_and_empty_baseline_produces_no_findings() -> None:
    assert detect_cron_drift([], []) == []


# --- unapproved_present ------------------------------------------------------


def test_unapproved_present_for_live_cron_not_in_baseline() -> None:
    """A rogue cron alongside its baseline's own matched pair (so the only
    finding is the unapproved one — no unrelated approved_missing noise)."""
    approved_live = _live_job()
    rogue = _live_job(name="rogue-cron", id="rogue-id", agentId="felix-admin-capture")

    findings = detect_cron_drift([approved_live, rogue], [BASELINE_ENTRY])

    assert len(findings) == 1
    finding = findings[0]
    assert finding.kind == KIND_UNAPPROVED_PRESENT
    assert finding.name == "rogue-cron"
    assert finding.agent_id == "felix-admin-capture"
    assert finding.cron_id == "rogue-id"
    assert finding.schedule_expr == "0 17 * * *"
    assert finding.enabled is True
    assert finding.created_at_ms == 1775153265189


def test_owner_mismatch_is_unapproved_present_not_schedule_mismatch() -> None:
    """An approved `name` running under a *different* `agent_id` must be
    reported as `unapproved_present` (the incident-relevant owner-mismatch
    case), never silently passed or misreported as `schedule_mismatch`.

    Because the match key is `(name, agent_id)`, the hijacked job no longer
    matches the baseline entry by key, so the baseline entry also correctly
    reports `approved_missing` (its own approved `(name, agent_id)` truly
    has no live match) — assert on the `unapproved_present` finding
    specifically rather than asserting it is the only finding.
    """
    hijacked = _live_job(agentId="some-other-agent")

    findings = detect_cron_drift([hijacked], [BASELINE_ENTRY])

    unapproved = [f for f in findings if f.kind == KIND_UNAPPROVED_PRESENT]
    assert len(unapproved) == 1
    finding = unapproved[0]
    assert finding.name == "inbox-5pm"
    assert finding.agent_id == "some-other-agent"

    # And no schedule_mismatch was fabricated for the hijacked job — the
    # owner-mismatch path must not fall through to the matched-pair diff.
    assert all(f.kind != KIND_SCHEDULE_MISMATCH for f in findings)


# --- approved_missing ---------------------------------------------------------


def test_approved_missing_for_baseline_entry_with_no_live_match() -> None:
    findings = detect_cron_drift([], [BASELINE_ENTRY])

    assert len(findings) == 1
    finding = findings[0]
    assert finding.kind == KIND_APPROVED_MISSING
    assert finding.name == "inbox-5pm"
    assert finding.agent_id == "felix-admin-capture"
    assert finding.expected_schedule_expr == "0 17 * * *"


# --- schedule_mismatch --------------------------------------------------------


def test_schedule_mismatch_on_differing_expr() -> None:
    live = _live_job(schedule={"kind": "cron", "expr": "0 18 * * *", "tz": "America/New_York"})

    findings = detect_cron_drift([live], [BASELINE_ENTRY])

    assert len(findings) == 1
    finding = findings[0]
    assert finding.kind == KIND_SCHEDULE_MISMATCH
    assert finding.schedule_expr == "0 18 * * *"
    assert finding.expected_schedule_expr == "0 17 * * *"


def test_schedule_mismatch_on_differing_tz_only() -> None:
    live = _live_job(schedule={"kind": "cron", "expr": "0 17 * * *", "tz": "America/Chicago"})

    findings = detect_cron_drift([live], [BASELINE_ENTRY])

    assert len(findings) == 1
    finding = findings[0]
    assert finding.kind == KIND_SCHEDULE_MISMATCH
    # expr unchanged; tz drift alone still triggers schedule_mismatch.
    assert finding.schedule_expr == "0 17 * * *"
    assert finding.expected_schedule_expr == "0 17 * * *"


# --- enabled_mismatch ----------------------------------------------------------


def test_enabled_mismatch_when_live_disabled() -> None:
    live = _live_job(enabled=False)

    findings = detect_cron_drift([live], [BASELINE_ENTRY])

    assert len(findings) == 1
    finding = findings[0]
    assert finding.kind == KIND_ENABLED_MISMATCH
    assert finding.enabled is False


def test_schedule_and_enabled_mismatch_both_reported_independently() -> None:
    """A matched pair may legitimately produce both findings at once."""
    live = _live_job(
        enabled=False,
        schedule={"kind": "cron", "expr": "0 18 * * *", "tz": "America/New_York"},
    )

    findings = detect_cron_drift([live], [BASELINE_ENTRY])

    kinds = {finding.kind for finding in findings}
    assert kinds == {KIND_SCHEDULE_MISMATCH, KIND_ENABLED_MISMATCH}
    assert len(findings) == 2


# --- tolerant parse ------------------------------------------------------------


def test_tolerant_parse_extra_fields_and_missing_tz() -> None:
    live = {
        "id": "some-id",
        "name": "inbox-5pm",
        "enabled": True,
        "createdAtMs": 1775153265189,
        "agentId": "felix-admin-capture",
        "schedule": {"kind": "cron", "expr": "0 17 * * *"},  # no tz key
        "unknownField": {"nested": "value"},
        "state": {"lastRunStatus": "ok"},
    }

    findings = detect_cron_drift([live], [BASELINE_ENTRY])

    # Baseline tz is "America/New_York"; live tz is None (missing key) which
    # differs from the baseline, so this is a legitimate schedule_mismatch —
    # the point of this test is that parsing does not raise/crash on the
    # missing key or the unknown extra fields.
    assert len(findings) == 1
    assert findings[0].kind == KIND_SCHEDULE_MISMATCH


def test_tolerant_parse_missing_schedule_object_entirely() -> None:
    live = {
        "id": "some-id",
        "name": "rogue-no-schedule",
        "enabled": True,
        "createdAtMs": 1775153265189,
        "agentId": "felix-admin-capture",
    }

    # Must not raise despite the wholly-absent `schedule` key.
    findings = detect_cron_drift([live], [BASELINE_ENTRY])

    kinds_by_name = {f.name: f.kind for f in findings}
    assert kinds_by_name["rogue-no-schedule"] == KIND_UNAPPROVED_PRESENT


# --- deterministic ordering ----------------------------------------------------


def test_findings_are_sorted_deterministically() -> None:
    baseline = [
        BASELINE_ENTRY,
        ApprovedCron(
            name="zzz-approved",
            agent_id="felix-admin-capture",
            schedule_expr="0 0 * * *",
            tz="America/New_York",
            purpose="test",
            approved_by="kent",
            approved_at="2026-07-10",
        ),
    ]
    live = [_live_job(name="aaa-rogue", agentId="felix-admin-capture")]

    findings = detect_cron_drift(live, baseline)

    keys = [(f.kind, f.name, f.agent_id) for f in findings]
    assert keys == sorted(keys)


# --- enumerate_live_crons: fail-safe wrapper ------------------------------------


def _mock_completed(returncode: int, stdout: str, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["openclaw", "cron", "list", "--all", "--json"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_enumerate_live_crons_returns_jobs_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps({"jobs": [_live_job()]})
    monkeypatch.setattr(
        "scripts.trust.cron_drift_detector.subprocess.run",
        lambda *a, **k: _mock_completed(0, payload),
    )

    jobs = enumerate_live_crons()

    assert jobs == [_live_job()]


def test_enumerate_live_crons_genuinely_empty_jobs_returns_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A genuinely empty `jobs: []` payload must return `[]` — this is the
    valid "no crons" case, distinct from every failure case below."""
    payload = json.dumps({"jobs": []})
    monkeypatch.setattr(
        "scripts.trust.cron_drift_detector.subprocess.run",
        lambda *a, **k: _mock_completed(0, payload),
    )

    jobs = enumerate_live_crons()

    assert jobs == []


def test_enumerate_live_crons_nonzero_exit_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scripts.trust.cron_drift_detector.subprocess.run",
        lambda *a, **k: _mock_completed(1, "", stderr="openclaw: command failed"),
    )

    with pytest.raises(CronEnumerationError):
        enumerate_live_crons()


def test_enumerate_live_crons_non_json_output_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scripts.trust.cron_drift_detector.subprocess.run",
        lambda *a, **k: _mock_completed(0, "not json at all"),
    )

    with pytest.raises(CronEnumerationError):
        enumerate_live_crons()


def test_enumerate_live_crons_missing_jobs_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scripts.trust.cron_drift_detector.subprocess.run",
        lambda *a, **k: _mock_completed(0, json.dumps({"total": 0})),
    )

    with pytest.raises(CronEnumerationError):
        enumerate_live_crons()


def test_enumerate_live_crons_jobs_not_a_list_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scripts.trust.cron_drift_detector.subprocess.run",
        lambda *a, **k: _mock_completed(0, json.dumps({"jobs": "not-a-list"})),
    )

    with pytest.raises(CronEnumerationError):
        enumerate_live_crons()


def test_enumerate_live_crons_timeout_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_timeout(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd=["openclaw"], timeout=30)

    monkeypatch.setattr(
        "scripts.trust.cron_drift_detector.subprocess.run", _raise_timeout
    )

    with pytest.raises(CronEnumerationError):
        enumerate_live_crons()


def test_enumerate_live_crons_os_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_os_error(*args: object, **kwargs: object) -> None:
        raise OSError("openclaw binary not found")

    monkeypatch.setattr(
        "scripts.trust.cron_drift_detector.subprocess.run", _raise_os_error
    )

    with pytest.raises(CronEnumerationError):
        enumerate_live_crons()


def test_enumerate_live_crons_response_not_a_dict_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scripts.trust.cron_drift_detector.subprocess.run",
        lambda *a, **k: _mock_completed(0, json.dumps([1, 2, 3])),
    )

    with pytest.raises(CronEnumerationError):
        enumerate_live_crons()


def test_tz_omitted_in_live_payload_is_not_schedule_mismatch() -> None:
    """A host default-tz cron (baseline tz="" + live payload omits schedule.tz)
    must NOT be flagged as schedule_mismatch (#683 deploy regression)."""
    from scripts.trust.cron_baseline import ApprovedCron

    baseline = [
        ApprovedCron(
            name="escalation-daily",
            agent_id="felix-admin-escalation",
            schedule_expr="0 12 * * *",
            tz="",
            purpose="p",
            approved_by="kent",
            approved_at="2026-07-10",
        )
    ]
    live = [
        {
            "id": "abc",
            "name": "escalation-daily",
            "agentId": "felix-admin-escalation",
            "enabled": True,
            "schedule": {"kind": "cron", "expr": "0 12 * * *"},  # no tz key
        }
    ]
    assert detect_cron_drift(live, baseline) == []


def test_genuine_tz_change_still_flagged() -> None:
    """A real tz change (baseline America/New_York vs live omitting tz) IS drift."""
    from scripts.trust.cron_baseline import ApprovedCron

    baseline = [
        ApprovedCron(
            name="inbox-5pm",
            agent_id="felix-admin-capture",
            schedule_expr="0 17 * * *",
            tz="America/New_York",
            purpose="p",
            approved_by="kent",
            approved_at="2026-07-10",
        )
    ]
    live = [
        {
            "id": "abc",
            "name": "inbox-5pm",
            "agentId": "felix-admin-capture",
            "enabled": True,
            "schedule": {"kind": "cron", "expr": "0 17 * * *"},  # tz dropped → change
        }
    ]
    findings = detect_cron_drift(live, baseline)
    assert [f.kind for f in findings] == ["schedule_mismatch"]


# --- #1124: plugin-managed crons with agentId null ---------------------------
#
# OpenClaw 2026.11.7 plugin-managed crons (memory-core "Memory Dreaming
# Promotion") carry ``agentId: null`` and a ``declarationKey``. The detector
# must normalise these at the parse boundary: ``name`` is always a str,
# ``agent_id`` is ``str | None`` (None stays None — truthful: no owner), and a
# non-str non-None agent id is coerced with ``str()``.


def _memory_core_job(**overrides: object) -> dict:
    job = {
        "id": "7d1c2b9e-0000-4000-8000-memorycore01",
        "name": "Memory Dreaming Promotion",
        "agentId": None,
        "declarationKey": "memory-core:memory-dreaming-promotion",
        "enabled": True,
        "createdAtMs": 1795000000000,
        "schedule": {"kind": "cron", "expr": "0 3 * * *"},
    }
    job.update(overrides)
    return job


def test_null_agent_plugin_cron_is_unapproved_present_with_declaration_key() -> None:
    findings = detect_cron_drift([_live_job(), _memory_core_job()], [BASELINE_ENTRY])

    assert len(findings) == 1
    finding = findings[0]
    assert finding.kind == KIND_UNAPPROVED_PRESENT
    assert finding.name == "Memory Dreaming Promotion"
    assert finding.agent_id is None
    assert finding.declaration_key == "memory-core:memory-dreaming-promotion"
    assert finding.schedule_expr == "0 3 * * *"
    assert finding.enabled is True


def test_absent_agent_key_parses_as_none() -> None:
    job = _memory_core_job()
    del job["agentId"]

    findings = detect_cron_drift([job], [])

    assert len(findings) == 1
    assert findings[0].kind == KIND_UNAPPROVED_PRESENT
    assert findings[0].agent_id is None
    assert findings[0].declaration_key == "memory-core:memory-dreaming-promotion"


def test_declaration_key_absent_is_none() -> None:
    findings = detect_cron_drift([_live_job(name="rogue")], [BASELINE_ENTRY])

    unapproved = [f for f in findings if f.kind == KIND_UNAPPROVED_PRESENT]
    assert len(unapproved) == 1
    assert unapproved[0].declaration_key is None


def test_non_str_agent_id_coerced_to_str_alongside_none() -> None:
    findings = detect_cron_drift(
        [_memory_core_job(), _memory_core_job(id="other", agentId=42)], []
    )

    agents = sorted((f.agent_id for f in findings), key=lambda a: (a is None, a or ""))
    assert agents == ["42", None]
    assert all(f.kind == KIND_UNAPPROVED_PRESENT for f in findings)


def test_name_normalised_to_str_at_parse_boundary() -> None:
    findings = detect_cron_drift(
        [_memory_core_job(name=None), _memory_core_job(id="n", name=7, agentId="x")], []
    )

    names = sorted(f.name for f in findings)
    assert names == ["", "7"]
    assert all(isinstance(f.name, str) for f in findings)


def test_sort_same_kind_and_name_with_none_and_str_agent_does_not_raise() -> None:
    """Two findings sharing kind+name, one with agent None — ``sorted`` must not
    raise TypeError (which would lose the whole cron sub-scan)."""
    live = [
        _memory_core_job(name="dup", agentId=None),
        _memory_core_job(id="dup-x", name="dup", agentId="x"),
    ]

    findings = detect_cron_drift(live, [])

    assert [(f.name, f.agent_id) for f in findings] == [("dup", "x"), ("dup", None)]


# --- #1127: `--all` enumeration, enabled default-deny, pagination guard -------

_ABSENT = object()


def test_cron_list_argv_includes_all_so_disabled_jobs_are_enumerated() -> None:
    """Without --all, OpenClaw omits disabled jobs: a disabled approved cron
    would read as approved_missing and a disabled unapproved one as invisible."""
    argv = list(detector_mod.OPENCLAW_CRON_LIST_ARGV)
    assert argv[-4:] == ["cron", "list", "--all", "--json"]


@pytest.mark.parametrize(
    "value,expected_state,expected_raw",
    [
        (False, "false", None),
        (None, "absent", None),
        (_ABSENT, "absent", None),
        (1, "malformed", "1"),
        (0, "malformed", "0"),
        ("true", "malformed", "'true'"),
        ("false", "malformed", "'false'"),
        ([], "malformed", "[]"),
        ({"a": 1}, "malformed", "{'a': 1}"),
    ],
    ids=["False", "None", "absent", "1", "0", "str-true", "str-false", "list", "dict"],
)
def test_enabled_default_deny_matrix(value, expected_state, expected_raw) -> None:
    """Only a literal True counts as enabled; every other value (identity
    checks — 1/0 are NOT bools here) raises enabled_mismatch with its state."""
    live = _live_job()
    if value is _ABSENT:
        del live["enabled"]
    else:
        live["enabled"] = value

    findings = detect_cron_drift([live], [BASELINE_ENTRY])

    assert [f.kind for f in findings] == [KIND_ENABLED_MISMATCH]
    finding = findings[0]
    assert finding.enabled_state == expected_state
    assert finding.enabled_raw == expected_raw
    assert finding.enabled is (False if expected_state == "false" else None)


def test_enabled_literal_true_yields_no_finding() -> None:
    assert detect_cron_drift([_live_job(enabled=True)], [BASELINE_ENTRY]) == []


def test_enabled_raw_repr_truncated_to_64_chars() -> None:
    findings = detect_cron_drift([_live_job(enabled="x" * 500)], [BASELINE_ENTRY])

    assert findings[0].enabled_state == "malformed"
    assert findings[0].enabled_raw is not None
    assert len(findings[0].enabled_raw) == 64


def test_unapproved_disabled_cron_is_still_unapproved_present() -> None:
    findings = detect_cron_drift(
        [_live_job(), _live_job(id="r", name="rogue", enabled=False)], [BASELINE_ENTRY]
    )

    assert [(f.kind, f.name) for f in findings] == [(KIND_UNAPPROVED_PRESENT, "rogue")]
    assert findings[0].enabled is False
    assert findings[0].enabled_state == "false"


def test_enumerate_live_crons_has_more_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """A paginated (truncated) payload must fail safe, never be read as complete."""
    payload = json.dumps({"jobs": [_live_job()], "hasMore": True})
    monkeypatch.setattr(
        "scripts.trust.cron_drift_detector.subprocess.run",
        lambda *a, **k: _mock_completed(0, payload),
    )

    with pytest.raises(CronEnumerationError, match="hasMore"):
        enumerate_live_crons()


@pytest.mark.parametrize("has_more", [False, None, "true", 1])
def test_enumerate_live_crons_has_more_not_literal_true_is_accepted(
    monkeypatch: pytest.MonkeyPatch, has_more: object
) -> None:
    payload = json.dumps({"jobs": [_live_job()], "hasMore": has_more})
    monkeypatch.setattr(
        "scripts.trust.cron_drift_detector.subprocess.run",
        lambda *a, **k: _mock_completed(0, payload),
    )

    assert enumerate_live_crons() == [_live_job()]


def test_enumerate_live_crons_error_strings_name_all_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.trust.cron_drift_detector.subprocess.run",
        lambda *a, **k: _mock_completed(1, "", stderr="boom"),
    )

    with pytest.raises(CronEnumerationError, match="cron list --all --json"):
        enumerate_live_crons()


# --- #1126: duplicate live crons sharing (name, agent_id) ---------------------

# Literal (not imported) so a missing constant fails only its own test.
KIND_DUPLICATE_PRESENT = "duplicate_present"


def _dup(id_: object, created: object, **overrides: object) -> dict:
    return _live_job(id=id_, createdAtMs=created, **overrides)


def test_two_copies_of_approved_cron_one_primary_one_duplicate() -> None:
    live = [_dup("later", 2000), _dup("earlier", 1000)]

    findings = detect_cron_drift(live, [BASELINE_ENTRY])

    assert len(findings) == 1
    finding = findings[0]
    assert finding.kind == KIND_DUPLICATE_PRESENT
    assert finding.name == "inbox-5pm"
    assert finding.agent_id == "felix-admin-capture"
    assert finding.cron_id == "later"
    assert finding.primary_cron_id == "earlier"
    assert finding.created_at_ms == 2000
    assert finding.schedule_expr == "0 17 * * *"
    assert finding.enabled is True
    assert finding.enabled_state == "true"
    assert finding.primary_enabled_state == "true"


def test_duplicate_primary_is_evaluated_exactly_as_a_single_job() -> None:
    """The primary of a group still gets its schedule_mismatch; the extra copy
    gets duplicate_present (and is not itself schedule-evaluated)."""
    drifted = {"kind": "cron", "expr": "0 18 * * *", "tz": "America/New_York"}
    live = [_dup("p", 1000, schedule=drifted), _dup("d", 2000, schedule=drifted)]

    findings = detect_cron_drift(live, [BASELINE_ENTRY])

    assert sorted((f.kind, f.cron_id) for f in findings) == [
        (KIND_DUPLICATE_PRESENT, "d"),
        (KIND_SCHEDULE_MISMATCH, "p"),
    ]


def test_three_copies_yield_two_duplicates_with_distinct_fingerprints() -> None:
    from scripts.trust.state import fingerprint_finding

    live = [_dup("c", 3000), _dup("a", 1000), _dup("b", 2000)]

    findings = detect_cron_drift(live, [BASELINE_ENTRY])

    dups = [f for f in findings if f.kind == KIND_DUPLICATE_PRESENT]
    assert [f.cron_id for f in dups] == ["b", "c"]
    assert all(f.primary_cron_id == "a" for f in dups)
    assert len({fingerprint_finding(f, "h") for f in dups}) == 2


def test_duplicate_primary_selection_is_order_independent() -> None:
    jobs = [_dup("c", 3000), _dup("a", 1000), _dup("b", 2000), _dup("z", None)]
    expected = detect_cron_drift(jobs, [BASELINE_ENTRY])

    for perm in permutations(jobs):
        assert detect_cron_drift(list(perm), [BASELINE_ENTRY]) == expected
    assert {f.primary_cron_id for f in expected} == {"a"}


def test_duplicate_primary_prefers_running_copy() -> None:
    """A3: the enabled copy is primary even if a disabled copy is older, so a
    disabled stray does not mask a healthy approved cron as enabled_mismatch."""
    live = [_dup("old-disabled", 1000, enabled=False), _dup("new-running", 2000)]

    findings = detect_cron_drift(live, [BASELINE_ENTRY])

    assert [(f.kind, f.cron_id) for f in findings] == [
        (KIND_DUPLICATE_PRESENT, "old-disabled")
    ]
    assert findings[0].primary_cron_id == "new-running"
    assert findings[0].enabled_state == "false"
    assert findings[0].primary_enabled_state == "true"


def test_duplicate_null_agent_plugin_crons() -> None:
    live = [
        _live_job(),
        _memory_core_job(id="m2", createdAtMs=1795000000002),
        _memory_core_job(id="m1", createdAtMs=1795000000001),
    ]

    findings = detect_cron_drift(live, [BASELINE_ENTRY])

    assert sorted((f.kind, f.cron_id, f.agent_id) for f in findings) == [
        (KIND_DUPLICATE_PRESENT, "m2", None),
        (KIND_UNAPPROVED_PRESENT, "m1", None),
    ]
    dup = next(f for f in findings if f.kind == KIND_DUPLICATE_PRESENT)
    assert dup.primary_cron_id == "m1"
    assert dup.declaration_key == "memory-core:memory-dreaming-promotion"


def test_duplicate_of_unapproved_key_is_unapproved_plus_duplicate() -> None:
    live = [_live_job(), _dup("r1", 1, name="rogue"), _dup("r2", 2, name="rogue")]

    findings = detect_cron_drift(live, [BASELINE_ENTRY])

    assert sorted((f.kind, f.cron_id) for f in findings) == [
        (KIND_DUPLICATE_PRESENT, "r2"),
        (KIND_UNAPPROVED_PRESENT, "r1"),
    ]


def test_duplicate_group_mixed_type_id_and_created_at_does_not_raise() -> None:
    """A1: id normalises to str|None; createdAtMs to int|None (bool, str and
    float rejected). Mixed raw types inside one group must not raise in the
    primary-selection sort and must be order-independent."""
    jobs = [
        _dup(5, "123"),  # id int -> "5"; created str -> None
        _dup("b", True),  # created bool -> None
        _dup(None, 1.5),  # id None; created float -> None
        _dup("a", 900),  # the only real int created -> primary
        _dup({"x": 1}, [1]),  # unhashable raws must not raise
    ]

    expected = detect_cron_drift(jobs, [BASELINE_ENTRY])
    for perm in permutations(jobs):
        assert detect_cron_drift(list(perm), [BASELINE_ENTRY]) == expected

    dups = [f for f in expected if f.kind == KIND_DUPLICATE_PRESENT]
    assert {f.primary_cron_id for f in dups} == {"a"}
    assert all(f.created_at_ms is None for f in dups)
    assert all(f.cron_id is None or isinstance(f.cron_id, str) for f in dups)
    assert {f.cron_id for f in dups} == {"5", "b", None, "{'x': 1}"}


def test_created_at_ms_normalised_at_parse_boundary() -> None:
    for raw, expected in [(1775153265189, 1775153265189), (True, None), ("1", None), (1.0, None)]:
        findings = detect_cron_drift([_live_job(name="rogue", createdAtMs=raw)], [])
        assert findings[0].created_at_ms == expected, raw


def test_id_less_duplicates_collapse_to_one_finding() -> None:
    """A2: id-less extra copies share one sentinel identity (no ordinal), so
    they collapse to one duplicate_present rather than churning."""
    live = [_dup("a", 1), _dup(None, 2), _dup(None, 3)]

    findings = detect_cron_drift(live, [BASELINE_ENTRY])

    assert [(f.kind, f.cron_id) for f in findings] == [(KIND_DUPLICATE_PRESENT, None)]


def test_single_copy_groups_unchanged_by_duplicate_handling() -> None:
    live = [_live_job(), _live_job(id="r", name="rogue")]

    findings = detect_cron_drift(live, [BASELINE_ENTRY])

    assert [(f.kind, f.name) for f in findings] == [(KIND_UNAPPROVED_PRESENT, "rogue")]
    assert findings[0].primary_cron_id is None


def test_kind_duplicate_present_exported() -> None:
    assert "KIND_DUPLICATE_PRESENT" in detector_mod.__all__
    assert detector_mod.KIND_DUPLICATE_PRESENT == "duplicate_present"
