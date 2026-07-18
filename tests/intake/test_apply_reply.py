"""Tests for :mod:`scripts.intake.apply_reply` (WP04, kentonium3/kg-automation#749;
closes #750).

All tests inject a stateful fake mirroring the real ``VikunjaClient`` write
surface — ``get/post/put/delete`` with an explicit ``timeout`` — over an
in-memory task store, so no real network is constructed (the global conftest
urlopen guard fails loud otherwise) and the read-modify-write + readback +
family-replace behaviour is observable end-to-end.

Load-bearing invariants under test:
- family-replace preserves non-family labels and never leaves two ``q:``/``f:``
  labels (NFR-003 zero-clobber / SC-005);
- each Tier-2 compatibility-matrix cell (FR-017 / FR-010): ``due:`` ET-EOD on
  ``q:do``/``q:schedule``, ignore-with-note on ``q:eliminate``/``f:4``, the
  non-blocking due follow-up, ``habit``→``t:habit`` (recurrence note), ``loe:``,
  and malformed ``due:``/``loe:`` echo-back;
- every per-line status incl. ``moved_conflict`` / ``not_found`` /
  ``access_denied`` (FR-012);
- idempotent re-apply → ``noop`` (FR-013);
- ``f:4`` terminal → ``overload_flagged``, not scheduled (SC-004);
- ``q:eliminate`` → task marked done (FR-008);
- correlation across two same-day digests + orphan-number echo-back (SC-011);
- kent-token-only writes — the felix-bot attach path is refused (SC-008 / #750).
"""
from __future__ import annotations

import copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.common import vikunja_refs
from scripts.common.vikunja_client import (
    VikunjaAuthError,
    VikunjaHttpError,
    VikunjaServerError,
)
from scripts.intake import apply_reply as ar

INBOX_ID = 1
PERSONAL_ID = 20
POINTERHEALTH_ID = 18
CLIENTS_ID = 17

NOW = datetime(2026, 7, 17, 22, 0, 0, tzinfo=timezone.utc)

# Live label ids from the #748 seam registry (kent namespace).
_LABEL_ID = {
    entry["name"]: entry["selector"]["value"]
    for entry in vikunja_refs.declared_labels()
    if entry["selector"]["value"] is not None
}
_ID_LABEL = {v: k for k, v in _LABEL_ID.items()}


# ---------------------------------------------------------------------------
# Fakes / fixtures
# ---------------------------------------------------------------------------


def _label(title: str) -> dict:
    return {"id": _LABEL_ID[title], "title": title}


def _task(
    task_id: int,
    *,
    project_id: int = INBOX_ID,
    labels: list[str] | None = None,
    done: bool = False,
    due_date: str | None = None,
    repeat_after: int | None = None,
    title: str | None = None,
) -> dict:
    task: dict = {
        "id": task_id,
        "title": title if title is not None else f"Task {task_id}",
        "project_id": project_id,
        "done": done,
        "labels": [_label(t) for t in (labels or [])],
    }
    if due_date is not None:
        task["due_date"] = due_date
    if repeat_after is not None:
        task["repeat_after"] = repeat_after
    return task


_TASK_RE = re.compile(r"^/tasks/(\d+)$")
_LABEL_ADD_RE = re.compile(r"^/tasks/(\d+)/labels$")
_LABEL_DEL_RE = re.compile(r"^/tasks/(\d+)/labels/(\d+)$")


class FakeVikunja:
    """Stateful fake of the ``VikunjaClient`` write surface over a task store."""

    def __init__(
        self,
        tasks: list[dict] | None = None,
        *,
        get_fail: dict[int, Exception] | None = None,
        put_fail: bool = False,
    ):
        self.tasks: dict[int, dict] = {t["id"]: t for t in (tasks or [])}
        self.get_fail = get_fail or {}
        self.put_fail = put_fail
        self.calls: list[tuple[str, str, object, object]] = []

    def get(self, path, *, params=None, timeout=None):
        self.calls.append(("GET", path, None, timeout))
        assert timeout is not None, "GET must be bounded by an explicit timeout"
        m = _TASK_RE.match(path)
        if m:
            tid = int(m.group(1))
            if tid in self.get_fail:
                raise self.get_fail[tid]
            if tid not in self.tasks:
                from scripts.common.vikunja_client import VikunjaNotFoundError

                raise VikunjaNotFoundError(path=path, status=404)
            return copy.deepcopy(self.tasks[tid])
        raise AssertionError(f"unexpected GET {path}")

    def post(self, path, *, json=None, params=None, timeout=None):
        self.calls.append(("POST", path, json, timeout))
        assert timeout is not None, "POST must be bounded by an explicit timeout"
        m = _TASK_RE.match(path)
        assert m, f"unexpected POST {path}"
        tid = int(m.group(1))
        self.tasks[tid].update(json)
        return {}

    def put(self, path, *, json=None, params=None, timeout=None):
        self.calls.append(("PUT", path, json, timeout))
        assert timeout is not None, "PUT must be bounded by an explicit timeout"
        if self.put_fail:
            raise VikunjaServerError(path=path, status=500)
        m = _LABEL_ADD_RE.match(path)
        assert m, f"unexpected PUT {path}"
        tid = int(m.group(1))
        lid = json["label_id"]
        labels = self.tasks[tid].setdefault("labels", [])
        if not any(label["id"] == lid for label in labels):
            labels.append({"id": lid, "title": _ID_LABEL[lid]})
        return {}

    def delete(self, path, *, params=None, timeout=None):
        self.calls.append(("DELETE", path, None, timeout))
        assert timeout is not None, "DELETE must be bounded by an explicit timeout"
        m = _LABEL_DEL_RE.match(path)
        assert m, f"unexpected DELETE {path}"
        tid, lid = int(m.group(1)), int(m.group(2))
        labels = self.tasks[tid].get("labels", [])
        self.tasks[tid]["labels"] = [x for x in labels if x["id"] != lid]
        return {}

    # convenience
    def titles(self, task_id: int) -> set[str]:
        return {x["title"] for x in self.tasks[task_id].get("labels", [])}

    def methods(self) -> list[str]:
        return [c[0] for c in self.calls]


def _line(text: str):
    from scripts.intake.shorthand import parse_reply

    return parse_reply(text)[0]


def _apply(client, text, task_id, *, dry_run=False):
    return ar.apply_line(
        client, _line(text), task_id, inbox_id=INBOX_ID, dry_run=dry_run
    )


def _write_digest(state_dir: Path, digest_id: str, created_utc: str, entries: list[dict]):
    digests = state_dir / "digests"
    digests.mkdir(parents=True, exist_ok=True)
    record = {
        "digest_id": digest_id,
        "created_utc": created_utc,
        "created_et_date": "2026-07-17",
        "source_cron": None,
        "entries": entries,
    }
    (digests / f"intake-{digest_id}.json").write_text(
        json.dumps(record), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# T015 — family-replace + kent-token RMW
# ---------------------------------------------------------------------------


def test_family_replace_swaps_family_labels_and_preserves_nonfamily():
    # Existing q:do + f:1-flow (families) plus t:habit + loe:s (non-family).
    task = _task(
        101,
        project_id=INBOX_ID,
        labels=["q:do", "f:1-flow", "t:habit", "loe:s"],
    )
    client = FakeVikunja([task])

    result = _apply(client, "1 schedule f3", 101)

    assert result.status == "applied"
    final = client.titles(101)
    # Family members swapped; non-family preserved.
    assert final == {"q:schedule", "f:3-edge", "t:habit", "loe:s"}
    # NFR-003: exactly one q: and one f:.
    assert len([t for t in final if t.startswith("q:")]) == 1
    assert len([t for t in final if t.startswith("f:")]) == 1


def test_family_replace_never_leaves_two_quadrants():
    task = _task(102, labels=["q:do"])
    client = FakeVikunja([task])

    _apply(client, "1 personal schedule", 102)

    final = client.titles(102)
    assert "q:do" not in final
    assert "q:schedule" in final
    assert len([t for t in final if t.startswith("q:")]) == 1


def test_sparse_apply_leaves_valid_family_untouched():
    # SC-010: reply supplies only the missing project; existing valid f:/q: stay.
    task = _task(103, labels=["f:3-edge", "q:schedule"])
    client = FakeVikunja([task])

    result = _apply(client, "1 personal", 103)

    assert result.status == "applied"
    assert client.tasks[103]["project_id"] == PERSONAL_ID
    assert client.titles(103) == {"f:3-edge", "q:schedule"}


def test_project_reassignment_uses_rmw_post_and_readback():
    task = _task(104, labels=["f:2-growth", "q:do"], title="Deck")
    client = FakeVikunja([task])

    result = _apply(client, "1 pointerhealth", 104)

    assert result.status == "applied"
    assert client.tasks[104]["project_id"] == POINTERHEALTH_ID
    # A field POST happened (project reassignment) and the title was echoed back
    # in the allowlisted payload (non-clobber #524).
    post_calls = [c for c in client.calls if c[0] == "POST"]
    assert len(post_calls) == 1
    assert post_calls[0][2]["title"] == "Deck"
    assert post_calls[0][2]["project_id"] == POINTERHEALTH_ID


# ---------------------------------------------------------------------------
# T016 — Tier-2 compatibility matrix + f:4 disposition
# ---------------------------------------------------------------------------


def test_due_on_q_do_writes_et_end_of_day():
    task = _task(201)
    client = FakeVikunja([task])

    result = _apply(client, "1 pointerhealth do due:2026-07-22", 201)

    assert result.status == "applied"
    due = client.tasks[201]["due_date"]
    # ET end-of-day, explicit offset, NOT UTC 'Z' (#733).
    assert due == "2026-07-22T23:59:59-04:00"
    assert not due.endswith("Z")
    assert result.applied["due_date"] == due


def test_due_on_q_schedule_writes_et_end_of_day():
    task = _task(202)
    client = FakeVikunja([task])
    _apply(client, "1 personal schedule due:2026-01-15", 202)
    # January → EST (-05:00).
    assert client.tasks[202]["due_date"] == "2026-01-15T23:59:59-05:00"


class _NormalizingVikunja(FakeVikunja):
    """FakeVikunja that mimics live Vikunja: it normalizes a written due_date to
    UTC 'Z' on store, so the readback returns a different STRING for the same
    instant (#733/#736). This is what the mock-only tests could not exercise."""

    def post(self, path, *, json=None, params=None, timeout=None):
        payload = dict(json or {})
        due = payload.get("due_date")
        if isinstance(due, str) and due:
            inst = datetime.fromisoformat(due).astimezone(timezone.utc)
            payload["due_date"] = inst.strftime("%Y-%m-%dT%H:%M:%SZ")
        return super().post(path, json=payload, params=params, timeout=timeout)


def test_due_readback_tolerates_vikunja_utc_normalization():
    # #757 — the ET-offset write reads back as UTC 'Z' (same instant). The
    # readback must compare INSTANTS, not strings, or it false-fails 'applied'
    # into 'failed' and the caller retries (the live retry storm).
    client = _NormalizingVikunja([_task(201)])
    result = _apply(client, "1 personal do due:2026-07-20", 201)
    assert result.status == "applied", result.notes
    assert result.applied.get("due_date") == "2026-07-20T23:59:59-04:00"
    # Stored (normalized) as the same instant in UTC 'Z' = Mon EOD ET.
    assert client.tasks[201]["due_date"] == "2026-07-21T03:59:59Z"


def test_due_readback_still_catches_a_genuinely_wrong_instant():
    # The instant compare must NOT mask a real partial-replace drift: a mock that
    # stores a DIFFERENT day must still raise → per-line 'failed'.
    class _WrongDayVikunja(FakeVikunja):
        def post(self, path, *, json=None, params=None, timeout=None):
            payload = dict(json or {})
            if isinstance(payload.get("due_date"), str) and payload["due_date"]:
                payload["due_date"] = "2026-07-25T03:59:59Z"  # wrong day
            return super().post(path, json=payload, params=params, timeout=timeout)

    client = _WrongDayVikunja([_task(201)])
    result = _apply(client, "1 personal do due:2026-07-20", 201)
    assert result.status == "failed", result.notes


def test_due_on_q_eliminate_is_ignored_with_note():
    task = _task(203)
    client = FakeVikunja([task])

    result = _apply(client, "1 elim due:2026-07-22", 203)

    assert result.status == "applied"
    assert client.tasks[203]["done"] is True
    # Due ignored — never written on an eliminate.
    assert "due_date" not in client.tasks[203] or not ar._has_due(client.tasks[203])
    assert any("ignored due" in n for n in result.notes)


def test_due_on_f4_is_ignored_with_note():
    task = _task(204)
    client = FakeVikunja([task])

    result = _apply(client, "1 f4 due:2026-07-22", 204)

    assert result.status == "overload_flagged"
    assert not ar._has_due(client.tasks[204])
    assert any("ignored due" in n for n in result.notes)


def test_q_do_without_due_emits_nonblocking_followup():
    task = _task(205)
    client = FakeVikunja([task])

    result = _apply(client, "1 personal do", 205)

    assert result.status == "applied"
    assert result.applied.get("due_followup") is True
    assert any("follow-up" in n for n in result.notes)
    # Tier-2 absence never blocks Tier-1 (project + quadrant still applied).
    assert client.tasks[205]["project_id"] == PERSONAL_ID
    assert "q:do" in client.titles(205)


def test_no_due_followup_when_task_already_has_due_date():
    # Review cycle 1 defect: the reply supplies NO quadrant token, so effective_q
    # falls back to the task's LIVE q:schedule. The task already carries a due
    # date, so the non-blocking follow-up must NOT fire (the _has_due guard).
    task = _task(
        215,
        project_id=INBOX_ID,
        labels=["q:schedule"],
        due_date="2026-08-01T23:59:59-04:00",
    )
    client = FakeVikunja([task])

    # Sparse reply: only the missing project; no due:, no quadrant token.
    result = _apply(client, "1 personal", 215)

    assert result.status == "applied"
    assert client.tasks[215]["project_id"] == PERSONAL_ID
    assert "due_followup" not in result.applied
    assert not any("follow-up" in n for n in result.notes)


def test_habit_attaches_t_habit_nonfamily():
    task = _task(206)
    client = FakeVikunja([task])
    result = _apply(client, "1 personal do habit", 206)
    assert result.status == "applied"
    assert "t:habit" in client.titles(206)


def test_habit_on_recurring_task_notes_no_double_recurrence():
    task = _task(207, repeat_after=86400)
    client = FakeVikunja([task])
    result = _apply(client, "1 personal do habit", 207)
    assert "t:habit" in client.titles(207)
    assert any("already recurring" in n for n in result.notes)


def test_loe_applies():
    task = _task(208)
    client = FakeVikunja([task])
    result = _apply(client, "1 personal do loe:m", 208)
    assert result.status == "applied"
    assert "loe:m" in client.titles(208)


def test_malformed_loe_is_echoed_back_but_tier1_still_applies():
    task = _task(209)
    client = FakeVikunja([task])
    # loe:x is malformed → WP03 captures it as an unresolved token.
    result = _apply(client, "1 personal do loe:x", 209)
    assert result.status == "applied"
    assert client.tasks[209]["project_id"] == PERSONAL_ID
    assert "loe:x" in result.failed
    assert "loe:x" not in client.titles(209)


def test_malformed_due_is_echoed_back_but_tier1_still_applies():
    task = _task(210)
    client = FakeVikunja([task])
    result = _apply(client, "1 personal do due:2026-13-45", 210)
    assert result.status == "applied"
    assert client.tasks[210]["project_id"] == PERSONAL_ID
    assert not ar._has_due(client.tasks[210])
    assert any("due:2026-13-45" in f for f in result.failed)


def test_f4_overload_is_terminal_flag_not_scheduled():
    # SC-004: f:4 records decomposition-pending, confirms once, not scheduled.
    task = _task(211, labels=["f:1-flow"])
    client = FakeVikunja([task])

    result = _apply(client, "1 f4", 211)

    assert result.status == "overload_flagged"
    final = client.titles(211)
    assert "f:4-overload" in final
    assert "f:1-flow" not in final  # family-replaced
    assert not ar._has_due(client.tasks[211])
    assert any("decomposition-pending" in n for n in result.notes)


def test_f4_overload_idempotent_stays_overload_flagged():
    task = _task(212, labels=["f:4-overload"])
    client = FakeVikunja([task])
    result = _apply(client, "1 f4", 212)
    assert result.status == "overload_flagged"
    # No new write needed.
    assert "PUT" not in client.methods()


def test_q_eliminate_marks_task_done():
    task = _task(213)
    client = FakeVikunja([task])

    result = _apply(client, "1 elim", 213)

    assert result.status == "applied"
    assert client.tasks[213]["done"] is True
    assert "q:eliminate" in client.titles(213)
    assert any("eliminated" in n for n in result.notes)


# ---------------------------------------------------------------------------
# T017 — per-line statuses
# ---------------------------------------------------------------------------


def test_status_not_found_when_task_gone():
    client = FakeVikunja([])  # task 301 absent → GET 404
    result = _apply(client, "1 personal do", 301)
    assert result.status == "not_found"


def test_status_access_denied_on_401():
    client = FakeVikunja([], get_fail={302: VikunjaAuthError(path="/tasks/302", status=401)})
    result = _apply(client, "1 personal do", 302)
    assert result.status == "access_denied"


def test_status_access_denied_on_403():
    client = FakeVikunja(
        [], get_fail={303: VikunjaHttpError(path="/tasks/303", status=403)}
    )
    result = _apply(client, "1 personal do", 303)
    assert result.status == "access_denied"


def test_status_already_done():
    task = _task(304, done=True)
    client = FakeVikunja([task])
    result = _apply(client, "1 personal do", 304)
    assert result.status == "already_done"


def test_status_moved_conflict_when_routed_elsewhere():
    # Task left Inbox to Clients(17); reply intends PointerHealth(18).
    task = _task(305, project_id=CLIENTS_ID)
    client = FakeVikunja([task])
    result = _apply(client, "1 pointerhealth do", 305)
    assert result.status == "moved_conflict"
    # Nothing clobbered.
    assert client.tasks[305]["project_id"] == CLIENTS_ID


def test_partial_resolution_is_not_moved_conflict():
    # A task already in a working project that only needs a quadrant is a
    # legitimate partial apply (FR-013), NOT a moved_conflict (no project token).
    task = _task(306, project_id=PERSONAL_ID, labels=["f:3-edge"])
    client = FakeVikunja([task])
    result = _apply(client, "1 do", 306)
    assert result.status == "applied"
    assert "q:do" in client.titles(306)


def test_status_echoed_back_on_unresolvable_line():
    task = _task(307)
    client = FakeVikunja([task])
    # 'wat' is an unknown project candidate → unresolved; no actionable field.
    result = _apply(client, "1 wat", 307)
    assert result.status == "echoed_back"
    assert "wat" in result.failed


def test_status_failed_on_write_error():
    task = _task(308)
    client = FakeVikunja([task], put_fail=True)
    result = _apply(client, "1 personal do", 308)
    assert result.status == "failed"
    assert any("write failed" in n for n in result.notes)


def test_idempotent_reapply_is_noop():
    task = _task(309)
    client = FakeVikunja([task])

    first = _apply(client, "1 personal do", 309)
    assert first.status == "applied"

    second = _apply(client, "1 personal do", 309)
    assert second.status == "noop"
    assert any("already matches" in n for n in second.notes)


def test_dry_run_plans_without_writing():
    task = _task(310)
    client = FakeVikunja([task])
    result = _apply(client, "1 personal do", 310, dry_run=True)
    assert result.status == "applied"  # planned
    # No mutating calls — only the initial GET.
    assert set(client.methods()) == {"GET"}
    assert client.tasks[310]["project_id"] == INBOX_ID  # unchanged


# ---------------------------------------------------------------------------
# T014 — correlation (FR-016 / SC-011)
# ---------------------------------------------------------------------------


def test_correlation_selects_digest_by_line_number_set(tmp_path):
    # SC-011: two same-day digests. Digest A covers {1,2}; digest B covers {1,3}.
    # A reply for lines {1,3} must correlate to B (best number-set overlap), and
    # an orphan number {5} echoes back.
    _write_digest(
        tmp_path,
        "2026-07-17T2000Z",
        "2026-07-17T20:00:00Z",
        [
            {"n": 1, "task_id": 401, "title": "A-one", "missing_fields": ["project"]},
            {"n": 2, "task_id": 402, "title": "A-two", "missing_fields": ["project"]},
        ],
    )
    _write_digest(
        tmp_path,
        "2026-07-17T2100Z",
        "2026-07-17T21:00:00Z",
        [
            {"n": 1, "task_id": 501, "title": "B-one", "missing_fields": ["project"]},
            {"n": 3, "task_id": 503, "title": "B-three", "missing_fields": ["project"]},
        ],
    )
    client = FakeVikunja([_task(501), _task(503)])

    doc = ar.apply_reply(
        client,
        "1 personal\n3 personal\n5 personal",
        state_dir=tmp_path,
        now_utc=NOW,
    )

    assert doc["digest_id"] == "2026-07-17T2100Z"
    by_line = {r["line"]: r for r in doc["results"]}
    # Numbers 1 & 3 map to digest B's tasks and apply.
    assert by_line[1]["task_id"] == 501 and by_line[1]["status"] == "applied"
    assert by_line[3]["task_id"] == 503 and by_line[3]["status"] == "applied"
    # Orphan number 5 echoes back.
    assert by_line[5]["status"] == "echoed_back"
    assert by_line[5]["task_id"] is None


def test_correlation_title_evidence_breaks_number_tie(tmp_path):
    # Both digests cover {1}; the reply text names digest-B's task title, so the
    # title-evidence tiebreak (FR-016) selects B over the (newer-but-untitled) A.
    _write_digest(
        tmp_path,
        "2026-07-17T2100Z",
        "2026-07-17T21:00:00Z",
        [{"n": 1, "task_id": 601, "title": "zzz", "missing_fields": ["project"]}],
    )
    _write_digest(
        tmp_path,
        "2026-07-17T2000Z",
        "2026-07-17T20:00:00Z",
        [{"n": 1, "task_id": 701, "title": "onboarding", "missing_fields": ["project"]}],
    )
    client = FakeVikunja([_task(601), _task(701)])

    doc = ar.apply_reply(
        client,
        "1 personal onboarding",
        state_dir=tmp_path,
        now_utc=NOW,
    )
    # Title 'onboarding' appears in the reply → older digest with that title wins.
    assert doc["digest_id"] == "2026-07-17T2000Z"
    assert doc["results"][0]["task_id"] == 701


def test_correlation_ignores_digests_outside_window(tmp_path):
    _write_digest(
        tmp_path,
        "2026-07-14T2000Z",  # >48h before NOW
        "2026-07-14T20:00:00Z",
        [{"n": 1, "task_id": 801, "title": "stale", "missing_fields": ["project"]}],
    )
    client = FakeVikunja([_task(801)])
    doc = ar.apply_reply(client, "1 personal", state_dir=tmp_path, now_utc=NOW)
    assert doc["digest_id"] is None
    assert doc["results"][0]["status"] == "echoed_back"


# ---------------------------------------------------------------------------
# T017 — aggregates + ledger
# ---------------------------------------------------------------------------


def test_aggregates_count_each_status(tmp_path):
    _write_digest(
        tmp_path,
        "2026-07-17T2100Z",
        "2026-07-17T21:00:00Z",
        [
            {"n": 1, "task_id": 901, "title": "t1", "missing_fields": ["project"]},
            {"n": 2, "task_id": 902, "title": "t2", "missing_fields": ["project"]},
        ],
    )
    client = FakeVikunja([_task(901), _task(902, done=True)])
    doc = ar.apply_reply(
        client, "1 personal do\n2 personal do\n7 personal", state_dir=tmp_path, now_utc=NOW
    )
    agg = doc["aggregates"]
    assert agg["applied"] == 1
    assert agg["already_done"] == 1
    assert agg["echoed_back"] == 1  # orphan number 7
    assert set(agg.keys()) == set(ar.STATUSES)


def test_ledger_append_writes_one_line_per_result(tmp_path):
    doc = {
        "digest_id": "d1",
        "results": [
            {"line": 1, "task_id": 1, "status": "applied", "applied": {}, "notes": [],
             "understood": {}, "failed": []},
            {"line": 2, "task_id": 2, "status": "noop", "applied": {}, "notes": [],
             "understood": {}, "failed": []},
        ],
        "aggregates": {},
    }
    path = ar.append_ledger(tmp_path, NOW, doc)
    assert path.name == "intake-apply-2026-07-17.jsonl"
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["digest_id"] == "d1"
    assert first["status"] == "applied"
    assert first["applied_at_utc"] == "2026-07-17T22:00:00Z"


# ---------------------------------------------------------------------------
# T015 / T019 — kent-token-only (SC-008 / #750)
# ---------------------------------------------------------------------------


def test_read_kent_token_refuses_felix_bot_path():
    with pytest.raises(ar.ApplyError, match="felix-bot"):
        ar.read_kent_token(ar.FELIX_BOT_TOKEN_FILE)


def test_read_kent_token_reads_a_real_file(tmp_path):
    token_file = tmp_path / "vikunja-api-kent"
    token_file.write_text("kent-secret-token\n", encoding="utf-8")
    assert ar.read_kent_token(str(token_file)) == "kent-secret-token\n"


def test_read_kent_token_rejects_empty_file(tmp_path):
    token_file = tmp_path / "empty"
    token_file.write_text("   \n", encoding="utf-8")
    with pytest.raises(ar.ApplyError, match="empty"):
        ar.read_kent_token(str(token_file))


def test_cli_refuses_felix_bot_token_and_never_touches_client(tmp_path):
    # SC-008: the felix-bot token path cannot yield a client — no attach path.
    client = FakeVikunja([_task(1)])
    rc = ar.main(
        [
            "--reply", "1 personal do",
            "--state-dir", str(tmp_path),
            "--now-utc", "2026-07-17T22:00:00Z",
            "--token-file", ar.FELIX_BOT_TOKEN_FILE,
        ],
        client=client,
    )
    assert rc == 1
    assert client.calls == []  # never issued a single request


def test_cli_applies_via_injected_client_and_writes_ledger(tmp_path):
    _write_digest(
        tmp_path,
        "2026-07-17T2100Z",
        "2026-07-17T21:00:00Z",
        [{"n": 1, "task_id": 1, "title": "t", "missing_fields": ["project"]}],
    )
    client = FakeVikunja([_task(1)])
    rc = ar.main(
        [
            "--reply", "1 personal do",
            "--state-dir", str(tmp_path),
            "--now-utc", "2026-07-17T22:00:00Z",
            "--json",
        ],
        client=client,
    )
    assert rc == 0
    # Every write went through the single injected (kent) client; a ledger row
    # was appended.
    assert client.tasks[1]["project_id"] == PERSONAL_ID
    ledger = tmp_path / "intake-apply-2026-07-17.jsonl"
    assert ledger.exists()


def test_cli_stdin_reply(tmp_path, monkeypatch, capsys):
    _write_digest(
        tmp_path,
        "2026-07-17T2100Z",
        "2026-07-17T21:00:00Z",
        [{"n": 1, "task_id": 1, "title": "t", "missing_fields": ["project"]}],
    )
    client = FakeVikunja([_task(1)])
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("1 personal do"))
    rc = ar.main(
        [
            "--reply", "-",
            "--state-dir", str(tmp_path),
            "--now-utc", "2026-07-17T22:00:00Z",
        ],
        client=client,
    )
    assert rc == 0
    assert client.tasks[1]["project_id"] == PERSONAL_ID


# ---------------------------------------------------------------------------
# T018 — constrained --unresolved fallback (WP03 re-resolution)
# ---------------------------------------------------------------------------


def test_unresolved_fallback_resolves_through_seam(tmp_path):
    _write_digest(
        tmp_path,
        "2026-07-17T2100Z",
        "2026-07-17T21:00:00Z",
        [{"n": 1, "task_id": 1, "title": "t", "missing_fields": ["project"]}],
    )
    client = FakeVikunja([_task(1)])
    # 'xyz' is unknown → echoed_back unless the fallback proposes a canonical name.
    unresolved = [
        {"line": 1, "token": "xyz", "position": 2, "canonical_name": "personal"}
    ]
    doc = ar.apply_reply(
        client,
        "1 xyz do",
        state_dir=tmp_path,
        now_utc=NOW,
        unresolved_map=unresolved,
    )
    assert doc["results"][0]["status"] == "applied"
    assert client.tasks[1]["project_id"] == PERSONAL_ID


def test_unresolved_fallback_rejects_raw_id(tmp_path):
    _write_digest(
        tmp_path,
        "2026-07-17T2100Z",
        "2026-07-17T21:00:00Z",
        [{"n": 1, "task_id": 1, "title": "t", "missing_fields": ["project"]}],
    )
    client = FakeVikunja([_task(1)])
    # A raw id proposal is rejected by WP03's re-resolution → token stays echoed.
    unresolved = [
        {"line": 1, "token": "xyz", "position": 2, "canonical_name": "20"}
    ]
    doc = ar.apply_reply(
        client, "1 xyz", state_dir=tmp_path, now_utc=NOW, unresolved_map=unresolved
    )
    assert doc["results"][0]["status"] == "echoed_back"
    assert "xyz" in doc["results"][0]["failed"]
