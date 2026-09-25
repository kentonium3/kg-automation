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

IDENT = S.ServingIdentity("gguf", "sha256:img", "emb", "tok")


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


def ok_row(tokens=1000):
    return {"assembled_context_tokens": tokens, "prompt_tokens": tokens + 300, "cache_read_tokens": 0,
            "uncached_tokens": tokens + 300, "cache_state": "cold", "text": "x"}


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
        led.begin_attempt(key); led.record(key, "ok", ok_row())
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
            led.record(key, "error", {"error": "boom"})
        for n in (1, 2, 3):
            assert led.begin_attempt(key) == n
            led.record(key, "error", {"error": f"boom {n}"})
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
        led.begin_attempt(key); led.record(key, "error", {"error": "transient"})
        led.begin_attempt(key); led.record(key, "ok", ok_row())
        assert led.terminal(key) == "ok"
        with pytest.raises(L.SecondScoredRow):
            led.begin_attempt(key)


def test_exceeds_row_must_carry_a_count_above_the_model_context(tmp_path):
    key = L.RunKey("D", "B2", 1)
    with fresh(tmp_path) as led:
        led.begin_attempt(key)
        with pytest.raises(ValueError, match="prompt_tokens"):
            led.record(key, "exceeds_model_context", {"prompt_tokens": 100})
        led.record(key, "exceeds_model_context", {"prompt_tokens": 362_996})
        assert led.terminal(key) == "exceeds_model_context"


def test_serving_mismatch_on_append_is_refused(tmp_path):
    key = L.RunKey("G", "C1", 1)
    with fresh(tmp_path) as led:
        led.begin_attempt(key)
        other = S.ServingConfiguration.secondary_yarn(IDENT).as_header_dict()
        with pytest.raises(L.LedgerBoundToAnotherConfig):
            led.record(key, "ok", ok_row(), serving=other)


# --------------------------------------------------------------------------
# Durability and the lock
# --------------------------------------------------------------------------


def test_torn_final_line_is_recovered_and_logged(tmp_path):
    key = L.RunKey("G", "C1", 1)
    with fresh(tmp_path) as led:
        led.begin_attempt(key); led.record(key, "ok", ok_row())
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
        led.begin_attempt(key); led.record(key, "ok", ok_row())
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
                S.ServingIdentity("gguf", "sha256:img", "emb", "tok")).as_header_dict(), "trained",
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
        led.begin_attempt(k1); led.record(k1, "ok", {**ok_row(50_000), "cache_state": "cold"})
        led.begin_attempt(k2); led.record(k2, "ok", {**ok_row(52_000), "cache_state": "warm", "cache_read_tokens": 40_000})
        led.begin_attempt(k3); led.record(k3, "exceeds_model_context", {"prompt_tokens": 362_996})
        s = led.summarise()
    c1, b2 = s[("D", "C1")], s[("D", "B2")]
    assert c1.n_scored == 2 and c1.mean_assembled_tokens == 51_000 and c1.range_assembled_tokens == (50_000, 52_000)
    assert c1.cold == 1 and c1.warm == 1 and c1.cache_read_tokens == 40_000
    assert b2.n_scored == 0 and b2.mean_assembled_tokens is None and b2.counts["exceeds_model_context"] == 1


def test_calibration_is_written_once_and_halt_input_is_visible(tmp_path):
    with fresh(tmp_path) as led:
        k = L.RunKey("G", "C1", 1)
        for _ in range(3):
            led.begin_attempt(k); led.record(k, "error", {"error": "down"})
        assert led.has_terminal_error("G", 1) == ["C1"]
        led.write_calibration({"r_k": 12, "parity": "ok"})
        assert led.calibration()["r_k"] == 12
        with pytest.raises(ValueError, match="once"):
            led.write_calibration({"r_k": 13})


def test_plan_keys_are_protocol_ordered():
    keys = L.plan_keys()
    assert len(keys) == 72 and len(set(keys)) == 72
    assert [k.question for k in keys[:8]] == ["C1", "A", "F1", "B1", "E2", "E1", "F2", "B2"]
    assert [k.arm for k in keys[::24]] == ["G", "D", "R"]
