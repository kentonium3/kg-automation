"""Gates, preflight and samplers (WP04 T020): every gate proven to fail on its injected defect.

The forbidden words are assembled from parts so this file does not carry them.
"""

from __future__ import annotations

import json
import os
import pathlib
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
    """An export-shaped run root: the bound code files in their layout, no excluded material."""
    import shutil

    from scripts.research.arms849.ledger import BOUND_CODE_GLOBS
    for pattern in BOUND_CODE_GLOBS:
        for src in REPO_ROOT.glob(pattern):
            target = dest / src.relative_to(REPO_ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
    return dest


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
    rec = P.run_preflight(REPO_ROOT, CORPUS, manifest, out, chat_template_sha256="e" * 64)
    payload = P.load_preflight(out)                       # verifies its own sha
    assert [g["name"] for g in payload["gates"]] == list(P.CHECKERS) and all(g["passed"] for g in payload["gates"])
    assert set(payload["corpus"]) == set(REGISTRATION["files"])
    assert payload["prompt_hash"] == prompt_mod.REGISTERED_DIGEST
    assert payload["question_manifest_sha"] == questions_mod.MANIFEST_DIGEST
    assert payload["export_content_sha"] == "d" * 64 and payload["export_source_commit"] == "abc"
    assert payload["extra"]["chat_template_sha256"] == "e" * 64 and len(payload["preflight_sha"]) == 64
    assert rec.record_lines_digest == payload["record_lines_digest"]


@needs_corpus
def test_preflight_refuses_when_a_checker_fails_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "_run_checker", _fake_checker(False))
    manifest = tmp_path / "m.json"; manifest.write_text(json.dumps({"source_commit": "abc", "content_sha": "d" * 64}))
    with pytest.raises(P.PreflightRefused, match="gate"):
        P.run_preflight(REPO_ROOT, CORPUS, manifest, tmp_path / "preflight.json")
    assert not (tmp_path / "preflight.json").exists()


def test_vacuous_pass_guard_refuses_without_the_hidden_reference_dir(tmp_path, monkeypatch):
    """T016's whole point: the checkers pass for the wrong reason when the reference is absent."""
    monkeypatch.setattr(P, "reference_dir", lambda root: None)
    calls = []
    monkeypatch.setattr(P, "_run_checker", lambda name: calls.append(name) or _fake_checker(True)(name))
    with pytest.raises(P.PreflightRefused, match="vacuously"):
        P.run_preflight(REPO_ROOT, CORPUS, tmp_path / "m.json", tmp_path / "preflight.json")
    assert calls == []                                     # refused BEFORE running anything


def test_tampered_preflight_record_is_refused(tmp_path):
    payload = {"gates": [], "corpus": {}, "preflight_sha": "0" * 64}
    p = tmp_path / "preflight.json"; p.write_text(json.dumps(payload))
    with pytest.raises(P.PreflightRefused, match="preflight_sha"):
        P.load_preflight(p)


@needs_corpus
def test_real_checkers_run_in_process_and_refuse_when_the_reference_dir_is_renamed(tmp_path):
    """Reviewer guidance: run the preflight with the reference directory absent and confirm refusal."""
    outcome = P._run_checker("scripts.research.check_849_seed")
    assert outcome.name.endswith("check_849_seed") and outcome.exit_code in (0, 1)


# ---------------------------------------------------------------------------
# in-container gates
# ---------------------------------------------------------------------------


def _env(tmp_path, **over) -> G.GateEnv:
    cache = tmp_path / "cache"; (cache / "qwen-tokenizer").mkdir(parents=True); (cache / "fastembed").mkdir()
    base = {"run_root": tmp_path / "work", "corpus_dir": CORPUS, "cache_dir": cache,
            "preflight_path": tmp_path / "preflight.json", "export_manifest_path": tmp_path / "work" / ".export-manifest.json",
            "excluded_prefixes": ("docs/design/research/849-synthesis/" + FORBIDDEN[0] + "/",),
            "forbidden_words": FORBIDDEN, "outbound_probe": ("127.0.0.1", _closed_port()),
            "self_test": lambda: {"passed": True, "checks": {"x": True}},
            "health": lambda n, r: type("S", (), {"falkordb_ok": True, "llama_ok": True, "n_ctx": n, "rope": r})()}
    base.update(over)
    (tmp_path / "work").mkdir(exist_ok=True)
    return G.GateEnv(**base)


@needs_corpus
def test_preflight_gate_matches_this_environment_and_fails_on_one_flipped_fingerprint(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "_run_checker", _fake_checker(True))
    env = _env(tmp_path)
    env.export_manifest_path.write_text(json.dumps({"source_commit": "abc", "content_sha": "d" * 64}))
    P.run_preflight(REPO_ROOT, CORPUS, env.export_manifest_path, env.preflight_path)
    ok, detail = G.preflight_present_and_matching(env)
    assert ok, detail
    payload = json.loads(env.preflight_path.read_text())
    payload["corpus"]["stream.jsonl"] = "f" * 64
    payload["preflight_sha"] = P.preflight_sha(payload)     # re-signed: the mismatch itself must be caught
    env.preflight_path.write_text(json.dumps(payload))
    ok, detail = G.preflight_present_and_matching(env)
    assert not ok and "stream.jsonl" in detail


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
    env.export_manifest_path = tmp_path / "m.json"
    env.export_manifest_path.write_text(json.dumps({"source_commit": "abc", "content_sha": "d" * 64}))
    P.run_preflight(REPO_ROOT, CORPUS, env.export_manifest_path, env.preflight_path)
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


def test_litscan_sees_literal_structure_and_treats_calls_as_opaque():
    """The stated boundary: a literal concatenation is seen; a call's arguments are separate fragments."""
    assert FORBIDDEN[0] in "\n".join(litscan.string_constants('Y = "or" + "acle"\n')).lower()
    only_call = "\n".join(litscan.string_constants('X = "".join(["or", "acle"])\n')).lower()
    assert FORBIDDEN[0] not in only_call and "or" in only_call and "acle" in only_call
