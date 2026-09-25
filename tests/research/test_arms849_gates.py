"""Gates, preflight and samplers (WP04 T020): every gate proven to fail on its injected defect.

The forbidden words are assembled from parts so this file does not carry them.
"""

from __future__ import annotations

import ast
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
    exercised on a REAL directory shape under a temp root (never the checkout: the review
    sandbox is read-only — Codex c8), with the checkout root and the data file re-pointed."""
    root = tmp_path / "root"; root.mkdir(); ref = root / "probe" / shape
    monkeypatch.setattr(P, "REPO_ROOT", root)              # the "own checkout" the checkers vouch for
    if shape != "absent":
        ref.mkdir(parents=True)
    if shape == "incomplete":
        for f in P.REFERENCE_FILES[:-1]:
            (ref / f).write_text("x: 1\n")
    data = tmp_path / "export-excludes.txt"; data.write_text(f"probe/{shape}/\nkitty-specs/\n")
    monkeypatch.setattr(P, "EXCLUDES_FILE", data)
    calls = []
    monkeypatch.setattr(P, "_run_checker", lambda name: calls.append(name) or _fake_checker(True)(name))
    with pytest.raises(P.PreflightRefused, match="vacuously"):
        P.run_preflight(root, CORPUS, tmp_path / "m.json", tmp_path / "preflight.json", cache_dir=CACHE)
    assert calls == []                                     # refused BEFORE running anything
    assert not (REPO_ROOT / "build").exists() or not list((REPO_ROOT / "build").glob("_guard_probe_*"))
    # and the complete shape passes the guard (the checkers then run)
    for f in P.REFERENCE_FILES:
        ref.mkdir(parents=True, exist_ok=True); (ref / f).write_text("x: 1\n")
    assert P.reference_dir(root) == ref


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


def _fake_pkg(where: pathlib.Path) -> pathlib.Path:
    """A package directory carrying every registered module as a clean stub — the inventory
    the gate REQUIRES before it will scan (an empty directory no longer passes)."""
    where.mkdir(parents=True, exist_ok=True)
    for name in G.REQUIRED_MODULES:
        (where / name).write_text("X = 'fine'\n")
    return where


def _env(tmp_path, **over) -> G.GateEnv:
    cache = tmp_path / "cache"; (cache / "qwen-tokenizer").mkdir(parents=True); (cache / "fastembed").mkdir()
    base = {"run_root": tmp_path / "work", "corpus_dir": CORPUS, "cache_dir": cache,
            "preflight_path": tmp_path / "preflight.json", "export_manifest_path": tmp_path / "work" / ".export-manifest.json",
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
    pkg = _fake_pkg(tmp_path / "pkg")
    (pkg / "clean.py").write_text("X = 'fine'\n")
    monkeypatch.setattr(G, "PKG_DIR", pkg)
    env = _env(tmp_path)
    ok, detail = G.excluded_material_absent(env)
    assert ok and "no hit" in detail, detail
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
    pkg = _fake_pkg(tmp_path / "pkg"); (pkg / "huge.py").write_text('X = "x" * (10000 ** 3)\n')
    monkeypatch.setattr(G, "PKG_DIR", pkg)
    ok, detail = G.excluded_material_absent(_env(tmp_path))
    assert not ok and "failed closed" in detail


def test_static_scan_gate_refuses_a_vacuous_word_list(tmp_path):
    ok, detail = G.excluded_material_absent(_env(tmp_path, forbidden_words=()))
    assert not ok and "vacuous" in detail


def test_excluded_path_present_under_the_run_root_fails(tmp_path):
    env = _env(tmp_path)
    p = env.run_root / P.reference_prefix().rstrip("/"); p.mkdir(parents=True)
    ok, detail = G.excluded_material_absent(env)
    assert not ok and "present" in detail


@pytest.mark.parametrize("shape", ["empty", "comments_only", "absent"])
def test_excluded_gate_refuses_an_empty_or_absent_exclusion_list(tmp_path, monkeypatch, shape):
    """Codex c8 MAJOR: with no exclusion list the gate used to pass over hidden material. The list
    is read from the canonical data file and an empty/absent one REFUSES — even though the
    reference directory IS present under the run root here."""
    env = _env(tmp_path)
    (env.run_root / P.reference_prefix().rstrip("/")).mkdir(parents=True)     # hidden material present
    data = tmp_path / "export-excludes.txt"
    if shape == "empty":
        data.write_text("")
    elif shape == "comments_only":
        data.write_text("# nothing\n\n")
    monkeypatch.setattr(P, "EXCLUDES_FILE", data)
    ok, detail = G.excluded_material_absent(env)
    assert not ok and "exclusion list" in detail, detail


@pytest.mark.parametrize("shape", ["missing_dir", "empty_dir", "partial"])
def test_excluded_gate_refuses_a_missing_empty_or_partial_package_inventory(tmp_path, monkeypatch, shape):
    """Codex c8 MAJOR: a missing package directory passed as "0 modules scanned". The inventory
    must hold every registered module before the scan counts."""
    pkg = tmp_path / "pkg"
    if shape == "empty_dir":
        pkg.mkdir()
    elif shape == "partial":
        _fake_pkg(pkg); (pkg / G.REQUIRED_MODULES[-1]).unlink()
    monkeypatch.setattr(G, "PKG_DIR", pkg)
    ok, detail = G.excluded_material_absent(_env(tmp_path))
    assert not ok and ("missing" in detail or "incomplete" in detail), detail
    if shape == "partial":
        assert G.REQUIRED_MODULES[-1] in detail


_LITERAL_ONLY_CAUGHT = {
    "format": 'X = "{}{}".format("or", "acle")',                 # Codex c8: a literal format call
    "adjacent": 'X = "or" "acle"',                                # implicit concatenation
    "percent": 'X = "%s%s" % ("or", "acle")',                     # %-formatting on literals
    "join": 'X = "".join(["or", "acle"])',                        # a literal join
    "format_map": 'X = "{a}{b}".format_map({"a": "or", "b": "acle"})',
    "lower": 'X = "OR".lower() + "acle"',
    "strip": 'X = "xxor".strip("x") + "acle"',
    "chained": 'X = "".join(["or", "acle"]).upper()',             # a literal call on a literal call
    "str": 'X = str("or") + "acle"',                              # Codex c9: an allowlisted builtin on a literal
    "split": 'X = "or acle".split()[0] + "or acle".split()[1]',   # Codex c9: ANY method of a literal, subscripted
    "bytes-decode": 'X = bytes([111, 114, 97, 99, 108, 101]).decode()',   # Codex c9: builtin → method chain
    "slice-twice": 'X = ("or" + "acle")[::-1][::-1]',
    "upper-lower": 'X = ("OR" "ACLE").lower()',
    "mult": 'X = "o" * 1 + "racle"',
    "reversed": 'X = "".join(reversed("elcaro"))',                # an iterator materialised by a consuming pure call
    "escape": 'X = "or\\x61cle"',                                 # an escape in the literal
    "chr": 'X = chr(111) + "racle"',
    "fromhex": 'X = bytes.fromhex("6f7261636c65").decode()',      # an attribute of an allowlisted builtin
    "opaque-call-pure-arg": 'X = RuntimeError("or" + "acle")',    # the CALL is opaque; its pure ARG is caught on its own
    "sorted-key": 'X = "".join(sorted(["acle", "or"], key=len))', # a keyword whose value is an allowlisted builtin
    "dict-fromkeys": 'X = dict.fromkeys(map("".join, [("or", "acle")]))',        # Codex c10: a dict KEY
    "list-zip": 'X = list(zip(map("".join, [("or", "acle")])))',                 # Codex c10: a tuple inside a list
    "nested-3": 'X = tuple(map(tuple, [map(tuple, [map("".join, [("or", "acle")])])]))',   # three containers deep
    "dict-value": 'X = dict(zip(["k"], map("".join, [("or", "acle")])))',       # a dict VALUE
    "bytes-in-tuple": 'X = tuple(map(bytes, [[111, 114, 97, 99, 108, 101]]))',  # bytes inside a tuple
    "set-sorted-reverse": 'X = "".join(sorted({"or", "acle"}, reverse=True))',  # an unordered container, ORDER-INSENSITIVELY consumed
    "set-max": 'X = max({"or" "acle", "a"})',
    "reversed-sorted-set": 'X = "".join(reversed(sorted({"or", "acle"})))',   # sorted clears; reversed over a list is ordered
    "fstring-sorted-set": 'X = f"{sorted({\'or\', \'acle\'})[1]}acle"[:6]',
}


@pytest.mark.parametrize("construction", list(_LITERAL_ONLY_CAUGHT.values()), ids=list(_LITERAL_ONLY_CAUGHT))
def test_excluded_gate_fails_on_a_literal_only_construction(tmp_path, monkeypatch, construction):
    pkg = _fake_pkg(tmp_path / "pkg"); (pkg / "bad.py").write_text(construction + "\n")
    monkeypatch.setattr(G, "PKG_DIR", pkg)
    ok, detail = G.excluded_material_absent(_env(tmp_path))
    assert not ok and "bad.py" in detail and "statically producible" in detail, detail


@pytest.mark.parametrize("construction", [
    'X = name.upper()',                                # a method of a NAME
    'def f(s): return s\nX = f("or") + "acle"',       # a literal-only call to a non-allowlisted name
    'X = "{}{}".format("or", tail)',                   # a non-literal argument
    'X = open("x").read()',                            # never evaluated (not allowlisted) — opaque, not refused
    'X = getattr("or", "upper")()',
    'X = eval("\'or\' + \'acle\'")',
    'X = RuntimeError("or", "acle")',                  # the call is opaque: its fragments stay separate
    'X = hash("or") and "acle"',                       # hash / id are NOT allowlisted (non-deterministic)
    'X = x.split()[0] + "acle"',
    'X = type("or")("acle")',
    'X = "".join(type({"a"})(["or", "acle"]))',        # `type` is NEVER allowlisted (c9 ruling): opaque, not evaluated — the
                                                       # c12 brief expected a refusal here; see the cycle report
], ids=["name-method", "user-call", "name-arg", "open", "getattr", "eval", "opaque-call", "hash", "name-split", "type", "type-of-set"])
def test_stateful_or_unlisted_calls_stay_opaque_and_the_gate_passes(tmp_path, monkeypatch, construction):
    """Design-lead ruling 2026-09-25: everything outside (i) allowlisted builtin on pure args and
    (ii) a method of a pure receiver is OPAQUE — the runtime boundary's job — never refused,
    so legitimate package code (RuntimeError("…"), @dataclass(frozen=True)) still scans."""
    pkg = _fake_pkg(tmp_path / "pkg"); (pkg / "ok.py").write_text(construction + "\n")
    monkeypatch.setattr(G, "PKG_DIR", pkg)
    ok, detail = G.excluded_material_absent(_env(tmp_path))
    assert ok and "no hit" in detail, detail


@pytest.mark.parametrize("construction", [
    'str = lambda x: x',                               # assignment target
    'str: int = 2',                                    # annotated assignment
    'def list(): pass',                                # def name
    'class bytes: pass',                               # class name
    'import os as chr',                                # import alias
    'from os import path as ord',
    'def g():\n    global len',                        # global declaration
    'Y = [0 for range in ()]',                         # comprehension target
    'for map in (): pass',                             # for-target
    'with a as sum: pass',                             # with-as
    'try:\n    pass\nexcept E as min:\n    pass',      # except-as
    'def h(format): pass',                             # a parameter (a rebind in its scope)
], ids=["assign", "annassign", "def", "class", "import-as", "from-as", "global", "comprehension", "for", "with", "except", "param"])
def test_a_module_that_shadows_an_allowlisted_builtin_is_refused(tmp_path, monkeypatch, construction):
    """The allowlist is only closed while its names mean what the interpreter says."""
    with pytest.raises(litscan.ScanRefused, match="rebinds allowlisted builtin"):
        litscan.string_constants(construction + "\n")
    pkg = _fake_pkg(tmp_path / "pkg"); (pkg / "shadow.py").write_text(construction + "\n")
    monkeypatch.setattr(G, "PKG_DIR", pkg)
    ok, detail = G.excluded_material_absent(_env(tmp_path))
    assert not ok and "failed closed" in detail and "shadow.py" in detail and "rebinds" in detail, detail


def test_an_absent_method_of_a_literal_refuses_the_scan(tmp_path, monkeypatch):
    with pytest.raises(litscan.ScanRefused, match="AttributeError"):
        litscan.string_constants('X = "or".nosuch()\n')


_ORDER_SENSITIVE = {
    "join": 'X = "".join({"or", "acle"})',                          # Codex c10: flipped with PYTHONHASHSEED
    "list": 'X = list({"or", "acle"})',
    "tuple-frozenset": 'X = tuple(frozenset({"or", "acle"}))',
    "percent": 'X = "%s" % {"or", "acle"}',
    "str": 'X = str({"or", "acle"})',
    "sorted-key": 'X = "".join(sorted({"or", "acle"}, key=len))',   # ties fall in hash order
    "min-key": 'X = min({"or", "acle"}, key=len)',
    "map": 'X = "".join(map(str, {"or", "acle"}))',
    "enumerate": 'X = list(enumerate({"or", "acle"}))',
    "fstring": 'X = f"{ {\'or\', \'acle\'} }"',
    "method": 'X = {"or", "acle"}.pop()',
    "subset": 'X = {"or", "acle"} < {"or"}',
    "ifexp-test": 'X = "x" if {"or", "acle"} else "y"',
    "starred": 'X = sorted(*[{"or", "acle"}])',
    "sorted-nested": 'X = "".join(sorted([{"or", "acle"}])[0])',      # Codex c11: sorted() hands the set back unsorted
    "min-nested": 'X = min([{"or", "acle"}])',
    "max-nested": 'X = max([{"or", "acle"}])',
    "min-default": 'X = min([], default={"or", "acle"})',              # Codex c11: a tainted default=
    "sorted-set-of-frozensets": 'X = sorted({frozenset({"or", "acle"})})[0]',
    "sorted-tuple-in-list": 'X = sorted([({"or", "acle"},)])',
    "max-nested-boolop": 'X = max([{"or", "acle"}] or "x")',
    "sorted-frozenset-nested": 'X = sorted(frozenset([frozenset({"or", "acle"})]))',
    "map-frozenset-sorted": 'X = "".join(sorted(map(frozenset, [["or", "acle"]]))[0])',   # Codex c12: sets built by a mapped callable
    "map-set-sorted": 'X = "".join(sorted(map(set, [["or", "acle"]]))[0])',
    "sorted-list-map-frozenset": 'X = sorted(list(map(frozenset, [["or", "acle"]])))[0]',
    "min-map-frozenset": 'X = min(map(frozenset, [["or", "acle"]]))',
    "frozenset-union": 'X = "".join(sorted(frozenset.union(frozenset(), ["or", "acle"])))',   # refused (a method over a set)
    "map-str-nested": 'X = "".join(map(str, [{"or", "acle"}]))',                # a callable applied to tainted members
    "subscript-copy": 'X = "".join([{"a"}][0].copy() | {"or", "acle"})',       # value-carried: the set came out of a subscript
    "copy-union": 'X = "".join({"a"}.copy() | {"or", "acle"})',
    "set-union-classmethod": 'X = "".join(set.union({"a"}, ["or", "acle"]))',
    "subscript-frozenset-class": 'X = "".join([frozenset][0](["or", "acle"]))',   # the class reached through a subscript
    "dict-fromkeys-set": 'X = dict.fromkeys({"or", "acle"})',
}


@pytest.mark.parametrize("construction", list(_ORDER_SENSITIVE.values()), ids=list(_ORDER_SENSITIVE))
@pytest.mark.parametrize("seed", ["0", "3"])
def test_order_sensitive_consumption_of_an_unordered_container_is_refused_under_any_hash_seed(tmp_path, monkeypatch, seed, construction):
    """Codex c10 MAJOR: `"".join({"or","acle"})` was a hit under PYTHONHASHSEED=0 and a pass under
    3 — a gate whose answer depends on the hash seed is not a gate. Consumed in any
    order-sensitive way, an unordered container REFUSES (child spawned under BOTH seeds)."""
    monkeypatch.setenv("PYTHONHASHSEED", seed)
    with pytest.raises(litscan.ScanRefused, match="order-sensitive"):
        litscan.string_constants(construction + "\n")
    pkg = _fake_pkg(tmp_path / "pkg"); (pkg / "unordered.py").write_text(construction + "\n")
    monkeypatch.setattr(G, "PKG_DIR", pkg)
    ok, detail = G.excluded_material_absent(_env(tmp_path))
    assert not ok and "failed closed" in detail and "unordered.py" in detail and "order-sensitive" in detail, detail


@pytest.mark.parametrize("seed", ["0", "3"])
def test_order_insensitive_consumers_of_an_unordered_container_stay_pure_and_deterministic(tmp_path, monkeypatch, seed):
    monkeypatch.setenv("PYTHONHASHSEED", seed)
    # the closed list of order-insensitive consumers: pure, and the gate passes
    for c in ['X = len({"or", "acle"})', 'X = "or" in {"or", "acle"}', 'X = {"or", "acle"} == {"acle", "or"}',
              'X = frozenset({"or", "acle"})', 'X = any({"or", "acle"})', 'X = sorted({"or", "acle"})[0] + "x"',
              'X = max({"or", "acle"}, default="x")',              # Codex c11: an UNTAINTED default over a set of scalars
              'X = len([{"or", "acle"}])', 'X = any([{"or", "acle"}])', 'X = [{"or", "acle"}] == [{"acle", "or"}]',
              'X = ("a", {"or", "acle"})[1]',                       # a subscript hands the Tainted set back, still Tainted
              'X = len(list(map(frozenset, [["a"]])))',             # Codex c12: an ordered list OF sets is deterministic
              'X = list(map(frozenset, [["or", "acle"]]))', 'X = list(reversed([{"or", "acle"}]))', 'X = dict([("k", {"or", "acle"})])',
              'X = sorted(filter(frozenset, [["or", "acle"]]))',    # filter keeps the LISTS: no set is produced
              'X = "".join(sorted(dict.fromkeys(["or", "acle"]).keys()))',   # dict keys are ordered → "acleor"
              'X = "".join(sorted(["acle", "or"], key=frozenset))']:  # subset order is hash-free; stable → "acleor"
        assert litscan.string_constants(c + "\n") == litscan.string_constants(c + "\n"), c
        pkg = _fake_pkg(tmp_path / f"pkg_{abs(hash(c))}"); (pkg / "ok.py").write_text(c + "\n")
        monkeypatch.setattr(G, "PKG_DIR", pkg)
        ok, detail = G.excluded_material_absent(_env(tmp_path / f"e_{abs(hash(c))}"))
        assert ok and "no hit" in detail, (c, detail)
    # sorted() makes the consumption deterministic: reverse=True yields the word under EVERY seed…
    assert FORBIDDEN[0] in "\n".join(litscan.string_constants('X = "".join(sorted({"or", "acle"}, reverse=True))\n')).lower()
    # …and plain sorted() yields "acle" + "or" (no hit) under every seed — the same answer each time
    plain = litscan.string_constants('X = "".join(sorted({"or", "acle"}))\n')
    assert FORBIDDEN[0] not in "\n".join(plain).lower() and "acleor" in plain
    assert plain == litscan.string_constants('X = "".join(sorted({"or", "acle"}))\n')


@pytest.mark.parametrize("construction", list(_LITERAL_ONLY_CAUGHT.values()), ids=list(_LITERAL_ONLY_CAUGHT))
def test_two_consecutive_scans_of_a_construction_agree(construction):
    """Every child process draws its own hash seed; the strings the scan reports must not
    depend on it (set members are reported in sorted order)."""
    first = litscan.string_constants(construction + "\n")
    assert first == litscan.string_constants(construction + "\n")
    assert FORBIDDEN[0] in "\n".join(first).lower()


def test_a_literal_call_that_raises_refuses_the_scan(tmp_path, monkeypatch):
    """Fail closed on ANY exception inside an allowlisted literal call — never skip it."""
    pkg = _fake_pkg(tmp_path / "pkg"); (pkg / "odd.py").write_text('X = "{}".format()\n')
    monkeypatch.setattr(G, "PKG_DIR", pkg)
    with pytest.raises(litscan.ScanRefused, match="IndexError"):
        litscan.string_constants('X = "{}".format()\n')
    ok, detail = G.excluded_material_absent(_env(tmp_path))
    assert not ok and "failed closed" in detail and "odd.py" in detail, detail


_SITECUSTOMIZE = """
import ast
_real_parse = ast.parse


class Novel(ast.expr):
    _fields = ()


def parse(source, *a, **k):
    tree = _real_parse(source, *a, **k)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            v = node.value
            node.value = Novel(lineno=v.lineno, col_offset=v.col_offset, end_lineno=v.end_lineno, end_col_offset=v.end_col_offset)
            break
    return tree


ast.parse = parse
"""


def test_unclassified_expression_node_refuses_the_scan_and_fails_the_gate(tmp_path, monkeypatch):
    """Codex c8 MAJOR: an expression node in neither explicit set used to be _UNKNOWN → [] →
    pass. Now the scan REFUSES, naming the node and its location, and the gate fails.
    In-process first; then END TO END through the rlimited child, whose ast.parse is patched by
    a sitecustomize on PYTHONPATH to hand back a synthetic node."""
    import gc

    def novel_parse(real):
        class Novel(ast.expr):
            _fields = ()

        def parse(src, *a, **k):
            tree = real(src, *a, **k)
            tree.body[0].value = Novel(lineno=1, col_offset=4, end_lineno=1, end_col_offset=5)
            return tree
        return parse
    monkeypatch.setattr(ast, "parse", novel_parse(ast.parse))
    try:
        with pytest.raises(litscan.ScanRefused, match=r"Novel at line 1:4"):
            litscan._string_constants_inprocess("X = 1\n")
    finally:
        monkeypatch.undo(); gc.collect()                 # the partition tests enumerate ast.expr's live subclasses
    shim = tmp_path / "shim"; shim.mkdir(); (shim / "sitecustomize.py").write_text(_SITECUSTOMIZE)
    monkeypatch.setenv("PYTHONPATH", str(shim) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    with pytest.raises(litscan.ScanRefused, match="Novel"):
        litscan.string_constants("X = 1\n")
    pkg = _fake_pkg(tmp_path / "pkg")
    monkeypatch.setattr(G, "PKG_DIR", pkg)
    ok, detail = G.excluded_material_absent(_env(tmp_path))
    assert not ok and "failed closed" in detail and "Novel" in detail, detail


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
    skip = {"tokenizer_equivalence", "substrate_health_inside"}   # need the live server / a host record
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


def test_returned_sample_is_frozen_after_exit_even_with_a_read_in_flight(tmp_path):
    """Codex c4: the closure check and the mutation are one critical section; the sample a
    caller holds after exit never changes, however the worker is scheduled."""
    import copy
    class Slow(SM.GttSampler):
        def read_once(self):
            time.sleep(0.35); return 3.0
    s = Slow(tmp_path / "unused"); s.interval_s = 0.1
    with s:
        time.sleep(0.5)
    snap = copy.deepcopy(s.sample.__dict__)
    time.sleep(1.5)                                          # any in-flight read completes here
    assert s.sample.__dict__ == snap


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


def test_production_scanner_partitions_the_grammar_explicitly():
    """Codex c8: both sets are EXPLICIT tuples of ast classes (never a complement), and every
    ast.expr subclass of the running interpreter is in exactly one — a grammar the interpreter
    grows (a new node type) fails HERE, loudly, instead of passing the scan silently."""
    pure, parts, opaque = litscan._PURE_EXPR, litscan._BY_PARTS_EXPR, litscan._OPAQUE_EXPR
    assert all(isinstance(t, tuple) for t in (pure, parts, opaque))
    assert all(isinstance(c, type) and issubclass(c, ast.expr) for c in pure + parts + opaque)
    assert len(set(pure) | set(parts) | set(opaque)) == len(pure) + len(parts) + len(opaque)   # disjoint
    every = {c for c in ast.expr.__subclasses__() if c.__module__ == "ast"}
    unclassified = sorted(c.__name__ for c in every - set(pure) - set(parts) - set(opaque))
    assert not unclassified, f"{sys.version}: ast.expr subclasses in no explicit set: {unclassified}"
    assert set(pure) | set(parts) | set(opaque) == every
    assert set(parts) == {ast.Name, ast.Call, ast.Attribute} and ast.Starred in pure and ast.Lambda in opaque
    # the CLOSED allowlist (design-lead ruling 2026-09-25): deterministic, no reflection, no I/O
    assert {"hash", "id", "type", "getattr", "eval", "exec", "open", "object", "super", "isinstance",
            "__import__", "print", "vars", "globals"}.isdisjoint(litscan._PURE_BUILTINS)
    assert {"str", "bytes", "chr", "sorted", "reversed", "format", "map"} <= litscan._PURE_BUILTINS


def test_litscan_sees_literal_structure_and_treats_stateful_calls_as_opaque():
    """The stated boundary: literal structure — including a pure str method on a literal — is
    seen; a call that touches a name is opaque (its literal arguments stay separate fragments)."""
    assert FORBIDDEN[0] in "\n".join(litscan.string_constants('Y = "or" + "acle"\n')).lower()
    assert FORBIDDEN[0] in "\n".join(litscan.string_constants('X = "".join(["or", "acle"])\n')).lower()
    on_name = "\n".join(litscan.string_constants('X = sep.join(["or", "acle"])\n')).lower()
    assert FORBIDDEN[0] not in on_name and "or" in on_name and "acle" in on_name
    with_name_arg = "\n".join(litscan.string_constants('X = "{}{}".format("or", tail)\n')).lower()
    assert FORBIDDEN[0] not in with_name_arg and "or" in with_name_arg


# ---------------------------------------------------------------------------
# two phases (design-lead ruling 2026-09-25)
# ---------------------------------------------------------------------------


def _later() -> str:
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(timespec="seconds")


def _props(n_ctx=262_144):
    from scripts.research.arms849.substrate import GGUF_FILE
    return lambda url: {"default_generation_settings": {"n_ctx": n_ctx}, "model_path": f"/models/{GGUF_FILE}"}


@needs_corpus
def test_host_phase_writes_a_signed_record_and_container_phase_verifies_it(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "_run_checker", _fake_checker(True))
    env = _env(tmp_path, run_root=_export_like(tmp_path / "export"))
    env.export_manifest_path = env.run_root / ".export-manifest.json"
    P.run_preflight(REPO_ROOT, CORPUS, env.export_manifest_path, env.preflight_path, cache_dir=CACHE)
    env.up_ts = "2026-09-25T03:00:00+00:00"
    host_path = tmp_path / "gate-host.json"
    results, host_sha = G.run_host_phase(env, host_path)
    assert [r.name for r in results][:3] == ["boundary", "substrate_health", "preflight_present_and_matching"]
    rec = json.loads(host_path.read_text())
    assert rec["gate_host_sha"] == host_sha == G.record_sha(rec, "gate_host_sha") and rec["up_ts"] == env.up_ts and rec["preflight_sha"]
    # container phase with injected probes: tokenizer + props
    from scripts.research.arms849 import serving
    class Tok:
        def equivalence_sample(self, lines): return [*lines, "<|im_start|>user\nprobe<|im_end|>\n<|im_start|>assistant\n"]
        def equivalence_check(self, base_url, lines): return True, "ok"
    monkeypatch.setattr(serving, "Tokenizer", lambda path: Tok())
    env.host_record_path = host_path; env.container_start_ts = _later(); env.props_probe = _props()
    monkeypatch.setattr(G, "PKG_DIR", _fake_pkg(tmp_path / "fakepkg"))
    c_results, c_sha = G.run_container_phase(env, tmp_path / "gate-container.json")
    crec = json.loads((tmp_path / "gate-container.json").read_text())
    assert crec["gate_container_sha"] == c_sha == G.record_sha(crec, "gate_container_sha") and crec["gate_host_sha"] == host_sha
    # substituting the cited host digest changes the container record's sha (Codex c6)
    assert G.record_sha({**crec, "gate_host_sha": "0" * 64}, "gate_container_sha") != c_sha
    assert "boundary" not in [r.name for r in c_results] and "substrate_health_inside" in [r.name for r in c_results]


@needs_corpus
@pytest.mark.parametrize("tamper", ["stale", "other_export", "failed_result", "resigned_other_preflight", "previous_stack"])
def test_container_phase_refuses_a_bad_host_record(tmp_path, monkeypatch, tamper):
    """(a) a host record older than up… (b) …or for another export is refused; so is one with a
    failed gate or a preflight sha that is not this run's."""
    monkeypatch.setattr(P, "_run_checker", _fake_checker(True))
    env = _env(tmp_path, run_root=_export_like(tmp_path / "export"))
    env.export_manifest_path = env.run_root / ".export-manifest.json"
    P.run_preflight(REPO_ROOT, CORPUS, env.export_manifest_path, env.preflight_path, cache_dir=CACHE)
    env.up_ts = "2026-09-25T03:00:00+00:00"
    host_path = tmp_path / "gate-host.json"
    G.run_host_phase(env, host_path)
    rec = json.loads(host_path.read_text())
    if tamper == "stale":
        rec["ts"] = "2026-09-25T02:59:00+00:00"                 # before up_ts
    elif tamper == "other_export":
        rec["export_content_sha"] = "e" * 64
    elif tamper == "failed_result":
        rec["results"][0]["passed"] = False
    elif tamper == "previous_stack":
        env.up_ts = "2026-09-25T03:05:00+00:00"                 # the stack came up AGAIN; the record is unchanged
    else:
        rec["preflight_sha"] = "f" * 64
    rec["gate_host_sha"] = G.record_sha(rec, "gate_host_sha")      # re-signed: the content itself must be caught
    host_path.write_text(json.dumps(rec))
    env.host_record_path = host_path; env.container_start_ts = _later(); env.props_probe = _props()
    ok, detail = G.substrate_health_inside(env)
    assert not ok and "gate-host.json" in detail
    # and a record whose sha does NOT recompute
    rec["ts"] = "2026-09-25T03:10:00+00:00"; host_path.write_text(json.dumps(rec))
    ok, detail = G.substrate_health_inside(env)
    assert not ok and "does not recompute" in detail


def test_timestamps_compare_as_parsed_datetimes_with_fractions_and_z(tmp_path, monkeypatch):
    """Codex c6 MINOR: same-second completion and "Z" spellings must not refuse a healthy run."""
    monkeypatch.setattr(P, "_run_checker", _fake_checker(True))
    env = _env(tmp_path, run_root=_export_like(tmp_path / "export"))
    env.export_manifest_path = env.run_root / ".export-manifest.json"
    P.run_preflight(REPO_ROOT, CORPUS, env.export_manifest_path, env.preflight_path, cache_dir=CACHE)
    env.up_ts = G.now_iso()                                   # fractional seconds, same second as the host ts
    host_path = tmp_path / "gate-host.json"
    G.run_host_phase(env, host_path)
    env.host_record_path = host_path; env.props_probe = _props()
    env.container_start_ts = _later().replace("+00:00", "Z")   # an equivalent UTC spelling
    ok, detail = G.substrate_health_inside(env)
    assert ok, detail
    env.up_ts = env.up_ts[:19]                                # naive → refused, not misordered
    ok, detail = G.substrate_health_inside(env)
    assert not ok and "timezone-aware" in detail


def test_container_phase_refuses_without_a_host_record_or_with_wrong_props(tmp_path):
    env = _env(tmp_path, props_probe=_props(n_ctx=4096), container_start_ts=_later(), up_ts=G.now_iso())
    ok, detail = G.substrate_health_inside(env)
    assert not ok and "n_ctx" in detail and "no host-phase record" in detail


def test_phase_membership_matches_the_ruling():
    host = [n for n, _ in G.HOST_GATES]; cont = [n for n, _ in G.CONTAINER_GATES]
    assert host == ["boundary", "substrate_health", "preflight_present_and_matching"]
    assert "env_clean" in cont and "boundary" not in cont and "substrate_health" not in cont and "substrate_health_inside" in cont
    assert set(host) | set(cont) == {n for n, _ in G.GATE_ORDER}
