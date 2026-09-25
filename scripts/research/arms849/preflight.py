"""Preflight (WP04 T016): the reference-dependent checkers run WHERE THE reference EXISTS.

`check_849_seed`, `check_849_reference`, `check_849_freeze` and `check_849_loader` load
the hidden reference; inside the isolated run environment (which excludes it) they
would return an empty finding list and pass for the wrong reason (Codex plan
blocker D-2). So they run here, from the FULL checkout, before the export, and
their result is bound into `preflight.json` — which the in-container gates
(`arms849.gates`) verify by recomputing every fingerprint against their own
environment. Refuses to write anything when a gate fails or when the reference is
absent (the vacuous-pass guard).

The record is what T039's registration cites: the four gate results, the three
corpus fingerprints, the record-line digest, the registered prompt and manifest
digests, the chat-template sha, the export's content sha and source commit.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib
import io
import json
import pathlib
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.research.arms849 import prompt as prompt_mod
from scripts.research.arms849 import questions as questions_mod
from scripts.research.arms849.text import FrozenCorpusText
from scripts.research.load_849_corpus import REGISTRATION, fingerprint

__all__ = ["CHECKERS", "EXCLUDES_FILE", "Preflight", "PreflightRefused", "preflight_sha", "reference_dir", "reference_prefix", "run_preflight"]

#: The four reference-dependent checkers, run in-process (an import failure is a loud failure).
CHECKERS = (
    "scripts.research.check_849_seed",
    "scripts.research.check_849_reference",
    "scripts.research.check_849_freeze",
    "scripts.research.check_849_loader",
)
#: The hidden reference directory is NAMED NOWHERE in this package: it is the excluded
#: prefix (compose/export-excludes.txt, the same data the export and the self-test use)
#: under which the eight per-question YAMLs live. Read at call time, never spelled.
EXCLUDES_FILE = pathlib.Path(__file__).resolve().parent / "compose" / "export-excludes.txt"
REFERENCE_FILES = ("A.yaml", "B1.yaml", "B2.yaml", "C1.yaml", "E1.yaml", "E2.yaml", "F1.yaml", "F2.yaml")
EXPORT_MANIFEST = ".export-manifest.json"


class PreflightRefused(RuntimeError):
    """A gate failed, the reference is absent, or the record would be vacuous — nothing is written."""


@dataclass(frozen=True)
class GateOutcome:
    name: str
    passed: bool
    exit_code: int | None
    tail: str
    seconds: float


@dataclass(frozen=True)
class Preflight:
    gates: list[GateOutcome]
    corpus: dict[str, str]
    record_lines_digest: str
    prompt_hash: str
    question_manifest_sha: str
    export_content_sha: str
    export_source_commit: str
    source_commit: str
    registration_commit: str
    ts: str
    wall_seconds: float
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "gates": [asdict(g) for g in self.gates]}


def _canonical(record: dict[str, Any]) -> bytes:
    return json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def preflight_sha(record: dict[str, Any]) -> str:
    """sha256 of the canonical JSON WITHOUT the `preflight_sha` field itself."""
    body = {k: v for k, v in record.items() if k != "preflight_sha"}
    return hashlib.sha256(_canonical(body)).hexdigest()


def excluded_prefixes() -> list[str]:
    return [line.strip() for line in EXCLUDES_FILE.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")]


def reference_prefix() -> str:
    """The data file's FIRST excluded prefix is the reference directory (that order is the rule)."""
    prefixes = excluded_prefixes()
    if not prefixes or not prefixes[0].endswith("/"):
        raise PreflightRefused(f"{EXCLUDES_FILE}: first entry must be the reference directory prefix")
    return prefixes[0]


def reference_dir(repo_root: pathlib.Path) -> pathlib.Path | None:
    """The reference directory under repo_root when it carries the eight per-question files."""
    candidate = pathlib.Path(repo_root) / reference_prefix().rstrip("/")
    return candidate if all((candidate / f).is_file() for f in REFERENCE_FILES) else None


def assert_reference_present(repo_root: pathlib.Path) -> pathlib.Path:
    """The vacuous-pass guard: the checkers must have the reference to check against."""
    found = reference_dir(repo_root)
    if found is None:
        raise PreflightRefused(
            f"no excluded prefix under {repo_root} carries the eight per-question reference files; "
            f"the checkers would pass vacuously — preflight refuses to run")
    return found


def _run_checker(name: str) -> GateOutcome:
    t0 = time.monotonic()
    buffer = io.StringIO()
    try:
        module = importlib.import_module(name)
        with contextlib.redirect_stdout(buffer):
            code = int(module.main([name]))
    except Exception as exc:  # noqa: BLE001 — a checker that cannot run is a failed gate, loudly
        return GateOutcome(name, False, None, f"raised {type(exc).__name__}: {exc}", time.monotonic() - t0)
    tail = "\n".join(buffer.getvalue().strip().splitlines()[-6:])
    return GateOutcome(name, code == 0, code, tail, time.monotonic() - t0)


def _git_head(repo_root: pathlib.Path) -> str:
    out = subprocess.run(["git", "-C", str(repo_root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
    return out.stdout.strip()


def run_preflight(repo_root: pathlib.Path, corpus_dir: pathlib.Path, export_manifest_path: pathlib.Path,
                  out_path: pathlib.Path, *, chat_template_sha256: str | None = None) -> Preflight:
    """Run the four checkers from the full checkout and bind everything into `out_path`.

    Refuses (writes nothing) when the reference is absent, a checker fails, a registered
    digest does not verify, or the export manifest is missing.
    """
    t0 = time.monotonic()
    repo_root = pathlib.Path(repo_root).resolve()
    assert_reference_present(repo_root)
    gates = [_run_checker(name) for name in CHECKERS]
    failed = [g for g in gates if not g.passed]
    if failed:
        detail = "\n".join(f"  {g.name}: exit {g.exit_code}\n    {g.tail}" for g in failed)
        raise PreflightRefused(f"{len(failed)} preflight gate(s) failed; nothing written:\n{detail}")

    ok_p, detail_p = prompt_mod.verify()
    if not ok_p:
        raise PreflightRefused(f"registered prompt does not verify: {detail_p}")
    ok_q, detail_q = questions_mod.verify()
    if not ok_q:
        raise PreflightRefused(f"question manifest does not verify: {detail_q}")

    corpus_dir = pathlib.Path(corpus_dir)
    registered: dict[str, str] = dict(REGISTRATION["files"])  # type: ignore[arg-type]
    corpus = {name: fingerprint(corpus_dir / name) for name in registered}
    for name, expected in registered.items():
        if not corpus[name].startswith(str(expected)):
            raise PreflightRefused(f"corpus file {name} fingerprint {corpus[name][:16]} != registered {expected}")
    text = FrozenCorpusText(corpus_dir)
    record_digest = text.record_lines_digest

    manifest_path = pathlib.Path(export_manifest_path)
    if not manifest_path.is_file():
        raise PreflightRefused(f"export manifest {manifest_path} is absent; export first")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for key in ("content_sha", "source_commit"):
        if not manifest.get(key):
            raise PreflightRefused(f"export manifest lacks {key}")

    record = Preflight(
        gates=gates, corpus=corpus, record_lines_digest=record_digest,
        prompt_hash=prompt_mod.REGISTERED_DIGEST, question_manifest_sha=questions_mod.MANIFEST_DIGEST,
        export_content_sha=str(manifest["content_sha"]), export_source_commit=str(manifest["source_commit"]),
        source_commit=_git_head(repo_root), registration_commit=str(REGISTRATION["commit"]),
        ts=datetime.now(timezone.utc).isoformat(timespec="seconds"), wall_seconds=round(time.monotonic() - t0, 3),
        extra={"chat_template_sha256": chat_template_sha256} if chat_template_sha256 else {},
    )
    payload = record.as_dict()
    payload["preflight_sha"] = preflight_sha(payload)
    out_path = pathlib.Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(out_path)
    return record


def load_preflight(path: pathlib.Path) -> dict[str, Any]:
    """Read and verify the record's own sha; a tampered or torn record is refused."""
    payload = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if payload.get("preflight_sha") != preflight_sha(payload):
        raise PreflightRefused(f"{path}: preflight_sha does not match its content")
    return payload


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="arms849.preflight")
    ap.add_argument("--repo-root", type=pathlib.Path, default=REPO_ROOT)
    ap.add_argument("--corpus", type=pathlib.Path, default=REPO_ROOT / "build" / "849-corpus")
    ap.add_argument("--export-manifest", type=pathlib.Path, required=True)
    ap.add_argument("--out", type=pathlib.Path, required=True)
    a = ap.parse_args(argv[1:])
    try:
        rec = run_preflight(a.repo_root, a.corpus, a.export_manifest, a.out)
    except PreflightRefused as exc:
        print(f"PREFLIGHT REFUSED: {exc}")
        return 1
    print(json.dumps({g.name: g.passed for g in rec.gates}, indent=2))
    print(f"preflight written: {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
