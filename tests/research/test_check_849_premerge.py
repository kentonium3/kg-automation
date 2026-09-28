"""T028: commit-bound, fail-closed pre-merge evidence."""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
from collections.abc import Mapping, Sequence

import pytest

from scripts.research.check_849_premerge import (
    LIVE_NODES,
    REQUIRED_NODES,
    REQUIRED_STEP_NAMES,
    WP05_REQUIRED_NODES,
    CommandResult,
    evaluate_required_nodes,
    finalize_record,
    parse_junit,
    run_ci_simulation,
    run_premerge,
    verify_record,
)


def _xml(path: pathlib.Path, cases: Sequence[tuple[str, str, str]]) -> pathlib.Path:
    body = []
    for classname, name, outcome in cases:
        child = "" if outcome == "passed" else f'<{outcome} message="forced" />'
        body.append(f'<testcase classname="{classname}" name="{name}">{child}</testcase>')
    path.write_text(
        "<testsuites><testsuite>" + "".join(body) + "</testsuite></testsuites>",
        encoding="utf-8",
    )
    return path


def test_missing_required_node_fails(tmp_path):
    report = parse_junit(_xml(tmp_path / "junit.xml", []))
    verdict = evaluate_required_nodes([report], ["tests/research/test_x.py::test_required"])
    assert verdict["tests/research/test_x.py::test_required"]["status"] == "missing"
    assert not verdict["tests/research/test_x.py::test_required"]["passed"]


@pytest.mark.parametrize("outcome", ["skipped", "failure", "error"])
def test_a_nonpassing_required_node_fails_even_when_pytest_exited_zero(tmp_path, outcome):
    report = parse_junit(
        _xml(tmp_path / "junit.xml", [("tests.research.test_x", "test_required", outcome)])
    )
    verdict = evaluate_required_nodes([report], ["tests/research/test_x.py::test_required"])
    assert verdict["tests/research/test_x.py::test_required"]["status"] == outcome
    assert not verdict["tests/research/test_x.py::test_required"]["passed"]


def test_every_parametrized_expansion_must_pass(tmp_path):
    selector = "tests/research/test_x.py::test_required"
    good = parse_junit(
        _xml(
            tmp_path / "good.xml",
            [
                ("tests.research.test_x", "test_required[a]", "passed"),
                ("tests.research.test_x", "test_required[b]", "passed"),
            ],
        )
    )
    bad = parse_junit(
        _xml(
            tmp_path / "bad.xml",
            [
                ("tests.research.test_x", "test_required[a]", "passed"),
                ("tests.research.test_x", "test_required[b]", "skipped"),
            ],
        )
    )
    assert evaluate_required_nodes([good], [selector])[selector]["passed"]
    assert evaluate_required_nodes([bad], [selector])[selector]["status"] == "skipped"


def test_a_duplicate_failed_result_cannot_be_hidden_by_a_later_pass(tmp_path):
    selector = "tests/research/test_x.py::test_required"
    report = parse_junit(
        _xml(
            tmp_path / "rerun.xml",
            [
                ("tests.research.test_x", "test_required", "failure"),
                ("tests.research.test_x", "test_required", "passed"),
            ],
        )
    )
    verdict = evaluate_required_nodes([report], [selector])[selector]
    assert verdict["status"] == "failure"
    assert not verdict["passed"]


def test_a_later_live_pass_satisfies_an_environment_skip(tmp_path):
    """The office suite skips live nodes; the explicit live phase is their evidence."""
    selector = "tests/research/test_x.py::test_live"
    office = parse_junit(
        _xml(tmp_path / "office.xml", [("tests.research.test_x", "test_live", "skipped")]),
        phase="office",
    )
    live = parse_junit(
        _xml(tmp_path / "live.xml", [("tests.research.test_x", "test_live", "passed")]),
        phase="live",
    )
    verdict = evaluate_required_nodes(
        [office, live], [selector], live_selectors=[selector]
    )[selector]
    assert verdict["passed"]
    assert verdict["status"] == "passed"


def test_a_required_node_missing_from_either_office_seed_fails(tmp_path):
    selector = "tests/research/test_x.py::test_required"
    seed_zero = parse_junit(
        _xml(tmp_path / "zero.xml", [("tests.research.test_x", "test_required", "passed")]),
        phase="office",
    )
    seed_three = parse_junit(_xml(tmp_path / "three.xml", []), phase="office")
    verdict = evaluate_required_nodes([seed_zero, seed_three], [selector])[selector]
    assert verdict["status"] == "missing"
    assert not verdict["passed"]


def test_collection_error_fails_a_step_even_with_exit_zero(tmp_path):
    report = parse_junit(
        _xml(tmp_path / "junit.xml", [("", "tests/research/test_broken.py", "error")])
    )
    assert report.errors == 1
    assert not report.passed(returncode=0)


def test_suite_level_collection_error_without_a_testcase_still_fails(tmp_path):
    path = tmp_path / "junit.xml"
    path.write_text(
        '<testsuites><testsuite errors="1" failures="0" skipped="0" /></testsuites>',
        encoding="utf-8",
    )
    report = parse_junit(path)
    assert report.errors == 1
    assert not report.passed(returncode=0)


def test_wrong_commit_invalidates_an_otherwise_passing_record(tmp_path):
    path = tmp_path / "record.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "commit": "a" * 40,
                "status": "PASS",
                "complete": True,
                "live": {"completed": True, "passed": True},
                "required_nodes": {"x": {"passed": True}},
            }
        ),
        encoding="utf-8",
    )
    ok, reasons = verify_record(path, "b" * 40)
    assert not ok
    assert any("commit" in reason for reason in reasons)


def test_no_live_is_always_an_incomplete_fail():
    record = finalize_record(
        commit="a" * 40,
        started_at="2026-09-28T00:00:00+00:00",
        steps=[{"name": "office-seed-0", "passed": True}],
        required_nodes={"x": {"passed": True, "status": "passed", "matches": ["x"]}},
        live_completed=False,
        cleanup={"attempted": True, "passed": True, "detail": "clean"},
        live_reason="record incomplete: live smoke was not run",
    )
    assert record["status"] == "FAIL"
    assert not record["complete"]
    assert record["live"]["reason"] == "record incomplete: live smoke was not run"


def test_a_failed_live_smoke_fails_the_record():
    record = finalize_record(
        commit="a" * 40,
        started_at="2026-09-28T00:00:00+00:00",
        steps=[{"name": "live-smoke", "passed": False}],
        required_nodes={"x": {"passed": True, "status": "passed", "matches": ["x"]}},
        live_completed=True,
        cleanup={"attempted": True, "passed": True, "detail": "clean"},
    )
    assert record["status"] == "FAIL"
    assert not record["live"]["passed"]


def test_passing_record_is_bound_to_head_and_verifies(tmp_path):
    runner = _FullRunner()
    path = tmp_path / "record.json"
    run_premerge(tmp_path, output=path, runner=runner)
    assert verify_record(path, runner.commit) == (True, [])


class _CiRunner:
    def __init__(
        self,
        *,
        raise_during_pytest: bool = False,
        leave_checkout: bool = False,
        junit_outcome: str = "passed",
        leave_registration: bool = False,
        timeout_during_pytest: bool = False,
        fail_worktree_add: bool = False,
    ):
        self.raise_during_pytest = raise_during_pytest
        self.leave_checkout = leave_checkout
        self.junit_outcome = junit_outcome
        self.leave_registration = leave_registration
        self.timeout_during_pytest = timeout_during_pytest
        self.fail_worktree_add = fail_worktree_add
        self.commands: list[tuple[str, ...]] = []
        self.checkout: pathlib.Path | None = None

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: pathlib.Path,
        env: Mapping[str, str] | None = None,
        timeout_s: float | None = None,
    ) -> CommandResult:
        command = tuple(argv)
        self.commands.append(command)
        if command[:3] == ("git", "worktree", "add"):
            self.checkout = pathlib.Path(command[-2])
            self.checkout.mkdir(parents=True)
            if self.fail_worktree_add:
                return CommandResult(returncode=9, stdout="", stderr="partial add")
        elif "pytest" in command:
            if self.timeout_during_pytest:
                raise subprocess.TimeoutExpired(command, timeout_s or 1)
            if self.raise_during_pytest:
                raise RuntimeError("injected pytest crash")
            junit_arg = next(arg for arg in command if arg.startswith("--junitxml="))
            if self.junit_outcome == "missing":
                return CommandResult(returncode=0, stdout="", stderr="")
            if self.junit_outcome == "malformed":
                pathlib.Path(junit_arg.split("=", 1)[1]).write_text("<", encoding="utf-8")
                return CommandResult(returncode=0, stdout="", stderr="")
            cases = (
                [] if self.junit_outcome == "passed" else
                [("", "tests/research/test_broken.py", self.junit_outcome)]
            )
            _xml(pathlib.Path(junit_arg.split("=", 1)[1]), cases)
        elif command[:3] == ("git", "worktree", "remove") and not self.leave_checkout:
            shutil.rmtree(command[-1])
        elif command[:4] == ("git", "worktree", "list", "--porcelain"):
            stdout = (
                f"worktree {self.checkout}\n" if self.leave_registration and self.checkout else ""
            )
            return CommandResult(returncode=0, stdout=stdout, stderr="")
        return CommandResult(returncode=0, stdout="", stderr="")


def test_ci_simulation_cleans_up_after_an_injected_exception(tmp_path):
    runner = _CiRunner(raise_during_pytest=True)
    result = run_ci_simulation(tmp_path, "a" * 40, runner=runner, temp_parent=tmp_path)
    assert not result["passed"]
    assert result["cleanup"]["attempted"]
    assert result["cleanup"]["passed"]
    assert not pathlib.Path(result["worktree"]).exists()
    assert any(command[:3] == ("git", "worktree", "remove") for command in runner.commands)


def test_ci_simulation_bounds_a_hung_suite_and_still_cleans_up(tmp_path):
    runner = _CiRunner(timeout_during_pytest=True)
    result = run_ci_simulation(tmp_path, "a" * 40, runner=runner, temp_parent=tmp_path)
    assert not result["passed"]
    assert result["timed_out"]
    assert result["cleanup"]["passed"]


def test_ci_simulation_fails_a_collection_error_despite_exit_zero(tmp_path):
    runner = _CiRunner(junit_outcome="error")
    result = run_ci_simulation(tmp_path, "a" * 40, runner=runner, temp_parent=tmp_path)
    assert not result["passed"]
    assert result["returncode"] == 0
    assert result["error_count"] == 1
    assert result["cleanup"]["passed"]


@pytest.mark.parametrize("junit_outcome", ["missing", "malformed"])
def test_ci_simulation_fails_missing_or_malformed_junit(tmp_path, junit_outcome):
    runner = _CiRunner(junit_outcome=junit_outcome)
    result = run_ci_simulation(tmp_path, "a" * 40, runner=runner, temp_parent=tmp_path)
    assert not result["passed"]
    assert result["cleanup"]["passed"]


def test_surviving_worktree_fails_the_ci_step_but_is_removed(tmp_path):
    runner = _CiRunner(leave_checkout=True)
    result = run_ci_simulation(tmp_path, "a" * 40, runner=runner, temp_parent=tmp_path)
    assert not result["passed"]
    assert not result["cleanup"]["passed"]
    assert "survived" in result["cleanup"]["detail"]
    assert not pathlib.Path(result["worktree"]).exists()


def test_surviving_worktree_registration_fails_cleanup(tmp_path):
    runner = _CiRunner(leave_registration=True)
    result = run_ci_simulation(tmp_path, "a" * 40, runner=runner, temp_parent=tmp_path)
    assert not result["passed"]
    assert not result["cleanup"]["passed"]
    assert "registration survived" in result["cleanup"]["detail"]


def test_partial_failed_worktree_add_still_attempts_registry_cleanup(tmp_path):
    runner = _CiRunner(fail_worktree_add=True, leave_registration=True)
    result = run_ci_simulation(tmp_path, "a" * 40, runner=runner, temp_parent=tmp_path)
    assert not result["passed"]
    assert result["cleanup"]["attempted"]
    assert not result["cleanup"]["passed"]
    assert any(command[:3] == ("git", "worktree", "remove") for command in runner.commands)
    assert any(command[:4] == ("git", "worktree", "list", "--porcelain") for command in runner.commands)


def test_required_node_inventory_is_explicit_and_contains_wp05_nodes():
    assert len(REQUIRED_NODES) == len(set(REQUIRED_NODES))
    assert set(WP05_REQUIRED_NODES) <= set(REQUIRED_NODES)
    assert "tests/research/test_arms849_arm_g.py::test_live_hybrid_search_returns_an_item_the_question_names" in REQUIRED_NODES
    assert "tests/research/test_arms849_grading.py::test_view_carries_nothing_but_the_allowed_fields" in REQUIRED_NODES
    assert "tests/research/test_arms849_grading.py::test_admin_report_holds_the_non_scored_cells_and_lives_apart" in REQUIRED_NODES
    assert "tests/research/test_arms849_arm_g.py::test_assembly_priority_cap_dedup_and_frozen_layout" in REQUIRED_NODES


class _FullRunner:
    """Whole-checker fake: creates only junit/worktree artifacts, never live state."""

    commit = "a" * 40

    def __init__(
        self,
        *,
        fail_live_smoke: bool = False,
        dirty_at_finish: bool = False,
        required_outcome: str | None = None,
        ci_collection_error: bool = False,
    ):
        self.fail_live_smoke = fail_live_smoke
        self.dirty_at_finish = dirty_at_finish
        self.required_outcome = required_outcome
        self.ci_collection_error = ci_collection_error
        self.status_calls = 0
        self.calls: list[tuple[tuple[str, ...], pathlib.Path, dict[str, str], float | None]] = []

    @staticmethod
    def _case(node: str, outcome: str) -> tuple[str, str, str]:
        file_name, test_name = node.split("::", 1)
        return file_name[:-3].replace("/", "."), test_name, outcome

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: pathlib.Path,
        env: Mapping[str, str] | None = None,
        timeout_s: float | None = None,
    ) -> CommandResult:
        command = tuple(argv)
        environment = dict(env or {})
        self.calls.append((command, cwd, environment, timeout_s))
        if command == ("git", "rev-parse", "HEAD"):
            return CommandResult(0, self.commit + "\n", "")
        if command[:2] == ("git", "status"):
            self.status_calls += 1
            dirty = self.dirty_at_finish and self.status_calls > 1
            return CommandResult(0, " M changed.py\n" if dirty else "", "")
        if command[:3] == ("git", "worktree", "add"):
            pathlib.Path(command[-2]).mkdir(parents=True)
            return CommandResult(0, "", "")
        if command[:3] == ("git", "worktree", "remove"):
            shutil.rmtree(command[-1], ignore_errors=True)
            return CommandResult(0, "", "")
        if command[:4] == ("git", "worktree", "list", "--porcelain"):
            return CommandResult(0, "", "")
        if "pytest" in command:
            junit_arg = next(arg for arg in command if arg.startswith("--junitxml="))
            junit = pathlib.Path(junit_arg.split("=", 1)[1])
            if cwd.name == "checkout":
                cases: list[tuple[str, str, str]] = (
                    [("", "tests/research/test_broken.py", "error")]
                    if self.ci_collection_error else []
                )
            elif environment.get("ARMS849_LIVE") == "1":
                cases = [self._case(node, "passed") for node in LIVE_NODES]
            else:
                cases = [
                    self._case(
                        node,
                        "skipped" if node in LIVE_NODES else (
                            self.required_outcome
                            if self.required_outcome and node == REQUIRED_NODES[1] else "passed"
                        ),
                    )
                    for node in REQUIRED_NODES
                    if not (self.required_outcome == "missing" and node == REQUIRED_NODES[1])
                ]
            _xml(junit, cases)
            return CommandResult(0, "", "")
        if (
            self.fail_live_smoke and
            "scripts.research.arms849.substrate" in command and
            "run" in command and "--smoke" in command
        ):
            return CommandResult(7, "", "forced smoke failure")
        return CommandResult(0, "", "")


def test_whole_checker_records_every_command_and_writes_a_verifiable_pass(tmp_path, monkeypatch):
    monkeypatch.setenv("ARMS849_LIVE", "1")
    runner = _FullRunner()
    output = tmp_path / "premerge.json"
    record = run_premerge(tmp_path, output=output, runner=runner)
    assert record["status"] == "PASS"
    assert output.is_file()
    assert verify_record(output, runner.commit) == (True, [])
    assert {step["name"] for step in record["steps"]} == REQUIRED_STEP_NAMES

    office = [call for call in runner.calls if "pytest" in call[0] and "tests/research" in call[0]]
    assert {call[2]["PYTHONHASHSEED"] for call in office} == {"0", "3"}
    assert all("ARMS849_LIVE" not in call[2] for call in office)
    assert all("junit_family=xunit1" in call[0] for call in office)
    assert any(call[0][:4] == ("git", "worktree", "add", "--detach") for call in runner.calls)

    host = next(call[0] for call in runner.calls if "--host-gates" in call[0])
    smoke = next(call[0] for call in runner.calls if "--smoke" in call[0])
    assert host[host.index("--up-ts") + 1] == smoke[smoke.index("--up-ts") + 1]
    down_index = next(i for i, call in enumerate(runner.calls) if call[0][-1:] == ("down",))
    final_status_index = max(i for i, call in enumerate(runner.calls) if call[0][:2] == ("git", "status"))
    assert down_index < final_status_index
    assert record["cleanup"]["ci"]["passed"]
    assert record["cleanup"]["evidence"]["passed"]


def test_whole_checker_marks_smoke_failure_incomplete_and_still_runs_down(tmp_path):
    runner = _FullRunner(fail_live_smoke=True)
    record = run_premerge(tmp_path, output=tmp_path / "failed.json", runner=runner)
    assert record["status"] == "FAIL"
    assert not record["live"]["completed"]
    assert "live-smoke" in record["live"]["reason"]
    assert next(step for step in record["steps"] if step["name"] == "live-required-nodes")["status"] == "not_run"
    assert any(call[0][-1:] == ("down",) for call in runner.calls)


def test_whole_checker_persists_no_live_as_an_incomplete_fail(tmp_path):
    runner = _FullRunner()
    output = tmp_path / "no-live.json"
    record = run_premerge(tmp_path, output=output, no_live=True, runner=runner)
    assert output.is_file()
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "FAIL"
    assert not record["live"]["completed"]
    assert "--no-live" in record["live"]["reason"]
    assert all(
        step["status"] == "not_run"
        for step in record["steps"] if step["name"] in {
            "live-export", "live-preflight", "live-up", "live-host-gates",
            "live-smoke", "live-required-nodes", "live-down",
        }
    )


def test_whole_checker_rejects_stable_head_when_the_tree_becomes_dirty(tmp_path):
    runner = _FullRunner(dirty_at_finish=True)
    record = run_premerge(tmp_path, output=tmp_path / "dirty.json", runner=runner)
    assert record["commit"] == runner.commit
    assert record["status"] == "FAIL"
    binding = next(step for step in record["steps"] if step["name"] == "commit-still-bound")
    assert not binding["passed"]
    assert "changed.py" in binding["detail"]


def test_verify_rejects_a_fabricated_step_command(tmp_path):
    runner = _FullRunner()
    output = tmp_path / "record.json"
    run_premerge(tmp_path, output=output, runner=runner)
    record = json.loads(output.read_text(encoding="utf-8"))
    next(step for step in record["steps"] if step["name"] == "office-seed-0")["command"] = ["true"]
    output.write_text(json.dumps(record), encoding="utf-8")
    ok, reasons = verify_record(output, runner.commit)
    assert not ok
    assert any("command semantics" in reason for reason in reasons)


def test_verify_rejects_missing_second_office_outcome(tmp_path):
    runner = _FullRunner()
    output = tmp_path / "record.json"
    run_premerge(tmp_path, output=output, runner=runner)
    record = json.loads(output.read_text(encoding="utf-8"))
    selector = next(node for node in REQUIRED_NODES if node not in LIVE_NODES)
    match = record["required_nodes"][selector]["matches"][0]
    record["required_nodes"][selector]["outcomes"][match] = ["passed"]
    output.write_text(json.dumps(record), encoding="utf-8")
    ok, reasons = verify_record(output, runner.commit)
    assert not ok
    assert any("required nodes" in reason for reason in reasons)


@pytest.mark.parametrize("outcome", ["missing", "skipped", "failure", "error"])
def test_whole_checker_writes_fail_for_each_nonpassing_required_node(tmp_path, outcome):
    runner = _FullRunner(required_outcome=outcome)
    output = tmp_path / f"{outcome}.json"
    record = run_premerge(tmp_path, output=output, runner=runner)
    assert output.is_file()
    assert record["status"] == "FAIL"
    assert not record["required_nodes"][REQUIRED_NODES[1]]["passed"]


def test_whole_checker_writes_fail_for_ci_collection_error(tmp_path):
    runner = _FullRunner(ci_collection_error=True)
    output = tmp_path / "collection-error.json"
    record = run_premerge(tmp_path, output=output, runner=runner)
    assert output.is_file()
    assert record["status"] == "FAIL"
    ci = next(step for step in record["steps"] if step["name"] == "fresh-worktree-ci")
    assert ci["returncode"] == 0
    assert ci["error_count"] == 1


@pytest.mark.parametrize("payload", [[], {"schema_version": 1}])
def test_verify_malformed_json_shapes_return_fail_without_raising(tmp_path, payload):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    ok, reasons = verify_record(path, _FullRunner.commit)
    assert not ok
    assert reasons
