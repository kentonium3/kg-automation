"""Unit tests for scripts.canary.crash_loop_model (mission #1133, WP01 T005)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from scripts.canary import crash_loop_model as model
from scripts.canary.crash_loop_model import (
    CrashLoopConfigError,
    CrashLoopEvent,
    Proof,
    RestartObservation,
    ScopeReading,
    load_config,
)

T0 = datetime(2026, 11, 23, 12, 0, 0, tzinfo=UTC)

VALID: dict[str, Any] = {
    "threshold": 3,
    "window_seconds": 900,
    "quiet_ticks_to_clear": 2,
    "max_alerts_per_tick": 3,
    "read_budget_seconds": 6,
    "ignore": [],
}


def _write(tmp_path: Path, document: Any) -> Path:
    path = tmp_path / "crash_loop_config.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _with(**changes: Any) -> dict[str, Any]:
    document = dict(VALID)
    document.update(changes)
    return document


def _without(key: str) -> dict[str, Any]:
    document = dict(VALID)
    del document[key]
    return document


def _obs(scope: str = "system", name: str = "a.service") -> RestartObservation:
    return RestartObservation(
        scope=scope,
        name=name,
        restart_policy="on-failure",
        restart_count=4,
        state="active (running)",
        generation="boot-1",
    )


def _proof(delta: int = 5, bound: int = 5) -> Proof:
    return Proof(
        baseline_at=T0,
        baseline_count=0,
        current_count=delta,
        observed_at=T0 + timedelta(minutes=16),
        delta=delta,
        period_seconds=960.0,
        m=2,
        bound=bound,
    )


# --------------------------------------------------------------------------- #
# Config: positive.
# --------------------------------------------------------------------------- #
def test_shipped_config_loads_with_the_documented_defaults() -> None:
    config = load_config(model.DEFAULT_CONFIG_PATH)
    assert config.threshold == 3
    assert config.window_seconds == 900
    assert config.quiet_ticks_to_clear == 2
    assert config.max_alerts_per_tick == 3
    assert config.read_budget_seconds == 6
    assert config.ignore == frozenset()
    assert dict(config.ignore_reasons) == {}


def test_default_config_path_is_beside_the_module() -> None:
    assert model.DEFAULT_CONFIG_PATH == Path(model.__file__).with_name(
        "crash_loop_config.json"
    )


def test_ignore_entries_load_as_a_set_with_reasons(tmp_path: Path) -> None:
    document = _with(
        ignore=[
            {"unit": "system:flaky.service", "reason": "known flapper, #1"},
            {"unit": "container:web", "reason": "restarted by its own watchdog"},
        ]
    )
    config = load_config(_write(tmp_path, document))
    assert config.ignore == frozenset({"system:flaky.service", "container:web"})
    assert config.ignore_reasons["container:web"] == "restarted by its own watchdog"
    with pytest.raises(TypeError):
        config.ignore_reasons["x"] = "y"  # type: ignore[index]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("threshold", 2),
        ("threshold", 50),
        ("window_seconds", 60),
        ("window_seconds", 3600),
        ("read_budget_seconds", 1),
        ("read_budget_seconds", 10),
        ("quiet_ticks_to_clear", 1),
        ("max_alerts_per_tick", 1),
    ],
)
def test_bounds_are_inclusive(tmp_path: Path, field: str, value: int) -> None:
    config = load_config(_write(tmp_path, _with(**{field: value})))
    assert getattr(config, field) == value


# --------------------------------------------------------------------------- #
# Config: one negative test per rule.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("document", "names"),
    [
        (_with(threshold=True), "threshold"),
        (_with(threshold=3.0), "threshold"),
        (_with(threshold="3"), "threshold"),
        (_with(threshold=1), "threshold"),
        (_with(threshold=51), "threshold"),
        (_with(window_seconds=0), "window_seconds"),
        (_with(window_seconds=59), "window_seconds"),
        (_with(window_seconds=3601), "window_seconds"),
        (_with(window_seconds=900.5), "window_seconds"),
        (_with(quiet_ticks_to_clear=0), "quiet_ticks_to_clear"),
        (_with(quiet_ticks_to_clear=-1), "quiet_ticks_to_clear"),
        (_with(quiet_ticks_to_clear=False), "quiet_ticks_to_clear"),
        (_with(max_alerts_per_tick=0), "max_alerts_per_tick"),
        (_with(read_budget_seconds=0), "read_budget_seconds"),
        (_with(read_budget_seconds=11), "read_budget_seconds"),
        (_with(slack_seconds=60), "slack_seconds"),
        (_with(extra=1), "extra"),
        (_without("threshold"), "threshold"),
        (_without("ignore"), "ignore"),
        (_with(ignore={}), "ignore"),
        (_with(ignore=["system:a.service"]), "ignore[0]"),
        (_with(ignore=[{"unit": "system:a.service"}]), "ignore[0]"),
        (
            _with(ignore=[{"unit": "system:a.service", "reason": "r", "note": "n"}]),
            "ignore[0]",
        ),
        (_with(ignore=[{"unit": "host:a.service", "reason": "r"}]), "ignore[0].unit"),
        (_with(ignore=[{"unit": "system:", "reason": "r"}]), "ignore[0].unit"),
        (_with(ignore=[{"unit": 7, "reason": "r"}]), "ignore[0].unit"),
        (
            _with(ignore=[{"unit": "system:a.service", "reason": ""}]),
            "ignore[0].reason",
        ),
        (
            _with(ignore=[{"unit": "system:a.service", "reason": "   "}]),
            "ignore[0].reason",
        ),
        (
            _with(ignore=[{"unit": "system:a.service", "reason": None}]),
            "ignore[0].reason",
        ),
        (
            _with(
                ignore=[
                    {"unit": "user:a.service", "reason": "one"},
                    {"unit": "user:a.service", "reason": "two"},
                ]
            ),
            "ignore[1].unit",
        ),
        ([], "top level"),
    ],
)
def test_each_rule_violation_raises_naming_the_field(
    tmp_path: Path, document: Any, names: str
) -> None:
    with pytest.raises(
        CrashLoopConfigError, match=names.replace("[", r"\[").replace("]", r"\]")
    ):
        load_config(_write(tmp_path, document))


def test_invalid_utf8_raises_config_error(tmp_path: Path) -> None:
    path = tmp_path / "crash_loop_config.json"
    path.write_bytes(b'{"threshold": "\xff\xfe"}')
    with pytest.raises(CrashLoopConfigError, match="unreadable"):
        load_config(path)


@pytest.mark.parametrize(
    "content",
    ['{"threshold": ' + "9" * 5000 + "}", "[" * 100_000 + "]" * 100_000],
    ids=["huge-integer", "deep-nesting"],
)
def test_decoder_failures_raise_config_error(tmp_path: Path, content: str) -> None:
    path = tmp_path / "crash_loop_config.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(CrashLoopConfigError, match="not valid JSON"):
        load_config(path)


def test_invalid_json_raises(tmp_path: Path) -> None:
    path = tmp_path / "crash_loop_config.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(CrashLoopConfigError, match="not valid JSON"):
        load_config(path)


def test_missing_file_raises_and_does_not_fall_back(tmp_path: Path) -> None:
    with pytest.raises(CrashLoopConfigError, match="unreadable"):
        load_config(tmp_path / "absent.json")


def test_config_error_is_a_value_error() -> None:
    assert issubclass(CrashLoopConfigError, ValueError)


# --------------------------------------------------------------------------- #
# Value types.
# --------------------------------------------------------------------------- #
def test_observation_key() -> None:
    assert _obs("container", "web").key == "container:web"
    assert _obs("user", "foo@bar.service").key == "user:foo@bar.service"


def test_scope_constants() -> None:
    assert model.SCOPES == ("system", "user", "container")
    assert model.UNIT_KEY_RE.match("system:x.service")
    assert not model.UNIT_KEY_RE.match("system:")
    assert not model.UNIT_KEY_RE.match("docker:x")
    assert model.HISTORY_RETENTION == timedelta(hours=24)
    assert model.HISTORY_MAX == 64


def test_scope_reading_ok_is_complete_without_error() -> None:
    reading = ScopeReading.ok("system", (_obs(),), excluded=2, elapsed_ms=40)
    assert reading.complete is True
    assert reading.error is None
    assert reading.observations == (_obs(),)
    assert reading.excluded == 2


def test_scope_reading_failed_has_no_observations_and_an_error() -> None:
    reading = ScopeReading.failed("user", "systemctl exited 1", elapsed_ms=12)
    assert reading.complete is False
    assert reading.observations == ()
    assert reading.error == "systemctl exited 1"


@pytest.mark.parametrize("error", ["", "   "])
def test_scope_reading_failed_requires_an_error(error: str) -> None:
    with pytest.raises(ValueError):
        ScopeReading.failed("user", error, elapsed_ms=1)


def test_scope_reading_rejects_inconsistent_construction() -> None:
    with pytest.raises(ValueError):
        ScopeReading("system", True, (), 0, "boom", 1)
    with pytest.raises(ValueError):
        ScopeReading("system", False, (_obs(),), 0, "boom", 1)
    with pytest.raises(ValueError):
        ScopeReading.ok("host", (), excluded=0, elapsed_ms=1)
    with pytest.raises(ValueError):
        ScopeReading.ok("user", (_obs("system"),), excluded=0, elapsed_ms=1)


@pytest.mark.parametrize(
    ("delta", "bound", "holds"), [(5, 5, True), (6, 5, True), (4, 5, False)]
)
def test_proof_holds_when_delta_reaches_bound(
    delta: int, bound: int, holds: bool
) -> None:
    assert _proof(delta, bound).holds is holds


@pytest.mark.parametrize("kind", ["alert", "reremind", "cleared"])
def test_event_accepts_known_kinds(kind: str) -> None:
    event = CrashLoopEvent(
        kind, "system:a.service", "system", "a.service", "failed", T0, _proof()
    )
    assert event.kind == kind


@pytest.mark.parametrize("kind", ["", "ALERT", "unverified", "recovered"])
def test_event_rejects_unknown_kind(kind: str) -> None:
    with pytest.raises(ValueError, match="kind"):
        CrashLoopEvent(
            kind, "system:a.service", "system", "a.service", "failed", T0, _proof()
        )


def test_value_types_are_frozen() -> None:
    obs = _obs()
    with pytest.raises(AttributeError):
        obs.restart_count = 9  # type: ignore[misc]
