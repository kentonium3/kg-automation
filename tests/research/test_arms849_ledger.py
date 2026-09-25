"""The ledger: binding, attempts, durability, summaries (WP03 T015).

Every check is paired with the defect it exists to catch; the binding test is
parametrised over EVERY header field so a new field cannot go uncompared.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import textwrap

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.research.arms849 import ledger as L
from scripts.research.arms849 import serving as S
from scripts.research.load_849_corpus import DEFAULT_CORPUS

pytestmark = pytest.mark.skipif(
    not (DEFAULT_CORPUS / "entities.json").exists(),
    reason="rendered corpus absent; run render_849_corpus first")

IDENT = S.ServingIdentity("gguf", "sha256:img", "emb", "tok", "c" * 64)
SERVING = S.ServingConfiguration.primary(IDENT).as_header_dict()
QUESTIONS = ["C1", "A", "F1", "B1", "E2", "E1", "F2", "B2"]


def rec(led, key, outcome, row, serving=SERVING):
    return led.record(key, outcome, row, serving)


def score_all_g_repeat1(led):
    for q in QUESTIONS:
        k = L.RunKey("G", q, 1)
        if led.terminal(k) is None:
            led.begin_attempt(k); rec(led, k, "ok", ok_row())


def calibrated(led):
    """All eight G repeat-1 cells scored and the calibration record written (D-10 precondition for R)."""
    score_all_g_repeat1(led)
    if led.calibration() is None:
        led.write_calibration({"r_k": 12, "parity": "ok"})


def binding(**over) -> L.Binding:
    cfg = S.ServingConfiguration.primary(IDENT)
    b = L.Binding.from_environment(DEFAULT_CORPUS, cfg.as_header_dict(), "trained", "c0ffee",
                                   "export-sha", "a" * 64, "b" * 64, "c" * 64,
                                   repo_root=REPO_ROOT, model_context_tokens=S.TRAINED_CONTEXT)
    if over:
        d = b.as_dict(); d.update(over); b = L.Binding(**d)
    return b


def fresh(tmp_path, **over) -> L.Ledger:
    return L.open_ledger(tmp_path / "ledger.jsonl", binding(**over), blinding_seed=7, plan=72)


ASK = "2026-04-20T09:00:00-04:00"


def ok_row(tokens=1000, arm="G"):
    row = {"ask_time": ASK, "elapsed_s": 3.5, "assembled_context_tokens": tokens, "prompt_tokens": tokens + 300,
           "client_prompt_tokens": tokens + 300, "output_tokens": 120, "cache_read_tokens": 0, "uncached_tokens": tokens + 300,
           "events_loaded": 10, "nodes_loaded": 5, "edges_loaded": 4, "links_loaded": 3,
           "cache_write_tokens": tokens + 300, "cache_state": "cold", "cache_fraction": 0.0,
           "prefill_s": 1.5, "generation_s": 2.0, "generation_tok_s": 60.0, "peak_gtt_gib": 40.0,
           "finish_reason": "stop", "assembled_context_sha256": "0" * 64, "seed": 1001, "text": "x",
           "plan": {"arm": arm}}
    row.update({"G": {"falkordb_rss_peak_mib": 512.0}, "R": {"r_g_ratio": 1.0},
                "D": {"context_limit_applied": "trained"}}[arm])
    return row


def err_row(msg="boom", arm="G"):
    row = {"ask_time": ASK, "elapsed_s": 1.0, "error": msg, "peak_gtt_gib": 12.0}
    if arm == "D":
        row["context_limit_applied"] = "trained"
    return row


def exceeds_row(pt=362_996):
    return {"ask_time": ASK, "elapsed_s": 0.2, "prompt_tokens": pt, "context_limit_applied": "trained"}


# --------------------------------------------------------------------------
# Header binding
# --------------------------------------------------------------------------


def test_header_is_first_line_and_carries_every_binding_field(tmp_path):
    with fresh(tmp_path) as led:
        pass
    first = json.loads((tmp_path / "ledger.jsonl").read_text().splitlines()[0])
    assert first["record"] == "header"
    for k in L.Binding.__dataclass_fields__:
        assert k in first, k
    assert first["prompt_hash"].startswith("0aa7ee77") and first["question_manifest_sha"].startswith("fe17beef")
    assert first["corpus"]["stream.jsonl"].startswith("188b9bf1")
    assert "scripts/research/arms849/text.py" in first["code_hashes"]


HEADER_FIELDS = sorted(set(L.Header.__dataclass_fields__) - {"record", "started", "binding"}
                       | set(L.Binding.__dataclass_fields__))


def test_every_header_field_is_covered_by_the_resume_test():
    """Opus c10: the exhaustiveness test was over Binding, so Header's own fields went uncompared."""
    assert set(HEADER_FIELDS) >= set(L.Binding.__dataclass_fields__)
    assert {"blinding_seed", "plan"} <= set(HEADER_FIELDS)


@pytest.mark.parametrize("field", HEADER_FIELDS)
def test_resume_refuses_on_every_binding_field(tmp_path, field):
    """Parametrised over EVERY header field (Binding's and the Header's own) so a new field
    cannot be added uncompared."""
    with fresh(tmp_path):
        pass
    if field in ("blinding_seed", "plan"):
        kw = {"blinding_seed": 7, "plan": 72}
        kw[field] += 1
        with pytest.raises(L.LedgerBoundToAnotherConfig, match=field):
            L.open_ledger(tmp_path / "ledger.jsonl", binding(), **kw)
        return
    current = binding().as_dict()[field]
    if field == "corpus":
        changed = {**current, "stream.jsonl": "f" * 64}     # a VALID-looking but different fingerprint
    elif field == "limit_applied":
        changed = "permitted"                                # the other legal value
    elif isinstance(current, dict):
        changed = {**current, "__probe__": "x"}
    elif isinstance(current, int):
        changed = current + 1
    elif field.endswith("_sha") and field != "run_env_manifest_sha":
        changed = "f" * 64                              # another VALID digest: the mismatch is what must be caught
    else:
        changed = str(current) + "-changed"
    with pytest.raises(L.LedgerBoundToAnotherConfig, match=field):
        L.open_ledger(tmp_path / "ledger.jsonl", binding(**{field: changed}), blinding_seed=7, plan=72)


def test_resume_with_identical_binding_reads_rows_back(tmp_path):
    key = L.RunKey("G", "C1", 1)
    with fresh(tmp_path) as led:
        led.begin_attempt(key); rec(led, key, "ok", ok_row())
    with fresh(tmp_path) as led:
        assert led.terminal(key) == "ok"
        assert len(led.run_rows()) == 1


# --------------------------------------------------------------------------
# Attempts
# --------------------------------------------------------------------------


def test_attempt_start_precedes_run_and_a_fourth_attempt_is_refused(tmp_path):
    key = L.RunKey("D", "B2", 2)
    with fresh(tmp_path) as led:
        with pytest.raises(ValueError, match="before begin_attempt"):
            rec(led, key, "error", err_row("boom", arm="D"))
        for n in (1, 2, 3):
            assert led.begin_attempt(key) == n
            rec(led, key, "error", err_row(f"boom {n}", arm="D"))
        assert led.terminal(key) == "error"
        with pytest.raises(L.AttemptsExhausted):                # T012.1: the named type, reachable
            led.begin_attempt(key)
        with pytest.raises(L.AttemptsExhausted):
            led.begin_attempt(key)
    kinds = [json.loads(l)["record"] for l in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert kinds == ["header"] + ["attempt_start", "run"] * 3


def test_an_interrupted_attempt_counts_toward_three(tmp_path):
    key = L.RunKey("G", "A", 1)
    with fresh(tmp_path) as led:
        led.begin_attempt(key)                      # process dies here: no run row
    with fresh(tmp_path) as led:
        assert led.attempts_for(key) == 1
        assert led.terminal(key) is None
        assert key in led.pending_keys(L.plan_keys())
        assert led.begin_attempt(key) == 2


def test_error_then_ok_is_legal_and_second_ok_is_not(tmp_path):
    key = L.RunKey("R", "F1", 3)
    with fresh(tmp_path) as led:
        calibrated(led)
        led.begin_attempt(key); rec(led, key, "error", err_row("transient"))
        led.begin_attempt(key); rec(led, key, "ok", ok_row(arm="R"))
        assert led.terminal(key) == "ok"
        with pytest.raises(L.SecondScoredRow):                  # a REAL terminal row, not exhaustion
            led.begin_attempt(key)
        kx = L.RunKey("D", "B2", 1)
        led.begin_attempt(kx)
        rec(led, kx, "exceeds_model_context", {"ask_time": ASK, "elapsed_s": 1.0, "prompt_tokens": 400_000,
                                                "context_limit_applied": "trained"})
        with pytest.raises(L.SecondScoredRow):
            led.begin_attempt(kx)


def test_exceeds_row_must_carry_a_count_above_the_model_context(tmp_path):
    key = L.RunKey("D", "B2", 1)
    with fresh(tmp_path) as led:
        led.begin_attempt(key)
        with pytest.raises(ValueError, match="prompt_tokens"):
            rec(led, key, "exceeds_model_context", exceeds_row(100))
        rec(led, key, "exceeds_model_context", exceeds_row())
        assert led.terminal(key) == "exceeds_model_context"


def test_serving_mismatch_on_append_is_refused(tmp_path):
    key = L.RunKey("G", "C1", 1)
    with fresh(tmp_path) as led:
        led.begin_attempt(key)
        other = S.ServingConfiguration.secondary_yarn(IDENT).as_header_dict()
        with pytest.raises(L.LedgerBoundToAnotherConfig):
            rec(led, key, "ok", ok_row(), serving=other)


# --------------------------------------------------------------------------
# Durability and the lock
# --------------------------------------------------------------------------


def test_torn_final_line_is_recovered_and_logged(tmp_path):
    key = L.RunKey("G", "C1", 1)
    with fresh(tmp_path) as led:
        led.begin_attempt(key); rec(led, key, "ok", ok_row())
    p = tmp_path / "ledger.jsonl"
    with p.open("ab") as fh:
        fh.write(b'{"record": "run", "arm": "G", "question": "A", "repeat": 1, "outc')   # killed mid-line
    with fresh(tmp_path) as led:
        assert led.terminal(key) == "ok"
        assert [r for r in led.rows if r.get("record") == "event" and r["kind"] == "recovered_torn_tail"]
    assert all(json.loads(l) for l in p.read_text().splitlines())


def test_interior_corruption_is_rejected(tmp_path):
    key = L.RunKey("G", "C1", 1)
    with fresh(tmp_path) as led:
        led.begin_attempt(key); rec(led, key, "ok", ok_row())
    p = tmp_path / "ledger.jsonl"
    lines = p.read_text().splitlines()
    lines[1] = lines[1][:20]                                   # torn in the MIDDLE
    p.write_text("\n".join(lines) + "\n")
    with pytest.raises(L.LedgerCorrupt, match="line 2"):
        fresh(tmp_path)


def test_second_writer_is_refused_while_the_first_holds_the_lock(tmp_path):
    with fresh(tmp_path):
        script = textwrap.dedent(f"""
            import sys; sys.path.insert(0, {str(REPO_ROOT)!r})
            from scripts.research.arms849 import ledger as L
            from scripts.research.arms849 import serving as S
            b = L.Binding.from_environment({str(DEFAULT_CORPUS)!r}, S.ServingConfiguration.primary(
                S.ServingIdentity("gguf", "sha256:img", "emb", "tok", "c" * 64)).as_header_dict(), "trained",
                "c0ffee", "export-sha", "a" * 64, "b" * 64, "c" * 64, repo_root={str(REPO_ROOT)!r},
                model_context_tokens=S.TRAINED_CONTEXT)
            try:
                L.open_ledger({str(tmp_path / 'ledger.jsonl')!r}, b, 7, 72); print("OPENED")
            except L.LedgerLocked as e:
                print("LOCKED", e)
        """)
        out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120)
        assert "LOCKED" in out.stdout, out.stdout + out.stderr
        assert str(os.getpid()) in out.stdout
    # released on close: a new opener succeeds
    with fresh(tmp_path):
        pass


# --------------------------------------------------------------------------
# summarise — never a non-scored cell
# --------------------------------------------------------------------------


def test_summarise_sums_ok_only_and_counts_the_rest(tmp_path):
    with fresh(tmp_path) as led:
        k1, k2, k3 = L.RunKey("D", "C1", 1), L.RunKey("D", "C1", 2), L.RunKey("D", "B2", 1)
        led.begin_attempt(k1); rec(led, k1, "ok", {**ok_row(50_000, "D"), "cache_state": "cold"})
        led.begin_attempt(k2); rec(led, k2, "ok", {**ok_row(52_000, "D"), "cache_state": "warm", "cache_read_tokens": 40_000})
        led.begin_attempt(k3); rec(led, k3, "exceeds_model_context", exceeds_row())
        s = led.summarise()
    c1, b2 = s[("D", "C1")], s[("D", "B2")]
    assert c1.n_scored == 2 and c1.mean_assembled_tokens == 51_000 and c1.range_assembled_tokens == (50_000, 52_000)
    assert c1.mean_prompt_tokens == 51_300 and c1.range_prompt_tokens == (50_300, 52_300)
    assert b2.range_prompt_tokens is None
    assert c1.cold == 1 and c1.warm == 1 and c1.cache_read_tokens == 40_000
    assert c1.cache_write_tokens == 50_300 + 52_300 and c1.uncached_tokens == 50_300 + 52_300
    assert c1.counts == {} and c1.attempts == 2
    assert b2.n_scored == 0 and b2.mean_assembled_tokens is None and b2.counts == {"exceeds_model_context": 1}


def test_halt_input_is_visible_after_three_errors(tmp_path):
    with fresh(tmp_path) as led:
        k = L.RunKey("G", "C1", 1)
        for _ in range(3):
            led.begin_attempt(k); rec(led, k, "error", err_row("down"))
        assert led.has_terminal_error("G", 1) == ["C1"]


def test_calibration_needs_all_eight_g_repeat1_scored_and_is_written_once(tmp_path):
    with fresh(tmp_path) as led:
        with pytest.raises(ValueError, match="unscored"):
            led.write_calibration({"r_k": 12})
        score_all_g_repeat1(led)
        led.write_calibration({"r_k": 12, "parity": "ok"})
        assert led.calibration()["r_k"] == 12
        with pytest.raises(ValueError, match="once"):
            led.write_calibration({"r_k": 13})


def test_three_interrupted_attempts_are_terminal_error(tmp_path):
    """Codex WP03 c1: attempts that died before recording must still exhaust the key."""
    key = L.RunKey("D", "E1", 2)
    for _ in range(3):
        with fresh(tmp_path) as led:
            led.begin_attempt(key)                  # dies before any run row
    with fresh(tmp_path) as led:
        assert led.terminal(key) == "error"
        assert key not in led.pending_keys(L.plan_keys())
        assert led.has_terminal_error("D", 2) == ["E1"]
        with pytest.raises(L.AttemptsExhausted):
            led.begin_attempt(key)


def test_payload_cannot_carry_ledger_authored_fields(tmp_path):
    key = L.RunKey("G", "C1", 1)
    with fresh(tmp_path) as led:
        led.begin_attempt(key)
        for bad in ({"outcome": "ok"}, {"attempt": 99}, {"arm": "D"}, {"serving": {}}, {"record": "header"}):
            with pytest.raises(ValueError, match="ledger-authored"):
                rec(led, key, "error", {"error": "x", **bad})
        row = rec(led, key, "error", err_row("x"))
        assert row["attempt"] == 1 and row["outcome"] == "error" and row["serving"] == SERVING


def test_one_result_per_attempt(tmp_path):
    key = L.RunKey("R", "A", 1)
    with fresh(tmp_path) as led:
        calibrated(led)
        led.begin_attempt(key); rec(led, key, "error", err_row("1"))
        with pytest.raises(ValueError, match="already has a result"):
            rec(led, key, "error", err_row("2"))
        led.begin_attempt(key); rec(led, key, "ok", ok_row(arm="R"))
    rows = [json.loads(l) for l in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert [r["attempt"] for r in rows if r["record"] == "run" and r["arm"] == "R"] == [1, 2]


def test_serving_is_required_and_stored_on_every_run_row(tmp_path):
    key = L.RunKey("G", "C1", 1)
    with fresh(tmp_path) as led:
        led.begin_attempt(key)
        with pytest.raises(TypeError):
            led.record(key, "error", err_row("x"))   # type: ignore[call-arg]
        with pytest.raises(L.LedgerBoundToAnotherConfig):
            rec(led, key, "error", err_row("x"), serving={**SERVING, "n_ctx": 1})
        assert rec(led, key, "error", err_row("x"))["serving"] == SERVING


# The contract, restated INDEPENDENTLY of the implementation's tuples (Codex c3): the
# data-model.md "Row run" fields marked `ok` / all, plus G's arm field.
CONTRACT_OK_FIELDS = (
    "ask_time", "elapsed_s", "prompt_tokens", "client_prompt_tokens", "assembled_context_tokens",
    "output_tokens", "finish_reason", "cache_read_tokens", "uncached_tokens", "cache_write_tokens",
    "cache_state", "cache_fraction", "prefill_s", "generation_s", "generation_tok_s", "peak_gtt_gib",
    "assembled_context_sha256", "seed", "text", "plan",
    "events_loaded", "nodes_loaded", "edges_loaded", "links_loaded", "falkordb_rss_peak_mib",
)


def test_contract_field_list_matches_the_implementation():
    impl = set(L.SCORED_ROW_FIELDS) | set(L.RUN_ROW_ALWAYS) | set(L.SCORED_ARM_FIELDS["G"])
    assert impl == set(CONTRACT_OK_FIELDS)


@pytest.mark.parametrize("missing", CONTRACT_OK_FIELDS)
def test_scored_row_missing_telemetry_is_refused(tmp_path, missing):
    """Every field data-model.md marks 'row refused if absent' — list derived from the contract."""
    key = L.RunKey("G", "C1", 1)
    with fresh(tmp_path) as led:
        led.begin_attempt(key)
        row = ok_row(); del row[missing]
        with pytest.raises(ValueError, match="telemetry"):
            rec(led, key, "ok", row)
        with pytest.raises(ValueError, match="cache_state"):
            rec(led, key, "ok", {**ok_row(), "cache_state": "lukewarm"})
        with pytest.raises(ValueError, match="non-negative int"):
            rec(led, key, "ok", {**ok_row(), "cache_read_tokens": "0"})


def test_per_arm_required_fields_and_d_rows_carry_the_limit(tmp_path):
    with fresh(tmp_path) as led:
        kr, kd = L.RunKey("R", "A", 1), L.RunKey("D", "A", 1)
        calibrated(led)
        led.begin_attempt(kr)
        with pytest.raises(ValueError, match="r_g_ratio"):
            rec(led, kr, "ok", {k: v for k, v in ok_row(arm="R").items() if k != "r_g_ratio"})
        rec(led, kr, "ok", ok_row(arm="R"))
        led.begin_attempt(kd)
        with pytest.raises(ValueError, match="context_limit_applied"):
            rec(led, kd, "error", {"ask_time": ASK, "elapsed_s": 1.0, "error": "x", "peak_gtt_gib": 1.0})
        with pytest.raises(ValueError, match="context_limit_applied"):
            rec(led, kd, "error", {**err_row(arm="D"), "context_limit_applied": "guessed"})
        rec(led, kd, "error", err_row(arm="D"))
        with pytest.raises(ValueError, match="error"):
            led.begin_attempt(kd); rec(led, kd, "error", {"ask_time": ASK, "elapsed_s": 1.0, "peak_gtt_gib": 1.0, "context_limit_applied": "trained"})


def test_calibration_payload_cannot_forge_its_record_kind(tmp_path):
    with fresh(tmp_path) as led:
        score_all_g_repeat1(led)
        with pytest.raises(ValueError, match="ledger-authored"):
            led.write_calibration({"record": "event", "r_k": 1})
        led.write_calibration({"r_k": 12})
        with pytest.raises(ValueError, match="once"):
            led.write_calibration({"r_k": 13})


def test_closed_ledger_refuses_to_append(tmp_path):
    """Codex c2: an old handle must not write after another opener owns the lock."""
    key = L.RunKey("G", "C1", 1)
    led = fresh(tmp_path)
    led.close()
    with fresh(tmp_path) as owner:
        owner.begin_attempt(key)
        with pytest.raises(L.LedgerClosed):
            led.begin_attempt(key)
        with pytest.raises(L.LedgerClosed):
            led.event("stale")
    assert owner.attempts_for(key) == 1


def test_summarise_counts_attempt_only_exhausted_cells(tmp_path):
    key = L.RunKey("D", "E1", 2)
    for _ in range(3):
        with fresh(tmp_path) as led:
            led.begin_attempt(key)
    with fresh(tmp_path) as led:
        s = led.summarise()
    cell = s[("D", "E1")]
    assert cell.n_scored == 0 and cell.counts == {"error": 1} and cell.attempts == 3


def test_lock_init_failure_releases_the_descriptor(tmp_path, monkeypatch):
    def boom(fd, n):
        raise OSError("disk full")
    monkeypatch.setattr(L.os, "ftruncate", boom)
    with pytest.raises(OSError):
        fresh(tmp_path)
    monkeypatch.undo()
    with fresh(tmp_path):            # would raise LedgerLocked if the fd leaked
        pass


def test_unterminated_valid_final_line_is_terminated_not_concatenated(tmp_path):
    key = L.RunKey("G", "C1", 1)
    with fresh(tmp_path) as led:
        led.begin_attempt(key)
    p = tmp_path / "ledger.jsonl"
    p.write_bytes(p.read_bytes().rstrip(b"\n"))            # newline lost after a complete record
    with fresh(tmp_path) as led:
        assert led.attempts_for(key) == 1
        rec(led, key, "error", err_row("x"))
    lines = p.read_text().splitlines()
    assert all(json.loads(l) for l in lines)
    assert [r["kind"] for r in map(json.loads, lines) if r["record"] == "event"] == ["recovered_torn_tail"]


def test_torn_tail_recovery_truncates_in_place_preserving_the_prefix_bytes(tmp_path):
    key = L.RunKey("G", "C1", 1)
    with fresh(tmp_path) as led:
        led.begin_attempt(key); rec(led, key, "ok", ok_row())
    p = tmp_path / "ledger.jsonl"
    before = p.read_bytes(); ino = p.stat().st_ino
    with p.open("ab") as fh:
        fh.write(b'{"record": "run", "arm": "G", "question": "A"')
    with fresh(tmp_path):
        pass
    after = p.read_bytes()
    assert after.startswith(before) and p.stat().st_ino == ino


def test_failed_open_releases_the_lock(tmp_path):
    """Codex WP03 c1: a refused open must not leave the lock held for the process lifetime."""
    with fresh(tmp_path):
        pass
    with pytest.raises(L.LedgerBoundToAnotherConfig):
        fresh(tmp_path, limit_applied="permitted")
    with fresh(tmp_path):            # would raise LedgerLocked if the fd leaked
        pass


def test_plan_keys_are_protocol_ordered():
    keys = L.plan_keys()
    assert len(keys) == 72 and len(set(keys)) == 72
    assert [k.question for k in keys[:8]] == ["C1", "A", "F1", "B1", "E2", "E1", "F2", "B2"]
    assert [k.arm for k in keys[::24]] == ["G", "D", "R"]


def test_error_rows_carry_elapsed_and_peak_gtt(tmp_path):
    key = L.RunKey("G", "C1", 1)
    with fresh(tmp_path) as led:
        led.begin_attempt(key)
        for drop in ("elapsed_s", "peak_gtt_gib", "error"):
            row = err_row(); del row[drop]
            with pytest.raises(ValueError, match="telemetry"):
                rec(led, key, "error", row)
        rec(led, key, "error", err_row())


def test_truncated_is_derived_from_finish_reason_never_supplied(tmp_path):
    k1, k2 = L.RunKey("G", "C1", 1), L.RunKey("G", "A", 1)
    with fresh(tmp_path) as led:
        led.begin_attempt(k1)
        with pytest.raises(ValueError, match="ledger-authored"):
            rec(led, k1, "ok", {**ok_row(), "truncated": False})
        assert rec(led, k1, "ok", {**ok_row(), "finish_reason": "length"})["truncated"] is True
        led.begin_attempt(k2)
        assert rec(led, k2, "ok", ok_row())["truncated"] is False
        assert [r["truncated"] for r in led.grading_rows()] == [True, False]


def test_r_g_ratio_must_be_a_number_or_an_unavailable_reason(tmp_path):
    key = L.RunKey("R", "A", 1)
    with fresh(tmp_path) as led:
        calibrated(led)
        led.begin_attempt(key)
        for bad in (None, 0, -1.0, "unavailable", "unavailable:", "n/a"):
            with pytest.raises(ValueError, match="r_g_ratio"):
                rec(led, key, "ok", {**ok_row(arm="R"), "r_g_ratio": bad})
        rec(led, key, "ok", {**ok_row(arm="R"), "r_g_ratio": "unavailable: G repeat-1 median absent"})


def test_client_and_server_prompt_counts_must_agree_on_scored_rows(tmp_path):
    key = L.RunKey("G", "C1", 1)
    with fresh(tmp_path) as led:
        led.begin_attempt(key)
        with pytest.raises(ValueError, match="client_prompt_tokens"):
            rec(led, key, "ok", {**ok_row(), "client_prompt_tokens": 1})


def test_binding_is_snapshotted_at_open(tmp_path):
    """Codex c3: mutating the caller's dicts after open must not move the append target."""
    b = binding()
    led = L.open_ledger(tmp_path / "ledger.jsonl", b, blinding_seed=7, plan=72)
    try:
        b.serving["n_ctx"] = 1                       # caller mutates its own object
        key = L.RunKey("G", "C1", 1); led.begin_attempt(key)
        rec(led, key, "error", err_row())            # the ORIGINAL serving still matches
        with pytest.raises(L.LedgerBoundToAnotherConfig):
            rec(led, key, "error", err_row(), serving=b.serving)
    finally:
        led.close()


def test_mismatched_opener_does_not_repair_the_tail(tmp_path):
    key = L.RunKey("G", "C1", 1)
    with fresh(tmp_path) as led:
        led.begin_attempt(key); rec(led, key, "ok", ok_row())
    p = tmp_path / "ledger.jsonl"
    with p.open("ab") as fh:
        fh.write(b'{"record": "run", "torn')
    before = p.read_bytes()
    with pytest.raises(L.LedgerBoundToAnotherConfig):
        fresh(tmp_path, limit_applied="permitted")
    assert p.read_bytes() == before                  # refused opener changed nothing
    with fresh(tmp_path) as led:                     # the rightful opener recovers and logs it
        assert [r for r in led.rows if r.get("record") == "event" and r["kind"] == "recovered_torn_tail"]


def test_header_and_rows_are_exposed_as_copies_only(tmp_path):
    """Codex c4: editing what the ledger hands out must change nothing it checks against."""
    key = L.RunKey("G", "C1", 1)
    with fresh(tmp_path) as led:
        led.header.binding.serving["n_ctx"] = 1                   # edits a copy
        led.begin_attempt(key); rec(led, key, "ok", ok_row())      # the real serving still matches
        with pytest.raises(L.LedgerBoundToAnotherConfig):
            rec(led, key, "error", err_row(), serving={**SERVING, "n_ctx": 1})
        led.run_rows()[0]["outcome"] = "error"                     # edits a copy
        led.rows[-1]["outcome"] = "error"
        led.grading_rows()[0]["outcome"] = "error"
        with pytest.raises(L.SecondScoredRow):                     # I2 still holds
            led.begin_attempt(key)
        score_all_g_repeat1(led)
        led.write_calibration({"r_k": 12})
        led.calibration()["r_k"] = 99
        assert led.calibration()["r_k"] == 12


def test_summary_counts_every_non_scored_row_even_when_the_key_later_succeeds(tmp_path):
    key = L.RunKey("D", "C1", 1)
    with fresh(tmp_path) as led:
        led.begin_attempt(key); rec(led, key, "error", err_row(arm="D"))
        led.begin_attempt(key); rec(led, key, "ok", ok_row(arm="D"))
        s = led.summarise()[("D", "C1")]
    assert s.n_scored == 1 and s.counts == {"error": 1} and s.attempts == 2


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), -1.0, "12"], ids=["none", "nan", "inf", "neg", "str"])
def test_measurements_must_be_finite_non_negative_numbers(tmp_path, bad):
    """Codex c5: None/NaN/inf are a missing measurement wearing a value."""
    with fresh(tmp_path) as led:
        kg, kr = L.RunKey("G", "C1", 1), L.RunKey("R", "C1", 1)
        led.begin_attempt(kg)
        for f in ("prefill_s", "peak_gtt_gib", "falkordb_rss_peak_mib", "elapsed_s", "cache_fraction"):
            with pytest.raises(ValueError, match=f):
                rec(led, kg, "ok", {**ok_row(), f: bad})
        for f in ("peak_gtt_gib", "elapsed_s"):
            with pytest.raises(ValueError, match=f):
                rec(led, kg, "error", {**err_row(), f: bad})
        for text in ("", "   ", None):
            with pytest.raises(ValueError, match="error"):
                rec(led, kg, "error", {**err_row(), "error": text})
        calibrated(led)
        led.begin_attempt(kr)
        if isinstance(bad, float):
            with pytest.raises(ValueError, match="r_g_ratio"):
                rec(led, kr, "ok", {**ok_row(arm="R"), "r_g_ratio": bad})


@pytest.mark.parametrize("dropped", ["preflight_sha", "gate_host_sha", "gate_container_sha"])
def test_header_missing_a_gate_sha_is_refused(tmp_path, dropped):
    """Design-lead ruling (2026-09-25): the header binds all three gate records; a header
    without one is corrupt — never opened, never resumed (test c)."""
    with fresh(tmp_path):
        pass
    p = tmp_path / "ledger.jsonl"
    lines = p.read_text().splitlines()
    head = json.loads(lines[0]); del head[dropped]
    p.write_text("\n".join([json.dumps(head), *lines[1:]]) + "\n")
    with pytest.raises(L.LedgerCorrupt, match=dropped):
        fresh(tmp_path)


def test_binding_carries_the_two_gate_shas_and_refuses_on_each(tmp_path):
    with fresh(tmp_path):
        pass
    for field in ("gate_host_sha", "gate_container_sha"):
        with pytest.raises(L.LedgerBoundToAnotherConfig, match=field):
            fresh(tmp_path, **{field: "d" * 64})


@pytest.mark.parametrize("field", ["preflight_sha", "gate_host_sha", "gate_container_sha"])
@pytest.mark.parametrize("bad", [None, "", "g" * 64, "a" * 63, "A" * 64, 12, "a" * 64 + "\n", "\n" + "a" * 64, "a" * 64 + " "],
                         ids=["none", "empty", "nonhex", "short", "upper", "int", "trailing-newline", "leading-newline", "trailing-space"])
def test_gate_shas_are_validated_on_creation_and_on_resume(tmp_path, field, bad):
    """Codex c7: a required sha that is None, a placeholder or the wrong length is refused —
    at creation (from_environment) and on resume (a header carrying it is corrupt)."""
    cfg = S.ServingConfiguration.primary(IDENT)
    kw = {"preflight_sha": "a" * 64, "gate_host_sha": "b" * 64, "gate_container_sha": "c" * 64}
    kw[field] = bad
    with pytest.raises(ValueError, match=field):
        L.Binding.from_environment(DEFAULT_CORPUS, cfg.as_header_dict(), "trained", "c0ffee", "export-sha",
                                   kw["preflight_sha"], kw["gate_host_sha"], kw["gate_container_sha"],
                                   repo_root=REPO_ROOT, model_context_tokens=S.TRAINED_CONTEXT)
    with fresh(tmp_path):
        pass
    p = tmp_path / "ledger.jsonl"
    lines = p.read_text().splitlines()
    head = json.loads(lines[0]); head[field] = bad
    p.write_text("\n".join([json.dumps(head), *lines[1:]]) + "\n")
    with pytest.raises(L.LedgerCorrupt, match=field):
        fresh(tmp_path)


@pytest.mark.parametrize("field", ["preflight_sha", "gate_host_sha", "gate_container_sha"])
def test_open_ledger_validates_a_directly_constructed_binding(tmp_path, field):
    """Codex c8: Binding(**dict) skips from_environment; open_ledger must still refuse a bad sha
    BEFORE writing a header (a persisted bad header could never resume)."""
    b = L.Binding(**{**binding().as_dict(), field: None})
    with pytest.raises(ValueError, match=field):
        L.open_ledger(tmp_path / "ledger.jsonl", b, blinding_seed=7, plan=72)
    assert not (tmp_path / "ledger.jsonl").exists() or (tmp_path / "ledger.jsonl").stat().st_size == 0
    assert not (tmp_path / "ledger.jsonl.lock").exists() or True   # the lock file may exist; the fd is released:
    with fresh(tmp_path):                                          # a valid opener succeeds (no leaked lock)
        pass


# ---------------------------------------------------------------------------
# Opus fallback cycle 10 (Codex out of credits)
# ---------------------------------------------------------------------------


def test_corpus_binding_is_verified_not_computed(tmp_path):
    """The header binds the REGISTERED fingerprints; a missing or tampered file, or an empty
    directory, is refused at binding time — never stored as whatever happened to exist."""
    cfg = S.ServingConfiguration.primary(IDENT).as_header_dict()

    def bind(corpus_dir):
        return L.Binding.from_environment(corpus_dir, cfg, "trained", "c0ffee", "export-sha",
                                          "a" * 64, "b" * 64, "c" * 64, repo_root=REPO_ROOT,
                                          model_context_tokens=S.TRAINED_CONTEXT)

    from scripts.research.load_849_corpus import REGISTRATION
    assert bind(DEFAULT_CORPUS).corpus == REGISTRATION["files"]
    empty = tmp_path / "empty"; empty.mkdir()
    with pytest.raises(L.LedgerBoundToAnotherConfig, match="MISSING"):
        bind(empty)
    partial = tmp_path / "partial"; partial.mkdir()
    for name in REGISTRATION["files"]:
        (partial / name).write_bytes((DEFAULT_CORPUS / name).read_bytes())
    (partial / "stream.jsonl").write_bytes(b'{"ref": "x", "at": "2026-01-01"}\n')
    with pytest.raises(L.LedgerBoundToAnotherConfig, match="stream.jsonl"):
        bind(partial)
    # A directly constructed Binding with no corpus (or a partial one) is refused at open.
    with pytest.raises(L.LedgerBoundToAnotherConfig, match="registered corpus"):
        L.open_ledger(tmp_path / "l1.jsonl", binding(corpus={}), blinding_seed=7, plan=72)
    part = dict(REGISTRATION["files"]); part.pop("stream.jsonl")
    with pytest.raises(L.LedgerBoundToAnotherConfig, match="registered corpus"):
        L.open_ledger(tmp_path / "l2.jsonl", binding(corpus=part), blinding_seed=7, plan=72)


def test_limit_applied_is_validated_and_d_rows_must_agree_with_the_header(tmp_path):
    cfg = S.ServingConfiguration.primary(IDENT).as_header_dict()
    with pytest.raises(ValueError, match="limit_applied"):
        L.Binding.from_environment(DEFAULT_CORPUS, cfg, "banana", "c0ffee", "export-sha", "a" * 64, "b" * 64,
                                   "c" * 64, repo_root=REPO_ROOT, model_context_tokens=S.TRAINED_CONTEXT)
    with pytest.raises(ValueError, match="limit_applied"):
        L.open_ledger(tmp_path / "l.jsonl", binding(limit_applied="banana"), blinding_seed=7, plan=72)
    key = L.RunKey("D", "A", 1)
    with fresh(tmp_path) as led:                         # header bound to "trained"
        led.begin_attempt(key)
        with pytest.raises(ValueError, match="one limit per ledger"):
            rec(led, key, "ok", {**ok_row(arm="D"), "context_limit_applied": "permitted"})
        rec(led, key, "ok", {**ok_row(arm="D"), "context_limit_applied": "trained"})


def test_rows_are_the_same_on_a_fresh_and_a_resumed_ledger(tmp_path):
    key = L.RunKey("G", "C1", 1)
    with fresh(tmp_path) as led:
        led.begin_attempt(key); rec(led, key, "ok", ok_row())
        fresh_rows = led.rows
    with fresh(tmp_path) as led:
        assert led.rows == fresh_rows
    assert [r["record"] for r in fresh_rows] == ["attempt_start", "run"]
    assert fresh_rows[0]["record"] != "header"


def test_assembled_context_sha_must_be_a_string(tmp_path):
    key = L.RunKey("G", "C1", 1)
    with fresh(tmp_path) as led:
        led.begin_attempt(key)
        with pytest.raises(ValueError, match="STRING"):
            rec(led, key, "ok", {**ok_row(), "assembled_context_sha256": int("1" * 64)})
        with pytest.raises(ValueError, match="STRING"):
            rec(led, key, "ok", {**ok_row(), "assembled_context_sha256": b"1" * 64})
        rec(led, key, "ok", {**ok_row(), "assembled_context_sha256": "1" * 64})


def test_summarise_counts_an_in_flight_key_as_pending(tmp_path):
    key = L.RunKey("D", "F2", 2)
    with fresh(tmp_path) as led:
        led.begin_attempt(key)                           # in flight, nothing recorded yet
        s = led.summarise()[("D", "F2")]
        assert s.counts == {"pending": 1} and s.n_scored == 0
    with fresh(tmp_path) as led:
        led.begin_attempt(key); rec(led, key, "ok", {**ok_row(arm="D"), "context_limit_applied": "trained"})
        assert "pending" not in led.summarise()[("D", "F2")].counts


def test_r_ok_row_requires_the_calibration_record(tmp_path):
    key = L.RunKey("R", "C1", 1)
    with fresh(tmp_path) as led:
        led.begin_attempt(key)
        with pytest.raises(ValueError, match="calibration record first"):
            rec(led, key, "ok", ok_row(arm="R"))
        rec(led, key, "error", err_row("no k yet"))      # an error row needs no calibration
        calibrated(led)
        led.begin_attempt(key); rec(led, key, "ok", ok_row(arm="R"))


# ---------------------------------------------------------------------------
# Opus fallback cycle 11 minors + the ArmRefusal ruling (cycle 12)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dropped", ["blinding_seed", "plan", "started"])
def test_header_missing_its_own_field_is_ledger_corrupt_not_key_error(tmp_path, dropped):
    with fresh(tmp_path):
        pass
    path = tmp_path / "ledger.jsonl"
    lines = path.read_text().splitlines()
    header = json.loads(lines[0]); header.pop(dropped)
    path.write_text("\n".join([json.dumps(header, sort_keys=True), *lines[1:]]) + "\n")
    with pytest.raises(L.LedgerCorrupt, match=dropped):
        fresh(tmp_path)


def test_exceeds_row_needs_an_int_count_and_is_a_d_outcome_only(tmp_path):
    with fresh(tmp_path) as led:
        kd = L.RunKey("D", "B2", 1)
        led.begin_attempt(kd)
        for bad in ("400000", 400000.0, None, True):
            with pytest.raises(ValueError, match="int prompt_tokens"):
                rec(led, kd, "exceeds_model_context", {"ask_time": ASK, "elapsed_s": 1.0, "prompt_tokens": bad,
                                                        "context_limit_applied": "trained"})
        row = rec(led, kd, "exceeds_model_context", {"ask_time": ASK, "elapsed_s": 1.0, "prompt_tokens": 400_000,
                                                     "context_limit_applied": "trained"})
        assert type(row["prompt_tokens"]) is int
        kg = L.RunKey("G", "B2", 1)
        led.begin_attempt(kg)
        with pytest.raises(ValueError, match="D outcome only"):
            rec(led, kg, "exceeds_model_context", {"ask_time": ASK, "elapsed_s": 1.0, "prompt_tokens": 400_000})


@pytest.mark.parametrize("bad", [("XX", "C1", 1), ("G", "NOPE", 1), ("G", "C1", 0), ("G", "C1", 4), ("G", "C1", "1")],
                         ids=["arm", "question", "repeat0", "repeat4", "repeat-str"])
def test_run_key_is_validated_against_the_cell_domain(bad):
    with pytest.raises(ValueError):
        L.RunKey(*bad)


def test_non_json_payload_is_refused_and_record_returns_the_persisted_row(tmp_path):
    key = L.RunKey("G", "C1", 1)
    with fresh(tmp_path) as led:
        led.begin_attempt(key)
        with pytest.raises(ValueError, match="not JSON-serialisable"):
            rec(led, key, "ok", {**ok_row(), "plan": {"ids": {1, 2}}})
        with pytest.raises(ValueError, match="not JSON-serialisable"):
            rec(led, key, "error", {**err_row(), "detail": object()})
        assert led.run_rows() == []                          # nothing persisted by a refused append
        row = rec(led, key, "ok", {**ok_row(), "plan": {"ids": (1, 2)}})
        assert row["plan"]["ids"] == [1, 2]                  # the round-tripped row, as persisted
        assert row == led.run_rows()[-1]


def test_a_non_object_first_line_is_ledger_corrupt(tmp_path):
    with fresh(tmp_path):
        pass
    path = tmp_path / "ledger.jsonl"
    path.write_text('"hello"\n' + path.read_text())
    with pytest.raises(L.LedgerCorrupt, match="not a JSON object"):
        fresh(tmp_path)
    with fresh(tmp_path / "other") if False else pytest.raises(L.LedgerCorrupt, match="not a JSON object"):
        p2 = tmp_path / "l2.jsonl"
        with L.open_ledger(p2, binding(), blinding_seed=7, plan=72):
            pass
        p2.write_text(p2.read_text() + "[1, 2]\n")
        L.open_ledger(p2, binding(), blinding_seed=7, plan=72)


def test_model_context_tokens_must_be_a_positive_int(tmp_path):
    cfg = S.ServingConfiguration.primary(IDENT).as_header_dict()
    for bad in (0, -1, "262144", 262144.0):                # None means "use n_ctx" (tested below)
        with pytest.raises(ValueError, match="model_context_tokens"):
            L.Binding.from_environment(DEFAULT_CORPUS, cfg, "trained", "c0ffee", "export-sha", "a" * 64, "b" * 64,
                                       "c" * 64, repo_root=REPO_ROOT, model_context_tokens=bad)
    with pytest.raises(ValueError, match="model_context_tokens"):
        L.open_ledger(tmp_path / "l.jsonl", binding(model_context_tokens=0), blinding_seed=7, plan=72)
    b = L.Binding.from_environment(DEFAULT_CORPUS, {**cfg, "n_ctx": 393_216}, "permitted", "c0ffee", "export-sha",
                                   "a" * 64, "b" * 64, "c" * 64, repo_root=REPO_ROOT)
    assert b.model_context_tokens == 393_216                 # falls back to n_ctx, never to 0


def test_arm_refusal_error_row_is_terminal_on_the_first_attempt(tmp_path):
    """Design-lead ruling 2026-09-25 (contracts/arm-interface.md): a configuration refusal is never retried."""
    key = L.RunKey("D", "A", 2)
    with fresh(tmp_path) as led:
        led.begin_attempt(key)
        rec(led, key, "error", {**err_row(arm="D"), "error": "ArmRefusal: arm D was handed 4 loader links"})
        assert led.terminal(key) == "error" and led.attempts_for(key) == 1
        assert key not in led.pending_keys(L.plan_keys())
        with pytest.raises(L.SecondScoredRow, match="never retried"):
            led.begin_attempt(key)
        assert led.has_terminal_error("D", 2) == ["A"]
        assert led.summarise()[("D", "A")].counts == {"error": 1}
    with fresh(tmp_path) as led:                              # survives a resume
        assert led.terminal(key) == "error"
        with pytest.raises(L.SecondScoredRow):
            led.begin_attempt(key)
        other = L.RunKey("D", "A", 3)                         # an ordinary error IS retried
        led.begin_attempt(other); rec(led, other, "error", err_row("TimeoutError: llama", arm="D"))
        assert led.terminal(other) is None and led.begin_attempt(other) == 2


# --------------------------------------------------------------------------
# Codex cycle 14 — append I/O failure, resume re-validation, final null
# --------------------------------------------------------------------------


@pytest.mark.parametrize("stage", ["write", "fsync"])
def test_append_io_failure_poisons_the_ledger_and_reopen_reads_the_disk(tmp_path, monkeypatch, stage):
    """Codex WP03 c14: an fsync failure after a successful flush left the row on disk but absent
    from memory, so a retry recorded a second `ok` row and both averaged after resume. Any append
    I/O failure now poisons the ledger (writes refused, lock released); reopening re-reads the file.
    `write` fails before anything lands (the attempt is retried); `fsync` fails after the line
    reached the kernel (the row IS the result and a retry is refused)."""
    key = L.RunKey("G", "C1", 1)
    led = fresh(tmp_path)
    led.begin_attempt(key)
    armed = {"on": True}
    if stage == "write":
        real_open = pathlib.Path.open

        class Failing:
            def __init__(self, real): self.real = real
            def __enter__(self): return self
            def __exit__(self, *a): self.real.close()
            def write(self, s):
                if armed["on"]:
                    armed["on"] = False
                    raise OSError(5, "Input/output error")
                return self.real.write(s)
            def flush(self): self.real.flush()
            def fileno(self): return self.real.fileno()

        def fake_open(self, mode="r", *a, **k):
            fh = real_open(self, mode, *a, **k)
            return Failing(fh) if (self == led.path and mode == "a" and armed["on"]) else fh
        monkeypatch.setattr(pathlib.Path, "open", fake_open)
    else:
        real_fsync = os.fsync

        def fsync_once_fails(fd):
            if armed["on"]:
                armed["on"] = False
                raise OSError(28, "No space left on device")
            return real_fsync(fd)
        monkeypatch.setattr(L.os, "fsync", fsync_once_fails)
    with pytest.raises(L.LedgerWriteFailed, match="reopen the ledger"):
        rec(led, key, "ok", ok_row())
    assert led._lock_fd < 0                                    # the lock was released with the poisoning
    for attempt_write in (lambda: led.event("after_failure"),
                          lambda: led.begin_attempt(L.RunKey("G", "A", 1)),
                          lambda: rec(led, key, "ok", ok_row())):
        with pytest.raises(L.LedgerWriteFailed):               # every further write is refused, forever
            attempt_write()
    with fresh(tmp_path) as led2:                              # a reopen is possible and reads the FILE
        ok_rows = [r for r in led2.run_rows() if L.RunKey.of(r) == key and r["outcome"] == "ok"]
        if stage == "fsync":
            assert len(ok_rows) == 1 and led2.terminal(key) == "ok"
            with pytest.raises(L.SecondScoredRow):             # the retry cannot double-record
                led2.begin_attempt(key)
        else:
            assert ok_rows == [] and led2.terminal(key) is None and led2.attempts_for(key) == 1
            assert led2.begin_attempt(key) == 2                # the attempt is legitimately retried
            rec(led2, key, "ok", ok_row())
        assert sum(1 for r in led2.run_rows() if r["outcome"] == "ok") == 1
        assert led2.summarise()[("G", "C1")].n_scored == 1
    assert all(json.loads(line) for line in (tmp_path / "ledger.jsonl").read_text().splitlines())


def _rows_of(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def _write_rows(path: pathlib.Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))


def _persisted(tmp_path) -> pathlib.Path:
    """A legal ledger: G C1 1 ok; D A 1 exceeds; G A 1 error (retryable) — attempt_start rows included."""
    with fresh(tmp_path) as led:
        k = L.RunKey("G", "C1", 1); led.begin_attempt(k); rec(led, k, "ok", ok_row())
        d = L.RunKey("D", "A", 1); led.begin_attempt(d); rec(led, d, "exceeds_model_context", exceeds_row())
        e = L.RunKey("G", "A", 1); led.begin_attempt(e); rec(led, e, "error", err_row())
    return tmp_path / "ledger.jsonl"


def _find(rows, **match):
    return next(r for r in rows if all(r.get(k) == v for k, v in match.items()))


def _c_unknown_outcome(rows):
    _find(rows, record="run", arm="G", question="C1")["outcome"] = "banana"; return rows

def _c_r_ok_without_calibration(rows):
    a = dict(_find(rows, record="attempt_start", arm="G", question="C1")); a.update(arm="R"); rows.append(a)
    r = dict(_find(rows, record="run", arm="G", question="C1")); r.update(arm="R", r_g_ratio=1.0); rows.append(r); return rows

def _c_d_row_under_the_other_limit(rows):
    _find(rows, record="run", arm="D")["context_limit_applied"] = "permitted"; return rows

def _c_run_without_attempt_start(rows):
    r = dict(_find(rows, record="run", arm="G", question="C1")); r.update(question="F1"); rows.append(r); return rows

def _c_attempt_out_of_sequence(rows):
    _find(rows, record="attempt_start", arm="G", question="C1")["attempt"] = 2; return rows

def _c_second_ok_for_a_key(rows):
    a = dict(_find(rows, record="attempt_start", arm="G", question="C1")); a["attempt"] = 2; rows.append(a)
    r = dict(_find(rows, record="run", arm="G", question="C1")); r["attempt"] = 2; rows.append(r); return rows

def _c_unknown_record_kind(rows):
    rows.append({"record": "banana", "ts": rows[-1]["ts"]}); return rows

def _c_missing_telemetry(rows):
    del _find(rows, record="run", arm="G", question="C1")["text"]; return rows

def _c_truncated_disagrees(rows):
    _find(rows, record="run", arm="G", question="C1")["truncated"] = True; return rows

def _c_serving_differs(rows):
    _find(rows, record="run", arm="G", question="C1")["serving"] = {**SERVING, "n_ctx": 1}; return rows

def _c_retried_refusal(rows):
    _find(rows, record="run", arm="G", question="A")["error"] = "ArmRefusal: handed links"
    a = dict(_find(rows, record="attempt_start", arm="G", question="A")); a["attempt"] = 2; rows.append(a); return rows

def _c_exceeds_under_the_model_context(rows):
    _find(rows, record="run", arm="D")["prompt_tokens"] = 10; return rows

def _c_exceeds_on_a_g_key(rows):
    r = dict(_find(rows, record="run", arm="D")); r.update(arm="G", question="B2"); rows.append(r)
    a = dict(_find(rows, record="attempt_start", arm="D")); a.update(arm="G", question="B2"); rows.insert(len(rows) - 1, a); return rows

CORRUPTIONS = {f.__name__[3:]: f for f in (
    _c_unknown_outcome, _c_r_ok_without_calibration, _c_d_row_under_the_other_limit, _c_run_without_attempt_start,
    _c_attempt_out_of_sequence, _c_second_ok_for_a_key, _c_unknown_record_kind, _c_missing_telemetry,
    _c_truncated_disagrees, _c_serving_differs, _c_retried_refusal, _c_exceeds_under_the_model_context,
    _c_exceeds_on_a_g_key)}


@pytest.mark.parametrize("corruption", sorted(CORRUPTIONS))
def test_resume_refuses_persisted_rows_the_ledger_would_not_have_written(tmp_path, corruption):
    """Codex WP03 c14: resume accepted parsed rows without their invariants — outcome "banana", an R
    scored row without calibration, a D row under `permitted` beneath a `trained` header — and
    exposed them to grading and averaging. Every row is now replayed through the same checks
    record()/begin_attempt()/write_calibration() apply on write, in order, BEFORE any repair."""
    path = _persisted(tmp_path)
    rows = CORRUPTIONS[corruption](_rows_of(path))
    _write_rows(path, rows)
    before = path.read_bytes()
    with pytest.raises(L.LedgerCorrupt, match="on resume"):
        fresh(tmp_path)
    assert path.read_bytes() == before                         # refused, never "repaired"
    fd = os.open(path.with_suffix(".jsonl.lock"), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)             # the refused opener released the lock
    finally:
        os.close(fd)


def test_resume_replays_a_legal_ledger_unchanged(tmp_path):
    """The replay accepts everything the ledger itself writes, including a calibration record and an
    R ok row after it, and a resume adds nothing to the file."""
    with fresh(tmp_path) as led:
        calibrated(led)
        r = L.RunKey("R", "C1", 1); led.begin_attempt(r); rec(led, r, "ok", ok_row(arm="R"))
        d = L.RunKey("D", "C1", 1); led.begin_attempt(d); rec(led, d, "ok", ok_row(arm="D"))
        led.event("note", {"x": 1})
    path = tmp_path / "ledger.jsonl"; before = path.read_bytes()
    with fresh(tmp_path) as led:
        assert led.terminal(r) == "ok" and led.calibration()["r_k"] == 12
    assert path.read_bytes() == before


def test_a_final_null_line_is_corruption_not_a_torn_tail(tmp_path):
    """Codex WP03 c14: a complete `null\\n` parsed to None and was mistaken for a torn tail, then
    silently truncated; a parsed non-object is corruption like any other."""
    with fresh(tmp_path) as led:
        led.event("x")
    path = tmp_path / "ledger.jsonl"; before = path.read_bytes()
    path.write_bytes(before + b"null\n")
    with pytest.raises(L.LedgerCorrupt, match="not a JSON object"):
        fresh(tmp_path)
    assert path.read_bytes() == before + b"null\n"             # refused, not deleted
    path.write_bytes(before + b'{"record": "event", "kind": "y", "ts": "2026-09-25T00:00:00Z"')   # a REAL torn tail
    with fresh(tmp_path) as led:                                # is still recovered
        assert [r for r in led.rows if r.get("record") == "event" and r["kind"] == "recovered_torn_tail"]


# --------------------------------------------------------------------------
# Codex cycle 15 — no key coercion on replay, header-write failure type, event kind on write
# --------------------------------------------------------------------------


@pytest.mark.parametrize("row", [
    {"arm": "G", "question": "C1", "repeat": 1.9}, {"arm": "G", "question": "C1", "repeat": 1.0},
    {"arm": "G", "question": "C1", "repeat": "1"}, {"arm": "G", "question": "C1", "repeat": True},
    {"arm": 1, "question": "C1", "repeat": 1}, {"arm": "G", "question": None, "repeat": 1},
    {"arm": "G", "question": "C1"},
], ids=["float", "float-int", "str", "bool", "int-arm", "none-question", "missing-repeat"])
def test_run_key_of_never_coerces(row):
    """Codex WP03 c15: `int(1.9)` made a persisted repeat of 1.9 read as repeat 1, so an invalid cell
    satisfied the repeat-1 completion and calibration checks on resume."""
    with pytest.raises((TypeError, ValueError)):       # TypeError for the wrong type, ValueError for the domain
        L.RunKey.of(row)


def _c_fractional_repeat(rows):
    _find(rows, record="attempt_start", arm="G", question="C1")["repeat"] = 1.9
    _find(rows, record="run", arm="G", question="C1")["repeat"] = 1.9; return rows

def _c_float_attempt(rows):
    _find(rows, record="attempt_start", arm="G", question="C1")["attempt"] = 1.0
    _find(rows, record="run", arm="G", question="C1")["attempt"] = 1.0; return rows

def _c_empty_event_kind(rows):
    rows.append({"record": "event", "kind": "", "detail": None, "ts": rows[-1]["ts"]}); return rows


@pytest.mark.parametrize("corruption", ["fractional_repeat", "float_attempt", "empty_event_kind"])
def test_resume_refuses_coerced_keys_attempts_and_empty_event_kinds(tmp_path, corruption):
    path = _persisted(tmp_path)
    rows = {"fractional_repeat": _c_fractional_repeat, "float_attempt": _c_float_attempt,
            "empty_event_kind": _c_empty_event_kind}[corruption](_rows_of(path))
    _write_rows(path, rows); before = path.read_bytes()
    with pytest.raises(L.LedgerCorrupt, match="on resume"):
        fresh(tmp_path)
    assert path.read_bytes() == before


@pytest.mark.parametrize("stage", ["write", "fsync"])
def test_header_write_failure_is_ledger_write_failed_and_releases_the_lock(tmp_path, monkeypatch, stage):
    """Codex WP03 c15: a failure writing the FRESH header surfaced as OSError(EBADF) because open_ledger
    closed a descriptor _append had already closed; the promised type and message were lost."""
    armed = {"on": True}
    if stage == "fsync":
        real_fsync = os.fsync

        def fsync_once_fails(fd):
            if armed["on"]:
                armed["on"] = False; raise OSError(28, "No space left on device")
            return real_fsync(fd)
        monkeypatch.setattr(L.os, "fsync", fsync_once_fails)
    else:
        real_open = pathlib.Path.open

        class Failing:
            def __init__(self, real): self.real = real
            def __enter__(self): return self
            def __exit__(self, *a): self.real.close()
            def write(self, s):
                armed["on"] = False; raise OSError(5, "Input/output error")
            def flush(self): self.real.flush()
            def fileno(self): return self.real.fileno()

        def fake_open(self, mode="r", *a, **k):
            fh = real_open(self, mode, *a, **k)
            return Failing(fh) if (mode == "a" and armed["on"]) else fh
        monkeypatch.setattr(pathlib.Path, "open", fake_open)
    with pytest.raises(L.LedgerWriteFailed, match="reopen the ledger"):
        L.open_ledger(tmp_path / "ledger.jsonl", binding(), blinding_seed=7, plan=72)
    with fresh(tmp_path) as led:                               # the lock is free; the file is the truth
        assert led.rows == [] and (tmp_path / "ledger.jsonl").read_text().count("\n") == 1   # header only, either way


@pytest.mark.parametrize("bad", ["", "   ", None, 3, b"x"], ids=["empty", "blank", "none", "int", "bytes"])
def test_event_kind_must_be_a_non_empty_string_on_write(tmp_path, bad):
    """Codex WP03 c15: event("") persisted a row that the resume replay then refused, so the public
    writer could make an otherwise valid run unresumable."""
    with fresh(tmp_path) as led:
        with pytest.raises(ValueError, match="event kind"):
            led.event(bad)
        led.event("fine")
    with fresh(tmp_path) as led:
        assert [r["kind"] for r in led.rows if r.get("record") == "event"] == ["fine"]


# --------------------------------------------------------------------------
# Codex cycle 16 — exact header types, type-aware binding/serving equality
# --------------------------------------------------------------------------


@pytest.mark.parametrize("field,bad", [("plan", 72.9), ("plan", 72.0), ("plan", "72"), ("plan", True), ("plan", 0),
                                       ("blinding_seed", 7.9), ("blinding_seed", 7.0), ("blinding_seed", "7"),
                                       ("blinding_seed", True), ("started", 3), ("started", "")],
                         ids=lambda v: repr(v))
def test_persisted_header_int_fields_are_exact_types_never_coerced(tmp_path, field, bad):
    """Codex WP03 c16: Header.from_dict applied int(), so plan=72.9 / blinding_seed=7.9 resumed as 72 / 7
    and silently satisfied the binding; the seed fixes the grading ids, so its meaning changed."""
    with fresh(tmp_path):
        pass
    path = tmp_path / "ledger.jsonl"
    rows = _rows_of(path); rows[0][field] = bad; _write_rows(path, rows); before = path.read_bytes()
    with pytest.raises(L.LedgerCorrupt, match="header"):
        fresh(tmp_path)
    assert path.read_bytes() == before


@pytest.mark.parametrize("field,bad", [("plan", 72.0), ("plan", True), ("blinding_seed", 7.0), ("blinding_seed", "7")],
                         ids=lambda v: repr(v))
def test_header_creation_refuses_non_int_seed_and_plan(tmp_path, field, bad):
    kwargs = {"blinding_seed": 7, "plan": 72}; kwargs[field] = bad
    with pytest.raises(ValueError):
        L.open_ledger(tmp_path / "ledger.jsonl", binding(), **kwargs)
    with pytest.raises(ValueError):
        L.Header(binding=binding(), started="2026-09-25T00:00:00Z", **kwargs)


def test_persisted_binding_fields_are_type_checked_on_resume(tmp_path):
    """Codex WP03 c16: model_context_tokens=262144.0 passed the header comparison against 262144."""
    with fresh(tmp_path):
        pass
    path = tmp_path / "ledger.jsonl"
    for field, bad, exc in (("model_context_tokens", 262144.0, L.LedgerCorrupt), ("model_context_tokens", True, L.LedgerCorrupt),
                            ("limit_applied", 1, L.LedgerCorrupt), ("serving", "primary", L.LedgerCorrupt),
                            ("run_env_commit", 12, L.LedgerCorrupt)):
        rows = _rows_of(path); good = rows[0][field]; rows[0][field] = bad; _write_rows(path, rows)
        with pytest.raises(exc):
            fresh(tmp_path)
        rows[0][field] = good; _write_rows(path, rows)
    with fresh(tmp_path) as led:                                # restored: resumes
        assert led.rows == []


def test_serving_comparison_is_type_aware_on_resume_and_on_append(tmp_path):
    """Codex WP03 c16: a scored row with serving parallel=True was accepted under a header with parallel=1."""
    key_name = next(k for k, v in SERVING.items() if type(v) is int and v == 1) if any(
        type(v) is int and v == 1 for v in SERVING.values()) else None
    assert key_name is not None, "the serving header dict needs an int field equal to 1 for this probe"
    with fresh(tmp_path) as led:
        key = L.RunKey("G", "C1", 1); led.begin_attempt(key)
        with pytest.raises(L.LedgerBoundToAnotherConfig, match="type-aware"):
            rec(led, key, "ok", ok_row(), serving={**SERVING, key_name: True})
        with pytest.raises(L.LedgerBoundToAnotherConfig):
            rec(led, key, "ok", ok_row(), serving={**SERVING, key_name: 1.0})
        rec(led, key, "ok", ok_row())                            # the exact dict still records
    path = tmp_path / "ledger.jsonl"
    rows = _rows_of(path); rows[0]["serving"][key_name] = True; _write_rows(path, rows)
    with pytest.raises(L.LedgerBoundToAnotherConfig):            # persisted True vs live 1: a different configuration
        fresh(tmp_path)


def test_same_is_type_aware_at_every_level():
    assert L._same({"a": [1, {"b": 2}]}, {"a": [1, {"b": 2}]})
    assert not L._same(1, True) and not L._same(1, 1.0) and not L._same([1], (1,)) and not L._same({"a": 1}, {"a": True})
    assert not L._same({"a": 1}, {"a": 1, "b": 2}) and not L._same([1, 2], [1]) and not L._same("1", 1)
