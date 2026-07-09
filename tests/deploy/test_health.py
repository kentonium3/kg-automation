"""Tests for :mod:`scripts.deploy.lib.health` + the generic ntfy health notifier.

Covers (WP03 / #667):
  * streak increments ONLY on confirmed failures; ``lock_unavailable`` leaves
    the streak untouched (benign defer);
  * exactly one alert per streak at threshold; no duplicate on the next failing
    tick;
  * success resets the streak and clears ``last_alert_ts``; a later streak
    re-alerts;
  * atomic write (state file is valid JSON after write); injected clock;
  * ``dispatch_health_notification`` topic resolution + fallback + best-effort
    failure (sender mocked);
  * a regression smoke assertion that the manifest-shaped
    ``dispatch_failure_notification`` still behaves.

The notify module lives under the hyphenated ``scripts/deploy/felix-deployer/``
directory, so — mirroring ``test_notify.py`` — it is loaded via ``importlib``
from its on-disk path rather than a dotted import.
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import pathlib
import sys
from typing import Any

import pytest

from scripts.deploy.lib import health
from scripts.deploy.lib.gitsync import AdvanceResult

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
FELIX_DEPLOYER_DIR = REPO_ROOT / "scripts" / "deploy" / "felix-deployer"


def _load_notify():
    """Import notify.py from the hyphenated felix-deployer/ dir."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    if str(FELIX_DEPLOYER_DIR) not in sys.path:
        sys.path.insert(0, str(FELIX_DEPLOYER_DIR))
    spec = importlib.util.spec_from_file_location(
        "felix_deployer_notify_health_under_test",
        FELIX_DEPLOYER_DIR / "notify.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


notify = _load_notify()


# --------------------------------------------------------------------------- #
# AdvanceResult builders (respect the frozen invariants: ok False iff reason set)
# --------------------------------------------------------------------------- #
def _ok_advance(post_head: str = "bbbbbbb", advanced: bool = True) -> AdvanceResult:
    return AdvanceResult(
        ok=True,
        advanced=advanced,
        pre_head="aaaaaaa",
        post_head=post_head if advanced else "aaaaaaa",
        origin_head=post_head,
        behind=1 if advanced else 0,
        ahead=0,
        diverged=False,
    )


def _clean_noop() -> AdvanceResult:
    return AdvanceResult(
        ok=True,
        advanced=False,
        pre_head="aaaaaaa",
        post_head="aaaaaaa",
        origin_head="aaaaaaa",
        behind=0,
        ahead=2,  # own unpushed commits — still a clean no-op
        diverged=False,
    )


def _failed_advance(reason: str) -> AdvanceResult:
    diverged = reason == "diverged"
    return AdvanceResult(
        ok=False,
        advanced=False,
        pre_head="aaaaaaa",
        post_head="aaaaaaa",
        origin_head="ccccccc",
        behind=1,
        ahead=1 if diverged else 0,
        diverged=diverged,
        reason=reason,
        stderr="boom",
    )


def _lock_unavailable() -> AdvanceResult:
    return AdvanceResult(
        ok=False,
        advanced=False,
        pre_head="aaaaaaa",
        post_head="aaaaaaa",
        origin_head="ccccccc",
        behind=0,
        ahead=0,
        diverged=False,
        reason="lock_unavailable",
    )


class _Clock:
    """Deterministic, monotonic injected clock producing distinct ISO stamps."""

    def __init__(self, start: int = 0):
        self._counter = itertools.count(start)

    def __call__(self) -> str:
        n = next(self._counter)
        # Distinct, lexicographically-ordered ISO-8601 UTC stamps.
        return f"2026-07-09T00:{n // 60:02d}:{n % 60:02d}Z"


class _RecordingNotifier:
    """Notifier that records calls and reports delivery via *delivered*.

    The notifier contract (#667 post-merge fix) is
    ``Callable[[str, str], bool]`` — True iff the alert was actually delivered.
    Default is a delivered alert; set ``delivered=False`` to simulate an
    undeliverable/misconfigured notifier (e.g. no ntfy topic).
    """

    def __init__(self, delivered: bool = True):
        self.calls: list[tuple[str, str]] = []
        self.delivered = delivered

    def __call__(self, title: str, body: str) -> bool:
        self.calls.append((title, body))
        return self.delivered


class _RaisingNotifier:
    """Notifier that raises — must be caught and treated as not-delivered."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def __call__(self, title: str, body: str) -> bool:
        self.calls.append((title, body))
        raise RuntimeError("notifier blew up")


@pytest.fixture()
def state_path(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "state" / "agent-prompt-sync-health.json"


# --------------------------------------------------------------------------- #
# read/write + atomic + zero-state
# --------------------------------------------------------------------------- #
def test_missing_watermark_reads_as_zero_state(state_path):
    wm = health.read_watermark("felix-deployer", state_path)
    assert wm.actor == "felix-deployer"
    assert wm.consecutive_failures == 0
    assert wm.failure_streak_started_ts is None
    assert wm.last_alert_ts is None
    assert wm.last_success_head == ""


def test_corrupt_watermark_reads_as_zero_state(state_path):
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text("{ this is not json", encoding="utf-8")
    wm = health.read_watermark("agent-prompt-sync", state_path)
    assert wm.consecutive_failures == 0


def test_write_is_atomic_and_valid_json(state_path):
    clock = _Clock()
    health.record(
        "agent-prompt-sync",
        _failed_advance("fetch_failed"),
        state_path=state_path,
        clock=clock,
    )
    # File exists, parses, and no stray temp files remain in the dir.
    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert data["actor"] == "agent-prompt-sync"
    assert data["consecutive_failures"] == 1
    leftovers = [
        p for p in state_path.parent.iterdir() if p.name.endswith(".tmp")
    ]
    assert leftovers == []


# --------------------------------------------------------------------------- #
# streak counting — confirmed failures only
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("reason", ["diverged", "fetch_failed", "merge_failed"])
def test_confirmed_failure_increments_streak(reason, state_path):
    clock = _Clock()
    health.record("felix-deployer", _failed_advance(reason), state_path=state_path, clock=clock)
    wm = health.read_watermark("felix-deployer", state_path)
    assert wm.consecutive_failures == 1
    assert wm.failure_streak_started_ts is not None


def test_lock_unavailable_leaves_streak_untouched(state_path):
    clock = _Clock()
    # Two confirmed failures, then a defer, then check the streak is unchanged.
    health.record("felix-deployer", _failed_advance("fetch_failed"), state_path=state_path, clock=clock)
    health.record("felix-deployer", _failed_advance("fetch_failed"), state_path=state_path, clock=clock)
    before = health.read_watermark("felix-deployer", state_path)
    assert before.consecutive_failures == 2
    streak_start = before.failure_streak_started_ts

    fired = health.record(
        "felix-deployer", _lock_unavailable(), state_path=state_path, clock=clock
    )
    after = health.read_watermark("felix-deployer", state_path)
    assert fired is False
    assert after.consecutive_failures == 2  # unchanged
    assert after.failure_streak_started_ts == streak_start  # unchanged
    # updated_ts still advances (state persisted).
    assert after.updated_ts != before.updated_ts


def test_lock_unavailable_alone_never_alerts(state_path):
    clock = _Clock()
    fired = False
    notifier = _RecordingNotifier()
    for _ in range(10):
        fired = health.record(
            "felix-deployer",
            _lock_unavailable(),
            state_path=state_path,
            threshold=3,
            notifier=notifier,
            clock=clock,
        ) or fired
    wm = health.read_watermark("felix-deployer", state_path)
    assert wm.consecutive_failures == 0
    assert notifier.calls == []
    assert fired is False


# --------------------------------------------------------------------------- #
# alert-once-per-streak + throttle
# --------------------------------------------------------------------------- #
def test_alert_fires_once_at_threshold(state_path):
    clock = _Clock()
    notifier = _RecordingNotifier()
    results = []
    for _ in range(3):
        results.append(
            health.record(
                "agent-prompt-sync",
                _failed_advance("merge_failed"),
                state_path=state_path,
                threshold=3,
                notifier=notifier,
                clock=clock,
            )
        )
    # First two below threshold → no alert; third crosses → exactly one alert.
    assert results == [False, False, True]
    assert len(notifier.calls) == 1
    title, body = notifier.calls[0]
    assert "agent-prompt-sync" in title
    assert "merge_failed" in body

    wm = health.read_watermark("agent-prompt-sync", state_path)
    assert wm.last_alert_ts is not None


def test_no_duplicate_alert_on_subsequent_failing_ticks(state_path):
    clock = _Clock()
    notifier = _RecordingNotifier()
    fired = []
    for _ in range(6):  # well past threshold
        fired.append(
            health.record(
                "felix-deployer",
                _failed_advance("fetch_failed"),
                state_path=state_path,
                threshold=3,
                notifier=notifier,
                clock=clock,
            )
        )
    # Exactly one alert across the whole streak.
    assert fired.count(True) == 1
    assert len(notifier.calls) == 1
    wm = health.read_watermark("felix-deployer", state_path)
    assert wm.consecutive_failures == 6


def test_defer_between_failures_does_not_break_throttle(state_path):
    clock = _Clock()
    notifier = _RecordingNotifier()
    seq = [
        _failed_advance("fetch_failed"),
        _failed_advance("fetch_failed"),
        _lock_unavailable(),  # benign, does not count
        _failed_advance("fetch_failed"),  # this is the 3rd confirmed → alert
        _lock_unavailable(),
        _failed_advance("fetch_failed"),  # still same streak → no new alert
    ]
    fired = [
        health.record(
            "felix-deployer", r, state_path=state_path, threshold=3,
            notifier=notifier, clock=clock,
        )
        for r in seq
    ]
    assert fired.count(True) == 1
    assert len(notifier.calls) == 1


# --------------------------------------------------------------------------- #
# success reset + re-alert
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("success", ["advance", "noop"])
def test_success_resets_streak_and_clears_last_alert(success, state_path):
    clock = _Clock()
    notifier = _RecordingNotifier()
    # Drive an alert.
    for _ in range(3):
        health.record("felix-deployer", _failed_advance("fetch_failed"),
                      state_path=state_path, threshold=3, notifier=notifier, clock=clock)
    assert len(notifier.calls) == 1

    ok = _ok_advance(post_head="deadbee") if success == "advance" else _clean_noop()
    fired = health.record(
        "felix-deployer", ok, state_path=state_path, threshold=3,
        notifier=notifier, clock=clock,
    )
    assert fired is False
    wm = health.read_watermark("felix-deployer", state_path)
    assert wm.consecutive_failures == 0
    assert wm.failure_streak_started_ts is None
    assert wm.last_alert_ts is None
    if success == "advance":
        assert wm.last_success_head == "deadbee"
    assert wm.last_success_ts is not None


def test_re_alert_after_recovery(state_path):
    clock = _Clock()
    notifier = _RecordingNotifier()

    # Streak 1 → alert.
    for _ in range(3):
        health.record("felix-deployer", _failed_advance("fetch_failed"),
                      state_path=state_path, threshold=3, notifier=notifier, clock=clock)
    # Recovery.
    health.record("felix-deployer", _ok_advance(),
                  state_path=state_path, threshold=3, notifier=notifier, clock=clock)
    # Streak 2 → must alert AGAIN (last_alert_ts cleared on recovery).
    fired = [
        health.record("felix-deployer", _failed_advance("merge_failed"),
                      state_path=state_path, threshold=3, notifier=notifier, clock=clock)
        for _ in range(3)
    ]
    assert fired == [False, False, True]
    assert len(notifier.calls) == 2  # one per streak


def test_notifier_none_does_not_stamp_or_crash(state_path):
    """notifier=None → never delivered → no stamp, no crash (delivery-gated)."""
    clock = _Clock()
    fired = [
        health.record("felix-deployer", _failed_advance("fetch_failed"),
                      state_path=state_path, threshold=3, notifier=None, clock=clock)
        for _ in range(4)
    ]
    # No notifier means nothing is ever delivered, so no crossing is ever
    # reported as alerted and last_alert_ts is never stamped — the crossing
    # keeps re-attempting on each failing tick (but there is nothing to deliver).
    assert fired == [False, False, False, False]
    wm = health.read_watermark("felix-deployer", state_path)
    assert wm.last_alert_ts is None
    assert wm.consecutive_failures == 4


def test_delivered_alert_stamps_and_returns_true(state_path):
    """A delivered alert (notifier returns True) stamps last_alert_ts once."""
    clock = _Clock()
    notifier = _RecordingNotifier(delivered=True)
    fired = [
        health.record("felix-deployer", _failed_advance("fetch_failed"),
                      state_path=state_path, threshold=3, notifier=notifier, clock=clock)
        for _ in range(3)
    ]
    assert fired == [False, False, True]
    assert len(notifier.calls) == 1
    wm = health.read_watermark("felix-deployer", state_path)
    assert wm.last_alert_ts is not None


def test_undelivered_alert_does_not_stamp_and_reattempts(state_path):
    """A failed delivery (notifier returns False) must NOT stamp last_alert_ts,
    and the NEXT failing tick must re-attempt the alert (not silently burned)."""
    clock = _Clock()
    notifier = _RecordingNotifier(delivered=False)
    # First cross the threshold with an undeliverable notifier.
    fired = [
        health.record("felix-deployer", _failed_advance("fetch_failed"),
                      state_path=state_path, threshold=3, notifier=notifier, clock=clock)
        for _ in range(3)
    ]
    assert fired == [False, False, False]  # crossing not delivered → not alerted
    wm = health.read_watermark("felix-deployer", state_path)
    assert wm.last_alert_ts is None  # NOT stamped
    assert wm.consecutive_failures == 3
    # The notifier was ATTEMPTED at the crossing (best-effort delivery).
    assert len(notifier.calls) == 1

    # Next failing tick: the notifier now succeeds — the alert re-attempts and
    # this time delivers + stamps (the alert was never lost).
    notifier.delivered = True
    fired_next = health.record(
        "felix-deployer", _failed_advance("fetch_failed"),
        state_path=state_path, threshold=3, notifier=notifier, clock=clock,
    )
    assert fired_next is True
    assert len(notifier.calls) == 2  # re-attempted
    wm2 = health.read_watermark("felix-deployer", state_path)
    assert wm2.last_alert_ts is not None
    assert wm2.consecutive_failures == 4


def test_raising_notifier_is_caught_and_not_delivered(state_path):
    """A raising notifier must be caught (no crash) and treated as not-delivered."""
    clock = _Clock()
    notifier = _RaisingNotifier()
    # Must not raise.
    fired = [
        health.record("felix-deployer", _failed_advance("merge_failed"),
                      state_path=state_path, threshold=3, notifier=notifier, clock=clock)
        for _ in range(3)
    ]
    assert fired == [False, False, False]  # exception → not delivered → not alerted
    assert len(notifier.calls) == 1  # attempted at the crossing
    wm = health.read_watermark("felix-deployer", state_path)
    assert wm.last_alert_ts is None  # NOT stamped — re-attempts next tick


def test_custom_threshold_respected(state_path):
    clock = _Clock()
    notifier = _RecordingNotifier()
    fired = [
        health.record("felix-deployer", _failed_advance("diverged"),
                      state_path=state_path, threshold=1, notifier=notifier, clock=clock)
    ]
    assert fired == [True]  # threshold=1 → alert on first confirmed failure
    assert len(notifier.calls) == 1


def test_injected_clock_controls_timestamps(state_path):
    clock = _Clock(start=100)
    health.record("felix-deployer", _failed_advance("fetch_failed"),
                  state_path=state_path, clock=clock)
    wm = health.read_watermark("felix-deployer", state_path)
    # First tick uses the very first clock value.
    assert wm.updated_ts == "2026-07-09T00:01:40Z"
    assert wm.failure_streak_started_ts == "2026-07-09T00:01:40Z"


# --------------------------------------------------------------------------- #
# dispatch_health_notification — topic resolution + fallback + best-effort
# --------------------------------------------------------------------------- #
class _FakeProc:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_health_notification_resolves_actor_topic(monkeypatch):
    monkeypatch.setenv("AGENT_PROMPT_SYNC_NTFY_TOPIC", "prompt-sync-topic-abcd")
    monkeypatch.setenv(notify.NTFY_TOPIC_ENV, "shared-deployer-topic-xyz")
    seen: dict[str, Any] = {}

    def _fake_run(argv, input=None, capture_output=None, text=None, check=None):
        seen["argv"] = list(argv)
        seen["input"] = input
        return _FakeProc(returncode=0)

    monkeypatch.setattr(notify.subprocess, "run", _fake_run)

    delivered = notify.dispatch_health_notification(
        "agent-prompt-sync", "stalled", "detail body",
        topic_env="AGENT_PROMPT_SYNC_NTFY_TOPIC",
    )
    # A successful POST reports delivery True (the contract health.record needs).
    assert delivered is True
    # Actor-specific topic wins over the shared fallback.
    assert seen["argv"][-1] == "https://ntfy.sh/prompt-sync-topic-abcd"


def test_health_notification_falls_back_to_shared_topic(monkeypatch):
    monkeypatch.delenv("AGENT_PROMPT_SYNC_NTFY_TOPIC", raising=False)
    monkeypatch.setenv(notify.NTFY_TOPIC_ENV, "shared-deployer-topic-xyz")
    seen: dict[str, Any] = {}

    def _fake_run(argv, input=None, capture_output=None, text=None, check=None):
        seen["argv"] = list(argv)
        return _FakeProc(returncode=0)

    monkeypatch.setattr(notify.subprocess, "run", _fake_run)

    delivered = notify.dispatch_health_notification(
        "agent-prompt-sync", "stalled", "body",
        topic_env="AGENT_PROMPT_SYNC_NTFY_TOPIC",
    )
    assert delivered is True
    assert seen["argv"][-1] == "https://ntfy.sh/shared-deployer-topic-xyz"


def test_health_notification_missing_topic_is_noop(monkeypatch):
    monkeypatch.delenv("AGENT_PROMPT_SYNC_NTFY_TOPIC", raising=False)
    monkeypatch.delenv(notify.NTFY_TOPIC_ENV, raising=False)
    called = []
    monkeypatch.setattr(
        notify.subprocess, "run",
        lambda *a, **kw: called.append(True) or _FakeProc(returncode=0),
    )
    delivered = notify.dispatch_health_notification(
        "agent-prompt-sync", "stalled", "body",
        topic_env="AGENT_PROMPT_SYNC_NTFY_TOPIC",
    )
    # No topic → not delivered. This is the case health.record must NOT burn.
    assert delivered is False
    assert called == []  # curl NOT invoked


def test_health_notification_best_effort_on_curl_missing(monkeypatch):
    monkeypatch.setenv("AGENT_PROMPT_SYNC_NTFY_TOPIC", "prompt-sync-topic-abcd")

    def _fake_run(*a, **kw):
        raise FileNotFoundError("curl")

    monkeypatch.setattr(notify.subprocess, "run", _fake_run)
    # Must NOT raise — best-effort — and reports not delivered.
    delivered = notify.dispatch_health_notification(
        "agent-prompt-sync", "stalled", "body",
        topic_env="AGENT_PROMPT_SYNC_NTFY_TOPIC",
    )
    assert delivered is False


def test_health_notification_best_effort_on_http_error(monkeypatch):
    monkeypatch.setenv("AGENT_PROMPT_SYNC_NTFY_TOPIC", "prompt-sync-topic-abcd")
    monkeypatch.setattr(
        notify.subprocess, "run",
        lambda *a, **kw: _FakeProc(returncode=22, stderr="HTTP 500"),
    )
    delivered = notify.dispatch_health_notification(
        "agent-prompt-sync", "stalled", "body",
        topic_env="AGENT_PROMPT_SYNC_NTFY_TOPIC",
    )
    # A non-zero curl rc → not delivered.
    assert delivered is False


def test_health_notification_redacts_body(monkeypatch):
    monkeypatch.setenv("AGENT_PROMPT_SYNC_NTFY_TOPIC", "prompt-sync-topic-abcd")
    seen: dict[str, Any] = {}

    def _fake_run(argv, input=None, **kw):
        seen["input"] = input
        return _FakeProc(returncode=0)

    monkeypatch.setattr(notify.subprocess, "run", _fake_run)
    secret = "S" * 40  # token-shaped → redacted by _redact_and_truncate
    notify.dispatch_health_notification(
        "agent-prompt-sync", "stalled", f"token={secret}",
        topic_env="AGENT_PROMPT_SYNC_NTFY_TOPIC",
    )
    assert secret not in seen["input"]


# --------------------------------------------------------------------------- #
# Regression: existing manifest-failure notifier still behaves.
# --------------------------------------------------------------------------- #
def test_dispatch_failure_notification_still_works(monkeypatch):
    monkeypatch.setenv(notify.NTFY_TOPIC_ENV, "test-topic-alpha-1234")
    seen: dict[str, Any] = {}

    def _fake_run(argv, input=None, capture_output=None, text=None, check=None):
        seen["argv"] = list(argv)
        seen["input"] = input
        return _FakeProc(returncode=0)

    monkeypatch.setattr(notify.subprocess, "run", _fake_run)

    result = notify.dispatch_failure_notification(
        manifest={"name": "vikunja-image-bump", "tier": 2},
        phase="verification_post",
        error_summary="vikunja smoke check failed",
        head_sha="31f63d6070bf5377fa20be921feb9f0e7f69a608",
        failed_at="2026-06-13T15:30:42Z",
    )
    assert result.ok is True
    assert result.summary == "ntfy notification sent"
    assert result.details["title"] == "felix-deployer failed: vikunja-image-bump"
    assert result.details["format_version"] == "v1"
    assert seen["argv"][-1] == "https://ntfy.sh/test-topic-alpha-1234"
    assert seen["input"].startswith("Phase: verification_post\n")
