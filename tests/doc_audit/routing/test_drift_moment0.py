"""Unit tests for the shared Moment 0 routing helper.

Mission ``moment0-integration-fix-01KS8XRM`` WP01 (T004): full coverage
of :func:`doc_audit.routing.drift_moment0.route_drift_event` and the
private helpers it orchestrates. Tests mirror the verdict-path coverage
the pre-refactor ``test_handle_drift_events.py`` had for
``_handle_moment0_event``, plus new assertions for the public
:class:`RoutingOutcome` shape (``retry_count`` + ``latency_ms``
populated).

All tests mock the LLM client and subprocess.run; no live Anthropic or
GitHub calls. Target coverage on ``routing/drift_moment0.py`` is ≥85%.

Verdict paths exercised:
- ``NO_CHANGE_NEEDED``  → no GitHub side effect; ledger row only
- ``JUDGMENT_REQUIRED`` → file judgment issue + ledger row
- ``PROPOSED_EDIT`` + tier_a → auto-commit + ledger row
- ``PROPOSED_EDIT`` + tier_b → file pending-approval issue + ledger row
- ``PROPOSED_EDIT`` + judgment → file debt-style issue + ledger row
- ``PROPOSED_EDIT`` + translator rejection → demoted to judgment issue
- DriftInterpretationError propagation (retry exhausted) → raised to caller

Additional coverage:
- ``RoutingOutcome`` field defaults + post-route population
- ``_parse_issue_number`` regex extraction
- ``_now_utc_iso`` format
- Empty `decode_diff` paths
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from doc_audit.routing import drift_moment0
from doc_audit.routing.drift_moment0 import (
    RoutingOutcome,
    _decode_diff,
    _now_utc_iso,
    _parse_issue_number,
    _resolve_repo_root,
    route_drift_event,
)


# ---------------------------------------------------------------------------
# Helpers — stub Mapping + stub Config
# ---------------------------------------------------------------------------


def _make_mapping():
    """Build a minimal Mapping matching the openclaw-cron-drift fixture."""
    # Import lazily to avoid forcing handle_drift_events to load before
    # the test runner has a chance to patch its dependencies.
    from doc_audit.helpers.handle_drift_events import Mapping

    return Mapping(
        id="openclaw-cron-drift",
        match={
            "source": "audit.sh",
            "baseline_name": "openclaw-cron.txt",
        },
        doc_targets=[
            "docs/design/architecture/data/service-inventory.json",
        ],
        rationale="OpenClaw cron drift implies service inventory may need updates.",
        issue_title_prefix="[doc-audit] openclaw-cron drift",
        issue_labels=["P3-candidate", "spec: brief", "area/felix-core"],
    )


class _StubDriftIntCfg:
    """Minimal stand-in for ``DriftInterpretationConfig``."""

    def __init__(
        self,
        *,
        ledger_path: Path,
        model: str = "claude-haiku-4-5-test",
        api_key_path: str = "/tmp/fake-key",
        timeout_seconds: int = 30,
        confidence_threshold: float = 0.80,
        enabled: bool = True,
    ) -> None:
        self.ledger_path = str(ledger_path)
        self.model = model
        self.api_key_path = api_key_path
        self.timeout_seconds = timeout_seconds
        self.confidence_threshold = confidence_threshold
        self.enabled = enabled


class _StubConfig:
    def __init__(self, drift_interpretation: _StubDriftIntCfg) -> None:
        self.drift_interpretation = drift_interpretation


def _make_config(tmp_path: Path) -> _StubConfig:
    return _StubConfig(
        _StubDriftIntCfg(ledger_path=tmp_path / "ledger.jsonl")
    )


def _make_event(**overrides):
    base = {
        "source": "audit.sh",
        "baseline_name": "openclaw-cron.txt",
        "timestamp": "2026-05-22T10:00:00Z",
        "diff": "@@ -1,1 +1,1 @@\n-old line\n+new line\n",
    }
    base.update(overrides)
    return base


def _make_verdict(verdict_value: str, **kwargs):
    """Build a fake :class:`DriftVerdict`."""
    from doc_audit.judgment.drift_interpretation import DriftVerdict

    base = {
        "verdict": verdict_value,
        "confidence": 0.92,
        "rationale": "stub-rationale",
    }
    if verdict_value == "PROPOSED_EDIT":
        base["proposed_edit"] = kwargs.pop(
            "proposed_edit",
            {
                "doc_path": "docs/design/architecture/data/service-inventory.json",
                "current_value": "old line",
                "proposed_value": "new line",
            },
        )
    if verdict_value == "JUDGMENT_REQUIRED":
        base["question"] = kwargs.pop("question", "Was this drift intentional?")
    base.update(kwargs)
    return DriftVerdict(**base)


# ---------------------------------------------------------------------------
# RoutingOutcome dataclass — shape + defaults
# ---------------------------------------------------------------------------


def test_routing_outcome_defaults_match_documented_shape():
    """RoutingOutcome accepts only the required ``outcome`` field."""
    outcome = RoutingOutcome(outcome="auto_closed")
    assert outcome.outcome == "auto_closed"
    assert outcome.tier_classification_outcome is None
    assert outcome.github_issue_number is None
    assert outcome.success is True
    assert outcome.error is None
    assert outcome.retry_count == 0
    assert outcome.latency_ms == 0


def test_routing_outcome_is_frozen():
    """RoutingOutcome is immutable per data-model.md."""
    outcome = RoutingOutcome(outcome="issue_filed")
    with pytest.raises(Exception):
        outcome.outcome = "auto_committed"  # type: ignore[misc]


def test_routing_outcome_populates_retry_count_and_latency_ms():
    outcome = RoutingOutcome(outcome="retry_exhausted", retry_count=3, latency_ms=4200)
    assert outcome.retry_count == 3
    assert outcome.latency_ms == 4200


# ---------------------------------------------------------------------------
# _parse_issue_number — regex extraction
# ---------------------------------------------------------------------------


def test_parse_issue_number_extracts_from_url():
    url = "https://github.com/kentonium3/kg-automation/issues/12345\n"
    assert _parse_issue_number(url) == 12345


def test_parse_issue_number_returns_none_when_missing():
    assert _parse_issue_number("not a url") is None
    assert _parse_issue_number("") is None
    assert _parse_issue_number(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _now_utc_iso — Z-suffixed ISO 8601
# ---------------------------------------------------------------------------


def test_now_utc_iso_ends_with_z_and_parses():
    from datetime import datetime

    value = _now_utc_iso()
    assert value.endswith("Z")
    # Z-suffix is convertible to a parseable form.
    datetime.fromisoformat(value[:-1])


# ---------------------------------------------------------------------------
# _decode_diff
# ---------------------------------------------------------------------------


def test_decode_diff_returns_plain_diff():
    assert _decode_diff({"diff": "raw diff"}) == "raw diff"


def test_decode_diff_decodes_base64():
    # base64("hello") = "aGVsbG8="
    assert _decode_diff({"diff_b64": "aGVsbG8="}) == "hello"


def test_decode_diff_handles_bad_base64():
    # ``!!! not valid base64 !!!`` produces a binascii error inside the
    # base64 module — covers the except branch.
    assert (
        _decode_diff({"diff_b64": "!!! not valid base64 !!!"})
        == "<diff decode failed>"
    )


def test_decode_diff_empty_event_returns_empty_string():
    assert _decode_diff({}) == ""


# ---------------------------------------------------------------------------
# _resolve_repo_root — falls back to cwd on git failure
# ---------------------------------------------------------------------------


def test_resolve_repo_root_falls_back_on_git_failure(monkeypatch):
    import subprocess as sp

    def boom(*args, **kwargs):
        raise sp.CalledProcessError(returncode=128, cmd=["git"], stderr="not a repo")

    monkeypatch.setattr(drift_moment0.subprocess, "run", boom)
    root = _resolve_repo_root()
    assert isinstance(root, Path)


def test_resolve_repo_root_returns_git_toplevel(monkeypatch, tmp_path):
    import subprocess as sp

    fake = sp.CompletedProcess(
        args=["git", "rev-parse", "--show-toplevel"],
        returncode=0,
        stdout=str(tmp_path) + "\n",
        stderr="",
    )
    monkeypatch.setattr(drift_moment0.subprocess, "run", lambda *a, **k: fake)
    assert _resolve_repo_root() == tmp_path.resolve()


# ---------------------------------------------------------------------------
# route_drift_event — verdict-path coverage
# ---------------------------------------------------------------------------


def _setup_real_target(tmp_path: Path) -> Path:
    """Create a fake repo root with the doc target file so Tier A appliers
    have something to substitute against.
    """
    fake_repo = tmp_path / "repo"
    target_rel = "docs/design/architecture/data/service-inventory.json"
    target_abs = fake_repo / target_rel
    target_abs.parent.mkdir(parents=True, exist_ok=True)
    target_abs.write_text("before old line after\nunrelated line\n", encoding="utf-8")
    return fake_repo


def test_route_drift_event_no_change_needed_writes_ledger_only(
    tmp_path: Path, monkeypatch
):
    """NO_CHANGE_NEEDED → no GitHub artifact, ledger row only, retry_count=0."""
    config = _make_config(tmp_path)
    ledger_path = Path(config.drift_interpretation.ledger_path)

    monkeypatch.setattr(
        "doc_audit.judgment.drift_interpretation.interpret",
        lambda *a, **k: _make_verdict("NO_CHANGE_NEEDED"),
    )

    forbidden = mock.MagicMock(
        side_effect=AssertionError("NO_CHANGE_NEEDED must not invoke subprocess")
    )
    monkeypatch.setattr(drift_moment0.subprocess, "run", forbidden)

    outcome = route_drift_event(
        event=_make_event(),
        mapping=_make_mapping(),
        config=config,
        client=object(),
        ledger_path=ledger_path,
        repo="kentonium3/kg-automation",
        event_id="0:2026-05-22T10:00:00Z",
        timestamp_utc="2026-05-22T10:00:00Z",
        cursor_line=0,
        repo_root=tmp_path,
        dry_run=False,
    )

    assert outcome.outcome == "auto_closed"
    assert outcome.tier_classification_outcome is None
    assert outcome.github_issue_number is None
    assert outcome.retry_count == 0
    assert outcome.latency_ms >= 0

    rows = ledger_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 1
    row = json.loads(rows[0])
    assert row["verdict"] == "NO_CHANGE_NEEDED"
    assert row["outcome"] == "auto_closed"
    assert row["confidence"] == 0.92


def test_route_drift_event_judgment_required_files_issue(
    tmp_path: Path, monkeypatch
):
    """JUDGMENT_REQUIRED → file [doc-audit] issue + ledger row."""
    config = _make_config(tmp_path)
    ledger_path = Path(config.drift_interpretation.ledger_path)
    captured: dict[str, str] = {}

    def fake_run(cmd, *args, **kwargs):
        if "--body" in cmd:
            captured["body"] = cmd[cmd.index("--body") + 1]
        return mock.MagicMock(
            returncode=0,
            stdout="https://github.com/kentonium3/kg-automation/issues/777\n",
            stderr="",
        )

    monkeypatch.setattr(drift_moment0.subprocess, "run", fake_run)
    monkeypatch.setattr(
        "doc_audit.judgment.drift_interpretation.interpret",
        lambda *a, **k: _make_verdict(
            "JUDGMENT_REQUIRED",
            confidence=0.55,
            question="Is the new openclaw-cron schedule correct?",
        ),
    )

    outcome = route_drift_event(
        event=_make_event(),
        mapping=_make_mapping(),
        config=config,
        client=object(),
        ledger_path=ledger_path,
        repo="kentonium3/kg-automation",
        event_id="0:2026-05-22T10:00:00Z",
        timestamp_utc="2026-05-22T10:00:00Z",
        cursor_line=0,
        repo_root=tmp_path,
        dry_run=False,
    )

    assert outcome.outcome == "issue_filed"
    assert outcome.github_issue_number == 777
    row = json.loads(ledger_path.read_text(encoding="utf-8").strip().splitlines()[0])
    assert row["verdict"] == "JUDGMENT_REQUIRED"
    assert row["outcome"] == "issue_filed"
    assert row["github_issue_number"] == 777
    assert "Is the new openclaw-cron schedule" in captured["body"]


def test_route_drift_event_proposed_edit_tier_a_auto_commits(
    tmp_path: Path, monkeypatch
):
    """PROPOSED_EDIT + tier_a → auto-commit + ledger row."""
    config = _make_config(tmp_path)
    ledger_path = Path(config.drift_interpretation.ledger_path)
    fake_repo = _setup_real_target(tmp_path)

    monkeypatch.setattr(
        "doc_audit.judgment.drift_interpretation.interpret",
        lambda *a, **k: _make_verdict("PROPOSED_EDIT"),
    )

    from doc_audit.data_model import EditTier

    monkeypatch.setattr(
        "doc_audit.judgment.tier_classification.classify",
        lambda *a, **k: (EditTier.TIER_A, "tier_a rationale", None),
    )

    # Mock subprocess.run (git add / git commit) — no real git mutations.
    monkeypatch.setattr(
        drift_moment0.subprocess,
        "run",
        lambda *a, **k: mock.MagicMock(returncode=0, stdout="", stderr=""),
    )

    outcome = route_drift_event(
        event=_make_event(),
        mapping=_make_mapping(),
        config=config,
        client=object(),
        ledger_path=ledger_path,
        repo="kentonium3/kg-automation",
        event_id="0:2026-05-22T10:00:00Z",
        timestamp_utc="2026-05-22T10:00:00Z",
        cursor_line=0,
        repo_root=fake_repo,
        dry_run=False,
    )

    assert outcome.outcome == "auto_committed"
    assert outcome.tier_classification_outcome == "tier_a"
    # The target file was actually mutated by the applier.
    target = (
        fake_repo
        / "docs/design/architecture/data/service-inventory.json"
    )
    assert "new line" in target.read_text(encoding="utf-8")

    row = json.loads(ledger_path.read_text(encoding="utf-8").strip().splitlines()[0])
    assert row["verdict"] == "PROPOSED_EDIT"
    assert row["outcome"] == "auto_committed"
    assert row["tier_classification_outcome"] == "tier_a"


def test_route_drift_event_proposed_edit_tier_b_files_pending_approval(
    tmp_path: Path, monkeypatch
):
    """PROPOSED_EDIT + tier_b → pending approval issue."""
    config = _make_config(tmp_path)
    ledger_path = Path(config.drift_interpretation.ledger_path)
    fake_repo = _setup_real_target(tmp_path)

    monkeypatch.setattr(
        "doc_audit.judgment.drift_interpretation.interpret",
        lambda *a, **k: _make_verdict("PROPOSED_EDIT"),
    )

    from doc_audit.data_model import EditTier

    monkeypatch.setattr(
        "doc_audit.judgment.tier_classification.classify",
        lambda *a, **k: (EditTier.TIER_B, "tier_b rationale", None),
    )

    monkeypatch.setattr(
        drift_moment0.subprocess,
        "run",
        lambda *a, **k: mock.MagicMock(
            returncode=0,
            stdout="https://github.com/kentonium3/kg-automation/issues/555\n",
            stderr="",
        ),
    )

    outcome = route_drift_event(
        event=_make_event(),
        mapping=_make_mapping(),
        config=config,
        client=object(),
        ledger_path=ledger_path,
        repo="kentonium3/kg-automation",
        event_id="0:2026-05-22T10:00:00Z",
        timestamp_utc="2026-05-22T10:00:00Z",
        cursor_line=0,
        repo_root=fake_repo,
        dry_run=False,
    )

    assert outcome.outcome == "pr_filed"
    assert outcome.tier_classification_outcome == "tier_b"
    assert outcome.github_issue_number == 555
    row = json.loads(ledger_path.read_text(encoding="utf-8").strip().splitlines()[0])
    assert row["outcome"] == "pr_filed"
    assert row["tier_classification_outcome"] == "tier_b"


def test_route_drift_event_proposed_edit_judgment_files_debt_issue(
    tmp_path: Path, monkeypatch
):
    """PROPOSED_EDIT + tier_classification=JUDGMENT → debt-style issue."""
    config = _make_config(tmp_path)
    ledger_path = Path(config.drift_interpretation.ledger_path)
    fake_repo = _setup_real_target(tmp_path)

    monkeypatch.setattr(
        "doc_audit.judgment.drift_interpretation.interpret",
        lambda *a, **k: _make_verdict("PROPOSED_EDIT"),
    )

    from doc_audit.data_model import EditTier

    monkeypatch.setattr(
        "doc_audit.judgment.tier_classification.classify",
        lambda *a, **k: (EditTier.JUDGMENT, "judgment rationale", None),
    )

    monkeypatch.setattr(
        drift_moment0.subprocess,
        "run",
        lambda *a, **k: mock.MagicMock(
            returncode=0,
            stdout="https://github.com/kentonium3/kg-automation/issues/888\n",
            stderr="",
        ),
    )

    outcome = route_drift_event(
        event=_make_event(),
        mapping=_make_mapping(),
        config=config,
        client=object(),
        ledger_path=ledger_path,
        repo="kentonium3/kg-automation",
        event_id="0:2026-05-22T10:00:00Z",
        timestamp_utc="2026-05-22T10:00:00Z",
        cursor_line=0,
        repo_root=fake_repo,
        dry_run=False,
    )

    assert outcome.outcome == "issue_filed"
    assert outcome.tier_classification_outcome == "judgment"
    assert outcome.github_issue_number == 888


def test_route_drift_event_proposed_edit_translator_rejection_demoted(
    tmp_path: Path, monkeypatch
):
    """PROPOSED_EDIT with out-of-set ``doc_path`` is demoted to judgment
    when the translator rejects it.

    Because ``drift_interpretation.interpret`` already enforces
    in-set ``doc_path``, we simulate the defensive demotion via a
    proposed_edit whose ``current_value`` is empty (translator
    requires non-empty string types).
    """
    config = _make_config(tmp_path)
    ledger_path = Path(config.drift_interpretation.ledger_path)

    # Build a verdict that will pass interpret-level validation but
    # fail translator-level validation. drift_to_proposed_edit raises
    # ValueError when current_value isn't a string. Force the translator
    # to raise directly via monkeypatch — simulates the regression path.
    monkeypatch.setattr(
        "doc_audit.judgment.drift_interpretation.interpret",
        lambda *a, **k: _make_verdict("PROPOSED_EDIT"),
    )

    def _reject(*a, **k):
        raise ValueError("simulated translator rejection (out-of-set doc_path)")

    monkeypatch.setattr(
        "doc_audit.routing.drift_to_proposed_edit.build", _reject
    )

    monkeypatch.setattr(
        drift_moment0.subprocess,
        "run",
        lambda *a, **k: mock.MagicMock(
            returncode=0,
            stdout="https://github.com/kentonium3/kg-automation/issues/999\n",
            stderr="",
        ),
    )

    outcome = route_drift_event(
        event=_make_event(),
        mapping=_make_mapping(),
        config=config,
        client=object(),
        ledger_path=ledger_path,
        repo="kentonium3/kg-automation",
        event_id="0:2026-05-22T10:00:00Z",
        timestamp_utc="2026-05-22T10:00:00Z",
        cursor_line=0,
        repo_root=tmp_path,
        dry_run=False,
    )

    assert outcome.outcome == "issue_filed"
    assert outcome.tier_classification_outcome == "judgment"
    assert outcome.github_issue_number == 999


def test_route_drift_event_unexpected_verdict_value_demoted(
    tmp_path: Path, monkeypatch
):
    """Defense-in-depth: an unknown verdict value lands in judgment."""
    config = _make_config(tmp_path)
    ledger_path = Path(config.drift_interpretation.ledger_path)

    # Build a DriftVerdict with an unexpected value by bypassing the
    # interpret() validation gate. We construct directly so the
    # branch in _route_verdict for the "neither NCN/JR/PE" path is hit.
    from doc_audit.judgment.drift_interpretation import DriftVerdict

    weird_verdict = DriftVerdict(
        verdict="EXTRATERRESTRIAL",
        confidence=0.50,
        rationale="from outer space",
    )

    monkeypatch.setattr(
        "doc_audit.judgment.drift_interpretation.interpret",
        lambda *a, **k: weird_verdict,
    )
    monkeypatch.setattr(
        drift_moment0.subprocess,
        "run",
        lambda *a, **k: mock.MagicMock(
            returncode=0,
            stdout="https://github.com/kentonium3/kg-automation/issues/4242\n",
            stderr="",
        ),
    )

    # Ledger append will reject "EXTRATERRESTRIAL" as not in VALID_VERDICTS,
    # but the helper's ledger writer logs+swallows ValueErrors so the
    # routing still returns; the routing outcome itself is "issue_filed".
    outcome = route_drift_event(
        event=_make_event(),
        mapping=_make_mapping(),
        config=config,
        client=object(),
        ledger_path=ledger_path,
        repo="kentonium3/kg-automation",
        event_id="0:2026-05-22T10:00:00Z",
        timestamp_utc="2026-05-22T10:00:00Z",
        cursor_line=0,
        repo_root=tmp_path,
        dry_run=False,
    )

    assert outcome.outcome == "issue_filed"
    assert outcome.github_issue_number == 4242


def test_route_drift_event_propagates_drift_interpretation_error(
    tmp_path: Path, monkeypatch
):
    """:class:`DriftInterpretationError` propagates to the caller (retry
    exhausted handling lives outside the helper per
    ``contracts/routing-helper.md``)."""
    from doc_audit.judgment.drift_interpretation import DriftInterpretationError

    config = _make_config(tmp_path)
    ledger_path = Path(config.drift_interpretation.ledger_path)

    def _raise(*a, **k):
        raise DriftInterpretationError("retry exhausted", attempts=3)

    monkeypatch.setattr(
        "doc_audit.judgment.drift_interpretation.interpret", _raise
    )

    # subprocess.run should NOT be called — the helper bails before the
    # ledger or any GitHub side effect.
    monkeypatch.setattr(
        drift_moment0.subprocess,
        "run",
        mock.MagicMock(
            side_effect=AssertionError("subprocess.run must not be called")
        ),
    )

    with pytest.raises(DriftInterpretationError) as exc:
        route_drift_event(
            event=_make_event(),
            mapping=_make_mapping(),
            config=config,
            client=object(),
            ledger_path=ledger_path,
            repo="kentonium3/kg-automation",
            event_id="0:2026-05-22T10:00:00Z",
            timestamp_utc="2026-05-22T10:00:00Z",
            cursor_line=0,
            repo_root=tmp_path,
            dry_run=False,
        )

    assert exc.value.attempts == 3
    # No ledger row written when the helper raises (caller writes the
    # RETRY_EXHAUSTED row from its catch block).
    assert not ledger_path.exists()


def test_route_drift_event_dry_run_skips_ledger_and_gh(
    tmp_path: Path, monkeypatch
):
    """dry_run=True skips both GitHub side-effects and ledger writes."""
    config = _make_config(tmp_path)
    ledger_path = Path(config.drift_interpretation.ledger_path)

    monkeypatch.setattr(
        "doc_audit.judgment.drift_interpretation.interpret",
        lambda *a, **k: _make_verdict(
            "JUDGMENT_REQUIRED", confidence=0.50, question="ambiguous"
        ),
    )

    forbidden = mock.MagicMock(
        side_effect=AssertionError("subprocess.run must not be called in dry-run")
    )
    monkeypatch.setattr(drift_moment0.subprocess, "run", forbidden)

    outcome = route_drift_event(
        event=_make_event(),
        mapping=_make_mapping(),
        config=config,
        client=object(),
        ledger_path=ledger_path,
        repo="kentonium3/kg-automation",
        event_id="0:2026-05-22T10:00:00Z",
        timestamp_utc="2026-05-22T10:00:00Z",
        cursor_line=0,
        repo_root=tmp_path,
        dry_run=True,
    )

    # Dry-run path returns the outcome but does NOT write the ledger row.
    assert outcome.outcome == "issue_filed"
    assert not ledger_path.exists()


def test_route_drift_event_missing_doc_target_yields_truncation_strategy(
    tmp_path: Path, monkeypatch
):
    """When a doc_target file is missing, the context records a
    ``missing_file`` truncation strategy and routing still completes.
    """
    config = _make_config(tmp_path)
    ledger_path = Path(config.drift_interpretation.ledger_path)

    captured_context: dict[str, object] = {}

    def fake_interpret(client, context, **kwargs):
        captured_context["context"] = context
        return _make_verdict("NO_CHANGE_NEEDED")

    monkeypatch.setattr(
        "doc_audit.judgment.drift_interpretation.interpret", fake_interpret
    )

    outcome = route_drift_event(
        event=_make_event(),
        mapping=_make_mapping(),
        config=config,
        client=object(),
        ledger_path=ledger_path,
        repo="kentonium3/kg-automation",
        event_id="0:2026-05-22T10:00:00Z",
        timestamp_utc="2026-05-22T10:00:00Z",
        cursor_line=0,
        repo_root=tmp_path / "does-not-exist",
        dry_run=False,
    )

    assert outcome.outcome == "auto_closed"
    ctx = captured_context["context"]
    assert ctx.doc_targets[0].truncation_strategy == "missing_file"
    assert ctx.doc_targets[0].truncated is True


def test_route_drift_event_latency_ms_populated(
    tmp_path: Path, monkeypatch
):
    """retry_count + latency_ms are populated on the returned RoutingOutcome."""
    config = _make_config(tmp_path)
    ledger_path = Path(config.drift_interpretation.ledger_path)

    monkeypatch.setattr(
        "doc_audit.judgment.drift_interpretation.interpret",
        lambda *a, **k: _make_verdict("NO_CHANGE_NEEDED"),
    )

    outcome = route_drift_event(
        event=_make_event(),
        mapping=_make_mapping(),
        config=config,
        client=object(),
        ledger_path=ledger_path,
        repo="kentonium3/kg-automation",
        event_id="0:2026-05-22T10:00:00Z",
        timestamp_utc="2026-05-22T10:00:00Z",
        cursor_line=0,
        repo_root=tmp_path,
        dry_run=False,
    )

    assert outcome.retry_count == 0
    assert outcome.latency_ms >= 0
    # Sanity: the ledger row should also carry the same latency.
    row = json.loads(ledger_path.read_text(encoding="utf-8").strip().splitlines()[0])
    assert row["latency_ms"] == outcome.latency_ms


def test_route_drift_event_ledger_failure_does_not_raise(
    tmp_path: Path, monkeypatch
):
    """Ledger append failures are logged but never re-raised (FR-010 from #362)."""
    config = _make_config(tmp_path)
    # Point ledger_path at a directory we cannot write into. The helper
    # is supposed to log and continue, not raise.
    ledger_path = tmp_path / "nonexistent"  # parent gets created by drift_ledger
    config.drift_interpretation.ledger_path = str(ledger_path / "ledger.jsonl")

    monkeypatch.setattr(
        "doc_audit.judgment.drift_interpretation.interpret",
        lambda *a, **k: _make_verdict("NO_CHANGE_NEEDED"),
    )

    # Force the ledger append to raise OSError.
    def _boom(*a, **k):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(
        "doc_audit.output.drift_ledger.append", _boom
    )

    outcome = route_drift_event(
        event=_make_event(),
        mapping=_make_mapping(),
        config=config,
        client=object(),
        ledger_path=Path(config.drift_interpretation.ledger_path),
        repo="kentonium3/kg-automation",
        event_id="0:2026-05-22T10:00:00Z",
        timestamp_utc="2026-05-22T10:00:00Z",
        cursor_line=0,
        repo_root=tmp_path,
        dry_run=False,
    )

    # Helper still returned a valid outcome despite the ledger failure.
    assert outcome.outcome == "auto_closed"


def test_file_judgment_issue_dry_run_no_subprocess(monkeypatch):
    """Dry-run path of the judgment-issue filer never invokes subprocess."""
    from doc_audit.routing.drift_moment0 import _file_judgment_issue

    forbidden = mock.MagicMock(side_effect=AssertionError("no subprocess"))
    monkeypatch.setattr(drift_moment0.subprocess, "run", forbidden)
    ok, output, issue_number = _file_judgment_issue(
        event=_make_event(),
        mapping=_make_mapping(),
        question="why?",
        rationale="because",
        repo="x/y",
        dry_run=True,
    )
    assert ok is True
    assert "[dry-run]" in output
    assert issue_number is None


def test_file_tier_b_pending_approval_dry_run_no_subprocess(monkeypatch):
    """Dry-run path of the tier-b filer never invokes subprocess."""
    from doc_audit.data_model import ProposedEdit
    from doc_audit.routing.drift_moment0 import _file_tier_b_pending_approval

    forbidden = mock.MagicMock(side_effect=AssertionError("no subprocess"))
    monkeypatch.setattr(drift_moment0.subprocess, "run", forbidden)

    edit = ProposedEdit(
        doc_path="docs/x.md",
        change_type="drift_derived",
        current_value="old",
        proposed_value="new",
        evidence_source="drift-event:baseline:0:T",
        tier="tier_b",
        confidence="high",
    )
    ok, output, issue_number = _file_tier_b_pending_approval(
        proposed_edit=edit,
        event=_make_event(),
        mapping=_make_mapping(),
        rationale="rationale",
        repo="x/y",
        dry_run=True,
    )
    assert ok is True
    assert "[dry-run]" in output
    assert issue_number is None


def test_file_judgment_issue_handles_gh_failure(monkeypatch):
    """gh exit non-zero → (False, error message, None)."""
    import subprocess as sp

    from doc_audit.routing.drift_moment0 import _file_judgment_issue

    err = sp.CalledProcessError(1, ["gh"], stderr="boom from gh")
    monkeypatch.setattr(
        drift_moment0.subprocess, "run", mock.MagicMock(side_effect=err)
    )
    ok, output, issue_number = _file_judgment_issue(
        event=_make_event(),
        mapping=_make_mapping(),
        question="why?",
        rationale="because",
        repo="x/y",
        dry_run=False,
    )
    assert ok is False
    assert "gh issue create failed" in output
    assert issue_number is None


def test_file_judgment_issue_handles_gh_timeout(monkeypatch):
    """gh timeout → (False, timeout message, None)."""
    import subprocess as sp

    from doc_audit.routing.drift_moment0 import _file_judgment_issue

    err = sp.TimeoutExpired(cmd=["gh"], timeout=60)
    monkeypatch.setattr(
        drift_moment0.subprocess, "run", mock.MagicMock(side_effect=err)
    )
    ok, output, issue_number = _file_judgment_issue(
        event=_make_event(),
        mapping=_make_mapping(),
        question="why?",
        rationale="because",
        repo="x/y",
        dry_run=False,
    )
    assert ok is False
    assert "timed out" in output


def test_route_drift_event_tier_a_applier_failure_demotes_to_judgment(
    tmp_path: Path, monkeypatch
):
    """If the Tier A applier fails (no applier match), routing demotes to judgment."""
    config = _make_config(tmp_path)
    ledger_path = Path(config.drift_interpretation.ledger_path)

    fake_repo = tmp_path / "repo"
    target_rel = "docs/design/architecture/data/service-inventory.json"
    target_abs = fake_repo / target_rel
    target_abs.parent.mkdir(parents=True, exist_ok=True)
    # Write content that won't match the applier substitutions.
    target_abs.write_text("nothing matches here\n", encoding="utf-8")

    monkeypatch.setattr(
        "doc_audit.judgment.drift_interpretation.interpret",
        lambda *a, **k: _make_verdict(
            "PROPOSED_EDIT",
            proposed_edit={
                "doc_path": target_rel,
                "current_value": "old line",  # not present in file
                "proposed_value": "new line",
            },
        ),
    )

    from doc_audit.data_model import EditTier

    monkeypatch.setattr(
        "doc_audit.judgment.tier_classification.classify",
        lambda *a, **k: (EditTier.TIER_A, "tier_a rationale", None),
    )

    monkeypatch.setattr(
        drift_moment0.subprocess,
        "run",
        lambda *a, **k: mock.MagicMock(
            returncode=0,
            stdout="https://github.com/kentonium3/kg-automation/issues/1010\n",
            stderr="",
        ),
    )

    outcome = route_drift_event(
        event=_make_event(),
        mapping=_make_mapping(),
        config=config,
        client=object(),
        ledger_path=ledger_path,
        repo="kentonium3/kg-automation",
        event_id="0:2026-05-22T10:00:00Z",
        timestamp_utc="2026-05-22T10:00:00Z",
        cursor_line=0,
        repo_root=fake_repo,
        dry_run=False,
    )

    # Tier A applier could not find a target to substitute → falls back
    # to a judgment-style issue.
    assert outcome.outcome == "issue_filed"
    assert outcome.tier_classification_outcome == "tier_a"
    assert outcome.github_issue_number == 1010
