"""Tests for :mod:`scripts.intake.scan_inbox` (WP02, kentonium3/kg-automation#749).

All tests inject a fake client mirroring the real ``VikunjaClient`` surface —
``.get(path, params=..., timeout=...)`` returning a list-shaped ``GET /tasks/all``
page. No real network is constructed (the global conftest urlopen guard fails
loud otherwise).

Load-bearing invariants under test:
- Tier-1 classification incl. the ``f:4-overload`` exclusion and the
  already-complete (non-Inbox) path (FR-002/FR-009);
- read path filters to ``project_id == inbox && done == false`` and paginates
  done-inclusive past 50 (FR-001);
- correlation records are **immutable** per ``digest_id`` — two ticks yield two
  files + an updated pointer, and a same-``digest_id`` re-run never overwrites
  (FR-016);
- 48h retention expiry;
- injectable-clock determinism (no wall-clock in the logic path);
- SC-009 zero-incomplete → empty ``digest_text``, no digest record, exit 0;
- digest_text numbering.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from scripts.intake import scan_inbox

INBOX_ID = 1  # matches the declared+provisioned seam id for "inbox".
WORKING_PROJECT_ID = 20  # a non-Inbox project (Personal), for the complete path.

NOW = datetime(2026, 7, 17, 22, 0, 0, tzinfo=timezone.utc)
NOW_LATER = datetime(2026, 7, 17, 23, 5, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _label(title: str) -> dict:
    return {"id": abs(hash(title)) % 10_000, "title": title}


def _task(
    task_id: int,
    *,
    project_id: int = INBOX_ID,
    labels: list[str] | None = None,
    done: bool = False,
    title: str | None = None,
) -> dict:
    return {
        "id": task_id,
        "title": title if title is not None else f"Task {task_id}",
        "project_id": project_id,
        "done": done,
        "labels": [_label(t) for t in (labels or [])],
    }


class _FakeClient:
    """Paginated fake of the ``VikunjaClient`` read surface."""

    def __init__(self, tasks: list[dict]):
        self._tasks = tasks
        self.calls: list[tuple[str, dict | None]] = []

    def get(self, path, *, params=None, timeout=None):
        self.calls.append((path, params))
        if path == "/tasks/all":
            page = int(params["page"])
            per = int(params["per_page"])
            start = (page - 1) * per
            return self._tasks[start : start + per]
        raise AssertionError(f"unexpected GET {path}")


# ---------------------------------------------------------------------------
# T006 — classification
# ---------------------------------------------------------------------------


def test_classify_bare_inbox_task_is_incomplete_on_all_three():
    verdict = scan_inbox.classify_task(_task(101), INBOX_ID)
    assert verdict.missing_fields == ("project", "friction", "quadrant")
    assert verdict.decomposition_pending is False
    assert verdict.is_complete is False
    assert verdict.prompts is True


def test_classify_f4_overload_is_decomposition_pending_and_not_prompted():
    # An Inbox task carrying f:4-overload is excluded from the incomplete set.
    verdict = scan_inbox.classify_task(
        _task(102, labels=["f:4-overload", "q:schedule"]), INBOX_ID
    )
    assert verdict.decomposition_pending is True
    assert verdict.prompts is False  # FR-009 — never re-prompt


def test_classify_f4_does_not_satisfy_friction():
    # f:4-overload must NOT count as a schedulable friction label.
    verdict = scan_inbox.classify_task(
        _task(103, project_id=WORKING_PROJECT_ID, labels=["f:4-overload", "q:do"]),
        INBOX_ID,
    )
    assert "friction" in verdict.missing_fields


def test_classify_complete_task_has_no_missing_fields():
    verdict = scan_inbox.classify_task(
        _task(
            104,
            project_id=WORKING_PROJECT_ID,
            labels=["f:3-edge", "q:schedule"],
        ),
        INBOX_ID,
    )
    assert verdict.missing_fields == ()
    assert verdict.is_complete is True
    assert verdict.prompts is False


def test_classify_partial_missing_quadrant_only():
    verdict = scan_inbox.classify_task(
        _task(105, project_id=WORKING_PROJECT_ID, labels=["f:1-flow"]),
        INBOX_ID,
    )
    assert verdict.missing_fields == ("quadrant",)


def test_classify_two_quadrants_is_missing_quadrant():
    # Exactly one quadrant is required; two is still "missing".
    verdict = scan_inbox.classify_task(
        _task(
            106,
            project_id=WORKING_PROJECT_ID,
            labels=["f:2-growth", "q:do", "q:schedule"],
        ),
        INBOX_ID,
    )
    assert verdict.missing_fields == ("quadrant",)


def test_classify_non_integer_id_fails_loud():
    with pytest.raises(scan_inbox.IntakeError):
        scan_inbox.classify_task({"id": "x", "project_id": INBOX_ID}, INBOX_ID)


# ---------------------------------------------------------------------------
# T005 — read path
# ---------------------------------------------------------------------------


def test_list_inbox_filters_done_and_other_projects():
    tasks = [
        _task(1),  # not-done inbox → kept
        _task(2, done=True),  # done inbox → dropped
        _task(3, project_id=WORKING_PROJECT_ID),  # other project → dropped
        _task(4),  # not-done inbox → kept
    ]
    got = scan_inbox.list_inbox_tasks(_FakeClient(tasks), INBOX_ID)
    assert [t["id"] for t in got] == [1, 4]


def test_list_inbox_paginates_past_page_size():
    # 55 not-done Inbox tasks spanning two pages (per_page=50).
    tasks = [_task(i) for i in range(1, 56)]
    client = _FakeClient(tasks)
    got = scan_inbox.list_inbox_tasks(client, INBOX_ID)
    assert len(got) == 55
    # Two pages requested (page 1 full, page 2 short).
    pages = [p["page"] for path, p in client.calls if path == "/tasks/all"]
    assert pages == ["1", "2"]


def test_list_inbox_malformed_task_fails_loud():
    client = _FakeClient([{"id": 1, "project_id": INBOX_ID}, "not-a-dict"])
    with pytest.raises(scan_inbox.IntakeError):
        scan_inbox.list_inbox_tasks(client, INBOX_ID)


# ---------------------------------------------------------------------------
# run_scan + digest rendering
# ---------------------------------------------------------------------------


def test_run_scan_numbers_incomplete_and_excludes_f4():
    tasks = [
        _task(10),  # incomplete
        _task(11, labels=["f:4-overload"]),  # decomposition-pending → excluded
        _task(12, labels=["f:1-flow"]),  # incomplete (missing project+quadrant)
    ]
    result = scan_inbox.run_scan(_FakeClient(tasks), inbox_id=INBOX_ID)
    assert result.scanned == 3
    assert result.incomplete == 2
    assert result.prompted == 2
    assert [(e.n, e.task_id) for e in result.entries] == [(1, 10), (2, 12)]


def test_render_digest_text_is_numbered():
    entries = [
        scan_inbox.DigestEntry(1, 10, "Alpha", ("project", "friction", "quadrant")),
        scan_inbox.DigestEntry(2, 12, "Beta", ("project", "quadrant")),
    ]
    text = scan_inbox.render_digest_text(entries)
    lines = text.splitlines()
    assert lines[1].startswith("1. Alpha")
    assert lines[2].startswith("2. Beta")
    assert "project, friction, quadrant" in lines[1]


def test_render_digest_text_empty_for_no_entries():
    assert scan_inbox.render_digest_text([]) == ""


def test_render_digest_text_appends_format_hint():
    # #755 — a non-empty digest carries the one-line shorthand hint as a footer.
    from scripts.intake.shorthand_key import render_hint

    entries = [scan_inbox.DigestEntry(1, 10, "Alpha", ("project",))]
    text = scan_inbox.render_digest_text(entries)
    assert text.splitlines()[-1] == render_hint()
    # Empty set still yields no message (SC-009) — no hint on an empty digest.
    assert scan_inbox.render_digest_text([]) == ""


# ---------------------------------------------------------------------------
# T007 — correlation record: immutability, pointer, determinism
# ---------------------------------------------------------------------------


def _run_main(tmp_path, tasks, *, now, source_cron="inbox-5pm", extra=None):
    argv = [
        "--state-dir",
        str(tmp_path),
        "--source-cron",
        source_cron,
        "--now-utc",
        now,
    ]
    if extra:
        argv.extend(extra)
    return scan_inbox.main(argv, client=_FakeClient(tasks))


def test_two_ticks_write_two_immutable_files_and_update_pointer(tmp_path):
    # Tick 1 at 22:00Z with task 10 incomplete.
    rc1 = _run_main(tmp_path, [_task(10)], now="2026-07-17T22:00:00Z")
    # Tick 2 at 23:05Z with task 20 incomplete.
    rc2 = _run_main(tmp_path, [_task(20)], now="2026-07-17T23:05:00Z")
    assert rc1 == 0 and rc2 == 0

    files = sorted((tmp_path / "digests").glob("intake-*.json"))
    assert len(files) == 2  # two distinct digest_ids → two immutable files

    pointer = json.loads((tmp_path / "latest.json").read_text())
    # latest points at the NEWER (23:05) digest.
    assert pointer["digest_id"] == "2026-07-17T2305Z-inbox-5pm"


def test_same_digest_id_rerun_never_overwrites(tmp_path):
    # First tick: task 10.
    _run_main(tmp_path, [_task(10)], now="2026-07-17T22:00:00Z")
    digest_path = tmp_path / "digests" / "intake-2026-07-17T2200Z-inbox-5pm.json"
    first = json.loads(digest_path.read_text())
    assert [e["task_id"] for e in first["entries"]] == [10]

    # Second tick at the SAME minute (same digest_id) but a DIFFERENT task set.
    _run_main(tmp_path, [_task(99)], now="2026-07-17T22:00:30Z")
    after = json.loads(digest_path.read_text())
    # Immutable: the original entry set survives, not the new one.
    assert [e["task_id"] for e in after["entries"]] == [10]


def test_digest_id_is_deterministic_under_injected_clock():
    a = scan_inbox.compute_digest_id(NOW, "inbox-5pm")
    b = scan_inbox.compute_digest_id(NOW, "inbox-5pm")
    assert a == b == "2026-07-17T2200Z-inbox-5pm"


def test_digest_id_without_source_cron_is_bare_compact_utc():
    assert scan_inbox.compute_digest_id(NOW, None) == "2026-07-17T2200Z"


def test_digest_record_schema(tmp_path):
    _run_main(tmp_path, [_task(10, title="Draft deck")], now="2026-07-17T22:00:00Z")
    record = json.loads(
        (tmp_path / "digests" / "intake-2026-07-17T2200Z-inbox-5pm.json").read_text()
    )
    assert record["digest_id"] == "2026-07-17T2200Z-inbox-5pm"
    assert record["source_cron"] == "inbox-5pm"
    assert record["created_utc"] == "2026-07-17T22:00:00Z"
    assert record["created_et_date"] == "2026-07-17"  # 22:00Z == 18:00 ET
    entry = record["entries"][0]
    assert entry == {
        "n": 1,
        "task_id": 10,
        "title": "Draft deck",
        "missing_fields": ["project", "friction", "quadrant"],
    }


# ---------------------------------------------------------------------------
# 48h expiry
# ---------------------------------------------------------------------------


def test_expire_old_digests_removes_stale_keeps_fresh(tmp_path):
    digests = tmp_path / "digests"
    digests.mkdir(parents=True)
    stale = digests / "intake-2026-07-15T1000Z.json"
    fresh = digests / "intake-2026-07-17T1000Z.json"
    stale.write_text(json.dumps({"digest_id": "old", "created_utc": "2026-07-15T10:00:00Z"}))
    fresh.write_text(json.dumps({"digest_id": "new", "created_utc": "2026-07-17T10:00:00Z"}))

    expired = scan_inbox.expire_old_digests(digests.parent, NOW, 48)

    assert "old" in expired
    assert not stale.exists()
    assert fresh.exists()  # 12h old — within window


def test_expire_leaves_undateable_records_in_place(tmp_path):
    digests = tmp_path / "digests"
    digests.mkdir(parents=True)
    bad = digests / "intake-bad.json"
    bad.write_text(json.dumps({"digest_id": "bad"}))  # no created_utc
    expired = scan_inbox.expire_old_digests(digests.parent, NOW, 48)
    assert expired == []
    assert bad.exists()


def test_main_expires_stale_digest_on_run(tmp_path):
    digests = tmp_path / "digests"
    digests.mkdir(parents=True)
    stale = digests / "intake-2026-07-14T2200Z-inbox-5pm.json"
    stale.write_text(
        json.dumps({"digest_id": "2026-07-14T2200Z-inbox-5pm", "created_utc": "2026-07-14T22:00:00Z"})
    )
    _run_main(tmp_path, [_task(10)], now="2026-07-17T22:00:00Z")
    assert not stale.exists()  # >48h → expired
    assert (digests / "intake-2026-07-17T2200Z-inbox-5pm.json").exists()


# ---------------------------------------------------------------------------
# SC-009 — zero incomplete → no message, no record, exit 0
# ---------------------------------------------------------------------------


def test_sc009_zero_incomplete_writes_no_digest_but_exits_zero(tmp_path):
    # Inbox holds only a decomposition-pending (f:4) task → 0 to prompt.
    rc = _run_main(tmp_path, [_task(10, labels=["f:4-overload"])], now="2026-07-17T22:00:00Z")
    assert rc == 0
    assert not (tmp_path / "digests").exists() or not list(
        (tmp_path / "digests").glob("intake-*.json")
    )
    assert not (tmp_path / "latest.json").exists()
    # Tick artifact IS still written, recording scanned=1 incomplete=0.
    tick = json.loads((tmp_path / "intake-tick-latest.json").read_text())
    assert tick["counts"] == {"scanned": 1, "incomplete": 0, "prompted": 0}
    assert tick["exit_status"] == "success"


def test_sc009_empty_inbox_json_output_has_empty_digest_text(tmp_path, capsys):
    rc = scan_inbox.main(
        ["--state-dir", str(tmp_path), "--now-utc", "2026-07-17T22:00:00Z", "--json"],
        client=_FakeClient([]),
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["incomplete"] == 0
    assert payload["digest_text"] == ""
    assert payload["digest_id"] is None


# ---------------------------------------------------------------------------
# --dry-run writes nothing
# ---------------------------------------------------------------------------


def test_dry_run_writes_no_state(tmp_path, capsys):
    rc = scan_inbox.main(
        [
            "--state-dir",
            str(tmp_path),
            "--now-utc",
            "2026-07-17T22:00:00Z",
            "--dry-run",
            "--json",
        ],
        client=_FakeClient([_task(10, title="Alpha")]),
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["incomplete"] == 1
    assert payload["entries"][0]["task_id"] == 10
    assert "1. Alpha" in payload["digest_text"]
    # No writes at all in dry-run.
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# tick artifact + infra-failure exit code
# ---------------------------------------------------------------------------


def test_tick_artifact_written_on_normal_run(tmp_path):
    _run_main(tmp_path, [_task(10), _task(11)], now="2026-07-17T22:00:00Z")
    tick = json.loads((tmp_path / "intake-tick-2026-07-17.json").read_text())
    assert tick["counts"]["scanned"] == 2
    assert tick["counts"]["incomplete"] == 2
    assert tick["digest_id"] == "2026-07-17T2200Z-inbox-5pm"
    assert tick["errors"] == []


def test_infra_failure_exits_nonzero_and_writes_failure_tick(tmp_path):
    from scripts.common.vikunja_client import VikunjaServerError

    class _BoomClient:
        def get(self, path, *, params=None, timeout=None):
            raise VikunjaServerError(path=path, status=500)

    rc = scan_inbox.main(
        ["--state-dir", str(tmp_path), "--now-utc", "2026-07-17T22:00:00Z"],
        client=_BoomClient(),
    )
    assert rc == 1
    tick = json.loads((tmp_path / "intake-tick-latest.json").read_text())
    assert tick["exit_status"] == "failure"
    assert tick["errors"]


def test_bad_now_utc_exits_one(capsys):
    rc = scan_inbox.main(["--now-utc", "not-a-date"], client=_FakeClient([]))
    assert rc == 1
    assert "invalid" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# felix-bot (read) — never the kent write token
# ---------------------------------------------------------------------------


def test_build_client_uses_felix_bot_default_token(monkeypatch):
    captured: dict = {}

    class _FakeVC:
        def __init__(self, *, base_url=None, token=None, timeout=None):
            captured["token"] = token
            captured["base_url"] = base_url

    monkeypatch.setattr("scripts.common.vikunja_client.VikunjaClient", _FakeVC)
    scan_inbox._build_client(None)
    # No explicit token → the felix-bot default credential (never kent's).
    assert captured["token"] is None


def test_main_resolves_inbox_via_seam(tmp_path):
    # main() uses the real vikunja_refs seam to resolve the Inbox id (== 1).
    # A task tagged project_id=1 is enumerated; a task in another project is not.
    rc = _run_main(
        tmp_path,
        [_task(10), _task(11, project_id=WORKING_PROJECT_ID)],
        now="2026-07-17T22:00:00Z",
    )
    assert rc == 0
    record = json.loads(
        (tmp_path / "digests" / "intake-2026-07-17T2200Z-inbox-5pm.json").read_text()
    )
    assert [e["task_id"] for e in record["entries"]] == [10]
