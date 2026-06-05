"""Unit tests for `scripts/vikunja/validate_felix_bot.py`.

Strategy: import the helper as a module (via importlib because of the
underscore-vs-hyphen filename convention), then exercise each pure
function. Network paths are exercised by monkeypatching `_request`
(the urllib wrapper) so no live HTTP is issued. Argparse / identity-
gate / SUMMARY-line tests run the helper as a subprocess to cover the
end-to-end CLI surface.

Pattern mirrors `tests/openclaw/agents/main/test_felix_file_issue.py`.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------


REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_PATH = REPO_ROOT / "scripts" / "vikunja" / "validate_felix_bot.py"


def _subprocess_env(**extra) -> dict:
    """Build a subprocess env with PYTHONPATH=REPO_ROOT and a dummy VIKUNJA_BASE_URL."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.setdefault("VIKUNJA_BASE_URL", "https://vikunja.test/api/v1/")
    env.update(extra)
    return env


def _load_helper_module():
    """Load the helper as a module so we can call its functions directly."""
    spec = importlib.util.spec_from_file_location(
        "validate_felix_bot", HELPER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


helper = _load_helper_module()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def good_token_file(tmp_path: Path) -> Path:
    p = tmp_path / "token.txt"
    p.write_text("test-felix-bot-token\n")
    p.chmod(0o600)
    return p


def _twelve_real_projects() -> list[dict[str, Any]]:
    return [
        {"id": i, "title": f"Project {i}", "is_archived": False}
        for i in range(1, 13)
    ]


# ---------------------------------------------------------------------------
# Argparse / CLI surface (subprocess)
# ---------------------------------------------------------------------------


def test_help_exits_zero():
    result = subprocess.run(
        [sys.executable, str(HELPER_PATH), "--help"],
        capture_output=True,
        text=True,
        check=False,
        env=_subprocess_env(),
    )
    assert result.returncode == 0
    assert "--token-file" in result.stdout
    assert "--rollback-smoke-test" in result.stdout
    assert "--dry-run" in result.stdout


def test_missing_token_file_arg_exits_2():
    result = subprocess.run(
        [sys.executable, str(HELPER_PATH)],
        capture_output=True,
        text=True,
        check=False,
        env=_subprocess_env(),
    )
    assert result.returncode == 2
    assert "--token-file" in result.stderr


# ---------------------------------------------------------------------------
# Identity gate
# ---------------------------------------------------------------------------


def test_identity_gate_missing_file_exits_2(tmp_path: Path):
    missing = tmp_path / "nope.txt"
    result = subprocess.run(
        [sys.executable, str(HELPER_PATH), "--token-file", str(missing)],
        capture_output=True,
        text=True,
        check=False,
        env=_subprocess_env(),
    )
    assert result.returncode == 2
    assert "does not exist" in result.stderr


def test_identity_gate_wrong_mode_exits_2(tmp_path: Path):
    p = tmp_path / "token.txt"
    p.write_text("abc\n")
    p.chmod(0o644)  # too permissive
    result = subprocess.run(
        [sys.executable, str(HELPER_PATH), "--token-file", str(p)],
        capture_output=True,
        text=True,
        check=False,
        env=_subprocess_env(),
    )
    assert result.returncode == 2
    assert "mode 600" in result.stderr


def test_identity_gate_empty_token_exits_2(tmp_path: Path):
    p = tmp_path / "token.txt"
    p.write_text("")
    p.chmod(0o600)
    result = subprocess.run(
        [sys.executable, str(HELPER_PATH), "--token-file", str(p)],
        capture_output=True,
        text=True,
        check=False,
        env=_subprocess_env(),
    )
    assert result.returncode == 2
    assert "empty" in result.stderr


def test_identity_gate_happy_returns_token(good_token_file: Path):
    token = helper.read_token_with_identity_gate(good_token_file)
    assert token == "test-felix-bot-token"


# ---------------------------------------------------------------------------
# Project access verification
# ---------------------------------------------------------------------------


def test_verify_project_access_happy_12(monkeypatch):
    calls: list[tuple[str, str]] = []

    def fake_request(method, url, token, body=None, timeout=30.0):
        calls.append((method, url))
        return 200, _twelve_real_projects()

    monkeypatch.setattr(helper, "_request", fake_request)

    summary = helper.verify_project_access(
        token="t",
        base_url="https://example.test/api/v1/",
        expected_count=12,
    )
    assert summary["count"] == 12
    assert summary["accessible_project_ids"] == list(range(1, 13))
    assert calls == [
        ("GET", "https://example.test/api/v1/projects?per_page=50")
    ]


def test_verify_project_access_eleven_exits_1(monkeypatch, capsys):
    eleven = _twelve_real_projects()[:-1]

    def fake_request(method, url, token, body=None, timeout=30.0):
        return 200, eleven

    monkeypatch.setattr(helper, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        helper.verify_project_access(
            token="t",
            base_url="https://example.test/api/v1/",
            expected_count=12,
        )
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "expected at least 12 accessible projects, got 11" in captured.err
    # The accessible ids should be in the error message so the operator
    # can deduce which grant is missing.
    assert "[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]" in captured.err


def test_verify_project_access_401_exits_1(monkeypatch, capsys):
    def fake_request(method, url, token, body=None, timeout=30.0):
        return 401, {"message": "Bad token"}

    monkeypatch.setattr(helper, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        helper.verify_project_access(
            token="t",
            base_url="https://example.test/api/v1/",
            expected_count=12,
        )
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "401" in captured.err
    assert "share grants may not have applied" in captured.err


def test_verify_project_access_filters_archived_and_pseudo(monkeypatch):
    """Real projects only — pseudo (id <= 0) and archived ones don't count."""
    projects = _twelve_real_projects() + [
        {"id": -1, "title": "Pseudo Filter", "is_archived": False},
        {"id": 99, "title": "Archived", "is_archived": True},
    ]

    def fake_request(method, url, token, body=None, timeout=30.0):
        return 200, projects

    monkeypatch.setattr(helper, "_request", fake_request)
    summary = helper.verify_project_access(
        token="t", base_url="https://example.test/api/v1/", expected_count=12
    )
    assert summary["count"] == 12


# ---------------------------------------------------------------------------
# Attribution probe
# ---------------------------------------------------------------------------


def _make_happy_attribution_responses(task_id: int = 4242, comment_id: int = 999):
    """Build a deterministic response stream for the happy-path probe.

    Live-probe finding (2026-05-17): Vikunja v0.24.6 attributes:
    - tasks via `created_by.username` (PUT /projects/{id}/tasks response)
    - comments via `author.username` (PUT /tasks/{id}/comments response +
      GET /tasks/{id}/comments readback). `created_by` is NOT populated
      on comment objects.
    """
    task_obj = {
        "id": task_id,
        "title": "felix-bot validation probe T",
        "created_by": {"username": "felix-bot"},
    }
    comment_obj = {
        "id": comment_id,
        "comment": "[Felix-Validation] x",
        "author": {"username": "felix-bot"},
    }
    readback_obj = {
        "id": comment_id,
        "comment": "[Felix-Validation] x",
        "author": {"username": "felix-bot"},
    }
    return task_obj, comment_obj, readback_obj


def _make_request_dispatcher(responses: list[tuple[int, Any]]):
    """Return a fake `_request` that pops from a fixed response queue."""
    calls: list[tuple[str, str]] = []

    def fake(method, url, token, body=None, timeout=30.0):
        calls.append((method, url))
        if not responses:
            raise AssertionError(f"unexpected extra request: {method} {url}")
        return responses.pop(0)

    return fake, calls


def test_validate_attribution_happy(monkeypatch, capsys):
    task_obj, comment_obj, readback_obj = _make_happy_attribution_responses()
    responses = [
        (200, task_obj),
        (200, comment_obj),
        (200, [readback_obj]),
        (204, None),  # delete comment
        (204, None),  # delete task
    ]
    fake, calls = _make_request_dispatcher(responses)
    monkeypatch.setattr(helper, "_request", fake)

    summary = helper.validate_attribution(
        token="t",
        base_url="https://example.test/api/v1/",
        target_project_id=13,
    )
    assert summary["task_id"] == 4242
    assert summary["comment_id"] == 999
    assert summary["attribution_checks"] == {
        "task_creation_username": "felix-bot",
        "comment_write_username": "felix-bot",
        "comment_readback_username": "felix-bot",
    }
    assert summary["cleanup"] == {"comment_deleted": True, "task_deleted": True}
    # Verify the call sequence (5 requests in order)
    methods = [m for m, _ in calls]
    assert methods == ["PUT", "PUT", "GET", "DELETE", "DELETE"]
    # Comment delete URL must include both IDs
    assert "/tasks/4242/comments/999" in calls[3][1]
    assert calls[4][1].endswith("/tasks/4242")


def test_validate_attribution_task_creation_wrong_username_exits_1(monkeypatch, capsys):
    task_obj = {"id": 1, "created_by": {"username": "kent"}}
    fake, _ = _make_request_dispatcher([(200, task_obj)])
    monkeypatch.setattr(helper, "_request", fake)

    with pytest.raises(SystemExit) as exc:
        helper.validate_attribution(
            token="t",
            base_url="https://example.test/api/v1/",
            target_project_id=13,
        )
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "task created_by.username" in captured.err
    assert "'kent'" in captured.err


def test_validate_attribution_comment_write_wrong_username_exits_1(monkeypatch, capsys):
    task_obj = {"id": 1, "created_by": {"username": "felix-bot"}}
    # Vikunja v0.24.6 comment write responses use author.username for
    # attribution. A response with author.username != 'felix-bot' must exit 1.
    bad_comment = {"id": 7, "author": {"username": "kent"}}
    fake, _ = _make_request_dispatcher([(200, task_obj), (200, bad_comment)])
    monkeypatch.setattr(helper, "_request", fake)

    with pytest.raises(SystemExit) as exc:
        helper.validate_attribution(
            token="t",
            base_url="https://example.test/api/v1/",
            target_project_id=13,
        )
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "comment author.username" in captured.err


def test_validate_attribution_cleanup_soft_fails(monkeypatch, capsys):
    """Cleanup DELETEs returning 404 should NOT fail validation."""
    task_obj, comment_obj, readback_obj = _make_happy_attribution_responses()
    responses = [
        (200, task_obj),
        (200, comment_obj),
        (200, [readback_obj]),
        (404, None),  # delete comment fails
        (404, None),  # delete task fails
    ]
    fake, _ = _make_request_dispatcher(responses)
    monkeypatch.setattr(helper, "_request", fake)

    summary = helper.validate_attribution(
        token="t",
        base_url="https://example.test/api/v1/",
        target_project_id=13,
    )
    # Validation still returns success, but cleanup flags are False and we
    # emitted WARNs.
    assert summary["cleanup"] == {
        "comment_deleted": False,
        "task_deleted": False,
    }
    captured = capsys.readouterr()
    assert "WARN" in captured.err
    assert "cleanup" in captured.err.lower()


def test_validate_attribution_readback_missing_comment_exits_1(monkeypatch, capsys):
    """If the just-written comment is not in the readback list, halt."""
    task_obj, comment_obj, _ = _make_happy_attribution_responses()
    responses = [
        (200, task_obj),
        (200, comment_obj),
        (200, []),  # readback returns empty list
    ]
    fake, _ = _make_request_dispatcher(responses)
    monkeypatch.setattr(helper, "_request", fake)

    with pytest.raises(SystemExit) as exc:
        helper.validate_attribution(
            token="t",
            base_url="https://example.test/api/v1/",
            target_project_id=13,
        )
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "not present on readback" in captured.err


# ---------------------------------------------------------------------------
# Regression: strict author.username for comments — no fallback
# ---------------------------------------------------------------------------
#
# Live probe against Vikunja v0.24.6 on 2026-05-17 confirmed: comment
# responses carry `author.username` (not `created_by`). The two tests
# below pin the strict-author behavior: the helper must reject any
# comment whose `author.username != 'felix-bot'`, with no fallback to
# any other field. Tasks remain attributed by `created_by.username`
# (verified separately above) — this distinction is enforced.


def test_validate_attribution_comment_write_wrong_author_exits_1(
    monkeypatch, capsys
):
    """Write response with author.username != felix-bot must FAIL.

    Even if a created_by field were present and named felix-bot, the
    helper must NOT consult it for comment attribution — `author` is
    the canonical field for comment objects.
    """
    task_obj = {"id": 1, "created_by": {"username": "felix-bot"}}
    bad_comment = {
        "id": 7,
        "author": {"username": "kent"},
        # If a created_by snuck into the payload claiming felix-bot, the
        # helper must still reject — author is canonical, no fallback.
        "created_by": {"username": "felix-bot"},
    }
    fake, _ = _make_request_dispatcher([(200, task_obj), (200, bad_comment)])
    monkeypatch.setattr(helper, "_request", fake)

    with pytest.raises(SystemExit) as exc:
        helper.validate_attribution(
            token="t",
            base_url="https://example.test/api/v1/",
            target_project_id=13,
        )
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "comment author.username" in captured.err
    assert "'kent'" in captured.err


def test_validate_attribution_readback_wrong_author_exits_1(monkeypatch, capsys):
    """Readback comment with author.username != felix-bot must FAIL."""
    task_obj, comment_obj, _ = _make_happy_attribution_responses()
    bad_readback = {
        "id": comment_obj["id"],
        "comment": "[Felix-Validation] x",
        "author": {"username": "kent"},
    }
    responses = [
        (200, task_obj),
        (200, comment_obj),
        (200, [bad_readback]),
    ]
    fake, _ = _make_request_dispatcher(responses)
    monkeypatch.setattr(helper, "_request", fake)

    with pytest.raises(SystemExit) as exc:
        helper.validate_attribution(
            token="t",
            base_url="https://example.test/api/v1/",
            target_project_id=13,
        )
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "readback comment author.username" in captured.err


# ---------------------------------------------------------------------------
# Rollback smoke test (FR-015)
# ---------------------------------------------------------------------------


def test_rollback_smoke_test_happy(tmp_path: Path, capsys, monkeypatch):
    secrets = tmp_path / "vikunja-api.kent"
    secrets.write_text("STUB")
    bak = tmp_path / "vikunja-api.kent-pre-felix-bot.bak"
    # bak does NOT exist — that is the legitimate pre-cutover state.

    # Sanity: ensure no real _request is invoked during the smoke test.
    def boom(*a, **kw):
        raise AssertionError("smoke test should never issue HTTP")

    monkeypatch.setattr(helper, "_request", boom)

    summary = helper.rollback_smoke_test(secrets_path=secrets, bak_path=bak)
    assert summary["within_budget"] is True
    assert summary["simulated_total_seconds"] < helper.NFR_003_BUDGET_SECONDS
    # All three modeled steps are present.
    step_names = [s["step"] for s in summary["steps"]]
    assert step_names == [
        "copy_bak_to_secrets",
        "restart_openclaw_gateway",
        "invoke_sample_agent_and_verify_kent",
    ]
    captured = capsys.readouterr()
    assert "Would copy" in captured.out
    assert "Would restart openclaw-gateway" in captured.out


def test_rollback_smoke_test_bak_exists_exits_1(tmp_path: Path, capsys):
    secrets = tmp_path / "vikunja-api.kent"
    secrets.write_text("STUB")
    bak = tmp_path / "vikunja-api.kent-pre-felix-bot.bak"
    bak.write_text("OLD")  # simulating Phase 3 already ran

    with pytest.raises(SystemExit) as exc:
        helper.rollback_smoke_test(secrets_path=secrets, bak_path=bak)
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "already exists" in captured.err
    assert "Phase 3" in captured.err


def test_rollback_smoke_test_cli_emits_summary(
    tmp_path: Path, good_token_file: Path
):
    """End-to-end CLI invocation of the smoke-test path, no network."""
    secrets = tmp_path / "vikunja-api.kent"
    secrets.write_text("STUB")
    bak = tmp_path / "vikunja-api.kent-pre-felix-bot.bak"

    result = subprocess.run(
        [
            sys.executable,
            str(HELPER_PATH),
            "--token-file",
            str(good_token_file),
            "--rollback-smoke-test",
            "--secrets-path",
            str(secrets),
            "--bak-path",
            str(bak),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=_subprocess_env(),
    )
    assert result.returncode == 0, result.stderr
    assert "SUMMARY: mode=rollback-smoke-test" in result.stdout
    assert "within_budget=True" in result.stdout


# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------


def test_dry_run_no_network(good_token_file: Path):
    """`--dry-run` issues no network calls, emits SUMMARY, exits 0."""
    result = subprocess.run(
        [
            sys.executable,
            str(HELPER_PATH),
            "--token-file",
            str(good_token_file),
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=_subprocess_env(),
    )
    assert result.returncode == 0, result.stderr
    assert "DRY-RUN" in result.stdout
    assert "SUMMARY: mode=dry-run" in result.stdout
    assert "network_calls=0" in result.stdout
