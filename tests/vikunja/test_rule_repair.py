"""Tests for ``scripts.vikunja.rule_repair`` (WP10, #1111).

Walks the contract step list (drift check -> snapshot + fsync -> intent ->
clear-first write -> readback -> outcome), ``--resume``, the ordered
``--restore`` algorithm and ``--emit-issue-markdown``. Vikunja is the stateful
fake from ``test_rule_inventory``; all state lives in ``tmp_path``.
"""
from __future__ import annotations

import json
import stat
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from scripts.common.vikunja_rule import rrule_text_to_parts
from scripts.vikunja import rule_repair as rep
from scripts.vikunja.rule_inventory import fingerprint
from tests.common.vikunja_v2_factory import make_task, strip_rule, with_reminder
from tests.vikunja.test_rule_inventory import (
    DAILY,
    TOKEN,
    FakeVikunja,
    client,
    timeout_error,
)

WEEKLY = "FREQ=WEEKLY;INTERVAL=1;BYDAY=MO"


def _entry(task: dict[str, Any], status: str = "lost", rule: str = DAILY,
           from_current: bool = False, **extra: Any) -> dict[str, Any]:
    return {
        "task_id": task["id"],
        "status": status,
        "proposed_restore": {"repeats_rrule": rule, "repeats_from_current_date": from_current},
        "current_fingerprint": fingerprint(task),
        **extra,
    }


def write_plan(tmp_path: Path, entries: list[dict[str, Any]]) -> Path:
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps({"schema": "vikunja-rule-inventory/v1", "entries": entries}))
    return path


def run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, dict, str]:
    code = rep.main(argv, client=client())
    captured = capsys.readouterr()
    lines = captured.out.strip().splitlines()
    return code, json.loads(lines[-1]), captured.out + captured.err


def journal(run_dir: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in (run_dir / "journal.jsonl").read_text().splitlines()]


def only_run_dir(state: Path) -> Path:
    dirs = [p for p in state.iterdir() if p.is_dir()]
    assert len(dirs) == 1, dirs
    return dirs[0]


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Callable[[list[dict[str, Any]]], FakeVikunja]:
    def install(tasks: list[dict[str, Any]]) -> FakeVikunja:
        server = FakeVikunja(tasks)
        monkeypatch.setattr("urllib.request.urlopen", server)
        return server

    return install


@pytest.fixture
def state(tmp_path: Path) -> Path:
    return tmp_path / "state"


# ---------------------------------------------------------------------------
# Selection and dry-run
# ---------------------------------------------------------------------------


class TestSelection:
    def test_dry_run_makes_no_writes_and_no_state(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        lost = strip_rule(make_task(id=18))
        drifted = strip_rule(make_task(id=19))
        server = fake([lost, {**drifted, "updated": "2026-11-20T09:00:00Z"}])
        plan = write_plan(tmp_path, [_entry(lost), _entry(drifted),
                                     _entry(make_task(id=20), status="changed")])
        code, summary, _out = run(["--plan", str(plan), "--dry-run", "--state-dir", str(state)],
                                 capsys)
        assert code == 0
        assert set(server.methods) == {"GET"}
        assert not state.exists()
        rows = {r["task_id"]: r for r in summary["tasks"]}
        assert set(rows) == {18, 19}  # changed is not in the default (lost) set
        assert rows[18]["drift"] == "none" and rows[18]["intended"] == DAILY
        assert rows[19]["drift"] == "drift:updated"
        assert rows[18]["before"] == "(none)"
        assert rows[18]["snapshot_path"].endswith("/18.before.json")

    def test_non_lost_needs_accept_changed(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        task = make_task(id=20, repeat={"freq": "weekly", "interval": 1})
        server = fake([task])
        plan = write_plan(tmp_path, [_entry(task, status="removed")])
        code, summary, _out = run(["--plan", str(plan), "--task-id", "20", "--apply",
                                  "--state-dir", str(state)], capsys)
        assert code == 2 and "--accept-changed" in summary["error"]
        assert server.calls == [] and not state.exists()

    @pytest.mark.parametrize("status", ["ok", "deleted", "unresolved"])
    def test_never_repaired_statuses_refused(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str],
        status: str,
    ) -> None:
        task = make_task(id=20)
        fake([task])
        plan = write_plan(tmp_path, [_entry(task, status=status)])
        code, _, _ = run(["--plan", str(plan), "--task-id", "20", "--accept-changed", "--apply",
                          "--state-dir", str(state)], capsys)
        assert code == 2

    def test_unknown_task_id_refused(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        fake([])
        plan = write_plan(tmp_path, [])
        code, _, _ = run(["--plan", str(plan), "--task-id", "5", "--apply",
                          "--state-dir", str(state)], capsys)
        assert code == 2


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


class TestApply:
    def test_apply_order_snapshot_intent_clear_write_get_outcome(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        task = make_task(id=20, repeat={"freq": "weekly", "interval": 2})
        server = fake([task])
        plan = write_plan(tmp_path, [_entry(task, status="changed", rule=WEEKLY)])
        seen: dict[str, Any] = {}

        def before_first_patch() -> None:
            run_dir = only_run_dir(state)
            snap = run_dir / "20.before.json"
            seen["snapshot"] = json.loads(snap.read_text())
            seen["mode"] = stat.S_IMODE(snap.stat().st_mode)
            seen["journal"] = journal(run_dir)

        server.hooks[("PATCH", 1)] = before_first_patch
        code, summary, out = run(["--plan", str(plan), "--task-id", "20", "--accept-changed",
                                  "--apply", "--state-dir", str(state)], capsys)
        assert code == 0, out
        assert seen["snapshot"] == task and seen["mode"] == 0o600
        assert [r["phase"] for r in seen["journal"]] == ["intent"]
        assert server.methods == ["GET", "PATCH", "PATCH", "GET"]
        assert server.patches == [
            {"repeat": None},
            {"repeats_rrule": WEEKLY, "repeats_from_current_date": False},
        ]
        run_dir = only_run_dir(state)
        records = journal(run_dir)
        assert [r["phase"] for r in records] == ["intent", "outcome"]
        intent, outcome = records
        assert intent["restore_command"] == (
            f"python3 -m scripts.vikunja.rule_repair --restore {run_dir}/20.before.json")
        assert intent["intended"] == {"repeats_rrule": WEEKLY, "repeats_from_current_date": False}
        assert outcome["outcome"] == "ok" and outcome["readback_ok"] is True
        assert outcome["after"]["repeats_rrule"] == WEEKLY
        assert summary["results"] == {"ok": [20]}
        assert stat.S_IMODE((run_dir / "journal.jsonl").stat().st_mode) == 0o600
        assert TOKEN not in out

    def test_apply_lost_has_no_clear_step(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        task = strip_rule(make_task(id=18))
        server = fake([task])
        plan = write_plan(tmp_path, [_entry(task)])
        code, _summary, _ = run(["--plan", str(plan), "--apply", "--state-dir", str(state)],
                               capsys)
        assert code == 0
        assert server.patches == [{"repeats_rrule": DAILY, "repeats_from_current_date": False}]
        assert server.tasks[18]["repeat"] == {"freq": "daily", "interval": 1}

    def test_drift_skips_without_write_and_continues(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        a = strip_rule(make_task(id=18))
        b = strip_rule(make_task(id=19))
        plan = write_plan(tmp_path, [_entry(a), _entry(b)])
        a_live = {**a, "due_date": "2026-11-25T04:59:59Z"}  # a UI edit after inventory
        server = fake([a_live, b])
        code, summary, _ = run(["--plan", str(plan), "--apply", "--state-dir", str(state)],
                               capsys)
        assert code == 0
        assert summary["results"] == {"skipped_drift": [18], "ok": [19]}
        assert [tid for m, tid, _ in server.calls if m == "PATCH"] == [19]
        run_dir = only_run_dir(state)
        assert not (run_dir / "18.before.json").exists()
        first = journal(run_dir)[0]
        assert first["outcome"] == "skipped_drift" and first["drift_fields"] == ["due_date"]

    def test_readback_mismatch_stops_run_and_prints_restore(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        a = strip_rule(make_task(id=18))
        b = strip_rule(make_task(id=19))
        server = fake([a, b])
        plan = write_plan(tmp_path, [_entry(a), _entry(b)])

        def ui_edit_lands() -> None:  # the readback sees a different rule
            server.tasks[18]["repeat"] = {"freq": "weekly", "interval": 1}

        server.hooks[3] = ui_edit_lands  # GET(18), PATCH(18), GET(18) readback
        code, summary, out = run(["--plan", str(plan), "--apply", "--state-dir", str(state)],
                                 capsys)
        assert code == rep.EXIT_STOPPED
        assert "--restore" in summary["restore_command"] and "Restore with:" in out
        assert [tid for _, tid, _ in server.calls] == [18, 18, 18]  # 19 never touched
        records = journal(only_run_dir(state))
        assert records[-1]["outcome"] == "mismatch" and records[-1]["diff_fields"] == ["repeat"]

    def test_timeout_on_patch_journals_unknown_and_resume_resolves(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        a = strip_rule(make_task(id=18))
        b = strip_rule(make_task(id=19))
        server = fake([a, b])
        plan = write_plan(tmp_path, [_entry(a), _entry(b)])

        def commit_then_timeout() -> None:  # the write commits, the answer is lost
            server._patch(server.tasks[18], {"repeats_rrule": DAILY,
                                             "repeats_from_current_date": False})
            timeout_error()

        server.hooks[("PATCH", 1)] = commit_then_timeout
        code, summary, _ = run(["--plan", str(plan), "--apply", "--state-dir", str(state)],
                               capsys)
        assert code == rep.EXIT_STOPPED
        run_dir = only_run_dir(state)
        assert [r.get("outcome") for r in journal(run_dir)] == [None, "unknown"]

        server.calls.clear()
        code, summary, _ = run(["--resume", run_dir.name, "--state-dir", str(state)], capsys)
        assert code == 0
        records = journal(run_dir)
        resolved = records[2]
        assert resolved["task_id"] == 18 and resolved["outcome"] == "ok"
        assert resolved["resolved_by"] == "resume"
        # The fresh read of 18 comes before anything else; then 19 continues.
        assert server.calls[0][:2] == ("GET", 18)
        assert [tid for m, tid, _ in server.calls if m == "PATCH"] == [19]
        assert [r["phase"] for r in records[3:]] == ["intent", "outcome"]
        assert summary["results"] == {"ok": [18, 19]}  # whole run, after resolution

    def test_resume_intent_without_outcome(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A crash between intent and outcome leaves an intent; resume reads first."""
        a = strip_rule(make_task(id=18))
        server = fake([a])
        plan = write_plan(tmp_path, [_entry(a)])

        class Crash(BaseException):
            pass

        def crash() -> None:
            raise Crash

        server.hooks[("PATCH", 1)] = crash
        with pytest.raises(Crash):
            rep.main(["--plan", str(plan), "--apply", "--state-dir", str(state)], client=client())
        capsys.readouterr()
        run_dir = only_run_dir(state)
        assert [r["phase"] for r in journal(run_dir)] == ["intent"]
        server.calls.clear()
        code, _, _ = run(["--resume", run_dir.name, "--state-dir", str(state)], capsys)
        # The write never landed: the fresh read shows no rule -> mismatch, stop.
        assert code == rep.EXIT_STOPPED
        assert server.methods == ["GET"]
        assert journal(run_dir)[-1]["outcome"] == "mismatch"

    def test_snapshot_write_failure_no_vikunja_write(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        a = strip_rule(make_task(id=18))
        server = fake([a])
        plan = write_plan(tmp_path, [_entry(a)])
        real = rep._write_snapshot_file

        def failing(path: Path, document: Any) -> None:
            if path.name.endswith(".before.json"):
                raise rep.StateWriteError("disk full")
            real(path, document)

        monkeypatch.setattr(rep, "_write_snapshot_file", failing)
        code, _, _ = run(["--plan", str(plan), "--apply", "--state-dir", str(state)], capsys)
        assert code == rep.EXIT_STATE
        assert "PATCH" not in server.methods

    def test_journal_write_failure_no_vikunja_write(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        a = strip_rule(make_task(id=18))
        server = fake([a])
        plan = write_plan(tmp_path, [_entry(a)])

        def failing(run_dir: Path, record: Any) -> None:
            raise rep.StateWriteError("journal")

        monkeypatch.setattr(rep, "_append_journal", failing)
        code, _, _ = run(["--plan", str(plan), "--apply", "--state-dir", str(state)], capsys)
        assert code == rep.EXIT_STATE
        assert "PATCH" not in server.methods

    def test_unwritable_state_dir_no_vikunja_call(
        self, tmp_path: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        a = strip_rule(make_task(id=18))
        server = fake([a])
        plan = write_plan(tmp_path, [_entry(a)])
        blocker = tmp_path / "file"
        blocker.write_text("x")
        code, _, _ = run(["--plan", str(plan), "--apply", "--state-dir", str(blocker / "s")],
                         capsys)
        assert code == rep.EXIT_STATE
        assert server.calls == []


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------


def _snapshot(tmp_path: Path, task: dict[str, Any]) -> Path:
    path = tmp_path / f"{task['id']}.before.json"
    path.write_text(json.dumps(task))
    return path


def _restore(snap: Path, state: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, dict, str]:
    return run(["--restore", str(snap), "--state-dir", str(state)], capsys)


class TestRestore:
    def test_different_rule_clear_first(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        snap_task = make_task(id=20, repeat=rrule_text_to_parts(WEEKLY))
        server = fake([make_task(id=20)])
        code, _summary, out = _restore(_snapshot(tmp_path, snap_task), state, capsys)
        assert code == 0, out
        assert server.patches == [
            {"repeat": None},
            {"repeats_rrule": WEEKLY, "repeats_from_current_date": False},
        ]
        run_dir = only_run_dir(state)
        assert json.loads((run_dir / "20.before.json").read_text())["repeats_rrule"] == DAILY
        assert [r["phase"] for r in journal(run_dir)] == ["intent", "outcome"]
        assert journal(run_dir)[0]["kind"] == "restore"

    def test_decremented_count_clear_first_defeats_stale_echo(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        five = rrule_text_to_parts(f"{WEEKLY};COUNT=5")
        four = rrule_text_to_parts(f"{WEEKLY};COUNT=4")
        server = fake([make_task(id=21, repeat=four)])
        code, _, _ = _restore(_snapshot(tmp_path, make_task(id=21, repeat=five)), state, capsys)
        assert code == 0
        assert server.methods == ["GET", "PATCH", "PATCH", "GET"]
        assert server.patches[0] == {"repeat": None}
        assert server.patches[1]["repeats_rrule"] == "FREQ=WEEKLY;INTERVAL=1;BYDAY=MO;COUNT=5"
        assert server.tasks[21]["repeat"]["count"] == 5

    def test_no_rule_snapshot_clears_with_flag(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        server = fake([make_task(id=22, repeats_from_current_date=True)])
        snap = strip_rule(make_task(id=22))
        code, _, _ = _restore(_snapshot(tmp_path, snap), state, capsys)
        assert code == 0
        assert server.patches == [{"repeat": None, "repeats_from_current_date": False}]

    def test_null_reminders_sent_as_empty_list(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        live = with_reminder(make_task(id=23))
        server = fake([live])
        code, _, _ = _restore(_snapshot(tmp_path, make_task(id=23, reminders=None)), state, capsys)
        assert code == 0
        assert server.patches == [{"reminders": []}]

    def test_null_due_date_restored_through_sanctioned_null(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        server = fake([make_task(id=24, repeat=None)])
        snap = make_task(id=24, repeat=None, due_date="0001-01-01T00:00:00Z")
        code, _, _ = _restore(_snapshot(tmp_path, snap), state, capsys)
        assert code == 0
        assert server.patches == [{"due_date": None}]

    def test_open_snapshot_against_done_task_sets_done_false_last(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        live = make_task(id=25, repeat=None, done=True, due_date="2026-11-30T04:59:59Z")
        server = fake([live])
        snap = make_task(id=25)  # open, daily rule, due 2026-11-20
        code, _, out = _restore(_snapshot(tmp_path, snap), state, capsys)
        assert code == 0, out
        assert server.patches == [
            {"repeats_rrule": DAILY, "repeats_from_current_date": False},
            {"due_date": "2026-11-20T04:59:59Z"},
            {"done": False},
        ]

    def test_done_snapshot_against_task_with_rule_refused(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        server = fake([make_task(id=26)])
        snap = make_task(id=26, done=True)
        code, summary, _ = _restore(_snapshot(tmp_path, snap), state, capsys)
        assert code == 2 and "done=true" in summary["error"]
        assert server.methods == ["GET"] and not state.exists()

    def test_restore_readback_reports_every_differing_field(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        server = fake([make_task(id=27)])
        snap = make_task(id=27, repeat=rrule_text_to_parts(WEEKLY), priority=3)

        def server_ignores() -> None:  # the rule write silently does nothing
            server.tasks[27]["repeat"] = {"freq": "daily", "interval": 1}

        server.hooks[4] = server_ignores  # GET, PATCH, PATCH, GET(readback)
        code, _summary, _ = _restore(_snapshot(tmp_path, snap), state, capsys)
        assert code == rep.EXIT_STOPPED
        assert journal(only_run_dir(state))[-1]["diff_fields"] == ["repeat"]

    def test_restore_timeout_journals_unknown_and_resume_resolves(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        server = fake([strip_rule(make_task(id=28))])
        server.hooks[("PATCH", 1)] = timeout_error
        code, _, _ = _restore(_snapshot(tmp_path, make_task(id=28)), state, capsys)
        assert code == rep.EXIT_STOPPED
        run_dir = only_run_dir(state)
        assert journal(run_dir)[-1]["outcome"] == "unknown"
        server._patch(server.tasks[28], {"repeats_rrule": DAILY})  # operator re-ran by hand
        code, _, _ = run(["--resume", run_dir.name, "--state-dir", str(state)], capsys)
        assert code == 0 and journal(run_dir)[-1]["outcome"] == "ok"


# ---------------------------------------------------------------------------
# Emit
# ---------------------------------------------------------------------------


class TestEmit:
    def test_markdown_ids_rules_allowed_titles_only_no_at(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        public = strip_rule(make_task(id=16, title="Morning shoulder PT"))
        private = strip_rule(make_task(id=40, title="Private appointment"))
        fake([public, private])
        plan = write_plan(tmp_path, [
            _entry(public, title="Morning shoulder PT"),
            _entry(private, title="Private appointment"),  # never public, even if present
        ])
        code, summary, _ = run(["--plan", str(plan), "--apply", "--state-dir", str(state),
                                "--operator", "kent@example.test"], capsys)
        assert code == 0
        run_id = summary["run_id"]
        code, summary, _ = run(["--emit-issue-markdown", run_id, "--state-dir", str(state)],
                               capsys)
        assert code == 0
        md_path = Path(summary["markdown"])
        md = md_path.read_text()
        assert stat.S_IMODE(md_path.stat().st_mode) == 0o600
        assert "gh issue comment 1111" in summary["post_with"]
        assert run_id in md and "Operator:" in md
        assert "| task id | before rule | after rule | readback | outcome | restore command |" in md
        assert "16 (Morning shoulder PT)" in md
        assert "Private appointment" not in md
        assert "@" not in md
        assert f"| 40 | (none) | {DAILY} | ok | ok |" in md
        assert "--restore" in md



# ---------------------------------------------------------------------------
# Review cycle 1 regressions
# ---------------------------------------------------------------------------


def _stop_on_first_patch(server: Any) -> None:
    """Task 18's first PATCH commits, then the answer is lost (timeout)."""

    def commit_then_timeout() -> None:
        server._patch(server.tasks[18], {"repeats_rrule": DAILY,
                                         "repeats_from_current_date": False})
        timeout_error()

    server.hooks[("PATCH", 1)] = commit_then_timeout


class TestResumeConsent:
    """Finding 2: resume uses the entries consented at apply time, not a reloaded plan."""

    def _interrupted_run(self, tmp_path: Path, state: Path, fake: Callable,
                         capsys: pytest.CaptureFixture[str]) -> tuple[Any, Path, Path, dict]:
        a = strip_rule(make_task(id=18))
        b = strip_rule(make_task(id=19))
        server = fake([a, b])
        plan = write_plan(tmp_path, [_entry(a), _entry(b)])
        _stop_on_first_patch(server)
        code, _, _ = run(["--plan", str(plan), "--apply", "--state-dir", str(state)], capsys)
        assert code == rep.EXIT_STOPPED
        return server, plan, only_run_dir(state), b

    def test_replaced_inventory_refused_no_write(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        server, plan, run_dir, b = self._interrupted_run(tmp_path, state, fake, capsys)
        # The inventory is regenerated: 19 is now "removed" (needs Kent's consent),
        # with a different proposal and a fresh fingerprint.
        b_now = {**b, "updated": "2026-11-21T09:00:00Z"}
        server.tasks[19] = b_now
        plan.write_text(json.dumps({"entries": [
            _entry(server.tasks[18]),
            _entry(b_now, status="removed", rule=WEEKLY),
        ]}))
        server.calls.clear()
        code, summary, _ = run(["--resume", run_dir.name, "--state-dir", str(state)], capsys)
        assert code == rep.EXIT_REFUSED and "inventory changed" in summary["error"]
        assert "PATCH" not in server.methods

    def test_resume_uses_persisted_entries_when_plan_gone(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        server, plan, run_dir, _ = self._interrupted_run(tmp_path, state, fake, capsys)
        plan.unlink()
        server.calls.clear()
        code, summary, _ = run(["--resume", run_dir.name, "--state-dir", str(state)], capsys)
        assert code == 0, summary
        assert [tid for m, tid, _ in server.calls if m == "PATCH"] == [19]
        run_doc = json.loads((run_dir / "run.json").read_text())
        assert [e["task_id"] for e in run_doc["entries"]] == [18, 19]
        assert len(run_doc["plan_sha256"]) == 64

    def test_persisted_entry_drift_fingerprint_still_protects(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        server, _, run_dir, b = self._interrupted_run(tmp_path, state, fake, capsys)
        server.tasks[19] = {**b, "updated": "2026-11-21T09:00:00Z"}  # a UI edit since apply
        server.calls.clear()
        code, _summary, _ = run(["--resume", run_dir.name, "--state-dir", str(state)], capsys)
        assert code == 0
        assert "PATCH" not in [m for m, tid, _ in server.calls if tid == 19]
        assert journal(run_dir)[-1]["outcome"] == "skipped_drift"


class TestTornJournal:
    """Finding 3: a torn final line is repaired before the next append."""

    def test_repeated_resume_after_torn_outcome(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        a = strip_rule(make_task(id=18))
        server = fake([a])
        plan = write_plan(tmp_path, [_entry(a)])

        def commit_then_timeout() -> None:
            server._patch(server.tasks[18], {"repeats_rrule": DAILY,
                                             "repeats_from_current_date": False})
            timeout_error()

        server.hooks[("PATCH", 1)] = commit_then_timeout
        code, _, _ = run(["--plan", str(plan), "--apply", "--state-dir", str(state)], capsys)
        assert code == rep.EXIT_STOPPED
        run_dir = only_run_dir(state)
        path = run_dir / "journal.jsonl"
        raw = path.read_bytes()
        torn = raw[: raw.rstrip(b"\n").rfind(b"\n") + 1] + b'{"phase": "outcome", "task'
        path.write_bytes(torn)  # crash mid-append of the outcome line

        for attempt in (1, 2):
            server.calls.clear()
            code, summary, _ = run(["--resume", run_dir.name, "--state-dir", str(state)], capsys)
            assert code == 0, (attempt, summary)
            assert "PATCH" not in server.methods
            records = [json.loads(x) for x in path.read_text().splitlines()]
            assert [r["phase"] for r in records] == ["intent", "outcome"]
            assert records[-1]["outcome"] == "ok" and records[-1]["resolved_by"] == "resume"
        assert path.read_bytes().endswith(b"\n")
        assert (run_dir / "journal.jsonl.torn").read_bytes() == b'{"phase": "outcome", "task'

    def test_unterminated_complete_record_kept_across_multi_task_resume(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Cycle-3 finding 1: a complete record missing its newline is kept, not truncated."""
        a = strip_rule(make_task(id=18))
        b = strip_rule(make_task(id=19))
        server = fake([a, b])
        plan = write_plan(tmp_path, [_entry(a), _entry(b)])
        server.hooks[("PATCH", 2)] = timeout_error  # 19's write never lands
        code, _, _ = run(["--plan", str(plan), "--apply", "--state-dir", str(state)], capsys)
        assert code == rep.EXIT_STOPPED
        run_dir = only_run_dir(state)
        path = run_dir / "journal.jsonl"
        lines = path.read_bytes().splitlines(keepends=True)
        # Crash after 18's ok outcome was written but before its newline,
        # so 19 was never started.
        path.write_bytes(lines[0] + lines[1].rstrip(b"\n"))
        (run_dir / "19.before.json").unlink()

        server.calls.clear()
        code, summary, _ = run(["--resume", run_dir.name, "--state-dir", str(state)], capsys)
        assert code == 0, summary
        assert summary["results"] == {"ok": [18, 19]}
        records = journal(run_dir)
        assert [(r["phase"], r["task_id"]) for r in records] == [
            ("intent", 18), ("outcome", 18), ("intent", 19), ("outcome", 19)]
        assert not (run_dir / "journal.jsonl.torn").exists()

        code, summary, _ = run(["--emit-issue-markdown", run_dir.name,
                                "--state-dir", str(state)], capsys)
        assert code == 0
        md = Path(summary["markdown"]).read_text()
        assert f"| 18 | (none) | {DAILY} | ok | ok |" in md
        assert f"| 19 | (none) | {DAILY} | ok | ok |" in md
        assert "(pending)" not in md


class TestMidRunReadFailure:
    """Re-review finding: exit 3 after earlier writes names the run and the writes."""

    def test_second_task_read_failure_reports_run_and_resume_reports_first(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        a = strip_rule(make_task(id=18))
        b = strip_rule(make_task(id=19))
        server = fake([a, b])
        plan = write_plan(tmp_path, [_entry(a), _entry(b)])
        # Calls: GET 18, PATCH 18, GET 18 (readback), GET 19 -> fails.
        server.hooks[4] = timeout_error
        code, summary, out = run(["--plan", str(plan), "--apply", "--state-dir", str(state)],
                                 capsys)
        assert code == rep.EXIT_VIKUNJA, out
        run_dir = only_run_dir(state)
        assert "before any write" not in out
        assert summary["run_id"] == run_dir.name and summary["writes"] == 1
        assert run_dir.name in summary["error"] and "1 write" in summary["error"]
        assert f"--resume {run_dir.name}" in summary["error"]

        code, summary, out = run(["--resume", run_dir.name, "--state-dir", str(state)], capsys)
        assert code == 0, out
        assert summary["results"] == {"ok": [18, 19]}
        code, summary, _ = run(["--emit-issue-markdown", run_dir.name,
                                "--state-dir", str(state)], capsys)
        md = Path(summary["markdown"]).read_text()
        assert f"| 18 | (none) | {DAILY} | ok | ok |" in md
        assert f"| 19 | (none) | {DAILY} | ok | ok |" in md

    def test_first_read_failure_says_before_any_write(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        a = strip_rule(make_task(id=18))
        server = fake([a])
        plan = write_plan(tmp_path, [_entry(a)])
        server.hooks[1] = timeout_error
        code, summary, _ = run(["--plan", str(plan), "--apply", "--state-dir", str(state)],
                               capsys)
        assert code == rep.EXIT_VIKUNJA
        assert summary["writes"] == 0 and "before any write" in summary["error"]


class TestDuplicateTaskIds:
    """Cycle-3 finding 2: a repeated --task-id never replaces a completed outcome."""

    def test_repeated_task_id_processed_once(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        a = strip_rule(make_task(id=18))
        server = fake([a])
        plan = write_plan(tmp_path, [_entry(a)])
        code, summary, out = run(["--plan", str(plan), "--task-id", "18", "--task-id", "18",
                                  "--apply", "--state-dir", str(state)], capsys)
        assert code == 0, out
        assert summary["results"] == {"ok": [18]}
        assert server.methods.count("PATCH") == 1
        run_dir = only_run_dir(state)
        run_doc = json.loads((run_dir / "run.json").read_text())
        assert run_doc["task_ids"] == [18]
        assert [e["task_id"] for e in run_doc["entries"]] == [18]
        assert [r["phase"] for r in journal(run_dir)] == ["intent", "outcome"]
        code, summary, _ = run(["--emit-issue-markdown", run_dir.name,
                                "--state-dir", str(state)], capsys)
        md = Path(summary["markdown"]).read_text()
        assert f"| 18 | (none) | {DAILY} | ok | ok |" in md
        assert "skipped_drift" not in md


class TestApplyReadbackPreservation:
    """Finding 4: apply verifies reminders, due date and done, not only the rule."""

    def _apply(self, tmp_path: Path, state: Path, fake: Callable,
               capsys: pytest.CaptureFixture[str], task: dict,
               mutate: Callable[[dict], None] | None) -> tuple[int, list[dict]]:
        server = fake([task])
        plan = write_plan(tmp_path, [_entry(task)])
        if mutate is not None:
            server.hooks[("PATCH", 1)] = lambda: mutate(server.tasks[task["id"]])
        code, _, _ = run(["--plan", str(plan), "--apply", "--state-dir", str(state)], capsys)
        return code, journal(only_run_dir(state))

    def test_intact_readback_ok(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        task = strip_rule(with_reminder(make_task(id=18)))
        code, records = self._apply(tmp_path, state, fake, capsys, task, None)
        assert code == 0 and records[-1]["outcome"] == "ok"

    def test_relative_reminder_instant_recomputed_is_ok(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str]
    ) -> None:
        task = strip_rule(with_reminder(make_task(id=18)))

        def recompute(t: dict) -> None:
            t["reminders"] = [{**t["reminders"][0], "reminder": "2026-11-20T03:00:00Z"}]

        code, records = self._apply(tmp_path, state, fake, capsys, task, recompute)
        assert code == 0 and records[-1]["outcome"] == "ok"

    @pytest.mark.parametrize(
        ("mutate", "field"),
        [
            (lambda t: t.update(reminders=None), "reminders"),
            (lambda t: t.update(due_date="0001-01-01T00:00:00Z"), "due_date"),
            (lambda t: t.update(done=True), "done"),
            (lambda t: t.update(reminders=[{"reminder": "2026-11-20T05:00:00Z",
                                            "relative_period": 0, "relative_to": ""}]),
             "reminders"),
        ],
    )
    def test_stripped_readback_is_mismatch(
        self, tmp_path: Path, state: Path, fake: Callable, capsys: pytest.CaptureFixture[str],
        mutate: Callable[[dict], None], field: str,
    ) -> None:
        task = strip_rule(make_task(id=18, reminders=[
            {"reminder": "2026-11-20T04:00:00Z", "relative_period": 0, "relative_to": ""}]))
        code, records = self._apply(tmp_path, state, fake, capsys, task, mutate)
        assert code == rep.EXIT_STOPPED
        assert records[-1]["outcome"] == "mismatch"
        assert field in records[-1]["diff_fields"]
