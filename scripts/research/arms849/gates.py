"""In-container gates (WP04 T017): run before the ledger header is written.

Every gate compares to a REGISTERED CONSTANT or to a value recomputed in THIS
environment — never to something "recorded on first run" (contracts/gates.md).
Any failure refuses the run with every failing detail; :func:`run_all` records
its own wall-clock so NFR-003 (under five minutes) is measured, not assumed.
"""

from __future__ import annotations

import functools
import importlib.util
import os
import pathlib
import socket
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.research.arms849 import (
    litscan,
    serving,
)
from scripts.research.arms849 import prompt as prompt_mod
from scripts.research.arms849 import questions as questions_mod
from scripts.research.arms849.preflight import (
    PreflightRefused,
    load_preflight,
)
from scripts.research.arms849.text import FrozenCorpusText
from scripts.research.load_849_corpus import REGISTRATION, fingerprint

__all__ = ["GATE_EXCLUDED_ABSENT", "GATE_ORDER", "GateEnv", "GateResult", "GatesRefused", "run_all"]

PKG_DIR = pathlib.Path(__file__).resolve().parent


def _gate_name_from_data() -> str:
    """The contract names this gate after the material it proves absent. The word comes from
    the exclusion data file (its FIRST entry is the reference directory — the data file's
    order is the rule), never spelled here: this module is inside its own scan."""
    from scripts.research.arms849.preflight import reference_prefix

    return reference_prefix().rstrip("/").rsplit("/", 1)[-1] + "_absent"


GATE_EXCLUDED_ABSENT = _gate_name_from_data()
EQUIVALENCE_LINES = 100
NFR003_BUDGET_S = 300.0


class GatesRefused(RuntimeError):
    """One or more gates failed; the run does not start."""


@dataclass(frozen=True)
class GateResult:
    name: str
    passed: bool
    detail: str
    seconds: float = 0.0


@dataclass
class GateEnv:
    """What the gates read. Everything is a path or a value the harness already holds."""
    run_root: pathlib.Path                      # the mounted export (/work)
    corpus_dir: pathlib.Path                    # /corpus
    cache_dir: pathlib.Path                     # /cache
    preflight_path: pathlib.Path                # <runs>/preflight.json
    export_manifest_path: pathlib.Path          # <run_root>/.export-manifest.json
    llama_base_url: str = "http://llama:8080"
    expect_n_ctx: int = serving.PRIMARY_N_CTX
    expect_rope: str = "none"
    header_code_hashes: dict[str, str] | None = None   # on resume: the ledger header's
    excluded_prefixes: tuple[str, ...] = ()            # from the export's data file
    forbidden_words: tuple[str, ...] = ()              # built from parts by the caller
    # Injection points so the gate set is testable without the stack.
    self_test: Callable[[], dict[str, Any]] | None = None
    health: Callable[[int, str], Any] | None = None
    outbound_probe: tuple[str, int] = ("1.1.1.1", 80)
    extra: dict[str, Any] = field(default_factory=dict)


def _timed(name: str, fn: Callable[[], tuple[bool, str]]) -> GateResult:
    t0 = time.monotonic()
    try:
        ok, detail = fn()
    except Exception as exc:  # noqa: BLE001 — a gate that raises has failed, with the reason
        ok, detail = False, f"raised {type(exc).__name__}: {exc}"
    return GateResult(name, bool(ok), detail, round(time.monotonic() - t0, 3))


# ---------------------------------------------------------------------------
# gates
# ---------------------------------------------------------------------------


def preflight_present_and_matching(env: GateEnv) -> tuple[bool, str]:
    if not env.preflight_path.is_file():
        return False, f"{env.preflight_path} absent — run the preflight from the full checkout first"
    try:
        rec = load_preflight(env.preflight_path)
    except PreflightRefused as exc:
        return False, str(exc)
    problems = []
    for g in rec.get("gates", []):
        if not g.get("passed"):
            problems.append(f"preflight gate {g.get('name')} did not pass")
    registered: dict[str, str] = dict(REGISTRATION["files"])  # type: ignore[arg-type]
    for name, expected in registered.items():
        here = fingerprint(env.corpus_dir / name) if (env.corpus_dir / name).exists() else "absent"
        if rec.get("corpus", {}).get(name) != here:
            problems.append(f"corpus {name}: preflight {str(rec.get('corpus', {}).get(name))[:16]} != here {here[:16]}")
        if not here.startswith(str(expected)):
            problems.append(f"corpus {name}: here {here[:16]} != registered {expected}")
    digest = FrozenCorpusText(env.corpus_dir).record_lines_digest
    if rec.get("record_lines_digest") != digest:
        problems.append("record_lines_digest differs from this corpus")
    if not env.export_manifest_path.is_file():
        problems.append(f"export manifest {env.export_manifest_path} absent")
    else:
        import json
        manifest = json.loads(env.export_manifest_path.read_text(encoding="utf-8"))
        if manifest.get("content_sha") != rec.get("export_content_sha"):
            problems.append("export content_sha differs from the preflight's")
    if rec.get("prompt_hash") != prompt_mod.REGISTERED_DIGEST:
        problems.append("preflight prompt_hash is not the registered digest")
    if rec.get("question_manifest_sha") != questions_mod.MANIFEST_DIGEST:
        problems.append("preflight question_manifest_sha is not the registered digest")
    return (not problems), ("; ".join(problems) or f"preflight {rec.get('preflight_sha', '')[:12]} matches this environment")


def prompt_digest(env: GateEnv) -> tuple[bool, str]:
    return prompt_mod.verify()


def question_manifest_digest(env: GateEnv) -> tuple[bool, str]:
    return questions_mod.verify()


def excluded_material_absent(env: GateEnv) -> tuple[bool, str]:
    present = [p for p in env.excluded_prefixes if (env.run_root / p.rstrip("/")).exists()]
    if present:
        return False, f"excluded paths present under {env.run_root}: {present}"
    if not env.forbidden_words:
        return False, "no forbidden words supplied — the scan would pass vacuously"
    try:
        hits = litscan.find_words(sorted(PKG_DIR.glob("*.py")), env.forbidden_words)
    except litscan.ScanBudgetExceeded as exc:
        return False, f"static scan failed closed: {exc}"
    return (not hits), ("; ".join(hits) or f"{len(list(PKG_DIR.glob('*.py')))} modules scanned, no hit")


def boundary(env: GateEnv) -> tuple[bool, str]:
    if env.self_test is None:
        return False, "no self-test supplied (WP02 substrate.self_test)"
    report = env.self_test()
    failed = [k for k, v in report.get("checks", {}).items() if v is False]
    return bool(report.get("passed")), ("boundary self-test passed" if report.get("passed")
                                        else f"boundary self-test failed: {failed or report.get('stderr', '')[-300:]}")


def env_clean(env: GateEnv) -> tuple[bool, str]:
    problems = []
    if os.environ.get("OPENAI_API_KEY"):
        problems.append("OPENAI_API_KEY is set")
    if importlib.util.find_spec("torch") is not None:
        problems.append("torch is importable")
    if not (env.cache_dir / "qwen-tokenizer").is_dir():
        problems.append("Qwen tokenizer cache absent")
    if not (env.cache_dir / "fastembed").is_dir():
        problems.append("FastEmbed cache absent")
    host, port = env.outbound_probe
    try:
        socket.create_connection((host, port), timeout=3).close()
        problems.append(f"outbound connection to {host}:{port} SUCCEEDED")
    except OSError:
        pass
    return (not problems), ("; ".join(problems) or "no key, no torch, caches present, no outbound")


def tokenizer_equivalence(env: GateEnv) -> tuple[bool, str]:
    tok = serving.Tokenizer(env.cache_dir / "qwen-tokenizer")
    text = FrozenCorpusText(env.corpus_dir)
    lines = text.sample_lines(EQUIVALENCE_LINES) if hasattr(text, "sample_lines") else _first_lines(env.corpus_dir, EQUIVALENCE_LINES)
    return tok.equivalence_check(env.llama_base_url, tok.equivalence_sample(lines))


def _first_lines(corpus_dir: pathlib.Path, n: int) -> list[str]:
    out: list[str] = []
    with (corpus_dir / "stream.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            out.append(line.rstrip("\n"))
            if len(out) >= n:
                break
    return out


def substrate_health(env: GateEnv) -> tuple[bool, str]:
    if env.health is None:
        return False, "no health probe supplied (WP02 substrate.health)"
    state = env.health(env.expect_n_ctx, env.expect_rope)
    ok = bool(getattr(state, "falkordb_ok", False) and getattr(state, "llama_ok", False))
    return ok, (f"n_ctx {getattr(state, 'n_ctx', '?')} rope {getattr(state, 'rope', '?')}" if ok
                else f"unhealthy: {state}")


def code_hashes(env: GateEnv) -> tuple[bool, str]:
    from scripts.research.arms849.ledger import code_hashes as compute

    here = compute(env.run_root)
    if env.header_code_hashes is None:
        return True, f"fresh ledger: {len(here)} bound files hashed"
    changed = sorted(k for k in set(here) | set(env.header_code_hashes) if here.get(k) != env.header_code_hashes.get(k))
    return (not changed), ("; ".join(changed) or "every bound file matches the header")


GATE_ORDER: tuple[tuple[str, Callable[[GateEnv], tuple[bool, str]]], ...] = (
    ("preflight_present_and_matching", preflight_present_and_matching),
    ("prompt_digest", prompt_digest),
    ("question_manifest_digest", question_manifest_digest),
    (GATE_EXCLUDED_ABSENT, excluded_material_absent),
    ("boundary", boundary),
    ("env_clean", env_clean),
    ("tokenizer_equivalence", tokenizer_equivalence),
    ("substrate_health", substrate_health),
    ("code_hashes", code_hashes),
)


def run_all(env: GateEnv, only: Iterable[str] | None = None) -> list[GateResult]:
    """Run every gate (or `only` those named), in order; refuse with every failing detail."""
    names = set(only) if only is not None else None
    results: list[GateResult] = []
    for name, fn in GATE_ORDER:
        if names is None or name in names:
            results.append(_timed(name, functools.partial(fn, env)))
    wall = sum(r.seconds for r in results)
    results.append(GateResult("_wall_seconds", wall <= NFR003_BUDGET_S, f"{wall:.3f}s (NFR-003 budget {NFR003_BUDGET_S:.0f}s)", wall))
    failed = [r for r in results if not r.passed]
    if failed:
        raise GatesRefused("run refused:\n" + "\n".join(f"  {r.name}: {r.detail}" for r in failed))
    return results
