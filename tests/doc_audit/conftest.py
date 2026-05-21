"""Pytest bootstrap and shared fixtures for ``tests/doc_audit/``.

WP01 created the sys.path bootstrap. WP02 extends this module with
shared fixtures used by all downstream WPs:

- ``tmp_config`` — synthesizes a ``Config`` whose paths point inside
  ``tmp_path`` (so tests never read/write real driver paths).
- ``mock_gh`` — patches ``subprocess.run`` to return canned ``gh``
  JSON outputs from ``tests/doc_audit/fixtures/gh_responses/``.
- ``mock_anthropic`` — patches ``anthropic.Anthropic`` (when used) to
  return canned LLM response shapes from
  ``tests/doc_audit/fixtures/anthropic_responses/``.
- ``sample_audit_issue`` — representative ``AuditIssue`` instance.
- ``sample_signal_gh_issue`` — representative ``Signal`` for a GH
  issue of kind ``doc_audit``.
- ``sample_signal_drift_event`` — representative ``Signal`` for a
  drift event.

Per mission #343 WP01: the helpers lifted out of
``scripts/openclaw/agents/felix-doc-auditor/`` are now under
``scripts/doc_audit/helpers/`` and expose importable library
functions (``process_events``, ``route_audit_decision``, plus
supporting types) alongside their CLI ``main()`` wrappers.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import pytest

# ---------------------------------------------------------------------------
# sys.path bootstrap (from WP01)
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))


# Imports below depend on the sys.path bootstrap above.
from doc_audit.config import Config, load_config  # noqa: E402
from doc_audit.data_model import (  # noqa: E402
    AuditIssue,
    Signal,
)


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
GH_FIXTURES_DIR = FIXTURES_DIR / "gh_responses"
ANTHROPIC_FIXTURES_DIR = FIXTURES_DIR / "anthropic_responses"


# ---------------------------------------------------------------------------
# tmp_config — a Config rooted under tmp_path
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_config(tmp_path: Path) -> Config:
    """Return a ``Config`` whose ``[paths]`` point inside ``tmp_path``.

    Writes a temp ``config.toml`` with the same shape as the in-tree
    default, but every filesystem path is rebound to a subdirectory
    of ``tmp_path``. The API key is a deterministic fake.
    """

    api_key_path = tmp_path / "anthropic.key"
    api_key_path.write_text("test-api-key-not-real\n", encoding="utf-8")

    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()

    activity_log_dir = tmp_path / "activity"
    activity_log_dir.mkdir()

    signal_map = tmp_path / "signal-to-doc-map.json"
    signal_map.write_text("{}", encoding="utf-8")
    doc_map = tmp_path / "doc-domain-map.json"
    doc_map.write_text("{}", encoding="utf-8")

    drift_events = tmp_path / "drift-events.jsonl"
    drift_events.write_text("", encoding="utf-8")
    drift_cursor = tmp_path / ".drift-events.cursor"
    drift_unmapped = tmp_path / "unmapped-events.jsonl"
    tick_signal = tmp_path / "last-tick.json"

    toml_body = f"""
[llm]
model = "claude-haiku-4-5"
api_key_path = "{api_key_path}"
max_tokens = 2048

[paths]
prompts_dir = "{prompts_dir}"
drift_events = "{drift_events}"
drift_cursor = "{drift_cursor}"
drift_unmapped = "{drift_unmapped}"
signal_to_doc_map = "{signal_map}"
doc_domain_map = "{doc_map}"
activity_log_dir = "{activity_log_dir}"
tick_signal_path = "{tick_signal}"

[signals]
sources = ["gh_issue", "drift_event"]

[github]
repo = "kentonium3/kg-automation"
bot_identity = "kg-felix-bot"
"""
    config_path = tmp_path / "config.toml"
    config_path.write_text(toml_body, encoding="utf-8")

    return load_config(config_path)


# ---------------------------------------------------------------------------
# mock_gh — patch subprocess.run to return canned gh JSON
# ---------------------------------------------------------------------------


def _load_gh_fixture(name: str) -> str:
    fixture = GH_FIXTURES_DIR / f"{name}.json"
    if not fixture.is_file():
        raise FileNotFoundError(
            f"gh fixture missing: {fixture} "
            "(add a JSON file under tests/doc_audit/fixtures/gh_responses/)"
        )
    return fixture.read_text(encoding="utf-8")


@pytest.fixture
def mock_gh(monkeypatch: pytest.MonkeyPatch) -> Callable[[str, str], None]:
    """Patch ``subprocess.run`` to return canned ``gh`` output.

    Returns a registrar function. Tests call
    ``mock_gh("issue-list-doc-audit", "issue_list_doc_audit_basic")``
    to bind the *command-key* (a stable name derived from the
    first arguments of ``gh``) to a fixture filename.

    Any unregistered call surfaces a clear ``RuntimeError`` rather
    than silently shelling out.
    """

    routes: dict[str, str] = {}

    def register(command_key: str, fixture_name: str) -> None:
        routes[command_key] = fixture_name

    def fake_run(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not (isinstance(cmd, (list, tuple)) and cmd and cmd[0] == "gh"):
            raise RuntimeError(
                f"mock_gh only handles 'gh ...' calls, got: {cmd!r}"
            )
        key = "-".join(str(part) for part in cmd[1:4])
        if key not in routes:
            raise RuntimeError(
                f"mock_gh has no fixture bound for key {key!r}; "
                f"available: {sorted(routes)}"
            )
        stdout = _load_gh_fixture(routes[key])
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout=stdout, stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    return register


# ---------------------------------------------------------------------------
# mock_anthropic — patch anthropic.Anthropic to return canned responses
# ---------------------------------------------------------------------------


def _load_anthropic_fixture(name: str) -> dict[str, Any]:
    fixture = ANTHROPIC_FIXTURES_DIR / f"{name}.json"
    if not fixture.is_file():
        raise FileNotFoundError(
            f"anthropic fixture missing: {fixture} "
            "(add JSON under tests/doc_audit/fixtures/anthropic_responses/)"
        )
    return json.loads(fixture.read_text(encoding="utf-8"))


class _FakeAnthropicResponse:
    """Minimal response shape compatible with ``response.content[0].text``."""

    def __init__(self, payload: dict[str, Any]) -> None:
        text = payload.get("text", "")

        class _Block:
            def __init__(self, value: str) -> None:
                self.text = value

        self.content = [_Block(text)]
        self.usage = payload.get(
            "usage",
            {
                "input_tokens": 0,
                "cache_read_input_tokens": 0,
                "output_tokens": 0,
            },
        )
        self.id = payload.get("id", "msg_fake")
        self.model = payload.get("model", "claude-haiku-4-5")


class _FakeAnthropicMessages:
    def __init__(self, fixture_loader: Callable[[str], dict[str, Any]]) -> None:
        self._loader = fixture_loader
        self.calls: list[dict[str, Any]] = []
        self.next_fixture: str = "tier_classification_tier_a"

    def create(self, **kwargs: Any) -> _FakeAnthropicResponse:
        self.calls.append(kwargs)
        return _FakeAnthropicResponse(self._loader(self.next_fixture))


class _FakeAnthropicClient:
    def __init__(self, fixture_loader: Callable[[str], dict[str, Any]]) -> None:
        self.messages = _FakeAnthropicMessages(fixture_loader)


@pytest.fixture
def mock_anthropic(
    monkeypatch: pytest.MonkeyPatch,
) -> _FakeAnthropicClient:
    """Return a fake Anthropic client AND patch the SDK constructor.

    Patches ``anthropic.Anthropic`` so any downstream code path that
    does ``import anthropic; client = anthropic.Anthropic(api_key=...)``
    transparently gets the fake client this fixture returns. This
    prevents tests from accidentally instantiating a real client
    (which would attempt network I/O against ``api.anthropic.com``).

    When the ``anthropic`` SDK is not installed in the test env (the
    package is a WP04 dependency), we register a minimal stub module
    in ``sys.modules`` so the patched ``anthropic.Anthropic`` symbol
    still resolves. WP04 code that imports ``anthropic`` will then
    pick up our stub at import time; downstream WPs that need the
    real SDK in production must declare the dependency in
    ``requirements.txt``.

    Tests change which fixture the next ``messages.create`` returns
    by setting ``mock_anthropic.messages.next_fixture = "name"``. The
    name resolves to
    ``tests/doc_audit/fixtures/anthropic_responses/<name>.json``.
    """

    fake_client = _FakeAnthropicClient(_load_anthropic_fixture)

    try:
        import anthropic as _anthropic_mod  # type: ignore[import-not-found]
    except ImportError:
        # The real SDK is not installed in this test env. Register a
        # stub module so downstream `import anthropic` works, then
        # patch the constructor on it.
        import types

        _anthropic_mod = types.ModuleType("anthropic")
        monkeypatch.setitem(sys.modules, "anthropic", _anthropic_mod)

    monkeypatch.setattr(
        _anthropic_mod,
        "Anthropic",
        lambda *args, **kwargs: fake_client,
        raising=False,
    )

    return fake_client


# ---------------------------------------------------------------------------
# Sample dataclass instances
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_audit_issue() -> AuditIssue:
    """Representative ``AuditIssue`` (E-002) for downstream tests."""

    return AuditIssue(
        issue_number=4242,
        title="Doc audit: abc1234 (felix-core)",
        is_weekly=False,
        triggering_sha="abc1234",
        area_labels=["area/felix-core"],
        in_scope_docs=[
            "docs/constitution/FELIX-CONSTITUTION.md",
            "docs/constitution/AGENT-REGISTRY.md",
        ],
        lock_acquired_at_utc=None,
    )


@pytest.fixture
def sample_signal_gh_issue() -> Signal:
    """Representative ``Signal`` (E-001) for a GH ``doc_audit`` issue."""

    return Signal(
        id="gh-issue:4242",
        source="gh_issue",
        kind="doc_audit",
        priority=20,
        payload={
            "issue_number": 4242,
            "title": "Doc audit: abc1234 (felix-core)",
            "body": "Triggered by commit abc1234 on main.",
            "labels": ["doc-audit", "area/felix-core"],
            "area_labels": ["area/felix-core"],
        },
        created_utc="2026-05-20T16:00:00Z",
    )


@pytest.fixture
def sample_signal_drift_event() -> Signal:
    """Representative ``Signal`` (E-001) for a drift event."""

    return Signal(
        id="drift:openclaw-cron.txt:2026-05-20T15:00:00Z",
        source="drift_event",
        kind="baseline_drift",
        priority=40,
        payload={
            "timestamp": "2026-05-20T15:00:00Z",
            "source": "audit.sh",
            "event_type": "baseline_drift",
            "baseline_name": "openclaw-cron.txt",
            "diff_b64": "ZGlmZi1nb2VzLWhlcmU=",
        },
        created_utc="2026-05-20T15:00:00Z",
    )
