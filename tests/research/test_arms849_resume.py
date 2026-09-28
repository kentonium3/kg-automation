"""WP05 T026 — live-style resume across fresh, timestamp-bearing gate phases."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from scripts.research import run_849_harness as h
from scripts.research.arms849 import gates, substrate
from scripts.research.arms849 import preflight as preflight_mod
from scripts.research.arms849.ledger import SessionGatesMissing
from tests.research import conftest as research_fakes
from tests.research.conftest import (
    PRIMARY,
    FakeG,
    FakeGtt,
    fake_arms,
    make_binding,
    rows_of,
    runs,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _signed_preflight(path) -> str:
    payload = {"source_commit": "test", "gates": []}
    payload["preflight_sha"] = preflight_mod.preflight_sha(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload["preflight_sha"]


def _real_gate_phases(
    root,
    ledger_path,
    monkeypatch,
    *,
    container_passes: bool = True,
) -> tuple[h.SessionGates, dict[str, Any]]:
    """Run host gates and the production ``live_gates`` orchestration with real timestamps."""
    run_root = root / "export"
    run_root.mkdir(parents=True)
    manifest = run_root / ".export-manifest.json"
    manifest.write_text(json.dumps({"source_commit": "test"}), encoding="utf-8")
    preflight = root / "preflight.json"
    _signed_preflight(preflight)
    host_record = root / "gate-host.json"
    container_record = root / "gate-container.json"

    def passing_check(env):
        return True, "injected boundary passed"

    def container_check(env):
        return container_passes, "injected container result"

    up_ts = _now()
    original_gate_env = h._gate_env

    def bound_gate_env(
        corpus,
        config,
        observed_up_ts,
        header_code_hashes=None,
        run_root_arg=h.REPO_ROOT,
        *,
        process_start=h.PROCESS_START,
    ):
        del run_root_arg
        env = original_gate_env(
            corpus,
            config,
            observed_up_ts,
            header_code_hashes,
            run_root,
            process_start=process_start,
        )
        env.corpus_dir = root
        env.cache_dir = root
        env.props_probe = lambda _url: {
            "default_generation_settings": {"n_ctx": gates.serving.PRIMARY_N_CTX},
            "model_path": f"/models/{substrate.GGUF_FILE}",
        }
        return env

    with monkeypatch.context() as gate_patch:
        gate_patch.setattr(gates, "HOST_GATES", (("boundary", passing_check),))
        gate_patch.setattr(
            gates,
            "CONTAINER_GATES",
            (
                ("substrate_health_inside", gates.substrate_health_inside),
                ("prompt_digest", container_check),
            ),
        )
        gate_patch.setattr(h, "RUNS_DIR", root)
        gate_patch.setattr(h, "_gate_env", bound_gate_env)
        host_env = bound_gate_env(root, PRIMARY, up_ts)
        gates.run_host_phase(host_env, host_record)
        process_start = _now()
        outcome = h.live_gates(
            ledger_path,
            root,
            PRIMARY,
            up_ts,
            False,
            container_phase=gates.run_container_phase,
            process_start=process_start,
        )

    records = {
        "host": json.loads(host_record.read_text(encoding="utf-8")),
        "container": json.loads(container_record.read_text(encoding="utf-8")),
    }
    return outcome, records


def _live_fake_runtime(
    monkeypatch,
    environment,
    outcome: h.SessionGates,
    *,
    arms=None,
) -> h.Runtime:
    """Construct through live_runtime using the integration suite's serving/G/D/R fake kit."""
    from scripts.research.arms849 import embed as embed_mod

    monkeypatch.setenv("ARMS849_CACHE", str(environment.cache))
    monkeypatch.setenv("ORT_DISABLE_TELEMETRY", "1")
    fake_runtime = research_fakes.make_runtime(arms or fake_arms())
    fake_tokenizer = SimpleNamespace()
    fake_embedder = SimpleNamespace()
    monkeypatch.setattr(h.serving, "Tokenizer", lambda *args, **kwargs: fake_tokenizer)
    monkeypatch.setattr(embed_mod, "Embedder", lambda *args, **kwargs: fake_embedder)
    monkeypatch.setattr(h, "build_arms", lambda resources: fake_runtime.arms)
    monkeypatch.setattr(
        h,
        "ServingFacade",
        lambda config, tokenizer, base_url, deadline, cancelled, before_send: fake_runtime.facade(
            deadline,
            cancelled,
            before_send,
        ),
    )
    monkeypatch.setattr(h, "container_health", lambda config: True)
    runtime = h.live_runtime(PRIMARY, environment.corpus, outcome)
    runtime.gtt_sampler = FakeGtt
    runtime.out = lambda message: None
    assert runtime.arms is fake_runtime.arms
    assert runtime.embedder is fake_embedder
    return runtime


def test_research_environment_declares_import_registered_corpus_and_nonempty_caches(research_environment):
    assert research_environment.graphiti_core.__name__ == "graphiti_core"
    assert research_environment.corpus == research_fakes.CORPUS
    for name in ("qwen-tokenizer", "fastembed"):
        assert any(path.is_file() for path in (research_environment.cache / name).rglob("*"))


def test_missing_research_environment_has_one_named_counted_skip_reason(monkeypatch):
    reason = research_fakes.RESEARCH_ENVIRONMENT_SKIP_REASON
    monkeypatch.setattr(research_fakes, "_load_research_environment", lambda: None)
    with pytest.raises(pytest.skip.Exception) as caught:
        research_fakes.research_environment.__wrapped__()
    assert str(caught.value) == reason

    written: list[tuple[str, str]] = []
    reporter = SimpleNamespace(
        stats={"skipped": [SimpleNamespace(longrepr=f"Skipped: {reason}")]},
        write_sep=lambda separator, message: written.append((separator, message)),
    )
    research_fakes.pytest_terminal_summary(reporter)
    assert written == [("=", f"{reason}: 1 skipped test")]


def test_live_style_resume_with_fresh_timestamped_gates_preserves_prior_rows(
    research_environment,
    tmp_path,
    monkeypatch,
):
    def first_cell_unreadable(question, ctx):
        if question.id == "C1" and ctx.repeat == 2:
            return h.CeilingUnreadable("injected send-time GTT read failure")
        return None

    ledger_path = tmp_path / "ledger.jsonl"
    first, first_records = _real_gate_phases(tmp_path / "session-1", ledger_path, monkeypatch)
    with h.open_run_ledger(ledger_path, make_binding(gates_outcome=first)) as ledger:
        report = h.run_session(
            ledger,
            _live_fake_runtime(
                monkeypatch,
                research_environment,
                first,
                arms=fake_arms(g=FakeG(fail=first_cell_unreadable)),
            ),
            limit=9,
        )
    assert report.completed == 8 and report.stopped is None
    terminal_key = ("G", "C1", 2)
    terminal_before = [
        line for line in ledger_path.read_bytes().splitlines(keepends=True)
        if (
            (row := json.loads(line))["record"] == "run" and
            (row["arm"], row["question"], row["repeat"]) == terminal_key
        )
    ]
    assert len(terminal_before) == 1
    assert json.loads(terminal_before[0])["outcome"] == "sampler_unreadable_at_send"
    earlier = ledger_path.read_bytes()

    second, second_records = _real_gate_phases(tmp_path / "session-2", ledger_path, monkeypatch)
    with h.open_run_ledger(ledger_path, make_binding(gates_outcome=second)) as ledger:
        report = h.run_session(
            ledger,
            _live_fake_runtime(monkeypatch, research_environment, second),
        )

    assert report.stopped is None
    assert ledger_path.read_bytes().startswith(earlier)
    keys = [(row["arm"], row["question"], row["repeat"]) for row in runs(ledger_path)]
    assert len(keys) == len(set(keys)) == h.PRIMARY_PLAN
    terminal_after = [
        line for line in ledger_path.read_bytes().splitlines(keepends=True)
        if (
            (row := json.loads(line))["record"] == "run" and
            (row["arm"], row["question"], row["repeat"]) == terminal_key
        )
    ]
    assert terminal_after == terminal_before
    assert sum(
        row.get("record") == "attempt_start" and
        (row["arm"], row["question"], row["repeat"]) == terminal_key
        for row in rows_of(ledger_path)
    ) == 1
    session_gates = [
        row["detail"] for row in rows_of(ledger_path)
        if row.get("record") == "event" and row.get("kind") == "session_gates"
    ]
    assert [detail["container_start_ts"] for detail in session_gates] == [
        first.container_start_ts,
        second.container_start_ts,
    ]
    assert first.container_start_ts != second.container_start_ts
    assert first.gate_host_sha != second.gate_host_sha
    for records in (first_records, second_records):
        up = datetime.fromisoformat(records["host"]["up_ts"])
        host = datetime.fromisoformat(records["host"]["ts"])
        start = datetime.fromisoformat(records["container"]["container_start_ts"])
        assert up <= host <= start
        assert records["container"]["gate_host_sha"] == records["host"]["gate_host_sha"]


def test_live_style_resume_stops_and_records_a_failing_fresh_gate(
    research_environment,
    tmp_path,
    monkeypatch,
):
    ledger_path = tmp_path / "ledger.jsonl"
    passed, _ = _real_gate_phases(tmp_path / "passed", ledger_path, monkeypatch)
    with h.open_run_ledger(ledger_path, make_binding(gates_outcome=passed)) as ledger:
        h.run_session(
            ledger,
            _live_fake_runtime(monkeypatch, research_environment, passed),
            limit=2,
        )
    earlier = ledger_path.read_bytes()
    before_runs = len(runs(ledger_path))

    failed, records = _real_gate_phases(
        tmp_path / "failed",
        ledger_path,
        monkeypatch,
        container_passes=False,
    )
    with h.open_existing(ledger_path) as ledger:
        report = h.run_session(
            ledger,
            _live_fake_runtime(monkeypatch, research_environment, failed),
            limit=2,
        )

    assert report.stopped and "gates failed" in report.stopped
    assert ledger_path.read_bytes().startswith(earlier)
    assert len(runs(ledger_path)) == before_runs
    assert records["container"]["passed"] is False
    last = rows_of(ledger_path)[-1]
    assert last["kind"] == "session_gates" and last["detail"]["passed"] is False
    assert last["detail"]["container_start_ts"] == failed.container_start_ts


def test_live_style_resume_cannot_write_after_skipped_gates(
    research_environment,
    tmp_path,
    monkeypatch,
):
    ledger_path = tmp_path / "ledger.jsonl"
    passed, _ = _real_gate_phases(tmp_path / "passed", ledger_path, monkeypatch)
    with h.open_run_ledger(ledger_path, make_binding(gates_outcome=passed)) as ledger:
        h.run_session(
            ledger,
            _live_fake_runtime(monkeypatch, research_environment, passed),
            limit=1,
        )
    before = rows_of(ledger_path)
    skipped = h.SessionGates(
        passed=True,
        skipped=True,
        gate_host_sha=passed.gate_host_sha,
        gate_container_sha=passed.gate_container_sha,
        preflight_sha=passed.preflight_sha,
        up_ts=_now(),
        container_start_ts=_now(),
    )
    with h.open_existing(ledger_path) as ledger, pytest.raises(SessionGatesMissing, match="skipped"):
        h.run_session(
            ledger,
            _live_fake_runtime(monkeypatch, research_environment, skipped),
            limit=1,
        )

    after = rows_of(ledger_path)
    assert after[:len(before)] == before
    assert len(after) == len(before) + 1
    assert after[-1]["kind"] == "session_gates" and after[-1]["detail"]["skipped"] is True
    assert len(runs(ledger_path)) == 1
