"""Integration tests for the 4 documented edge cases (T031).

These tests cover the spec's User Scenarios edge cases end-to-end:

1. **LLM API outage** — Anthropic SDK raises after retries; driver
   logs the error and continues (or sets status=failure if no signal
   processed).
2. **GitHub rate limit** — ``gh`` returns 403 with rate-limit headers;
   driver BREAKs the loop, status=failure, no further API calls.
3. **Audit references missing file** — :class:`FileNotFoundError` from
   the routing layer; driver logs, files a debt marker, continues.
4. **Stuck lock recovery (FR-014)** — in-progress audit with no matching
   pending-approval; driver flags as stale, clears the label, records
   the recovery in ``result.errors``.

All tests verify the tick signal artifact is written and reflects the
failure mode correctly (status + errors[]). No unhandled exceptions
should reach top-level — the ``try/finally`` in ``main()`` is
load-bearing.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from doc_audit import run  # noqa: E402
from doc_audit.helpers.handle_audit_routing import RoutingResult  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers (mirror those in test_integration_tick_outcomes — duplicated
# intentionally so each test file is self-contained)
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(
        args=["gh"], returncode=rc, stdout=stdout, stderr=stderr
    )


def _make_gh_router(
    monkeypatch: pytest.MonkeyPatch,
    *,
    list_by_label: dict[str, list[dict]] | None = None,
    view_by_number: dict[int, dict] | None = None,
    default_list: list[dict] | None = None,
    raise_on: Callable[[list[str]], BaseException | None] | None = None,
) -> list[list[str]]:
    list_by_label = list_by_label or {}
    view_by_number = view_by_number or {}
    default_list = default_list if default_list is not None else []

    calls: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not (isinstance(cmd, (list, tuple)) and cmd and cmd[0] == "gh"):
            raise RuntimeError(f"unexpected non-gh subprocess: {cmd!r}")
        cmd = list(cmd)
        calls.append(cmd)
        if raise_on is not None:
            exc = raise_on(cmd)
            if exc is not None:
                raise exc
        if len(cmd) >= 3 and cmd[1] == "issue" and cmd[2] == "list":
            label_values = [
                cmd[i + 1] for i, tok in enumerate(cmd)
                if tok == "--label" and i + 1 < len(cmd)
            ]
            for lbl in label_values:
                if lbl in list_by_label:
                    return _completed(json.dumps(list_by_label[lbl]))
            return _completed(json.dumps(default_list))
        if len(cmd) >= 4 and cmd[1] == "issue" and cmd[2] == "view":
            try:
                number = int(cmd[3])
            except ValueError:
                number = -1
            return _completed(json.dumps(view_by_number.get(number, {})))
        return _completed("")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


def _read_tick_signal(tmp_config: Any) -> dict[str, Any]:
    path = Path(tmp_config.paths.tick_signal_path)
    assert path.exists(), "tick signal was not written"
    return json.loads(path.read_text(encoding="utf-8"))


def _config_path(tmp_config: Any) -> Path:
    api_key_path = Path(tmp_config.llm.api_key_path)
    return api_key_path.parent / "config.toml"


# ---------------------------------------------------------------------------
# Edge case 1: LLM API outage
# ---------------------------------------------------------------------------


def test_llm_api_outage(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic: Any,
) -> None:
    """Audit processing surfaces an Anthropic error via routing.

    We simulate the LLM outage at the routing-layer boundary (the
    routing layer is where the driver actually orchestrates the audit
    in WP06). The routing function raises ``RuntimeError`` mimicking
    an Anthropic-derived failure; the orchestration loop logs to
    ``errors``, marks the tick partial, and STILL writes the tick
    signal.
    """
    audits = [
        {
            "number": 8000,
            "title": "Doc audit: ccc3333 (felix-core)",
            "body": "",
            "labels": [{"name": "doc-audit"}, {"name": "area/felix-core"}],
            "createdAt": "2026-05-20T11:00:00Z",
        }
    ]
    _make_gh_router(monkeypatch, list_by_label={"doc-audit": audits})

    def fake_apply(*args, **kwargs):
        # Simulate the Anthropic outage propagating up.
        raise RuntimeError("anthropic.APIConnectionError: dns failure")

    monkeypatch.setattr(run, "apply_routing", fake_apply)

    exit_code = run.main(["--config", str(_config_path(tmp_config))])

    # Single-signal failure → partial (per FR error semantics)
    assert exit_code in (1, 2)
    signal = _read_tick_signal(tmp_config)
    assert signal["status"] in ("partial", "failure")
    assert any(
        "anthropic" in err.lower() or "apiconnectionerror" in err.lower()
        for err in signal["errors"]
    ), f"expected anthropic outage marker; got {signal['errors']}"


# ---------------------------------------------------------------------------
# Edge case 2: GitHub rate limit
# ---------------------------------------------------------------------------


def test_gh_rate_limit(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic: Any,
) -> None:
    """gh CLI returns 403 + rate-limit body → driver BREAKs the loop.

    The first gh call (the signal-source's issue list) raises a
    ``CalledProcessError`` with the canonical rate-limit body. The
    driver classifies it as a ``RateLimitError`` and BREAKs — no
    further gh calls.
    """
    def raise_on(cmd):
        if len(cmd) >= 3 and cmd[1] == "issue" and cmd[2] == "list":
            return subprocess.CalledProcessError(
                returncode=1,
                cmd=cmd,
                output="",
                stderr=(
                    "HTTP 403: API rate limit exceeded for installation "
                    "ID 12345. (https://docs.github.com/rest/overview/"
                    "resources-in-the-rest-api#rate-limiting)\n"
                ),
            )
        return None

    calls = _make_gh_router(monkeypatch, raise_on=raise_on)

    exit_code = run.main(["--config", str(_config_path(tmp_config))])

    assert exit_code == 1  # failure
    signal = _read_tick_signal(tmp_config)
    assert signal["status"] == "failure"
    assert signal["exit_code"] == 1
    assert any(
        "rate" in err.lower() for err in signal["errors"]
    ), f"expected rate-limit marker in errors; got {signal['errors']}"
    # No issue-list calls past the first one — the driver shouldn't
    # have retried after the first 403.
    list_calls = [
        c for c in calls if len(c) >= 3 and c[1] == "issue" and c[2] == "list"
    ]
    # Only the first scan (in pending) should have been attempted.
    assert len(list_calls) <= 1


# ---------------------------------------------------------------------------
# Edge case 3: Audit references missing file
# ---------------------------------------------------------------------------


def test_audit_references_missing_file(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic: Any,
) -> None:
    """Audit's routing surfaces FileNotFoundError → REAL debt issue filed
    + originating audit closed + real issue number in debt_filed.

    Post-#348 behavior: the driver no longer records a placeholder ``0``.
    It files a real ``docs-debt`` issue, comments on the originating
    audit with the cross-reference, and closes the audit.
    """
    audits = [
        {
            "number": 8500,
            "title": "Doc audit: ddd4444 (felix-core)",
            "body": "",
            "labels": [{"name": "doc-audit"}, {"name": "area/felix-core"}],
            "createdAt": "2026-05-20T11:30:00Z",
        }
    ]

    # Custom router that handles BOTH list/view queries AND the missing-
    # file debt-filing ops (create/comment/close). Returns a fake issue
    # #9999 URL on `gh issue create`.
    gh_calls: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        if not (isinstance(cmd, (list, tuple)) and cmd and cmd[0] == "gh"):
            raise RuntimeError(f"unexpected non-gh subprocess: {cmd!r}")
        cmd = list(cmd)
        gh_calls.append(cmd)
        # gh issue list --label doc-audit → audits fixture
        if (
            len(cmd) >= 3 and cmd[1] == "issue" and cmd[2] == "list"
            and "--label" in cmd
        ):
            label_idx = cmd.index("--label")
            if label_idx + 1 < len(cmd) and cmd[label_idx + 1] == "doc-audit":
                return subprocess.CompletedProcess(
                    cmd, 0, stdout=json.dumps(audits), stderr="",
                )
            return subprocess.CompletedProcess(
                cmd, 0, stdout="[]", stderr="",
            )
        # gh issue view <N> → empty (no in-progress recovery context)
        if cmd[1] == "issue" and cmd[2] == "view":
            return subprocess.CompletedProcess(
                cmd, 0, stdout="{}", stderr="",
            )
        # gh issue create → fake URL with issue #9999
        if cmd[1] == "issue" and cmd[2] == "create":
            return subprocess.CompletedProcess(
                cmd, 0,
                stdout=(
                    "https://github.com/kentonium3/kg-automation/"
                    "issues/9999\n"
                ),
                stderr="",
            )
        # gh issue comment, close, edit, etc. → succeed silently
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    def fake_apply(*args, **kwargs):
        # Raise with a real filename so the helper has a path to file
        # the debt issue against.
        raise FileNotFoundError(
            2, "No such file or directory",
            "docs/design/architecture/missing-doc.md",
        )

    monkeypatch.setattr(run, "apply_routing", fake_apply)

    exit_code = run.main(["--config", str(_config_path(tmp_config))])

    assert exit_code in (1, 2)  # partial / failure status
    signal = _read_tick_signal(tmp_config)
    assert signal["status"] in ("partial", "failure")

    # Post-#348: a REAL issue number is recorded, NOT a placeholder 0.
    assert signal["tick"]["debt_filed"] == [9999], (
        f"expected real debt issue [9999] for missing file; got "
        f"{signal['tick']['debt_filed']}"
    )

    # Error message still recorded for operator visibility.
    assert any(
        "missing file" in err.lower() or "missing-doc.md" in err.lower()
        for err in signal["errors"]
    ), f"expected missing-file marker; got {signal['errors']}"

    # Verify the 3 gh operations happened.
    has_create = any(
        "create" in c and "docs-debt" in c and "missing-doc.md" in " ".join(c)
        for c in gh_calls
    )
    has_comment = any(
        "comment" in c and "8500" in c for c in gh_calls
    )
    has_close = any(
        "close" in c and "8500" in c for c in gh_calls
    )
    assert has_create, (
        f"expected gh issue create with docs-debt + filename; "
        f"got {[' '.join(c) for c in gh_calls]}"
    )
    assert has_comment, (
        f"expected gh issue comment 8500 (audit cross-reference); "
        f"got {[' '.join(c) for c in gh_calls]}"
    )
    assert has_close, (
        f"expected gh issue close 8500 (audit closed); "
        f"got {[' '.join(c) for c in gh_calls]}"
    )


# ---------------------------------------------------------------------------
# Edge case 4: Stuck lock recovery
# ---------------------------------------------------------------------------


def test_stuck_lock_recovery(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic: Any,
) -> None:
    """In-progress audit + NO pending-approval → flagged as stale + recovered.

    Setup:
    - The normal ``doc-audit`` query (no in-progress filter at the gh
      level; we just hand it an issue without the ``status:in-progress``
      label).
    - The dedicated in-progress query (label=doc-audit + label=
      status:in-progress) returns an issue (#9000) whose body does NOT
      reference any pending-approval.
    - The pending-approval query is empty, so the cross-reference
      index is empty → #9000 is unambiguously stale.

    Expectations:
    - Tick signal contains a ``recovered-stale-lock`` marker in errors.
    - A ``gh issue edit ... --remove-label status:in-progress`` call
      was issued for #9000.
    """
    stale = [
        {
            "number": 9000,
            "title": "Doc audit: eee5555 (felix-core)",
            "body": "",
            "labels": [
                {"name": "doc-audit"},
                {"name": "status:in-progress"},
                {"name": "area/felix-core"},
            ],
            "createdAt": "2026-05-20T08:00:00Z",
            "updatedAt": "2026-05-20T08:01:00Z",
        }
    ]
    # The normal doc-audit list should NOT include the in-progress
    # issue (the signal source filters status:in-progress out). The
    # in-progress query (two --label flags) returns the stale issue.
    def list_router(cmd):
        labels = [
            cmd[i + 1] for i, tok in enumerate(cmd)
            if tok == "--label" and i + 1 < len(cmd)
        ]
        if "doc-audit" in labels and "status:in-progress" in labels:
            return _completed(json.dumps(stale))
        if "doc-audit" in labels:
            # The normal scan: no audits emitted (the only audit is
            # the in-progress one).
            return _completed("[]")
        return _completed("[]")

    def fake_run(cmd, *args, **kwargs):
        if not (isinstance(cmd, (list, tuple)) and cmd and cmd[0] == "gh"):
            raise RuntimeError(f"unexpected non-gh subprocess: {cmd!r}")
        cmd = list(cmd)
        calls.append(cmd)
        if len(cmd) >= 3 and cmd[1] == "issue" and cmd[2] == "list":
            return list_router(cmd)
        return _completed("")

    calls: list[list[str]] = []
    monkeypatch.setattr(subprocess, "run", fake_run)

    exit_code = run.main(["--config", str(_config_path(tmp_config))])

    assert exit_code == 0, (
        f"stuck-lock recovery should be a clean recovery, not a failure; "
        f"exit_code={exit_code}"
    )
    signal = _read_tick_signal(tmp_config)
    # Recovery marker must be present.
    assert any(
        "recovered-stale-lock" in err for err in signal["errors"]
    ), f"expected recovered-stale-lock marker; got {signal['errors']}"
    # A label-removal call was issued for #9000.
    label_removals = [
        c for c in calls
        if len(c) >= 5
        and c[1] == "issue"
        and c[2] == "edit"
        and c[3] == "9000"
        and "--remove-label" in c
    ]
    assert label_removals, (
        f"expected remove-label call for stuck lock #9000; got calls={calls!r}"
    )
