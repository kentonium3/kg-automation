#!/usr/bin/env python3
"""Write or verify the commit-bound #849 pre-merge evidence record.

The checker deliberately treats subprocess status as only one piece of
evidence.  Its junit reports must also contain every required node, every
parametrized expansion must pass, the live phase must complete, and the
detached CI worktree must be removed.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SUITE_TIMEOUT_S = 900.0
COMMAND_TIMEOUT_S = 3_700.0  # substrate up itself permits a one-hour health wait
GIT_TIMEOUT_S = 60.0

# Each selector is a reviewable contract item.  Do not replace this with a
# marker expression: ``-m live`` selected nothing in the environment that
# motivated this gate.
REQUIRED_NODES: tuple[str, ...] = (
    "tests/research/test_arms849_integration.py::test_live_runtime_registers_g_d_r_with_one_embedder",
    "tests/research/test_arms849_integration.py::test_a_premise_violation_records_both_events_and_halts_before_later_work",
    "tests/research/test_arms849_integration.py::test_an_unacknowledged_g_cancellation_records_stop_and_escapes_without_more_graph_work",
    "tests/research/test_arms849_integration.py::test_graph_store_generation_and_boundaries_are_run_level_and_ordered",
    "tests/research/test_arms849_integration.py::test_send_time_ceiling_breach_is_terminal_stops_and_sends_zero_bytes",
    "tests/research/test_run_849_harness.py::test_measurement_is_ordered_exact_and_bound_to_commit_and_preflight",
    "tests/research/test_run_849_harness.py::test_preflight_generation_refuses_dirty_or_changed_code_and_writes_nothing",
    "tests/research/test_run_849_harness.py::test_an_unregistered_arm_is_recorded_not_silently_skipped",
    "tests/research/test_arms849_grading.py::test_export_refuses_not_implemented_cells",
    "tests/research/test_arms849_arm_d.py::test_the_arms_share_one_refusal_class",
    "tests/research/test_arms849_arm_g.py::test_live_hybrid_search_returns_an_item_the_question_names",
    "tests/research/test_arms849_isolation.py::test_every_package_module_is_registered_in_the_isolation_inventory",
    "tests/research/test_arms849_isolation.py::test_every_registered_module_exists_in_the_package",
    "tests/research/test_arms849_ledger.py::test_attempt_start_carries_the_session_id_of_its_own_session",
    "tests/research/test_arms849_sampler.py::test_real_cgroup_writer_emits_bound_header_records_and_a_clean_trailer",
    "tests/research/test_arms849_sampler.py::test_graph_store_report_round_trips_the_real_writer_against_a_fake_cgroup",
    "tests/research/test_arms849_sampler.py::test_report_unavailable_conditions_are_honest_and_never_raise",
    "tests/research/test_arms849_sampler.py::test_c19_only_the_canonical_isoformat_form_is_accepted",
    # Prior mission post-plan findings C-1, C-2, and C-5.
    "tests/research/test_arms849_grading.py::test_view_carries_nothing_but_the_allowed_fields",
    "tests/research/test_arms849_grading.py::test_admin_report_holds_the_non_scored_cells_and_lives_apart",
    "tests/research/test_arms849_arm_g.py::test_assembly_priority_cap_dedup_and_frozen_layout",
    # WP05: environment declaration, all three resume properties, and this
    # checker's positive commit-binding path.
    "tests/research/test_arms849_resume.py::test_live_style_resume_with_fresh_timestamped_gates_preserves_prior_rows",
    "tests/research/test_arms849_resume.py::test_live_style_resume_stops_and_records_a_failing_fresh_gate",
    "tests/research/test_arms849_resume.py::test_live_style_resume_cannot_write_after_skipped_gates",
    "tests/research/test_arms849_resume.py::test_missing_research_environment_has_one_named_counted_skip_reason",
    "tests/research/test_check_849_premerge.py::test_passing_record_is_bound_to_head_and_verifies",
)

WP05_REQUIRED_NODES = REQUIRED_NODES[-5:]
LIVE_NODES: tuple[str, ...] = (
    REQUIRED_NODES[0],
    REQUIRED_NODES[10],
)
LIVE_STEP_NAMES = (
    "live-export", "live-preflight", "live-up", "live-host-gates",
    "live-smoke", "live-required-nodes", "live-down",
)
REQUIRED_STEP_NAMES = frozenset({
    "checkout-clean-at-start",
    "office-seed-0",
    "office-seed-3",
    "fresh-worktree-ci",
    "live-export",
    "live-preflight",
    "live-up",
    "live-host-gates",
    "live-smoke",
    "live-required-nodes",
    "live-down",
    "commit-still-bound",
})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class Runner(Protocol):
    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: pathlib.Path,
        env: Mapping[str, str] | None = None,
        timeout_s: float | None = None,
    ) -> CommandResult: ...


class SubprocessRunner:
    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: pathlib.Path,
        env: Mapping[str, str] | None = None,
        timeout_s: float | None = None,
    ) -> CommandResult:
        proc = subprocess.run(
            list(argv), cwd=cwd, env=None if env is None else dict(env),
            capture_output=True, text=True, check=False, timeout=timeout_s,
        )
        return CommandResult(proc.returncode, proc.stdout, proc.stderr)


@dataclass(frozen=True)
class TestCase:
    node_id: str
    outcome: str


@dataclass(frozen=True)
class JUnitReport:
    cases: tuple[TestCase, ...]
    skipped: int
    failures: int
    errors: int
    phase: str = "evidence"

    def passed(self, returncode: int) -> bool:
        return returncode == 0 and self.failures == 0 and self.errors == 0


def _node_id(case: ET.Element) -> str:
    name = case.get("name", "")
    file_name = case.get("file")
    if file_name:
        file_name = file_name.replace("\\", "/")
        return f"{file_name}::{name}"
    classname = case.get("classname", "")
    parts = classname.split(".") if classname else []
    if parts and parts[0] == "tests":
        module = "/".join(parts) + ".py"
    elif parts and parts[0].startswith("test_"):
        module = "tests/research/" + parts[0] + ".py"
    else:
        # Collection failures normally have an empty classname and a path in
        # name.  Keep a stable identifier even though they cannot satisfy a
        # required selector.
        module = classname.replace(".", "/") or "<collection>"
    suffix = "::".join(parts[3:]) if len(parts) > 3 else ""
    return f"{module}::{suffix + '::' if suffix else ''}{name}"


def parse_junit(path: pathlib.Path, *, phase: str = "evidence") -> JUnitReport:
    root = ET.parse(path).getroot()
    cases: list[TestCase] = []
    skipped = failures = errors = 0
    for case in root.iter("testcase"):
        if case.find("error") is not None:
            outcome = "error"
            errors += 1
        elif case.find("failure") is not None:
            outcome = "failure"
            failures += 1
        elif case.find("skipped") is not None:
            outcome = "skipped"
            skipped += 1
        else:
            outcome = "passed"
        cases.append(TestCase(_node_id(case), outcome))
    suites = [
        suite for suite in root.iter("testsuite")
        if not any(child.tag == "testsuite" for child in suite)
    ]
    # Pytest normally emits an error testcase for a collection failure.  Some
    # junit producers expose it only in suite totals, which must fail too.
    def total(attribute: str) -> int:
        values: list[int] = []
        for suite in suites:
            try:
                values.append(int(suite.get(attribute, "0")))
            except ValueError:
                values.append(0)
        return sum(values)

    skipped = max(skipped, total("skipped"))
    failures = max(failures, total("failures"))
    errors = max(errors, total("errors"))
    return JUnitReport(tuple(cases), skipped, failures, errors, phase)


def evaluate_required_nodes(
    reports: Sequence[JUnitReport],
    selectors: Sequence[str] = REQUIRED_NODES,
    live_selectors: Sequence[str] = LIVE_NODES,
) -> dict[str, dict[str, object]]:
    """Return fail-closed verdicts, including every parametrized expansion.

    Every non-live selector and parametrized expansion must pass in every
    office report.  Live selectors are judged only in the explicit live
    report, so their intentional office skips cannot masquerade as evidence.
    With unlabelled reports, all reports are authoritative.
    """
    verdicts: dict[str, dict[str, object]] = {}
    live_set = set(live_selectors)
    for selector in selectors:
        desired_phase = "live" if selector in live_set else "office"
        relevant = [report for report in reports if report.phase == desired_phase]
        if not relevant:
            relevant = [report for report in reports if report.phase == "evidence"]
        per_report: list[dict[str, list[str]]] = []
        for report in relevant:
            found: dict[str, list[str]] = {}
            for case in report.cases:
                if case.node_id == selector or case.node_id.startswith(selector + "["):
                    found.setdefault(case.node_id, []).append(case.outcome)
            per_report.append(found)
        matches = sorted({node for found in per_report for node in found})
        if not matches or any(set(found) != set(matches) for found in per_report):
            status = "missing"
            passed = False
        else:
            outcomes = {
                outcome for found in per_report
                for node_outcomes in found.values() for outcome in node_outcomes
            }
            if "error" in outcomes:
                status, passed = "error", False
            elif "failure" in outcomes:
                status, passed = "failure", False
            elif "skipped" in outcomes:
                status, passed = "skipped", False
            else:
                status, passed = "passed", True
        verdicts[selector] = {
            "passed": passed,
            "status": status,
            "matches": matches,
            "outcomes": {
                node: [outcome for found in per_report for outcome in found.get(node, ["missing"])]
                for node in matches
            },
        }
    return verdicts


def _step(
    name: str,
    argv: Sequence[str],
    *,
    runner: Runner,
    cwd: pathlib.Path,
    env: Mapping[str, str] | None = None,
    junit: pathlib.Path | None = None,
    junit_phase: str = "evidence",
    timeout_s: float = COMMAND_TIMEOUT_S,
) -> tuple[dict[str, object], JUnitReport | None]:
    started = _now()
    command = list(argv)
    evidence_env = {
        key: env[key] for key in ("PYTHONHASHSEED", "ARMS849_CACHE", "ARMS849_LIVE", "PYTHONPATH")
        if env is not None and key in env
    }
    try:
        result = runner.run(command, cwd=cwd, env=env, timeout_s=timeout_s)
        report = (
            parse_junit(junit, phase=junit_phase)
            if junit is not None and junit.is_file() else None
        )
        passed = result.returncode == 0
        if junit is not None:
            passed = report is not None and report.passed(result.returncode)
        detail = (result.stderr or result.stdout)[-2000:]
        return ({
            "name": name,
            "command": command,
            "environment": evidence_env,
            "started_at": started,
            "finished_at": _now(),
            "returncode": result.returncode,
            "timed_out": False,
            "passed": passed,
            "status": "pass" if passed else "fail",
            "skip_count": report.skipped if report else 0,
            "failure_count": report.failures if report else 0,
            "error_count": report.errors if report else 0,
            "detail": detail,
        }, report)
    except Exception as exc:  # noqa: BLE001 — arbitrary runner failures must become FAIL evidence
        return ({
            "name": name,
            "command": command,
            "environment": evidence_env,
            "started_at": started,
            "finished_at": _now(),
            "returncode": None,
            "timed_out": isinstance(exc, subprocess.TimeoutExpired),
            "passed": False,
            "status": "fail",
            "skip_count": 0,
            "failure_count": 0,
            "error_count": 1,
            "detail": f"{type(exc).__name__}: {exc}",
        }, None)


def _not_run_step(name: str, detail: str) -> dict[str, object]:
    stamp = _now()
    return {
        "name": name, "command": [], "environment": {},
        "started_at": stamp, "finished_at": stamp,
        "returncode": None, "timed_out": False, "passed": False,
        "status": "not_run", "skip_count": 0, "failure_count": 0,
        "error_count": 1, "detail": detail,
    }


def _binding_step(
    name: str,
    repo_root: pathlib.Path,
    expected_head: str,
    runner: Runner,
) -> dict[str, object]:
    started = _now()
    command = ["git", "status", "--porcelain", "--untracked-files=all"]
    try:
        head = _head(repo_root, runner)
        result = runner.run(command, cwd=repo_root, timeout_s=GIT_TIMEOUT_S)
        passed = result.returncode == 0 and not result.stdout.strip() and head == expected_head
        detail = (
            f"expected_head={expected_head} observed_head={head}; "
            f"status={(result.stdout or result.stderr)[-2000:]!r}"
        )
        return {
            "name": name, "command": command, "environment": {}, "started_at": started,
            "finished_at": _now(), "returncode": result.returncode,
            "timed_out": False, "passed": passed,
            "status": "pass" if passed else "fail", "skip_count": 0,
            "failure_count": 0, "error_count": 0 if passed else 1,
            "detail": detail,
        }
    except Exception as exc:  # noqa: BLE001 — binding probes fail closed on any runner failure
        return {
            "name": name, "command": command, "environment": {}, "started_at": started,
            "finished_at": _now(), "returncode": None,
            "timed_out": isinstance(exc, subprocess.TimeoutExpired),
            "passed": False, "status": "fail", "skip_count": 0,
            "failure_count": 0, "error_count": 1,
            "detail": f"{type(exc).__name__}: {exc}",
        }


def run_ci_simulation(
    repo_root: pathlib.Path,
    commit: str,
    *,
    runner: Runner,
    temp_parent: pathlib.Path | None = None,
) -> dict[str, object]:
    """Run the no-build/no-graphiti detached-worktree simulation and clean it."""
    temp_root = pathlib.Path(tempfile.mkdtemp(prefix="arms849-ci-", dir=temp_parent))
    checkout = temp_root / "checkout"
    stub = temp_root / "stub"
    junit = temp_root / "ci.xml"
    (stub / "graphiti_core").mkdir(parents=True)
    (stub / "graphiti_core" / "__init__.py").write_text(
        "raise ModuleNotFoundError('graphiti_core intentionally absent in CI simulation')\n",
        encoding="utf-8",
    )
    started = _now()
    add_ok = False
    build_absent = False
    command_step: dict[str, object] = {
        "name": "fresh-worktree-ci", "command": [], "environment": {},
        "started_at": started,
        "finished_at": started, "returncode": None, "passed": False,
        "timed_out": False, "status": "not_run", "skip_count": 0,
        "failure_count": 0, "error_count": 1, "detail": "not run",
    }
    cleanup = {"attempted": False, "passed": True, "detail": "worktree was not created"}
    try:
        add = runner.run(
            ["git", "worktree", "add", "--detach", str(checkout), commit],
            cwd=repo_root, timeout_s=GIT_TIMEOUT_S,
        )
        add_ok = add.returncode == 0
        if not add_ok:
            command_step.update({
                "command": ["git", "worktree", "add", "--detach", str(checkout), commit],
                "finished_at": _now(), "returncode": add.returncode, "status": "fail",
                "detail": f"git worktree add failed: {(add.stderr or add.stdout)[-2000:]}",
            })
        elif (checkout / "build").exists():
            command_step["detail"] = "detached worktree unexpectedly contains build/"
        else:
            build_absent = True
            env = dict(os.environ)
            env.pop("ARMS849_LIVE", None)
            env["ARMS849_CACHE"] = str(temp_root / "absent-cache")
            env["PYTHONPATH"] = os.pathsep.join(
                [str(stub), str(checkout), env.get("PYTHONPATH", "")]
            ).rstrip(os.pathsep)
            command_step, _ = _step(
                "fresh-worktree-ci",
                [sys.executable, "-m", "pytest", "-q", "--ignore=docs/archive",
                 "-o", "junit_family=xunit1", f"--junitxml={junit}"],
                runner=runner, cwd=checkout, env=env, junit=junit,
                timeout_s=SUITE_TIMEOUT_S,
            )
    except Exception as exc:  # noqa: BLE001 — cleanup still runs after any injected runner failure
        command_step = {
            "name": "fresh-worktree-ci", "command": ["git", "worktree", "add"],
            "environment": {},
            "started_at": started, "finished_at": _now(), "returncode": None,
            "passed": False, "timed_out": isinstance(exc, subprocess.TimeoutExpired),
            "status": "fail", "skip_count": 0, "failure_count": 0,
            "error_count": 1, "detail": f"{type(exc).__name__}: {exc}",
        }
    finally:
        # ``worktree add`` may register before returning nonzero or before the
        # checkout directory appears, so cleanup is unconditional after the
        # attempt.  A second targeted remove follows filesystem fallback.
        cleanup["attempted"] = True
        cleanup_errors: list[str] = []
        try:
            removed = runner.run(
                ["git", "worktree", "remove", "--force", str(checkout)],
                cwd=repo_root, timeout_s=GIT_TIMEOUT_S,
            )
            if removed.returncode != 0:
                cleanup_errors.append(f"remove: {(removed.stderr or removed.stdout)[-1000:]}")
        except Exception as exc:  # noqa: BLE001 — runner implementations may raise arbitrary errors
            cleanup_errors.append(f"remove: {type(exc).__name__}: {exc}")
        if checkout.exists():
            cleanup_errors.append("checkout survived remove command")
            try:
                shutil.rmtree(checkout)
            except OSError as exc:
                cleanup_errors.append(f"filesystem fallback: {exc}")
        try:
            listed = runner.run(
                ["git", "worktree", "list", "--porcelain"],
                cwd=repo_root, timeout_s=GIT_TIMEOUT_S,
            )
            registered = f"worktree {checkout}" in listed.stdout.splitlines()
            if listed.returncode != 0:
                cleanup_errors.append(f"worktree list: {(listed.stderr or listed.stdout)[-1000:]}")
        except Exception as exc:  # noqa: BLE001 — registry verification fails closed on any error
            listed = None
            registered = True
            cleanup_errors.append(f"worktree list: {type(exc).__name__}: {exc}")
        if registered:
            cleanup_errors.append("registration survived remove command")
            try:
                runner.run(
                    ["git", "worktree", "remove", "--force", str(checkout)],
                    cwd=repo_root, timeout_s=GIT_TIMEOUT_S,
                )
                listed = runner.run(
                    ["git", "worktree", "list", "--porcelain"],
                    cwd=repo_root, timeout_s=GIT_TIMEOUT_S,
                )
                registered = f"worktree {checkout}" in listed.stdout.splitlines()
            except Exception as exc:  # noqa: BLE001 — targeted cleanup must preserve every failure
                cleanup_errors.append(f"targeted retry: {type(exc).__name__}: {exc}")
        survived = checkout.exists()
        cleanup["passed"] = (
            not cleanup_errors and not survived and not registered and
            listed is not None and listed.returncode == 0
        )
        cleanup["detail"] = (
            "removed from filesystem and worktree registry" if cleanup["passed"] else
            "; ".join(cleanup_errors + (["checkout survived"] if survived else []) +
                      (["registration survived"] if registered else []))
        )
        try:
            shutil.rmtree(temp_root)
        except OSError as exc:
            cleanup["passed"] = False
            cleanup["detail"] = f"temporary tree survived cleanup: {exc}"

    command_step["passed"] = bool(command_step.get("passed")) and bool(cleanup["passed"])
    command_step["status"] = "pass" if command_step["passed"] else "fail"
    return {
        **command_step,
        "started_at": command_step.get("started_at", started),
        "finished_at": command_step.get("finished_at", _now()),
        "worktree": str(checkout),
        "commit": commit,
        "detached": add_ok,
        "build_absent": build_absent,
        "graphiti_stub": str(stub / "graphiti_core" / "__init__.py"),
        "worktree_add_command": ["git", "worktree", "add", "--detach", str(checkout), commit],
        "cleanup": cleanup,
    }


def finalize_record(
    *,
    commit: str,
    started_at: str,
    steps: Sequence[Mapping[str, object]],
    required_nodes: Mapping[str, Mapping[str, object]],
    live_completed: bool,
    cleanup: Mapping[str, object],
    live_reason: str | None = None,
) -> dict[str, object]:
    live_steps = [step for step in steps if str(step.get("name", "")).startswith("live-")]
    live_passed = live_completed and bool(live_steps) and all(bool(step.get("passed")) for step in live_steps)
    node_passed = bool(required_nodes) and all(bool(item.get("passed")) for item in required_nodes.values())
    steps_passed = bool(steps) and all(bool(step.get("passed")) for step in steps)
    complete = live_completed and live_passed and cleanup.get("passed") is True
    passed = complete and steps_passed and node_passed
    return {
        "schema_version": 1,
        "commit": commit,
        "started_at": started_at,
        "finished_at": _now(),
        "status": "PASS" if passed else "FAIL",
        "complete": complete,
        "steps": list(steps),
        "skip_count": sum(int(step.get("skip_count", 0)) for step in steps),
        "required_nodes": dict(required_nodes),
        "live": {
            "required": True,
            "completed": live_completed,
            "passed": live_passed,
            "reason": None if live_passed else (
                live_reason or "record incomplete: live smoke did not complete"
            ),
        },
        "cleanup": dict(cleanup),
    }


def verify_record(path: pathlib.Path, head: str) -> tuple[bool, list[str]]:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return False, [f"record unreadable: {type(exc).__name__}: {exc}"]
    if not isinstance(record, dict):
        return False, ["record root must be a JSON object"]
    reasons: list[str] = []
    def aware_iso(value: object) -> bool:
        try:
            stamp = datetime.fromisoformat(value) if isinstance(value, str) else None
        except ValueError:
            return False
        return stamp is not None and stamp.tzinfo is not None

    for field in ("started_at", "finished_at"):
        value = record.get(field)
        if not aware_iso(value):
            reasons.append(f"{field} is not a timezone-aware ISO timestamp")
    if record.get("schema_version") != 1:
        reasons.append("unsupported schema_version")
    if record.get("commit") != head:
        reasons.append(f"record commit {record.get('commit')!r} does not equal HEAD {head!r}")
    if record.get("status") != "PASS" or record.get("complete") is not True:
        reasons.append("record is not a complete PASS")
    live = record.get("live")
    if not isinstance(live, dict) or live.get("completed") is not True or live.get("passed") is not True:
        reasons.append("live smoke is absent or failed")
    nodes = record.get("required_nodes")
    nodes_valid = isinstance(nodes, dict) and set(nodes) == set(REQUIRED_NODES)
    if nodes_valid:
        for selector, value in nodes.items():
            matches = value.get("matches") if isinstance(value, dict) else None
            outcomes = value.get("outcomes") if isinstance(value, dict) else None
            if (
                not isinstance(value, dict) or value.get("passed") is not True or
                value.get("status") != "passed" or not isinstance(matches, list) or
                not matches or any(
                    not isinstance(match, str) or
                    not (match == selector or match.startswith(selector + "["))
                    for match in matches
                ) or not isinstance(outcomes, dict) or set(outcomes) != set(matches) or
                any(
                    not isinstance(item, list) or
                    len(item) != (1 if selector in LIVE_NODES else 2) or
                    set(item) != {"passed"} for item in outcomes.values()
                )
            ):
                nodes_valid = False
                break
    if not nodes_valid:
        reasons.append("one or more required nodes did not pass")
    steps = record.get("steps")
    def valid_step(step: object) -> bool:
        if not isinstance(step, dict):
            return False
        command = step.get("command")
        environment = step.get("environment")
        counts = (step.get("skip_count"), step.get("failure_count"), step.get("error_count"))
        return (
            step.get("passed") is True and step.get("status") == "pass" and
            step.get("returncode") == 0 and step.get("timed_out") is False and
            isinstance(command, list) and command and all(isinstance(arg, str) for arg in command) and
            isinstance(environment, dict) and all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in environment.items()
            ) and
            aware_iso(step.get("started_at")) and aware_iso(step.get("finished_at")) and
            all(isinstance(count, int) and count >= 0 for count in counts) and
            isinstance(step.get("detail"), str)
        )
    if (
        not isinstance(steps, list) or not steps or
        any(not valid_step(step) for step in steps)
    ):
        reasons.append("one or more recorded steps did not pass")
    elif (
        len(steps) != len(REQUIRED_STEP_NAMES) or
        {step.get("name") for step in steps} != REQUIRED_STEP_NAMES
    ):
        reasons.append("recorded step inventory does not match this checker")
    else:
        by_name = {str(step["name"]): step for step in steps}

        def command_has(name: str, *parts: str) -> bool:
            command = by_name[name]["command"]
            return all(part in command for part in parts)

        semantics_ok = True
        for seed in (0, 3):
            step = by_name[f"office-seed-{seed}"]
            semantics_ok &= (
                command_has(f"office-seed-{seed}", "pytest", "tests/research", "junit_family=xunit1") and
                any(str(arg).startswith("--junitxml=") for arg in step["command"]) and
                step["environment"].get("PYTHONHASHSEED") == str(seed) and
                bool(step["environment"].get("ARMS849_CACHE"))
            )
        ci = by_name["fresh-worktree-ci"]
        worktree_add = ci.get("worktree_add_command", [])
        semantics_ok &= (
            command_has("fresh-worktree-ci", "pytest", "--ignore=docs/archive", "junit_family=xunit1") and
            any(str(arg).startswith("--junitxml=") for arg in ci["command"]) and
            ci.get("detached") is True and ci.get("build_absent") is True and
            ci.get("commit") == record.get("commit") and
            str(ci.get("graphiti_stub", "")).endswith("graphiti_core/__init__.py") and
            worktree_add[:4] == ["git", "worktree", "add", "--detach"] and
            worktree_add[-1:] == [record.get("commit")] and
            "ARMS849_LIVE" not in ci["environment"] and bool(ci["environment"].get("PYTHONPATH"))
        )
        semantics_ok &= command_has(
            "live-export", "scripts.research.arms849.substrate", "export", "--commit", record.get("commit")
        )
        semantics_ok &= command_has("live-preflight", "scripts.research.run_849_harness", "--preflight")
        semantics_ok &= command_has("live-up", "scripts.research.arms849.substrate", "up")
        semantics_ok &= command_has("live-host-gates", "--host-gates", "--up-ts")
        semantics_ok &= command_has(
            "live-smoke", "scripts.research.arms849.substrate", "run", "--smoke",
            "--up-ts", "--ledger",
        )
        required_live = by_name["live-required-nodes"]
        semantics_ok &= (
            command_has("live-required-nodes", "pytest", "junit_family=xunit1", *LIVE_NODES) and
            any(str(arg).startswith("--junitxml=") for arg in required_live["command"]) and
            required_live["environment"].get("ARMS849_LIVE") == "1"
        )
        semantics_ok &= command_has("live-down", "scripts.research.arms849.substrate", "down")
        for name in ("checkout-clean-at-start", "commit-still-bound"):
            semantics_ok &= by_name[name]["command"] == [
                "git", "status", "--porcelain", "--untracked-files=all",
            ]
        host_command = by_name["live-host-gates"]["command"]
        smoke_command = by_name["live-smoke"]["command"]
        try:
            host_ts = host_command[host_command.index("--up-ts") + 1]
            smoke_ts = smoke_command[smoke_command.index("--up-ts") + 1]
        except (ValueError, IndexError):
            host_ts = smoke_ts = ""
        semantics_ok &= bool(host_ts) and host_ts == smoke_ts
        if not semantics_ok:
            reasons.append("recorded command semantics do not match this checker")
    cleanup = record.get("cleanup")
    if (
        not isinstance(cleanup, dict) or cleanup.get("attempted") is not True or
        cleanup.get("passed") is not True or not isinstance(cleanup.get("detail"), str)
    ):
        reasons.append("cleanup did not pass")
    return not reasons, reasons


def _head(repo_root: pathlib.Path, runner: Runner) -> str:
    result = runner.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, timeout_s=GIT_TIMEOUT_S,
    )
    if result.returncode != 0:
        raise RuntimeError(f"cannot resolve HEAD: {result.stderr or result.stdout}")
    return result.stdout.strip()


def run_premerge(
    repo_root: pathlib.Path = REPO_ROOT,
    *,
    output: pathlib.Path | None = None,
    no_live: bool = False,
    runner: Runner | None = None,
) -> dict[str, object]:
    runner = runner or SubprocessRunner()
    started = _now()
    commit = _head(repo_root, runner)
    steps: list[dict[str, object]] = [
        _binding_step("checkout-clean-at-start", repo_root, commit, runner)
    ]
    reports: list[JUnitReport] = []
    cache = os.environ.get("ARMS849_CACHE", str(repo_root / "build" / "849-cache"))
    evidence_root = pathlib.Path(tempfile.mkdtemp(prefix="arms849-premerge-"))
    ci_cleanup: dict[str, object] = {
        "attempted": False, "passed": False, "detail": "CI cleanup did not run",
    }
    live_completed = False
    live_reason: str | None = None
    try:
        for seed in (0, 3):
            junit = evidence_root / f"office-seed-{seed}.xml"
            env = {**os.environ, "PYTHONHASHSEED": str(seed), "ARMS849_CACHE": cache}
            env.pop("ARMS849_LIVE", None)
            step, report = _step(
                f"office-seed-{seed}",
                [sys.executable, "-m", "pytest", "-q", "tests/research",
                 "-o", "junit_family=xunit1", f"--junitxml={junit}"],
                runner=runner, cwd=repo_root, env=env, junit=junit,
                junit_phase="office",
                timeout_s=SUITE_TIMEOUT_S,
            )
            steps.append(step)
            if report is not None:
                reports.append(report)

        ci = run_ci_simulation(repo_root, commit, runner=runner, temp_parent=evidence_root)
        steps.append({key: value for key, value in ci.items() if key != "cleanup"})
        ci_cleanup = dict(ci["cleanup"])

        if no_live:
            live_reason = "record incomplete: live smoke was not run (--no-live)"
            steps.extend(_not_run_step(name, live_reason) for name in LIVE_STEP_NAMES)
        else:
            python = sys.executable
            substrate = [python, "-m", "scripts.research.arms849.substrate"]
            harness = [python, "-m", "scripts.research.run_849_harness"]
            live_steps: dict[str, dict[str, object]] = {}
            blocked_by: str | None = None
            up_ts = ""

            def live_step(
                name: str,
                command: Sequence[str],
                *,
                env: Mapping[str, str] | None = None,
                junit: pathlib.Path | None = None,
            ) -> JUnitReport | None:
                nonlocal blocked_by
                if blocked_by is not None:
                    live_steps[name] = _not_run_step(name, f"blocked by {blocked_by}")
                    return None
                step, report = _step(
                    name, command, runner=runner, cwd=repo_root, env=env,
                    junit=junit, junit_phase="live", timeout_s=(
                        SUITE_TIMEOUT_S if junit is not None else COMMAND_TIMEOUT_S
                    ),
                )
                live_steps[name] = step
                if not step["passed"]:
                    blocked_by = name
                return report

            try:
                live_step("live-export", [*substrate, "export", "--commit", commit])
                live_step("live-preflight", [*harness, "--preflight"])
                live_step("live-up", [*substrate, "up"])
                if blocked_by is None:
                    up_ts = _now()
                stamp = (up_ts or _now()).replace(":", "").replace("+", "_")
                ledger = repo_root / "build" / "849-runs" / f"smoke-{stamp}.jsonl"
                live_step("live-host-gates", [*harness, "--host-gates", "--up-ts", up_ts])
                live_step(
                    "live-smoke",
                    [*substrate, "run", "--", "--smoke", "--up-ts", up_ts,
                     "--ledger", str(ledger)],
                )
                junit = evidence_root / "live-nodes.xml"
                env = {**os.environ, "ARMS849_LIVE": "1", "ARMS849_CACHE": cache}
                report = live_step(
                    "live-required-nodes",
                    [python, "-m", "pytest", "-q", *LIVE_NODES,
                     "-o", "junit_family=xunit1", f"--junitxml={junit}"],
                    env=env, junit=junit,
                )
                if report is not None:
                    reports.append(report)
            finally:
                down, _ = _step("live-down", [*substrate, "down"], runner=runner, cwd=repo_root)
                live_steps["live-down"] = down
                steps.extend(live_steps[name] for name in LIVE_STEP_NAMES)
                live_completed = all(
                    live_steps[name].get("status") != "not_run" for name in LIVE_STEP_NAMES
                )
                if blocked_by is not None:
                    live_reason = f"record incomplete: live phase blocked by {blocked_by}"

        steps.append(_binding_step("commit-still-bound", repo_root, commit, runner))
        verdicts = evaluate_required_nodes(reports)
    finally:
        evidence_cleanup = {"attempted": True, "passed": True, "detail": "removed"}
        try:
            shutil.rmtree(evidence_root)
        except OSError as exc:
            evidence_cleanup = {
                "attempted": True, "passed": False,
                "detail": f"evidence directory cleanup failed: {exc}",
            }

    cleanup = {
        "attempted": bool(ci_cleanup.get("attempted")) and evidence_cleanup["attempted"],
        "passed": ci_cleanup.get("passed") is True and evidence_cleanup["passed"] is True,
        "detail": f"ci: {ci_cleanup.get('detail')}; evidence: {evidence_cleanup['detail']}",
        "ci": ci_cleanup,
        "evidence": evidence_cleanup,
    }
    record = finalize_record(
        commit=commit, started_at=started, steps=steps, required_nodes=verdicts,
        live_completed=live_completed, cleanup=cleanup, live_reason=live_reason,
    )

    destination = output or repo_root / "build" / "849-runs" / f"premerge-{commit}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="check_849_premerge")
    parser.add_argument("--output", "--record", dest="record", type=pathlib.Path)
    parser.add_argument("--no-live", action="store_true")
    parser.add_argument("--verify", type=pathlib.Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    runner = SubprocessRunner()
    if args.verify is not None:
        ok, reasons = verify_record(args.verify, _head(REPO_ROOT, runner))
        print("PASS" if ok else "FAIL: " + "; ".join(reasons))
        return 0 if ok else 1
    record = run_premerge(output=args.record, no_live=args.no_live, runner=runner)
    print(json.dumps({"commit": record["commit"], "status": record["status"]}, sort_keys=True))
    return 0 if record["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
