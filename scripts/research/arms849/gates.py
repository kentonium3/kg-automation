"""Pre-run gates (WP04 T017) in TWO PHASES (design-lead ruling 2026-09-25, contracts/gates.md
dated correction): the D-8 runner has no docker socket, so the gates that need docker run on
the HOST immediately before the runner is launched, and the rest run INSIDE the container
before the ledger header is written. Each phase writes a signed record; the header binds
``preflight_sha``, ``gate_host_sha`` and ``gate_container_sha``.

- HOST phase (:func:`run_host_phase`): ``boundary`` (the docker self-test),
  ``substrate_health`` (docker-derived rope mode, n_ctx, model file, GRAPH.LIST),
  ``preflight_present_and_matching`` → ``gate-host.json``.
- CONTAINER phase (:func:`run_container_phase`): ``preflight_present_and_matching`` recomputed
  inside, ``prompt_digest``, ``question_manifest_digest``, the excluded-material gate + scan,
  ``env_clean`` (NO outbound — the only place it is meaningful), ``tokenizer_equivalence``
  against the compose llama service, ``substrate_health_inside`` (a ``/props`` re-probe AND
  verification of the host record: its sha recomputes, its export/preflight identities equal
  what the container computed, every host result passed, ``up_ts ≤ ts ≤ container start``),
  ``code_hashes`` → ``gate-container.json``.

Every gate compares to a REGISTERED CONSTANT or to a value recomputed in THIS environment —
never to something "recorded on first run". Any failure refuses the run with every failing
detail; each phase records its wall-clock so NFR-003 is measured, not assumed.
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
    RUBRIC_COMMIT,
    PreflightRefused,
    load_preflight,
)
from scripts.research.arms849.text import FrozenCorpusText
from scripts.research.load_849_corpus import REGISTRATION, fingerprint

__all__ = ["CONTAINER_GATES", "GATE_EXCLUDED_ABSENT", "GATE_ORDER", "HOST_GATES", "GateEnv", "GateResult",
           "GatesRefused", "record_sha", "run_all", "run_container_phase", "run_host_phase"]

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
    expected_chat_template_sha256: str = ""            # ServingConfiguration.chat_template_sha256
    up_ts: str = ""                                     # host: when `up` reported healthy (ISO UTC)
    host_record_path: pathlib.Path | None = None        # container: the host phase's signed record
    container_start_ts: str = ""                        # container: when this process started (ISO UTC)
    props_probe: Callable[[str], dict[str, Any]] | None = None   # container: GET /props (injectable)
    header_code_hashes: dict[str, str] | None = None   # on resume: the ledger header's
    excluded_prefixes: tuple[str, ...] = ()            # from the export's data file
    forbidden_words: tuple[str, ...] = ()              # built from parts by the caller
    # Injection points so the gate set is testable without the stack.
    self_test: Callable[[], dict[str, Any]] | None = None
    health: Callable[[int, str], Any] | None = None
    outbound_probe: tuple[str, int] = ("1.1.1.1", 80)
    extra: dict[str, Any] = field(default_factory=dict)


def export_content_sha(root: pathlib.Path, manifest_name: str = ".export-manifest.json") -> str:
    """substrate._sha256_tree's algorithm (relative path + sha256(contents), sorted), minus the
    manifest file — the export hashed the tree before the manifest existed."""
    import hashlib

    h = hashlib.sha256()
    for path in sorted(p for p in pathlib.Path(root).rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        if rel == manifest_name:
            continue
        h.update(rel.encode("utf-8") + b"\0" + hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii") + b"\n")
    return h.hexdigest()


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
    from scripts.research.arms849.preflight import checkers

    expected = list(checkers())
    seen = {str(g.get("name")): g for g in rec.get("gates", [])}
    if sorted(seen) != sorted(expected) or len(rec.get("gates", [])) != len(expected):
        problems.append(f"preflight gates are {sorted(seen)}; exactly {expected} required (an empty or partial "
                        f"list is not evidence)")
    for name in expected:
        g = seen.get(name) or {}
        if g.get("passed") is not True or g.get("exit_code") != 0:
            problems.append(f"preflight gate {name} did not pass (passed={g.get('passed')!r}, exit={g.get('exit_code')!r})")
    registered: dict[str, str] = dict(REGISTRATION["files"])  # type: ignore[arg-type]
    for name, registered_fp in registered.items():
        here = fingerprint(env.corpus_dir / name) if (env.corpus_dir / name).exists() else "absent"
        if rec.get("corpus", {}).get(name) != here:
            problems.append(f"corpus {name}: preflight {str(rec.get('corpus', {}).get(name))[:16]} != here {here[:16]}")
        if here != str(registered_fp):
            problems.append(f"corpus {name}: here {here[:16]} != registered {str(registered_fp)[:16]}")
    digest = FrozenCorpusText(env.corpus_dir).record_lines_digest
    if rec.get("record_lines_digest") != digest:
        problems.append("record_lines_digest differs from this corpus")
    if not env.export_manifest_path.is_file():
        problems.append(f"export manifest {env.export_manifest_path} absent")
    else:
        # The export's bytes are hashed HERE — the manifest's own claim is not evidence
        # (Codex WP04 c1). The export computed its sha BEFORE writing the manifest, so the
        # manifest file itself is excluded from the recomputation.
        here_sha = export_content_sha(env.run_root)
        if here_sha != rec.get("export_content_sha"):
            problems.append(f"export content sha here {here_sha[:12]} != preflight {str(rec.get('export_content_sha'))[:12]}")
    if rec.get("prompt_hash") != prompt_mod.REGISTERED_DIGEST:
        problems.append("preflight prompt_hash is not the registered digest")
    if rec.get("question_manifest_sha") != questions_mod.MANIFEST_DIGEST:
        problems.append("preflight question_manifest_sha is not the registered digest")
    sha = rec.get("chat_template_sha256")
    if not isinstance(sha, str) or len(sha) != 64:
        problems.append("preflight carries no chat_template_sha256 (939d9b29 requires it)")
    elif not env.expected_chat_template_sha256:
        problems.append("no expected chat_template_sha256 supplied (ServingConfiguration) — cannot compare")
    elif sha != env.expected_chat_template_sha256:
        problems.append(f"chat_template_sha256 {sha[:12]} != serving configuration {env.expected_chat_template_sha256[:12]}")
    if rec.get("rubric_commit") != RUBRIC_COMMIT:
        problems.append(f"preflight cites rubric {rec.get('rubric_commit')!r}; this build cites {RUBRIC_COMMIT}")
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
        hits = litscan.find_words(sorted(PKG_DIR.rglob("*.py")), env.forbidden_words)   # recursive: subpackages too
    except litscan.ScanBudgetExceeded as exc:
        return False, f"static scan failed closed: {exc}"
    return (not hits), ("; ".join(hits) or f"{len(list(PKG_DIR.rglob('*.py')))} modules scanned, no hit")


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


def _props_get(base_url: str) -> dict[str, Any]:
    import json
    import urllib.request

    with urllib.request.urlopen(f"{base_url.rstrip('/')}/props", timeout=10) as r:
        return json.loads(r.read().decode())


def record_sha(record: dict[str, Any]) -> str:
    """sha256 over the canonical JSON without the record's own sha field(s)."""
    import hashlib
    import json

    body = {k: v for k, v in record.items() if not k.endswith("_sha") or k in ("export_content_sha", "preflight_sha")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def substrate_health_inside(env: GateEnv) -> tuple[bool, str]:
    """Inside the runner: /props re-probe (n_ctx, model file) AND the host record verified."""
    import json

    from scripts.research.arms849.substrate import GGUF_FILE

    problems = []
    probe = env.props_probe or _props_get
    try:
        props = probe(env.llama_base_url)
    except Exception as exc:  # noqa: BLE001 — a failed probe is a failed gate, with the reason
        return False, f"/props probe failed: {type(exc).__name__}: {exc}"
    gen = props.get("default_generation_settings") or {}
    if int(gen.get("n_ctx") or 0) != env.expect_n_ctx:
        problems.append(f"/props n_ctx {gen.get('n_ctx')} != expected {env.expect_n_ctx}")
    if pathlib.PurePosixPath(str(props.get("model_path") or "")).name != GGUF_FILE:
        problems.append(f"/props model_path {props.get('model_path')!r} is not {GGUF_FILE}")
    if env.host_record_path is None or not pathlib.Path(env.host_record_path).is_file():
        return False, "; ".join([*problems, "no host-phase record (gate-host.json) — the host phase must run first"])
    rec = json.loads(pathlib.Path(env.host_record_path).read_text(encoding="utf-8"))
    if rec.get("gate_host_sha") != record_sha(rec):
        problems.append("gate-host.json: gate_host_sha does not recompute")
    if rec.get("export_content_sha") != export_content_sha(env.run_root):
        problems.append("gate-host.json: export_content_sha differs from this environment's export")
    manifest_commit = None
    if env.export_manifest_path.is_file():
        manifest_commit = json.loads(env.export_manifest_path.read_text(encoding="utf-8")).get("source_commit")
    if rec.get("export_source_commit") != manifest_commit:
        problems.append("gate-host.json: export_source_commit differs from the export manifest")
    try:
        preflight = load_preflight(env.preflight_path)
        if rec.get("preflight_sha") != preflight.get("preflight_sha"):
            problems.append("gate-host.json: preflight_sha differs from preflight.json")
    except (PreflightRefused, OSError) as exc:
        problems.append(f"preflight.json unreadable: {exc}")
    failed = [r.get("name") for r in rec.get("results", []) if r.get("passed") is not True]
    expected_names = [n for n, _ in HOST_GATES]
    if sorted(r.get("name") for r in rec.get("results", [])) != sorted(expected_names) or failed:
        problems.append(f"gate-host.json: results {sorted(r.get('name') for r in rec.get('results', []))} "
                        f"must be exactly {sorted(expected_names)} all passed; failed={failed}")
    ts, up_ts, start = str(rec.get("ts") or ""), str(rec.get("up_ts") or ""), env.container_start_ts
    if not (ts and up_ts and start) or not (up_ts <= ts <= start):
        problems.append(f"gate-host.json: ts {ts!r} must satisfy up_ts {up_ts!r} ≤ ts ≤ container start {start!r} "
                        f"(a stale record from a previous stack is refused)")
    return (not problems), ("; ".join(problems) or f"/props n_ctx {gen.get('n_ctx')}, model ok; host record "
                                                    f"{str(rec.get('gate_host_sha'))[:12]} verified")


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
    ("substrate_health_inside", substrate_health_inside),
    ("code_hashes", code_hashes),
)


HOST_GATES: tuple[tuple[str, Callable[[GateEnv], tuple[bool, str]]], ...] = (
    ("boundary", boundary),
    ("substrate_health", substrate_health),
    ("preflight_present_and_matching", preflight_present_and_matching),
)
CONTAINER_GATES: tuple[tuple[str, Callable[[GateEnv], tuple[bool, str]]], ...] = (
    ("preflight_present_and_matching", preflight_present_and_matching),
    ("prompt_digest", prompt_digest),
    ("question_manifest_digest", question_manifest_digest),
    (GATE_EXCLUDED_ABSENT, excluded_material_absent),
    ("env_clean", env_clean),
    ("tokenizer_equivalence", tokenizer_equivalence),
    ("substrate_health_inside", substrate_health_inside),
    ("code_hashes", code_hashes),
)


def _run_gates(env: GateEnv, gates: Iterable[tuple[str, Callable[[GateEnv], tuple[bool, str]]]]) -> list[GateResult]:
    results: list[GateResult] = []
    for name, fn in gates:
        results.append(_timed(name, functools.partial(fn, env)))
    wall = sum(r.seconds for r in results)
    results.append(GateResult("_wall_seconds", wall <= NFR003_BUDGET_S, f"{wall:.3f}s (NFR-003 budget {NFR003_BUDGET_S:.0f}s)", wall))
    return results


def _refuse_if_failed(results: list[GateResult], phase: str) -> None:
    failed = [r for r in results if not r.passed]
    if failed:
        raise GatesRefused(f"{phase} phase refused:\n" + "\n".join(f"  {r.name}: {r.detail}" for r in failed))


def _write_signed(path: pathlib.Path, record: dict[str, Any], sha_field: str) -> str:
    import json

    record[sha_field] = record_sha(record)
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    return record[sha_field]


def run_host_phase(env: GateEnv, out_path: pathlib.Path) -> tuple[list[GateResult], str]:
    """HOST phase, right before the runner launches: refuses on any failure, else writes the
    signed gate-host.json and returns (results, gate_host_sha)."""
    import json
    from datetime import datetime, timezone

    if not env.up_ts:
        raise GatesRefused("host phase refused: up_ts (when `up` reported healthy) is required")
    results = _run_gates(env, HOST_GATES)
    _refuse_if_failed(results, "host")
    preflight = load_preflight(env.preflight_path)
    manifest = json.loads(env.export_manifest_path.read_text(encoding="utf-8"))
    record: dict[str, Any] = {
        "phase": "host", "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "up_ts": env.up_ts,
        "export_content_sha": export_content_sha(env.run_root), "export_source_commit": manifest.get("source_commit"),
        "preflight_sha": preflight["preflight_sha"],
        "results": [{"name": r.name, "passed": r.passed, "seconds": r.seconds, "detail": r.detail}
                    for r in results if r.name != "_wall_seconds"],
        "wall_seconds": results[-1].seconds,
    }
    return results, _write_signed(out_path, record, "gate_host_sha")


def run_container_phase(env: GateEnv, out_path: pathlib.Path) -> tuple[list[GateResult], str]:
    """CONTAINER phase, before the header: refuses on any failure, else writes the signed
    gate-container.json (which cites the host record's sha) and returns (results, sha)."""
    import json
    from datetime import datetime, timezone

    if not env.container_start_ts:
        raise GatesRefused("container phase refused: container_start_ts is required")
    results = _run_gates(env, CONTAINER_GATES)
    _refuse_if_failed(results, "container")
    host = json.loads(pathlib.Path(env.host_record_path).read_text(encoding="utf-8"))  # type: ignore[arg-type]
    preflight = load_preflight(env.preflight_path)
    record: dict[str, Any] = {
        "phase": "container", "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "container_start_ts": env.container_start_ts, "gate_host_sha": host["gate_host_sha"],
        "preflight_sha": preflight["preflight_sha"], "export_content_sha": export_content_sha(env.run_root),
        "results": [{"name": r.name, "passed": r.passed, "seconds": r.seconds, "detail": r.detail}
                    for r in results if r.name != "_wall_seconds"],
        "wall_seconds": results[-1].seconds,
    }
    return results, _write_signed(out_path, record, "gate_container_sha")


def run_all(env: GateEnv, only: Iterable[str] | None = None) -> list[GateResult]:
    """Every gate of BOTH phases in one process (evidence runs / tests), or `only` those named;
    refuses with every failing detail. The phases are the run's real shape."""
    names = set(only) if only is not None else None
    results = _run_gates(env, [(n, f) for n, f in GATE_ORDER if names is None or n in names])
    _refuse_if_failed(results, "all")
    return results
