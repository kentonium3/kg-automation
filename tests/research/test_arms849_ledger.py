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


def binding(**over) -> L.Binding:
    cfg = S.ServingConfiguration.primary(IDENT)
    b = L.Binding.from_environment(DEFAULT_CORPUS, cfg.as_header_dict(), "trained", "c0ffee",
                                   "export-sha", "preflight-sha", repo_root=REPO_ROOT,
                                   model_context_tokens=S.TRAINED_CONTEXT)
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


@pytest.mark.parametrize("field", sorted(L.Binding.__dataclass_fields__))
def test_resume_refuses_on_every_binding_field(tmp_path, field):
    """Parametrised over the dataclass so a new field cannot be added uncompared."""
    with fresh(tmp_path):
        pass
    current = binding().as_dict()[field]
    if isinstance(current, dict):
        changed = {**current, "__probe__": "x"}
    elif isinstance(current, int):
        changed = current + 1
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
        with pytest.raises(L.SecondScoredRow):
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
        led.begin_attempt(key); rec(led, key, "error", err_row("transient"))
        led.begin_attempt(key); rec(led, key, "ok", ok_row(arm="R"))
        assert led.terminal(key) == "ok"
        with pytest.raises(L.SecondScoredRow):
            led.begin_attempt(key)


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
                "c0ffee", "export-sha", "preflight-sha", repo_root={str(REPO_ROOT)!r},
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
        with pytest.raises(L.SecondScoredRow):
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
        led.begin_attempt(key); rec(led, key, "error", err_row("1"))
        with pytest.raises(ValueError, match="already has a result"):
            rec(led, key, "error", err_row("2"))
        led.begin_attempt(key); rec(led, key, "ok", ok_row(arm="R"))
    rows = [json.loads(l) for l in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert [r["attempt"] for r in rows if r["record"] == "run"] == [1, 2]


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
        fresh(tmp_path, limit_applied="configured")
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
        fresh(tmp_path, limit_applied="configured")
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
