"""Gates, preflight and samplers (WP04 T020): every gate proven to fail on its injected defect.

The forbidden words are assembled from parts so this file does not carry them.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import socket
import sys
import time

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.research.arms849 import gates as G
from scripts.research.arms849 import litscan
from scripts.research.arms849 import preflight as P
from scripts.research.arms849 import prompt as prompt_mod
from scripts.research.arms849 import questions as questions_mod
from scripts.research.arms849 import sampler as SM
from scripts.research.load_849_corpus import DEFAULT_CORPUS, REGISTRATION

CORPUS = pathlib.Path(os.environ.get("ARMS849_CORPUS", str(DEFAULT_CORPUS)))
CACHE = pathlib.Path(os.environ.get("ARMS849_CACHE", str(REPO_ROOT / "build" / "849-cache")))
needs_corpus = pytest.mark.skipif(not (CORPUS / "stream.jsonl").exists(), reason="rendered corpus absent")
FORBIDDEN = ("or" + "acle", "se" + "ed/", "trace" + "ability")


def _export_like(dest: pathlib.Path) -> pathlib.Path:
    """An export-shaped run root: the bound code files in their layout, no excluded material,
    with a manifest whose content_sha is the REAL hash of those bytes."""
    import shutil

    from scripts.research.arms849.ledger import BOUND_CODE_GLOBS
    from scripts.research.arms849.substrate import content_manifest_sha
    for pattern in BOUND_CODE_GLOBS:
        for src in REPO_ROOT.glob(pattern):
            target = dest / src.relative_to(REPO_ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
    (dest / ".export-manifest.json").write_text(json.dumps({"source_commit": "abc", "content_sha": content_manifest_sha(dest)}))
    return dest


def _template_sha() -> str:
    from scripts.research.arms849.serving import Tokenizer
    try:
        return Tokenizer(CACHE / "qwen-tokenizer").chat_template_sha256()
    except RuntimeError:
        return ""


TEMPLATE_SHA = _template_sha()          # once, at import — before any test monkeypatches Tokenizer


def _closed_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    return port


# ---------------------------------------------------------------------------
# preflight
# ---------------------------------------------------------------------------


def _fake_checker(passed: bool):
    return lambda name: P.GateOutcome(name, passed, 0 if passed else 1, "fake", 0.01)


@needs_corpus
def test_preflight_writes_a_signed_record_binding_everything(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "_run_checker", _fake_checker(True))
    manifest = tmp_path / ".export-manifest.json"
    manifest.write_text(json.dumps({"source_commit": "abc", "content_sha": "d" * 64, "excludes": []}))
    out = tmp_path / "preflight.json"
    rec = P.run_preflight(REPO_ROOT, CORPUS, manifest, out, cache_dir=CACHE)
    payload = P.load_preflight(out)                       # verifies its own sha
    assert [g["name"] for g in payload["gates"]] == list(P.checkers()) and all(g["passed"] for g in payload["gates"])
    assert set(payload["corpus"]) == set(REGISTRATION["files"])
    assert payload["prompt_hash"] == prompt_mod.REGISTERED_DIGEST
    assert payload["question_manifest_sha"] == questions_mod.MANIFEST_DIGEST
    assert payload["export_content_sha"] == "d" * 64 and payload["export_source_commit"] == "abc"
    assert len(payload["chat_template_sha256"]) == 64 and payload["rubric_commit"] == P.RUBRIC_COMMIT
    assert len(payload["preflight_sha"]) == 64 and "extra" in payload
    assert rec.record_lines_digest == payload["record_lines_digest"]


@needs_corpus
def test_preflight_refuses_when_a_checker_fails_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "_run_checker", _fake_checker(False))
    manifest = tmp_path / "m.json"; manifest.write_text(json.dumps({"source_commit": "abc", "content_sha": "d" * 64}))
    with pytest.raises(P.PreflightRefused, match="gate"):
        P.run_preflight(REPO_ROOT, CORPUS, manifest, tmp_path / "preflight.json", cache_dir=CACHE)
    assert not (tmp_path / "preflight.json").exists()


@pytest.mark.parametrize("shape", ["absent", "empty", "incomplete"])
def test_vacuous_pass_guard_refuses_absent_empty_or_incomplete_reference_dir(tmp_path, monkeypatch, shape):
    """T016's whole point: the checkers pass for the wrong reason when the reference is absent —
    exercised on a REAL directory shape under a temp root, with the data file re-pointed."""
    root = REPO_ROOT; ref = REPO_ROOT / "build" / f"_guard_probe_{shape}"
    shutil.rmtree(ref, ignore_errors=True)
    if shape != "absent":
        ref.mkdir(parents=True)
    if shape == "incomplete":
        for f in P.REFERENCE_FILES[:-1]:
            (ref / f).write_text("x: 1\n")
    data = tmp_path / "export-excludes.txt"; data.write_text(f"build/_guard_probe_{shape}/\nkitty-specs/\n")
    monkeypatch.setattr(P, "EXCLUDES_FILE", data)
    calls = []
    monkeypatch.setattr(P, "_run_checker", lambda name: calls.append(name) or _fake_checker(True)(name))
    with pytest.raises(P.PreflightRefused, match="vacuously"):
        P.run_preflight(REPO_ROOT, CORPUS, tmp_path / "m.json", tmp_path / "preflight.json", cache_dir=CACHE)
    assert calls == []                                     # refused BEFORE running anything
    # and the complete shape passes the guard (the checkers then run)
    for f in P.REFERENCE_FILES:
        ref.mkdir(parents=True, exist_ok=True); (ref / f).write_text("x: 1\n")
    assert P.reference_dir(root) == ref
    shutil.rmtree(ref, ignore_errors=True)


def test_empty_or_headless_data_file_refuses(tmp_path, monkeypatch):
    """Design lead 02:54Z: the guard fails when the data file is empty or its first entry is not a dir."""
    for body in ("", "# only comments\n", "docs/design/research/849-traceability.md\n"):
        data = tmp_path / "x.txt"; data.write_text(body)
        monkeypatch.setattr(P, "EXCLUDES_FILE", data)
        with pytest.raises(P.PreflightRefused):
            P.reference_prefix()


@needs_corpus
def test_preflight_refuses_a_checkout_or_corpus_the_checkers_cannot_vouch_for(tmp_path, monkeypatch):
    """Codex c3: the checkers inspect their own checkout and default corpus; overrides are refused."""
    monkeypatch.setattr(P, "_run_checker", _fake_checker(True))
    with pytest.raises(P.PreflightRefused, match="own checkout"):
        P.run_preflight(tmp_path, CORPUS, tmp_path / "m.json", tmp_path / "p.json", cache_dir=CACHE)
    with pytest.raises(P.PreflightRefused, match="default corpus"):
        P.run_preflight(REPO_ROOT, tmp_path / "corpus", tmp_path / "m.json", tmp_path / "p.json", cache_dir=CACHE)


@needs_corpus
def test_preflight_refuses_without_the_tokenizer_cache(tmp_path, monkeypatch):
    """Design lead MAJOR: no chat template sha → no preflight."""
    monkeypatch.setattr(P, "_run_checker", _fake_checker(True))
    manifest = tmp_path / "m.json"; manifest.write_text(json.dumps({"source_commit": "abc", "content_sha": "d" * 64}))
    with pytest.raises(P.PreflightRefused, match="chat template"):
        P.run_preflight(REPO_ROOT, CORPUS, manifest, tmp_path / "p.json", cache_dir=tmp_path / "no-cache")
    assert not (tmp_path / "p.json").exists()


def test_tampered_preflight_record_is_refused(tmp_path):
    payload = {"gates": [], "corpus": {}, "preflight_sha": "0" * 64}
    p = tmp_path / "preflight.json"; p.write_text(json.dumps(payload))
    with pytest.raises(P.PreflightRefused, match="preflight_sha"):
        P.load_preflight(p)


def test_all_four_real_checkers_import_and_expose_main():
    """Codex c2 BLOCKER: the fourth checker's module name is derived from the data file; every
    name must resolve to a real module with main()."""
    import importlib
    names = P.checkers()
    assert len(names) == 4 and names[0].endswith("check_849_seed") and names[2].endswith("check_849_freeze")
    for name in names:
        mod = importlib.import_module(name)
        assert callable(getattr(mod, "main", None)), name
    assert FORBIDDEN[0] in names[1]                        # the data-derived one


def test_preflight_record_with_an_empty_or_partial_gate_list_is_refused(tmp_path, monkeypatch):
    """Codex c2 BLOCKER: a re-signed record with gates=[] must not pass."""
    monkeypatch.setattr(P, "_run_checker", _fake_checker(True))
    env = _env(tmp_path, run_root=_export_like(tmp_path / "export"))
    env.export_manifest_path = env.run_root / ".export-manifest.json"
    P.run_preflight(REPO_ROOT, CORPUS, env.export_manifest_path, env.preflight_path, cache_dir=CACHE)
    payload = json.loads(env.preflight_path.read_text())
    for gates in ([], payload["gates"][:3], [{**payload["gates"][0], "exit_code": 1}] + payload["gates"][1:],
                  [{**g, "passed": "yes"} for g in payload["gates"]]):
        bad = {**payload, "gates": gates}; bad["preflight_sha"] = P.preflight_sha(bad)
        env.preflight_path.write_text(json.dumps(bad))
        ok, detail = G.preflight_present_and_matching(env)
        assert not ok and ("required" in detail or "did not pass" in detail), detail


# ---------------------------------------------------------------------------
# in-container gates
# ---------------------------------------------------------------------------


def _env(tmp_path, **over) -> G.GateEnv:
    cache = tmp_path / "cache"; (cache / "qwen-tokenizer").mkdir(parents=True); (cache / "fastembed").mkdir()
    base = {"run_root": tmp_path / "work", "corpus_dir": CORPUS, "cache_dir": cache,
            "preflight_path": tmp_path / "preflight.json", "export_manifest_path": tmp_path / "work" / ".export-manifest.json",
            "excluded_prefixes": ("docs/design/research/849-synthesis/" + FORBIDDEN[0] + "/",),
            "forbidden_words": FORBIDDEN, "outbound_probe": ("127.0.0.1", _closed_port()),
            "expected_chat_template_sha256": TEMPLATE_SHA,
            "self_test": lambda: {"passed": True, "checks": {"x": True}},
            "health": lambda n, r: type("S", (), {"falkordb_ok": True, "llama_ok": True, "n_ctx": n, "rope": r})()}
    base.update(over)
    (tmp_path / "work").mkdir(exist_ok=True)
    return G.GateEnv(**base)


@needs_corpus
def test_preflight_gate_matches_this_environment_and_fails_on_one_flipped_fingerprint(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "_run_checker", _fake_checker(True))
    env = _env(tmp_path, run_root=_export_like(tmp_path / "export"))
    env.export_manifest_path = env.run_root / ".export-manifest.json"
    P.run_preflight(REPO_ROOT, CORPUS, env.export_manifest_path, env.preflight_path, cache_dir=CACHE)
    ok, detail = G.preflight_present_and_matching(env)
    assert ok, detail
    # a manifest whose claim is fictitious must NOT pass: the gate hashes the bytes itself
    forged = json.loads(env.export_manifest_path.read_text()); forged["content_sha"] = "e" * 64
    env.export_manifest_path.write_text(json.dumps(forged))
    payload = json.loads(env.preflight_path.read_text()); payload["export_content_sha"] = "e" * 64
    payload["preflight_sha"] = P.preflight_sha(payload); env.preflight_path.write_text(json.dumps(payload))
    ok, detail = G.preflight_present_and_matching(env)
    assert not ok and "content sha" in detail
    env.export_manifest_path.write_text(json.dumps({**forged, "content_sha": json.loads(env.export_manifest_path.read_text())["content_sha"]}))
    payload = json.loads(env.preflight_path.read_text())
    payload["corpus"]["stream.jsonl"] = "f" * 64
    payload["preflight_sha"] = P.preflight_sha(payload)     # re-signed: the mismatch itself must be caught
    env.preflight_path.write_text(json.dumps(payload))
    ok, detail = G.preflight_present_and_matching(env)
    assert not ok and "stream.jsonl" in detail
    # the chat template sha must match the serving configuration's (design-lead MAJOR)
    env2 = G.GateEnv(**{**env.__dict__, "expected_chat_template_sha256": "f" * 64})
    payload = json.loads(env.preflight_path.read_text()); payload["corpus"]["stream.jsonl"] = env.corpus_dir and P.load_preflight(env.preflight_path)["corpus"]["stream.jsonl"]
    env.preflight_path.write_text(json.dumps(payload))
    ok, detail = G.preflight_present_and_matching(env2)
    assert not ok and "chat_template_sha256" in detail


def test_preflight_gate_fails_when_absent(tmp_path):
    ok, detail = G.preflight_present_and_matching(_env(tmp_path))
    assert not ok and "absent" in detail


def test_prompt_digest_fails_on_one_changed_character(monkeypatch):
    assert G.prompt_digest(None)[0]
    monkeypatch.setattr(prompt_mod, "REGISTERED_TEXT", prompt_mod.REGISTERED_TEXT.replace("material", "materiel", 1))
    assert not G.prompt_digest(None)[0]


def test_question_manifest_fails_on_one_changed_text(monkeypatch):
    assert G.question_manifest_digest(None)[0]
    import dataclasses
    rows = list(questions_mod.QUESTIONS)
    rows[0] = dataclasses.replace(rows[0], text=rows[0].text + " ")
    monkeypatch.setattr(questions_mod, "QUESTIONS", tuple(rows))
    assert not G.question_manifest_digest(None)[0]


def test_static_scan_gate_fails_on_a_package_file_naming_the_material(tmp_path, monkeypatch):
    pkg = tmp_path / "pkg"; pkg.mkdir()
    (pkg / "clean.py").write_text("X = 'fine'\n")
    monkeypatch.setattr(G, "PKG_DIR", pkg)
    env = _env(tmp_path)
    assert G.excluded_material_absent(env)[0]
    (pkg / "bad.py").write_text('X = "or" + "acle"\n')          # concatenation, not the literal word
    ok, detail = G.excluded_material_absent(env)
    assert not ok and "bad.py" in detail and "statically producible" in detail
    (pkg / "bad.py").unlink()
    (pkg / "worse.py").write_text('X = f"{111:c}racle" * (1 ** 65)\n')
    assert not G.excluded_material_absent(env)[0]
    (pkg / "worse.py").unlink()
    nested = pkg / "sub" / "deep"; nested.mkdir(parents=True)
    (nested / "hidden.py").write_text('X = "or" "acle"\n')          # Codex c2: subpackages are scanned too
    ok, detail = G.excluded_material_absent(env)
    assert not ok and "hidden.py" in detail


def test_static_scan_gate_fails_closed_on_a_budget_violation(tmp_path, monkeypatch):
    pkg = tmp_path / "pkg"; pkg.mkdir(); (pkg / "huge.py").write_text('X = "x" * (10000 ** 3)\n')
    monkeypatch.setattr(G, "PKG_DIR", pkg)
    ok, detail = G.excluded_material_absent(_env(tmp_path))
    assert not ok and "failed closed" in detail


def test_static_scan_gate_refuses_a_vacuous_word_list(tmp_path):
    ok, detail = G.excluded_material_absent(_env(tmp_path, forbidden_words=()))
    assert not ok and "vacuous" in detail


def test_excluded_path_present_under_the_run_root_fails(tmp_path):
    env = _env(tmp_path)
    p = env.run_root / env.excluded_prefixes[0].rstrip("/"); p.mkdir(parents=True)
    ok, detail = G.excluded_material_absent(env)
    assert not ok and "present" in detail


def test_env_clean_fails_on_a_key_torch_missing_cache_or_outbound(tmp_path, monkeypatch):
    env = _env(tmp_path)
    assert G.env_clean(env)[0]
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    ok, detail = G.env_clean(env)
    assert not ok and "OPENAI_API_KEY" in detail
    monkeypatch.delenv("OPENAI_API_KEY")
    import importlib.util
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object() if name == "torch" else None)
    assert "torch" in G.env_clean(env)[1]
    monkeypatch.undo()
    (env.cache_dir / "fastembed").rmdir()
    assert "FastEmbed" in G.env_clean(env)[1]
    # an outbound probe that SUCCEEDS is a failure
    srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1)
    env2 = _env(tmp_path / "b", outbound_probe=("127.0.0.1", srv.getsockname()[1]))
    ok, detail = G.env_clean(env2)
    srv.close()
    assert not ok and "SUCCEEDED" in detail


def test_boundary_and_health_gates_use_the_injected_probes(tmp_path):
    env = _env(tmp_path, self_test=lambda: {"passed": False, "checks": {"no_outbound": False}})
    ok, detail = G.boundary(env)
    assert not ok and "no_outbound" in detail
    env = _env(tmp_path / "h", health=lambda n, r: type("S", (), {"falkordb_ok": True, "llama_ok": False})())
    ok, detail = G.substrate_health(env)
    assert not ok and "unhealthy" in detail
    assert not G.boundary(_env(tmp_path / "n", self_test=None))[0]
    assert not G.substrate_health(_env(tmp_path / "m", health=None))[0]


def test_tokenizer_equivalence_gate_refuses_an_injected_mismatch(tmp_path, monkeypatch):
    class Tok:
        def __init__(self, ok): self.ok = ok
        def equivalence_sample(self, lines): return [*lines, "<|im_start|>user\nprobe<|im_end|>\n<|im_start|>assistant\n"]
        def equivalence_check(self, base_url, lines):
            assert any("<|im_start|>" in l for l in lines)
            return (self.ok, "client == server" if self.ok else "line 3 differs: client 12 ids vs server 11")
    from scripts.research.arms849 import serving
    monkeypatch.setattr(serving, "Tokenizer", lambda path: Tok(False))
    ok, detail = G.tokenizer_equivalence(_env(tmp_path))
    assert not ok and "differs" in detail
    monkeypatch.setattr(serving, "Tokenizer", lambda path: Tok(True))
    assert G.tokenizer_equivalence(_env(tmp_path / "b"))[0]


def test_code_hashes_gate_compares_to_the_header_on_resume(tmp_path):
    env = _env(tmp_path, run_root=REPO_ROOT)
    ok, detail = G.code_hashes(env)
    assert ok and "fresh" in detail
    from scripts.research.arms849.ledger import code_hashes as compute
    header = compute(REPO_ROOT)
    assert G.code_hashes(G.GateEnv(**{**env.__dict__, "header_code_hashes": header}))[0]
    tampered = {**header, "scripts/research/arms849/gates.py": "0" * 64}
    ok, detail = G.code_hashes(G.GateEnv(**{**env.__dict__, "header_code_hashes": tampered}))
    assert not ok and "gates.py" in detail


@needs_corpus
def test_run_all_records_wall_clock_and_refuses_with_every_failing_detail(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "_run_checker", _fake_checker(True))
    env = _env(tmp_path, run_root=_export_like(tmp_path / "export"))   # the checkout itself would be refused: it holds the reference dir
    env.export_manifest_path = env.run_root / ".export-manifest.json"
    P.run_preflight(REPO_ROOT, CORPUS, env.export_manifest_path, env.preflight_path, cache_dir=CACHE)
    skip = {"tokenizer_equivalence"}                       # needs the live server
    t0 = time.monotonic()
    results = G.run_all(env, only=[n for n, _ in G.GATE_ORDER if n not in skip])
    assert results[-1].name == "_wall_seconds" and results[-1].passed and time.monotonic() - t0 < G.NFR003_BUDGET_S
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    with pytest.raises(G.GatesRefused) as ei:
        G.run_all(env, only=["env_clean", "prompt_digest"])
    assert "env_clean" in str(ei.value) and "prompt_digest" not in str(ei.value).split("refused:")[1].split("env_clean")[0]


# ---------------------------------------------------------------------------
# samplers
# ---------------------------------------------------------------------------


def test_gtt_sampler_reads_peak_and_flags_the_ceiling(tmp_path):
    counter = tmp_path / "gtt"; counter.write_text(str(int(10 * SM.GIB)))
    s = SM.GttSampler(counter)
    with s:
        counter.write_text(str(int(58 * SM.GIB)))          # above 57.5
        time.sleep(1.3)
    assert s.ceiling_gib == 57.5 and s.breached and s.sample.breached
    assert s.peak_gib is not None and s.peak_gib >= 58 - 1e-9 and s.sample.readings >= 2


def test_a_failed_reading_invalidates_the_window_and_keeps_its_reason(tmp_path):
    counter = tmp_path / "gtt"; counter.write_text(str(int(10 * SM.GIB)))
    s = SM.GttSampler(counter)
    with s:
        time.sleep(0.6)
        counter.unlink()                                     # the source disappears mid-window
        time.sleep(1.2)
        counter.write_text(str(int(11 * SM.GIB)))            # and comes back — the window is still invalid
        time.sleep(1.2)
    assert s.peak_gib is None and s.sample.failures >= 1 and "FileNotFoundError" in (s.sample.reason or "")
    assert s.sample.readings >= 2                            # later successes are recorded but do not revive the peak


def test_sampler_period_is_the_interval_not_read_time_plus_interval(tmp_path, monkeypatch):
    class Slow(SM.GttSampler):
        def read_once(self):
            time.sleep(0.4); return 1.0
    s = Slow(tmp_path / "unused"); s.interval_s = 0.5
    with s:
        time.sleep(2.6)
    assert s.sample.readings >= 4, s.sample                  # ~5 in 2.6 s at 0.5 s; "0.4 + 0.5" would give ≤ 3
    assert s.sample.missed_intervals == 0


def test_an_outstanding_read_at_exit_invalidates_the_window(tmp_path):
    """Codex c2: exit must not persist a numeric peak while a read is still running."""
    class Hanging(SM.GttSampler):
        def read_once(self):
            if self.sample.readings >= 1:
                time.sleep(6)                                # longer than the exit join
            return 5.0
    s = Hanging(tmp_path / "unused"); s.interval_s = 0.2
    with s:
        time.sleep(0.5)
    assert s.peak_gib is None and "outstanding" in (s.sample.reason or "")
    time.sleep(6.5)                                          # the late read completes after exit…
    assert s.peak_gib is None                                # …and does not revive the window


def test_samplers_never_raise_into_the_arm(tmp_path, monkeypatch):
    s = SM.GttSampler(tmp_path / "absent")
    with s:
        pass
    assert s.peak_gib is None and s.sample.reason and "FileNotFoundError" in s.sample.reason
    import subprocess
    def boom(*a, **k): raise subprocess.CalledProcessError(1, "docker")
    monkeypatch.setattr(subprocess, "run", boom)
    r = SM.RssSampler("nope")
    with r:
        pass
    assert r.peak_mib is None and "CalledProcessError" in r.sample.reason


def test_rss_sampler_parses_docker_stats(monkeypatch):
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: type("P", (), {"stdout": "1.5GiB / 62.5GiB"})())
    assert SM.RssSampler().read_once() == pytest.approx(1536.0)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: type("P", (), {"stdout": "512.3MiB / 62.5GiB"})())
    assert SM.RssSampler().read_once() == pytest.approx(512.3)
    with pytest.raises(ValueError):
        SM._to_mib("lots")


@pytest.mark.parametrize("construction", [
    'X = "or" "acle"', 'X = "or" + "acle"', 'X = f"or{\'acle\'!s}"', 'X = b"or" + b"acle"',
    'X = f"{111:c}racle"', 'X = f"{110 + 1:c}racle"', 'X = f"or{None!s:.0}acle"', 'X = f"{+111:c}racle"',
    'X = f"or{1 / 2!s:.0}acle"', 'X = "%s%s" % ("or", "acle")', 'X = "or" + "acle" * (1 ** 65)',
    'X = "%s%s" % (*("or", "acle"),)',
], ids=["adjacent", "plus", "conv", "bytes", "numc", "arith", "none", "uplus", "div", "percent", "pow65", "starred"])
def test_production_scanner_catches_wp02s_adversarial_constructions(construction):
    """Every construction WP02's review found must be caught by the PRODUCTION scanner too."""
    assert FORBIDDEN[0] in "\n".join(litscan.string_constants(construction + "\n")).lower()


def test_production_scanner_partitions_the_grammar():
    every = set(__import__("ast").expr.__subclasses__())
    assert litscan._PURE_EXPR | litscan._OPAQUE_EXPR == every and not (litscan._PURE_EXPR & litscan._OPAQUE_EXPR)


def test_litscan_sees_literal_structure_and_treats_calls_as_opaque():
    """The stated boundary: a literal concatenation is seen; a call's arguments are separate fragments."""
    assert FORBIDDEN[0] in "\n".join(litscan.string_constants('Y = "or" + "acle"\n')).lower()
    only_call = "\n".join(litscan.string_constants('X = "".join(["or", "acle"])\n')).lower()
    assert FORBIDDEN[0] not in only_call and "or" in only_call and "acle" in only_call
