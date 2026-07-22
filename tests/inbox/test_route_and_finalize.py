"""Tests for `scripts.inbox.route_and_finalize` — the note-level finalize
transaction (mission capture-atomic-finalize-01KXRM7J / #746, WP02).

Coverage posture (T013): per kind — success; route-failure (note unprocessed);
verify-failure (note unprocessed); and the NFR-004 retry-safety proof
(route-success then mark/log-failure → re-run → NO double-create). Plus a
multi-block note (one block fails → whole note unprocessed; a clean re-run skips
the succeeded block and marks once), delegated-vikunja provenance, github null
issue number, empty non-empty-body refusal, and the dry-run / CLI edges.

All external calls are mocked at the module seams — no live Vikunja / GitHub /
calendar helper / mark_processed. Tests drive ``raf.main()`` directly (the
existing ``tests/inbox/`` convention). The global ``_block_live_http`` guard in
``tests/conftest.py`` blows up loudly on any escape to the network.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.inbox import clarification_sweep_finalize as csf
from scripts.inbox import route_and_finalize as raf
from scripts.inbox import route_calendar_event as rce
from scripts.inbox import route_journal_entry as rje
from scripts.inbox import route_someday
from scripts.inbox import routing_log as _routing_log


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_existing_task(monkeypatch):
    """#751: default the in-process provenance precheck to 'no existing task' so
    the create path behaves as before. Tests that exercise the reconcile/reuse
    path override this with their own store-scanning stub. (The delegated
    vikunja_task path never calls the precheck.)"""
    monkeypatch.setattr(
        raf, "_find_existing_task_by_provenance", lambda *a, **k: None
    )


def _write_plan(tmp_path: Path, plan: dict | str, name: str = "plan.json") -> Path:
    target = tmp_path / name
    if isinstance(plan, str):
        # Raw-string plans bypass content injection — used by the tests that
        # deliberately omit `content` to exercise the validation gate.
        target.write_text(plan, encoding="utf-8")
    else:
        target.write_text(json.dumps(_with_default_content(plan)), encoding="utf-8")
    return target


def _with_default_content(plan: dict) -> dict:
    """Give every non-empty routed block a default verbatim `content` if it lacks
    one.

    The #746 post-merge validation gate requires a non-empty `content` string on
    every routed block (it is the D10 idempotency key; AGENTS.md instructs the
    agent to copy the verbatim block text). Fixtures that don't care about the
    key get a deterministic default so they stay valid under the gate; tests that
    assert missing/invalid content build the plan as a raw JSON string (which
    skips this helper). ``setdefault`` is idempotent, so blocks shared across two
    plans keep a stable hash.
    """
    blocks = plan.get("blocks")
    if isinstance(blocks, list):
        for block in blocks:
            if isinstance(block, dict) and block.get("kind") != "empty":
                block.setdefault("content", f"verbatim block text {block.get('block_index')}")
    return plan


def _run(argv: list[str], capsys) -> tuple[int, str, str]:
    code = raf.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _fake_completed(returncode: int, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(
        args=["seam"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def _created_stdout(event_id="evt_1", html="https://cal/evt_1"):
    return (
        f'{{"status": "created", "idempotent": false, '
        f'"event_id": "{event_id}", "html_link": "{html}"}}\n'
        "SUMMARY: op=create status=created\n"
    )


class _MarkSpy:
    """Records mark_processed calls; returns a configurable return code."""

    def __init__(self, returncode: int = 0, stderr: str = ""):
        self.calls: list[str] = []
        self.returncode = returncode
        self.stderr = stderr

    def __call__(self, source_path: str):
        self.calls.append(source_path)
        return _fake_completed(self.returncode, stdout='{"finalized": true}\n', stderr=self.stderr)


@pytest.fixture
def log_path(tmp_path, monkeypatch):
    """Redirect the routing log to a tmp file for the test's lifetime."""
    p = tmp_path / "routing.jsonl"
    monkeypatch.setattr(_routing_log, "DEFAULT_ROUTING_LOG_PATH", p)
    return p


def _log_rows(log_path: Path) -> list[dict]:
    if not log_path.exists():
        return []
    return [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]


def _source(tmp_path: Path, name: str = "Inbox Note.md", body: str = "content") -> Path:
    """Write a real inbox note (used where the finalize reads the note body)."""
    note = tmp_path / name
    note.write_text(f"---\nstatus: unprocessed\n---\n\n{body}\n", encoding="utf-8")
    return note


# ===========================================================================
# someday
# ===========================================================================


class TestSomeday:
    def _plan(self):
        return {
            "note_filename": "Note.md",
            "blocks": [{"block_index": 0, "kind": "someday", "payload": {"title": "Try Iceland"}}],
        }

    def test_success_marks_and_logs(self, tmp_path, capsys, monkeypatch, log_path):
        monkeypatch.setattr(raf, "_create_vikunja_task", lambda *a, **k: 512)
        monkeypatch.setattr(raf, "_fetch_vikunja_task", lambda tid: {"id": 512})
        mark = _MarkSpy()
        monkeypatch.setattr(raf, "_invoke_mark_processed", mark)

        pf = _write_plan(tmp_path, self._plan())
        code, out, err = _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys)

        assert code == 0, err
        result = json.loads(out)
        assert result["status"] == "finalized"
        assert result["marked_processed"] is True
        assert mark.calls == ["/inbox/Note.md"]
        rows = _log_rows(log_path)
        assert len(rows) == 1
        assert rows[0]["kind"] == "someday"
        assert rows[0]["destination"] == "512"
        assert rows[0]["vikunja_task_id"] == 512
        assert rows[0]["block_index"] == 0
        assert rows[0]["block_hash"]  # block-keyed (D10)

    def test_route_failure_leaves_note_unprocessed(self, tmp_path, capsys, monkeypatch, log_path):
        def boom(*a, **k):
            raise route_someday.RouteSomedayError("vikunja down")

        monkeypatch.setattr(raf, "_create_vikunja_task", boom)
        mark = _MarkSpy()
        monkeypatch.setattr(raf, "_invoke_mark_processed", mark)

        pf = _write_plan(tmp_path, self._plan())
        code, out, _ = _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys)

        assert code == 1
        result = json.loads(out)
        assert result["status"] == "error"
        assert result["blocks"][0]["stage"] == "route"
        assert mark.calls == [], "note must NOT be marked when a block fails"
        assert _log_rows(log_path) == []

    def test_verify_failure_leaves_note_unprocessed(self, tmp_path, capsys, monkeypatch, log_path):
        monkeypatch.setattr(raf, "_create_vikunja_task", lambda *a, **k: 512)
        # Task did not resolve (id mismatch) → verify failure.
        monkeypatch.setattr(raf, "_fetch_vikunja_task", lambda tid: {})
        mark = _MarkSpy()
        monkeypatch.setattr(raf, "_invoke_mark_processed", mark)

        pf = _write_plan(tmp_path, self._plan())
        code, out, _ = _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys)

        assert code == 1
        result = json.loads(out)
        assert result["status"] == "error"
        assert result["blocks"][0]["stage"] == "verify"
        assert mark.calls == []
        assert _log_rows(log_path) == []

    def test_retry_no_double_create_after_mark_failure(self, tmp_path, capsys, monkeypatch, log_path):
        """NFR-004: route succeeds + logs, then MARK fails → re-run skips the
        already-logged block (no double-create) and marks once."""
        create_calls = {"n": 0}

        def counting_create(*a, **k):
            create_calls["n"] += 1
            return 512

        monkeypatch.setattr(raf, "_create_vikunja_task", counting_create)
        monkeypatch.setattr(raf, "_fetch_vikunja_task", lambda tid: {"id": 512})
        pf = _write_plan(tmp_path, self._plan())

        # Run 1: log written (before mark), mark FAILS → note unprocessed.
        fail_mark = _MarkSpy(returncode=1, stderr="boom")
        monkeypatch.setattr(raf, "_invoke_mark_processed", fail_mark)
        code, out, _ = _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys)
        assert code == 1
        assert json.loads(out)["status"] == "error"
        assert create_calls["n"] == 1
        assert len(_log_rows(log_path)) == 1  # the block IS logged (log-before-mark)

        # Run 2: block already logged → skipped (no re-create); mark succeeds.
        ok_mark = _MarkSpy(returncode=0)
        monkeypatch.setattr(raf, "_invoke_mark_processed", ok_mark)
        code, out, _ = _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys)
        assert code == 0
        result = json.loads(out)
        assert result["status"] == "finalized"
        assert result["blocks"][0]["skipped"] is True
        assert create_calls["n"] == 1, "must NOT re-create the task on retry"
        assert ok_mark.calls == ["/inbox/Note.md"]
        assert len(_log_rows(log_path)) == 1, "no duplicate routing-log row"

    # -- #751: the create→verify / create→log failure windows ---------------
    #
    # These are the windows the routing-log skip does NOT cover: the create
    # succeeds but the tick dies BEFORE the routing-log row is written (verify
    # fails, or the log append itself fails). Without the provenance precheck the
    # next tick re-creates → orphan. With it, the next tick finds the task the
    # prior tick created and reuses it (no double-create).

    def _install_store(self, monkeypatch):
        """Wire the create + precheck seams to a shared in-memory Vikunja 'world'.

        create appends a task whose description carries the SAME Source/Block
        footer route_someday writes; the precheck runs the REAL line-anchored
        matcher over the store. Returns (store, create_calls)."""
        store: list[dict] = []
        create_calls = {"n": 0}
        next_id = {"v": 900}

        def fake_create(title, body, note_filename, project, block_key):
            create_calls["n"] += 1
            next_id["v"] += 1
            store.append(
                {
                    "id": next_id["v"],
                    "description": f"{body}\n\nSource: {note_filename}\nBlock: {block_key}",
                }
            )
            return next_id["v"]

        def fake_find(note_filename, block_key):
            return raf._match_provenance(store, note_filename, block_key)

        monkeypatch.setattr(raf, "_create_vikunja_task", fake_create)
        monkeypatch.setattr(raf, "_find_existing_task_by_provenance", fake_find)
        return store, create_calls

    def test_retry_no_double_create_after_verify_failure(
        self, tmp_path, capsys, monkeypatch, log_path
    ):
        """Tick 1: create succeeds, VERIFY fails (task never logged). Tick 2: the
        precheck finds the task tick 1 created and reuses it — no second create."""
        store, create_calls = self._install_store(monkeypatch)
        pf = _write_plan(tmp_path, self._plan())

        # Tick 1: fetch returns a non-matching id → verify failure. The task IS
        # created (and lands in `store`) but the block is never logged.
        monkeypatch.setattr(raf, "_fetch_vikunja_task", lambda tid: {})
        mark1 = _MarkSpy()
        monkeypatch.setattr(raf, "_invoke_mark_processed", mark1)
        code, out, _ = _run(
            ["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys
        )
        assert code == 1
        assert json.loads(out)["blocks"][0]["stage"] == "verify"
        assert create_calls["n"] == 1
        assert len(store) == 1  # the orphan-risk task exists
        assert mark1.calls == []
        assert _log_rows(log_path) == []

        # Tick 2: verify now resolves. The precheck must find the tick-1 task and
        # REUSE it (deduped) rather than create a second one.
        monkeypatch.setattr(
            raf, "_fetch_vikunja_task", lambda tid: {"id": tid}
        )
        mark2 = _MarkSpy()
        monkeypatch.setattr(raf, "_invoke_mark_processed", mark2)
        code, out, _ = _run(
            ["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys
        )
        result = json.loads(out)
        assert code == 0, out
        assert result["status"] == "finalized"
        assert result["blocks"][0].get("deduped") is True
        assert create_calls["n"] == 1, "must NOT re-create; the tick-1 task is reused"
        assert len(store) == 1, "no duplicate task created"
        assert mark2.calls == ["/inbox/Note.md"]
        rows = _log_rows(log_path)
        assert len(rows) == 1
        assert rows[0]["vikunja_task_id"] == 901

    def test_retry_no_double_create_after_log_failure(
        self, tmp_path, capsys, monkeypatch, log_path
    ):
        """Tick 1: create + verify succeed but the routing-log APPEND fails (block
        never logged). Tick 2: the precheck finds the task and reuses it."""
        store, create_calls = self._install_store(monkeypatch)
        monkeypatch.setattr(raf, "_fetch_vikunja_task", lambda tid: {"id": tid})
        pf = _write_plan(tmp_path, self._plan())

        # Tick 1: force the routing-log append to fail AFTER create+verify.
        real_append = raf.RoutingLogWriter.append

        def boom_append(self, *a, **k):
            raise OSError("disk full")

        monkeypatch.setattr(raf.RoutingLogWriter, "append", boom_append)
        mark1 = _MarkSpy()
        monkeypatch.setattr(raf, "_invoke_mark_processed", mark1)
        code, out, _ = _run(
            ["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys
        )
        assert code == 1
        assert json.loads(out)["blocks"][0]["stage"] == "log"
        assert create_calls["n"] == 1
        assert len(store) == 1
        assert mark1.calls == []
        assert _log_rows(log_path) == []

        # Tick 2: log append works again. Precheck finds the tick-1 task → reuse.
        monkeypatch.setattr(raf.RoutingLogWriter, "append", real_append)
        mark2 = _MarkSpy()
        monkeypatch.setattr(raf, "_invoke_mark_processed", mark2)
        code, out, _ = _run(
            ["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys
        )
        result = json.loads(out)
        assert code == 0, out
        assert result["status"] == "finalized"
        assert result["blocks"][0].get("deduped") is True
        assert create_calls["n"] == 1, "must NOT re-create; the tick-1 task is reused"
        assert len(store) == 1
        assert mark2.calls == ["/inbox/Note.md"]
        assert len(_log_rows(log_path)) == 1

    def test_precheck_scan_failure_fails_closed_no_create(
        self, tmp_path, capsys, monkeypatch, log_path
    ):
        """If the precheck scan itself errors, the block fails CLOSED — no task is
        created (never create when we could not first check for an existing one)."""
        from scripts.common.vikunja_client import VikunjaError

        def boom_find(note_filename, block_key):
            raise VikunjaError("tasks/all unreachable")

        created = {"n": 0}

        def must_not_create(*a, **k):
            created["n"] += 1
            return 512

        monkeypatch.setattr(raf, "_find_existing_task_by_provenance", boom_find)
        monkeypatch.setattr(raf, "_create_vikunja_task", must_not_create)
        mark = _MarkSpy()
        monkeypatch.setattr(raf, "_invoke_mark_processed", mark)

        pf = _write_plan(tmp_path, self._plan())
        code, out, _ = _run(
            ["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys
        )
        assert code == 1
        assert json.loads(out)["blocks"][0]["stage"] == "precheck"
        assert created["n"] == 0, "must NOT create when the precheck could not run"
        assert mark.calls == []
        assert _log_rows(log_path) == []


# ===========================================================================
# #751: the pure provenance matcher (_match_provenance)
# ===========================================================================


class TestMatchProvenance:
    def _task(self, tid, note, block):
        return {"id": tid, "description": f"body\n\nSource: {note}\nBlock: {block}"}

    def test_matches_on_both_source_and_block(self):
        tasks = [self._task(10, "Note.md", "0:hash0")]
        m = raf._match_provenance(tasks, "Note.md", "0:hash0")
        assert m is not None and m["id"] == 10

    def test_no_match_when_block_key_differs(self):
        tasks = [self._task(10, "Note.md", "0:hash0")]
        assert raf._match_provenance(tasks, "Note.md", "1:hash1") is None

    def test_no_match_when_source_differs(self):
        tasks = [self._task(10, "Other.md", "0:hash0")]
        assert raf._match_provenance(tasks, "Note.md", "0:hash0") is None

    def test_source_is_line_anchored_not_substring(self):
        # A task belonging to "Inbox 10.md" must not match "Inbox 1.md".
        tasks = [self._task(10, "Inbox 10.md", "0:hash0")]
        assert raf._match_provenance(tasks, "Inbox 1.md", "0:hash0") is None

    def test_lowest_id_wins_on_duplicate(self):
        tasks = [
            self._task(30, "Note.md", "0:h"),
            self._task(11, "Note.md", "0:h"),
            self._task(22, "Note.md", "0:h"),
        ]
        m = raf._match_provenance(tasks, "Note.md", "0:h")
        assert m["id"] == 11

    def test_ignores_malformed_entries(self):
        tasks = ["nope", {"id": 5}, {"id": 6, "description": None}]
        assert raf._match_provenance(tasks, "Note.md", "0:h") is None


class _PagedClient:
    """Fake VikunjaClient returning a queued sequence of task page bodies.

    Production ``VikunjaClient.list_all_tasks`` enumerates project-scoped (its
    rigor is covered in ``tests/common/test_vikunja_client``). This double
    reproduces the same *result* — a flat task list — by paging its queued
    fixtures, so ``_iter_all_tasks`` delegation and the null/partial/non-list
    termination intents keep being exercised.
    """

    def __init__(self, pages):
        self._pages = list(pages)
        self.calls = 0

    def list_all_tasks(self, *, updated_since=None, per_page=50, max_pages_per_project=200):
        from scripts.common.vikunja_client import VikunjaError

        tasks: list[dict] = []
        page = 1
        while True:
            batch = self.get("/tasks/all", params={"page": str(page), "per_page": str(per_page)})
            if batch is None:
                break
            if not isinstance(batch, list):
                raise VikunjaError(path="/tasks/all", status=200)
            if not batch:
                break
            tasks.extend(b for b in batch if isinstance(b, dict))
            if len(batch) < per_page:
                break
            page += 1
        return tasks

    def get(self, path, params=None, **kwargs):
        assert path == "/tasks/all"
        self.calls += 1
        return self._pages.pop(0) if self._pages else []


class TestIterAllTasks:
    def test_null_body_on_page_one_is_empty_not_error(self):
        """#751 review: Vikunja returns null for an empty collection — must be
        treated as an empty page (end of pagination), NOT a scan error that would
        fail the precheck closed and strand the note."""
        client = _PagedClient([None])
        assert raf._iter_all_tasks(client) == []

    def test_null_after_full_page_terminates_with_that_page(self):
        full = [{"id": i, "description": "x"} for i in range(50)]
        client = _PagedClient([full, None])
        result = raf._iter_all_tasks(client)
        assert len(result) == 50
        assert client.calls == 2

    def test_partial_page_terminates(self):
        client = _PagedClient([[{"id": 1, "description": "x"}]])
        assert len(raf._iter_all_tasks(client)) == 1
        assert client.calls == 1

    def test_non_list_non_null_body_is_error(self):
        from scripts.common.vikunja_client import VikunjaError

        client = _PagedClient([{"unexpected": "dict"}])
        with pytest.raises(VikunjaError):
            raf._iter_all_tasks(client)


# ===========================================================================
# vikunja_task (delegated provenance — D11 / FR-006)
# ===========================================================================


class TestVikunjaTaskDelegated:
    def test_success_verifies_provenance_no_create(self, tmp_path, capsys, monkeypatch, log_path):
        # Delegated: the plan carries a task_id; finalize must NOT create.
        monkeypatch.setattr(
            raf,
            "_create_vikunja_task",
            lambda *a, **k: pytest.fail("delegated path must not create a task"),
        )
        monkeypatch.setattr(
            raf,
            "_fetch_vikunja_task",
            lambda tid: {"id": 777, "description": "body\n\nSource: Note.md"},
        )
        mark = _MarkSpy()
        monkeypatch.setattr(raf, "_invoke_mark_processed", mark)

        plan = {
            "note_filename": "Note.md",
            "blocks": [{"block_index": 0, "kind": "vikunja_task", "task_id": 777}],
        }
        pf = _write_plan(tmp_path, plan)
        code, out, _ = _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys)

        assert code == 0
        result = json.loads(out)
        assert result["status"] == "finalized"
        assert mark.calls == ["/inbox/Note.md"]
        rows = _log_rows(log_path)
        assert rows[0]["kind"] == "vikunja_task"
        assert rows[0]["vikunja_task_id"] == 777

    def test_non_belonging_id_is_failure(self, tmp_path, capsys, monkeypatch, log_path):
        # SC-004: the id exists but its provenance does NOT match this note.
        monkeypatch.setattr(
            raf,
            "_fetch_vikunja_task",
            lambda tid: {"id": 777, "description": "Source: SomeOther.md"},
        )
        mark = _MarkSpy()
        monkeypatch.setattr(raf, "_invoke_mark_processed", mark)

        plan = {
            "note_filename": "Note.md",
            "blocks": [{"block_index": 0, "kind": "vikunja_task", "task_id": 777}],
        }
        pf = _write_plan(tmp_path, plan)
        code, out, _ = _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys)

        assert code == 1
        result = json.loads(out)
        assert result["status"] == "error"
        assert result["blocks"][0]["stage"] == "verify"
        assert "provenance" in result["blocks"][0]["error"]
        assert mark.calls == []
        assert _log_rows(log_path) == []

    def test_provenance_substring_false_positive_rejected(self, tmp_path, capsys, monkeypatch, log_path):
        # Finding 6 (#746 post-merge): provenance must be a line-anchored EXACT
        # `Source: <filename>` match, not a substring. Here the delegated task
        # belongs to `Inbox 10.md` (its `Source:` footer) but its body happens to
        # mention `Inbox 1.md`. The old `note_filename in description` substring
        # test matched that stray mention and wrongly attributed the task to
        # `Inbox 1.md`; the exact-line test rejects it.
        monkeypatch.setattr(
            raf,
            "_fetch_vikunja_task",
            lambda tid: {
                "id": 777,
                "description": "Follow-up on Inbox 1.md discussion\n\nSource: Inbox 10.md",
            },
        )
        mark = _MarkSpy()
        monkeypatch.setattr(raf, "_invoke_mark_processed", mark)
        plan = {
            "note_filename": "Inbox 1.md",
            "blocks": [{"block_index": 0, "kind": "vikunja_task", "task_id": 777}],
        }
        pf = _write_plan(tmp_path, plan)
        code, out, _ = _run(["--source-path", "/inbox/Inbox 1.md", "--plan-file", str(pf)], capsys)

        assert code == 1
        result = json.loads(out)
        assert result["status"] == "error"
        assert result["blocks"][0]["stage"] == "verify"
        assert "provenance" in result["blocks"][0]["error"]
        assert mark.calls == []
        assert _log_rows(log_path) == []

    def test_absent_id_is_verify_failure(self, tmp_path, capsys, monkeypatch, log_path):
        from scripts.common.vikunja_client import VikunjaError

        def not_found(tid):
            raise VikunjaError("404")

        monkeypatch.setattr(raf, "_fetch_vikunja_task", not_found)
        mark = _MarkSpy()
        monkeypatch.setattr(raf, "_invoke_mark_processed", mark)
        plan = {
            "note_filename": "Note.md",
            "blocks": [{"block_index": 0, "kind": "vikunja_task", "task_id": 42}],
        }
        pf = _write_plan(tmp_path, plan)
        code, out, _ = _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys)
        assert code == 1
        assert json.loads(out)["blocks"][0]["stage"] == "verify"
        assert mark.calls == []


# ===========================================================================
# github_issue (FR-012 / D11)
# ===========================================================================


class TestGithubIssue:
    def test_success_verifies_and_logs(self, tmp_path, capsys, monkeypatch, log_path):
        monkeypatch.setattr(raf, "_verify_issue_exists", lambda n: True)
        mark = _MarkSpy()
        monkeypatch.setattr(raf, "_invoke_mark_processed", mark)
        plan = {
            "note_filename": "Note.md",
            "blocks": [{"block_index": 0, "kind": "github_issue", "issue_number": 290}],
        }
        pf = _write_plan(tmp_path, plan)
        code, out, _ = _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys)
        assert code == 0
        result = json.loads(out)
        assert result["status"] == "finalized"
        rows = _log_rows(log_path)
        assert rows[0]["kind"] == "github_issue"
        assert rows[0]["destination"] == "290"
        assert rows[0]["issue_number"] == 290

    def test_null_issue_number_is_failure(self, tmp_path, capsys, monkeypatch, log_path):
        # FR-012: a null/missing issue number blocks the mark.
        monkeypatch.setattr(
            raf, "_verify_issue_exists", lambda n: pytest.fail("must not verify a null number")
        )
        mark = _MarkSpy()
        monkeypatch.setattr(raf, "_invoke_mark_processed", mark)
        plan = {
            "note_filename": "Note.md",
            "blocks": [{"block_index": 0, "kind": "github_issue", "issue_number": None}],
        }
        pf = _write_plan(tmp_path, plan)
        code, out, _ = _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys)
        assert code == 1
        assert json.loads(out)["status"] == "error"
        assert mark.calls == []
        assert _log_rows(log_path) == []

    def test_verify_failure_when_issue_missing(self, tmp_path, capsys, monkeypatch, log_path):
        monkeypatch.setattr(raf, "_verify_issue_exists", lambda n: False)
        mark = _MarkSpy()
        monkeypatch.setattr(raf, "_invoke_mark_processed", mark)
        plan = {
            "note_filename": "Note.md",
            "blocks": [{"block_index": 0, "kind": "github_issue", "issue_number": 999}],
        }
        pf = _write_plan(tmp_path, plan)
        code, out, _ = _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys)
        assert code == 1
        assert json.loads(out)["blocks"][0]["stage"] == "verify"
        assert mark.calls == []

    def test_inline_filer_provenance(self, tmp_path, capsys, monkeypatch, log_path):
        # In-line path: plan carries a filing payload; finalize invokes the filer.
        filer_out = '{"issue_number": 291, "issue_url": "https://x/291"}\nSUMMARY: issue=#291\n'
        monkeypatch.setattr(raf, "_invoke_issue_filer", lambda payload: _fake_completed(0, stdout=filer_out))
        monkeypatch.setattr(raf, "_verify_issue_exists", lambda n: True)
        mark = _MarkSpy()
        monkeypatch.setattr(raf, "_invoke_mark_processed", mark)
        plan = {
            "note_filename": "Note.md",
            "blocks": [
                {
                    "block_index": 0,
                    "kind": "github_issue",
                    "payload": {"type": "bug", "title": "x", "problem_statement": "p"},
                }
            ],
        }
        pf = _write_plan(tmp_path, plan)
        code, out, _ = _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys)
        assert code == 0
        result = json.loads(out)
        assert result["status"] == "finalized"
        assert _log_rows(log_path)[0]["issue_number"] == 291

    def test_retry_no_double_verify_after_mark_failure(self, tmp_path, capsys, monkeypatch, log_path):
        verify_calls = {"n": 0}

        def counting_verify(n):
            verify_calls["n"] += 1
            return True

        monkeypatch.setattr(raf, "_verify_issue_exists", counting_verify)
        plan = {
            "note_filename": "Note.md",
            "blocks": [{"block_index": 0, "kind": "github_issue", "issue_number": 290}],
        }
        pf = _write_plan(tmp_path, plan)

        monkeypatch.setattr(raf, "_invoke_mark_processed", _MarkSpy(returncode=1))
        code, _, _ = _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys)
        assert code == 1
        assert len(_log_rows(log_path)) == 1

        ok = _MarkSpy(returncode=0)
        monkeypatch.setattr(raf, "_invoke_mark_processed", ok)
        code, out, _ = _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys)
        assert code == 0
        assert json.loads(out)["blocks"][0]["skipped"] is True
        assert verify_calls["n"] == 1
        assert len(_log_rows(log_path)) == 1


# ===========================================================================
# journal (FR-010 sentinel dedup)
# ===========================================================================


class TestJournal:
    def _plan(self):
        return {
            "note_filename": "Note.md",
            "blocks": [
                {
                    "block_index": 0,
                    "kind": "journal",
                    "payload": {
                        "content": "Today I felt calm and focused.",
                        "datetime": "2026-07-17T09:30:00-04:00",
                    },
                }
            ],
        }

    def test_success_appends_with_sentinel_and_logs(self, tmp_path, capsys, monkeypatch, log_path):
        journal_dir = tmp_path / "journal"
        monkeypatch.setattr(rje, "resolve_journal_dir", lambda: journal_dir)
        mark = _MarkSpy()
        monkeypatch.setattr(raf, "_invoke_mark_processed", mark)

        pf = _write_plan(tmp_path, self._plan())
        code, out, err = _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys)

        assert code == 0, err
        result = json.loads(out)
        assert result["status"] == "finalized"
        target = journal_dir / rje.target_filename(rje._parse_iso_datetime("2026-07-17T09:30:00-04:00"))
        text = target.read_text()
        assert "<!-- src: Note.md#0 -->" in text
        assert "Today I felt calm" in text
        rows = _log_rows(log_path)
        assert rows[0]["kind"] == "journal"
        assert rows[0]["destination"] == str(target)

    def test_reprocess_does_not_duplicate_section(self, tmp_path, capsys, monkeypatch, log_path):
        # FR-010: even if the routing-log entry is lost, the per-block sentinel
        # (verify-before-append) prevents a duplicated journal section.
        journal_dir = tmp_path / "journal"
        monkeypatch.setattr(rje, "resolve_journal_dir", lambda: journal_dir)
        monkeypatch.setattr(raf, "_invoke_mark_processed", _MarkSpy())
        pf = _write_plan(tmp_path, self._plan())

        _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys)
        # Simulate the routing-log being lost (block key no longer present).
        log_path.unlink()
        _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys)

        target = journal_dir / rje.target_filename(rje._parse_iso_datetime("2026-07-17T09:30:00-04:00"))
        text = target.read_text()
        assert text.count("<!-- src: Note.md#0 -->") == 1, "section must not be duplicated"

    def test_route_failure_on_missing_datetime(self, tmp_path, capsys, monkeypatch, log_path):
        monkeypatch.setattr(rje, "resolve_journal_dir", lambda: tmp_path / "journal")
        mark = _MarkSpy()
        monkeypatch.setattr(raf, "_invoke_mark_processed", mark)
        plan = {
            "note_filename": "Note.md",
            "blocks": [{"block_index": 0, "kind": "journal", "payload": {"content": "hi"}}],
        }
        pf = _write_plan(tmp_path, plan)
        code, out, _ = _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys)
        assert code == 1
        assert json.loads(out)["blocks"][0]["stage"] == "route"
        assert mark.calls == []


# ===========================================================================
# calendar (fold #737 — NFR-003 preserved)
# ===========================================================================


class TestCalendar:
    def _plan(self):
        return {
            "note_filename": "Note.md",
            "blocks": [
                {
                    "block_index": 0,
                    "kind": "calendar",
                    "payload": {"title": "Emanuel call", "start": "2026-07-16T12:00:00-04:00"},
                }
            ],
        }

    def test_success_marks_and_logs(self, tmp_path, capsys, monkeypatch, log_path):
        monkeypatch.setattr(rce, "_invoke_calendar_helper", lambda *a, **k: _fake_completed(0, stdout=_created_stdout()))
        mark = _MarkSpy()
        monkeypatch.setattr(raf, "_invoke_mark_processed", mark)

        pf = _write_plan(tmp_path, self._plan())
        code, out, err = _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys)

        assert code == 0, err
        result = json.loads(out)
        assert result["status"] == "finalized"
        rows = _log_rows(log_path)
        assert rows[0]["kind"] == "calendar"
        assert rows[0]["destination"] == "evt_1"

    def test_needs_clarification_leaves_note_unprocessed(self, tmp_path, capsys, monkeypatch, log_path):
        # NFR-003: incomplete payload → needs_clarification (helper NOT called),
        # note left unprocessed, exit 0.
        def fake_invoke(*a, **k):
            pytest.fail("helper must not be called for an invalid payload")

        monkeypatch.setattr(rce, "_invoke_calendar_helper", fake_invoke)
        mark = _MarkSpy()
        monkeypatch.setattr(raf, "_invoke_mark_processed", mark)
        plan = {
            "note_filename": "Note.md",
            "blocks": [{"block_index": 0, "kind": "calendar", "payload": {"title": "Sync"}}],
        }
        pf = _write_plan(tmp_path, plan)
        code, out, _ = _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys)
        assert code == 0
        result = json.loads(out)
        assert result["status"] == "needs_clarification"
        assert "start" in result["blocks"][0]["missing"]
        assert mark.calls == []
        assert _log_rows(log_path) == []

    def test_create_error_leaves_note_unprocessed(self, tmp_path, capsys, monkeypatch, log_path):
        # NFR-003: create failure → error, note unprocessed, non-zero exit.
        monkeypatch.setattr(
            rce,
            "_invoke_calendar_helper",
            lambda *a, **k: _fake_completed(3, stderr="ERROR: auth_failed invalid_grant\n"),
        )
        mark = _MarkSpy()
        monkeypatch.setattr(raf, "_invoke_mark_processed", mark)
        pf = _write_plan(tmp_path, self._plan())
        code, out, _ = _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys)
        assert code == 1
        result = json.loads(out)
        assert result["status"] == "error"
        assert "auth_failed" in result["blocks"][0]["error"]
        assert mark.calls == []
        assert _log_rows(log_path) == []

    def test_retry_no_double_create_after_mark_failure(self, tmp_path, capsys, monkeypatch, log_path):
        create_calls = {"n": 0}

        def counting_invoke(*a, **k):
            create_calls["n"] += 1
            return _fake_completed(0, stdout=_created_stdout())

        monkeypatch.setattr(rce, "_invoke_calendar_helper", counting_invoke)
        pf = _write_plan(tmp_path, self._plan())

        monkeypatch.setattr(raf, "_invoke_mark_processed", _MarkSpy(returncode=1))
        code, _, _ = _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys)
        assert code == 1
        assert len(_log_rows(log_path)) == 1

        ok = _MarkSpy(returncode=0)
        monkeypatch.setattr(raf, "_invoke_mark_processed", ok)
        code, out, _ = _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys)
        assert code == 0
        assert json.loads(out)["blocks"][0]["skipped"] is True
        assert create_calls["n"] == 1
        assert len(_log_rows(log_path)) == 1


# ===========================================================================
# calendar clarification eligibility signal (#780 — Codex post-merge gap fix)
# ===========================================================================


class TestCalendarClarificationSignal:
    """The needs_clarification path builds the all-day-fallback eligibility signal
    ``{title, start_date, missing_fields}`` deterministically in code and surfaces
    it on the calendar block so it reaches the pending record — the reachable path
    the aged-out sweep (``clarification_sweep_finalize.is_eligible``) reads. The
    ``start_date`` is resolved against the note's CAPTURE-time anchor (INV-5: a
    relative "Thursday" must not drift to the wrong week when re-parsed later).
    """

    def _note(self, tmp_path, name, *, date="2026-07-14", time="16:28", body):
        note = tmp_path / name
        note.write_text(
            f"---\ndate: {date}\ntime: {time}\ntype: inbox\nstatus: unprocessed\n---\n\n{body}\n",
            encoding="utf-8",
        )
        return note

    def _plan(self, content, filename="Inbox.md"):
        # Title present but NO valid `start` → needs_clarification (helper NOT
        # called); `content` is the verbatim block text parse_datetime searches.
        return {
            "note_filename": filename,
            "blocks": [
                {
                    "block_index": 0,
                    "kind": "calendar",
                    "content": content,
                    "payload": {"title": "Meet Rob"},
                }
            ],
        }

    @staticmethod
    def _no_helper(monkeypatch):
        def fake_invoke(*a, **k):
            pytest.fail("calendar helper must not be called for an invalid payload")

        monkeypatch.setattr(rce, "_invoke_calendar_helper", fake_invoke)

    def test_no_time_block_surfaces_tick_anchored_signal(
        self, tmp_path, capsys, monkeypatch, log_path
    ):
        self._no_helper(monkeypatch)
        mark = _MarkSpy()
        monkeypatch.setattr(raf, "_invoke_mark_processed", mark)

        # Capture anchor: Tuesday 2026-07-14 → "Thursday" resolves to 2026-07-16.
        note = self._note(tmp_path, "Inbox.md", body="Meet Rob Thursday")
        pf = _write_plan(tmp_path, self._plan("Meet Rob Thursday"))
        code, out, err = _run(["--source-path", str(note), "--plan-file", str(pf)], capsys)

        assert code == 0, err
        result = json.loads(out)
        assert result["status"] == "needs_clarification"
        block = result["blocks"][0]
        # `missing` (backward-compat) is still present alongside the new signal.
        assert "start" in block["missing"]
        signal = block["clarification_signal"]
        assert signal["title"] == "Meet Rob"
        # Tick-anchored (this Thursday from the Tuesday capture), NOT `now`.
        assert signal["start_date"] == "2026-07-16"
        assert "start_time" in signal["missing_fields"]
        assert mark.calls == []  # note left unprocessed
        assert _log_rows(log_path) == []

    def test_undateable_block_is_fail_closed_no_start_date(
        self, tmp_path, capsys, monkeypatch, log_path
    ):
        self._no_helper(monkeypatch)
        mark = _MarkSpy()
        monkeypatch.setattr(raf, "_invoke_mark_processed", mark)

        note = self._note(tmp_path, "Inbox.md", body="Meet Rob sometime soon")
        pf = _write_plan(tmp_path, self._plan("Meet Rob sometime soon"))
        code, out, err = _run(["--source-path", str(note), "--plan-file", str(pf)], capsys)

        assert code == 0, err
        result = json.loads(out)
        assert result["status"] == "needs_clarification"
        block = result["blocks"][0]
        assert "start" in block["missing"]
        # Fail-closed: an un-dateable block surfaces NO signal (the validator
        # emits no start_date) → the record stays ineligible for the fallback.
        assert "clarification_signal" not in block
        assert mark.calls == []

    def test_produced_signal_drives_is_eligible_true_and_false(
        self, tmp_path, capsys, monkeypatch, log_path
    ):
        # End-to-end: the produced signal, recorded as `partial_payload`, drives
        # the aged-out sweep's eligibility predicate — True for the dateable case,
        # False for the un-dateable one.
        self._no_helper(monkeypatch)
        monkeypatch.setattr(raf, "_invoke_mark_processed", _MarkSpy())

        good = self._note(tmp_path, "Good.md", body="Meet Rob Thursday")
        pf = _write_plan(tmp_path, self._plan("Meet Rob Thursday", "Good.md"), name="good.json")
        _c, out, _e = _run(["--source-path", str(good), "--plan-file", str(pf)], capsys)
        good_signal = json.loads(out)["blocks"][0]["clarification_signal"]
        assert csf.is_eligible({"partial_payload": good_signal}) is True

        bad = self._note(tmp_path, "Bad.md", body="Meet Rob sometime soon")
        pf2 = _write_plan(tmp_path, self._plan("Meet Rob sometime soon", "Bad.md"), name="bad.json")
        _c2, out2, _e2 = _run(["--source-path", str(bad), "--plan-file", str(pf2)], capsys)
        bad_block = json.loads(out2)["blocks"][0]
        bad_signal = bad_block.get("clarification_signal", {})
        assert csf.is_eligible({"partial_payload": bad_signal}) is False


# ===========================================================================
# empty disposition (D12 / FR-007)
# ===========================================================================


class TestEmpty:
    def test_empty_body_marks_and_logs(self, tmp_path, capsys, monkeypatch, log_path):
        note = _source(tmp_path, "Empty.md", body="")
        mark = _MarkSpy()
        monkeypatch.setattr(raf, "_invoke_mark_processed", mark)
        pf = _write_plan(tmp_path, {"note_filename": "Empty.md", "blocks": []})
        code, out, err = _run(["--source-path", str(note), "--plan-file", str(pf)], capsys)
        assert code == 0, err
        result = json.loads(out)
        assert result["status"] == "finalized"
        assert mark.calls == [str(note)]
        rows = _log_rows(log_path)
        assert rows[0]["kind"] == "empty"
        assert rows[0]["destination"] == ""

    def test_templater_only_body_is_empty(self, tmp_path, capsys, monkeypatch, log_path):
        note = _source(tmp_path, "Cursor.md", body="<% tp.file.cursor() %>")
        monkeypatch.setattr(raf, "_invoke_mark_processed", _MarkSpy())
        pf = _write_plan(tmp_path, {"note_filename": "Cursor.md", "blocks": []})
        code, out, err = _run(["--source-path", str(note), "--plan-file", str(pf)], capsys)
        assert code == 0, err
        assert json.loads(out)["status"] == "finalized"

    def test_non_empty_body_refused(self, tmp_path, capsys, monkeypatch, log_path):
        # FR-007: the empty disposition must refuse a note with real content.
        note = _source(tmp_path, "Real.md", body="Buy milk and call the dentist")
        mark = _MarkSpy()
        monkeypatch.setattr(raf, "_invoke_mark_processed", mark)
        pf = _write_plan(tmp_path, {"note_filename": "Real.md", "blocks": []})
        code, out, _ = _run(["--source-path", str(note), "--plan-file", str(pf)], capsys)
        assert code == 1
        result = json.loads(out)
        assert result["status"] == "error"
        assert result["blocks"][0]["stage"] == "verify"
        assert mark.calls == []
        assert _log_rows(log_path) == []

    def test_explicit_empty_kind_block(self, tmp_path, capsys, monkeypatch, log_path):
        note = _source(tmp_path, "E2.md", body="")
        monkeypatch.setattr(raf, "_invoke_mark_processed", _MarkSpy())
        pf = _write_plan(
            tmp_path, {"note_filename": "E2.md", "blocks": [{"block_index": 0, "kind": "empty"}]}
        )
        code, out, err = _run(["--source-path", str(note), "--plan-file", str(pf)], capsys)
        assert code == 0, err
        assert json.loads(out)["status"] == "finalized"


# ===========================================================================
# multi-block note (SC-002 / SC-003)
# ===========================================================================


class TestMultiBlock:
    def test_one_block_fails_whole_note_unprocessed_then_clean_rerun(
        self, tmp_path, capsys, monkeypatch, log_path
    ):
        someday_block = {"block_index": 0, "kind": "someday", "payload": {"title": "Iceland"}}
        create_calls = {"n": 0}

        def counting_create(*a, **k):
            create_calls["n"] += 1
            return 512

        monkeypatch.setattr(raf, "_create_vikunja_task", counting_create)
        monkeypatch.setattr(raf, "_fetch_vikunja_task", lambda tid: {"id": 512})
        monkeypatch.setattr(raf, "_verify_issue_exists", lambda n: True)

        # Run 1: someday routes+logs; github has a null issue number → fails.
        plan1 = {
            "note_filename": "Note.md",
            "blocks": [someday_block, {"block_index": 1, "kind": "github_issue", "issue_number": None}],
        }
        pf1 = _write_plan(tmp_path, plan1, name="plan1.json")
        mark1 = _MarkSpy()
        monkeypatch.setattr(raf, "_invoke_mark_processed", mark1)
        code, out, _ = _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf1)], capsys)
        assert code == 1
        result = json.loads(out)
        assert result["status"] == "error"
        assert mark1.calls == [], "note must NOT be marked when any block fails"
        rows = _log_rows(log_path)
        assert len(rows) == 1 and rows[0]["kind"] == "someday"  # only the succeeded block logged
        assert create_calls["n"] == 1

        # Run 2: github now carries a valid issue number; someday is skipped.
        plan2 = {
            "note_filename": "Note.md",
            "blocks": [someday_block, {"block_index": 1, "kind": "github_issue", "issue_number": 290}],
        }
        pf2 = _write_plan(tmp_path, plan2, name="plan2.json")
        mark2 = _MarkSpy()
        monkeypatch.setattr(raf, "_invoke_mark_processed", mark2)
        code, out, _ = _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf2)], capsys)
        assert code == 0
        result = json.loads(out)
        assert result["status"] == "finalized"
        # someday skipped (no re-create), github routed, mark once.
        assert create_calls["n"] == 1, "succeeded block must not re-create on retry"
        assert result["blocks"][0]["skipped"] is True
        assert mark2.calls == ["/inbox/Note.md"]
        rows = _log_rows(log_path)
        kinds = sorted(r["kind"] for r in rows)
        assert kinds == ["github_issue", "someday"]  # exactly one row each; no dup


# ===========================================================================
# plan validation gate (#746 post-merge — findings 3 & 5)
# ===========================================================================


class TestPlanValidation:
    """Every non-empty routed block must carry an integer `block_index` and a
    non-empty `content` string BEFORE any side effect. A bad plan fails loud
    (note left unprocessed, nothing routed / marked)."""

    def _guard(self, monkeypatch):
        monkeypatch.setattr(
            raf, "_create_vikunja_task", lambda *a, **k: pytest.fail("must not route on a bad plan")
        )
        monkeypatch.setattr(
            raf, "_invoke_mark_processed", lambda p: pytest.fail("must not mark on a bad plan")
        )

    def test_missing_block_index_is_finalize_error(self, tmp_path, capsys, monkeypatch, log_path):
        self._guard(monkeypatch)
        plan = {
            "note_filename": "Note.md",
            "blocks": [{"kind": "someday", "content": "buy milk", "payload": {"title": "Buy milk"}}],
        }
        pf = _write_plan(tmp_path, plan)
        code, out, _ = _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys)
        assert code == 1
        result = json.loads(out)
        assert result["status"] == "error"
        assert result["blocks"][0]["stage"] == "validate"
        assert "block_index" in result["blocks"][0]["error"]
        assert _log_rows(log_path) == []

    def test_non_integer_block_index_is_finalize_error(self, tmp_path, capsys, monkeypatch, log_path):
        self._guard(monkeypatch)
        plan = {
            "note_filename": "Note.md",
            "blocks": [{"block_index": "0", "kind": "someday", "content": "x", "payload": {"title": "t"}}],
        }
        pf = _write_plan(tmp_path, plan)
        code, out, _ = _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys)
        assert code == 1
        result = json.loads(out)
        assert result["status"] == "error"
        assert result["blocks"][0]["stage"] == "validate"
        assert "block_index" in result["blocks"][0]["error"]
        assert _log_rows(log_path) == []

    def test_bool_block_index_is_finalize_error(self, tmp_path, capsys, monkeypatch, log_path):
        # bool is an int subclass — a JSON `true` must not slip through as index 1.
        self._guard(monkeypatch)
        plan = {
            "note_filename": "Note.md",
            "blocks": [{"block_index": True, "kind": "someday", "content": "x", "payload": {"title": "t"}}],
        }
        pf = _write_plan(tmp_path, plan)
        code, out, _ = _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys)
        assert code == 1
        result = json.loads(out)
        assert result["status"] == "error"
        assert result["blocks"][0]["stage"] == "validate"
        assert _log_rows(log_path) == []

    def test_missing_content_is_finalize_error(self, tmp_path, capsys, monkeypatch, log_path):
        # Raw JSON string bypasses the fixture's default-content injection so the
        # block genuinely lacks `content`.
        self._guard(monkeypatch)
        plan_str = json.dumps(
            {
                "note_filename": "Note.md",
                "blocks": [{"block_index": 0, "kind": "someday", "payload": {"title": "t"}}],
            }
        )
        pf = _write_plan(tmp_path, plan_str)
        code, out, _ = _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys)
        assert code == 1
        result = json.loads(out)
        assert result["status"] == "error"
        assert result["blocks"][0]["stage"] == "validate"
        assert "content" in result["blocks"][0]["error"]
        assert _log_rows(log_path) == []

    def test_empty_string_content_is_finalize_error(self, tmp_path, capsys, monkeypatch, log_path):
        # A present-but-blank content is as bad as a missing one (not a real key).
        self._guard(monkeypatch)
        plan_str = json.dumps(
            {
                "note_filename": "Note.md",
                "blocks": [{"block_index": 0, "kind": "someday", "content": "   ", "payload": {"title": "t"}}],
            }
        )
        pf = _write_plan(tmp_path, plan_str)
        code, out, _ = _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys)
        assert code == 1
        result = json.loads(out)
        assert result["status"] == "error"
        assert result["blocks"][0]["stage"] == "validate"
        assert "content" in result["blocks"][0]["error"]
        assert _log_rows(log_path) == []


# ===========================================================================
# dry-run + CLI edges
# ===========================================================================


class TestDryRunAndCli:
    def test_dry_run_no_side_effects(self, tmp_path, capsys, monkeypatch, log_path):
        monkeypatch.setattr(
            raf, "_create_vikunja_task", lambda *a, **k: pytest.fail("dry-run must not route")
        )
        monkeypatch.setattr(
            raf, "_invoke_mark_processed", lambda p: pytest.fail("dry-run must not mark")
        )
        plan = {
            "note_filename": "Note.md",
            "blocks": [{"block_index": 0, "kind": "someday", "payload": {"title": "x"}}],
        }
        pf = _write_plan(tmp_path, plan)
        code, out, _ = _run(
            ["--source-path", "/inbox/Note.md", "--plan-file", str(pf), "--dry-run"], capsys
        )
        assert code == 0
        result = json.loads(out)
        assert result["status"] == "dry_run"
        assert result["would_finalize"] is True
        assert _log_rows(log_path) == []

    def test_dry_run_invalid_calendar_reports_would_not_finalize(self, tmp_path, capsys):
        plan = {
            "note_filename": "Note.md",
            "blocks": [{"block_index": 0, "kind": "calendar", "payload": {"title": "Sync"}}],
        }
        pf = _write_plan(tmp_path, plan)
        code, out, _ = _run(
            ["--source-path", "/inbox/Note.md", "--plan-file", str(pf), "--dry-run"], capsys
        )
        assert code == 0
        result = json.loads(out)
        assert result["would_finalize"] is False
        assert "start" in result["blocks"][0]["missing"]

    def test_unknown_kind_is_error(self, tmp_path, capsys, monkeypatch, log_path):
        monkeypatch.setattr(raf, "_invoke_mark_processed", _MarkSpy())
        plan = {
            "note_filename": "Note.md",
            "blocks": [{"block_index": 0, "kind": "sasquatch"}],
        }
        pf = _write_plan(tmp_path, plan)
        code, out, _ = _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys)
        assert code == 1
        assert json.loads(out)["status"] == "error"

    def test_plan_file_missing_exits_1(self, tmp_path, capsys):
        code, _, err = _run(
            ["--source-path", "/inbox/Note.md", "--plan-file", str(tmp_path / "nope.json")], capsys
        )
        assert code == 1
        assert "file_not_found" in err

    def test_malformed_plan_json_exits_1(self, tmp_path, capsys):
        pf = _write_plan(tmp_path, "{not json", name="bad.json")
        code, _, err = _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys)
        assert code == 1
        assert "malformed_json" in err

    def test_plan_not_object_exits_1(self, tmp_path, capsys):
        pf = _write_plan(tmp_path, "[1, 2, 3]", name="arr.json")
        code, _, err = _run(["--source-path", "/inbox/Note.md", "--plan-file", str(pf)], capsys)
        assert code == 1
        assert "invalid_plan" in err
