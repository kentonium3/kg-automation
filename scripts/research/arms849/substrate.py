"""Substrate lifecycle and the run boundary on office4 (WP02; research.md D-8, D-9, D-11).

Everything that touches the machine lives here, so the sandbox note in
research.md D-9 has exactly one implementation to be checked against:

* ``setup``   — pinned installs, images pulled BY DIGEST, the embedder and
                tokenizer fetched ONCE into the cache with their shas recorded,
                the GGUF verified against SHA256SUMS. The only step allowed to
                reach the network.
* ``up``/``down``/``health`` — the two services via compose project ``arms849``,
                127.0.0.1 only; ``down`` verifies nothing remains (SC-008).
* ``export``  — a ``git archive`` of a clean commit minus the paths in
                ``compose/export-excludes.txt``, with a CONTENT manifest sha.
* ``run``     — the runner container whose only mounts are the export (ro), the
                corpus (ro), the cache (ro) and the ledger directory (rw), on the
                compose network and nothing else; ``--self-test`` proves it.

Nothing here deploys to office2 (C-005). Helpers: ``python3 -m
scripts.research.arms849.substrate <command>``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass

__all__ = [
    "CACHE_DIR",
    "COMPOSE_DIR",
    "EXPORT_DIR",
    "LLAMA_IMAGE",
    "PROJECT",
    "RUNS_DIR",
    "SubstrateState",
    "content_manifest_sha",
    "down",
    "excluded_prefixes",
    "export",
    "health",
    "load_setup",
    "run",
    "self_test",
    "setup",
    "up",
]

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
COMPOSE_DIR = pathlib.Path(__file__).resolve().parent / "compose"
BUILD_DIR = REPO_ROOT / "build"
#: OUTSIDE the repo tree (learned live): the export is a full repo copy, and the
#: repo's pre-commit secret scan walks even gitignored build/ directories, so an
#: export under build/ aborts every commit with the test fixtures' fake secrets.
EXPORT_DIR = pathlib.Path(os.environ.get("ARMS849_RUN_ENV", str(pathlib.Path.home() / ".cache" / "arms849" / "run-env")))
RUNS_DIR = BUILD_DIR / "849-runs"
CACHE_DIR = pathlib.Path(os.environ.get("ARMS849_CACHE", str(BUILD_DIR / "849-cache")))
CORPUS_DIR = BUILD_DIR / "849-corpus"
SETUP_JSON = RUNS_DIR / "setup.json"

PROJECT = "arms849"
NETWORK = f"{PROJECT}-net"
VOLUME = f"{PROJECT}-falkor"
RUNNER_IMAGE = f"{PROJECT}-runner:local"
FALKOR_PORT, LLAMA_PORT = 16379, 18080

#: SOURCE.md's known-good serving image, by digest.
LLAMA_IMAGE = ("ghcr.io/ggml-org/llama.cpp@sha256:"
               "063e88aef1c168cf4a0a4b3a7983604561f96870a3c4953bd1fad908b4e41716")
#: #974 ran FalkorDB 4.20.1; #976 records only the digest prefix. ``setup`` resolves
#: the full digest from this tag and records it — and says so if the prefix differs.
FALKORDB_TAG = "falkordb/falkordb:v4.20.1"
FALKORDB_DIGEST_PREFIX = "sha256:9042fdc4"

GGUF_DIR = pathlib.Path.home() / "models" / "gguf" / "unsloth" / "Qwen3-Next-80B-A3B-Instruct-GGUF"
GGUF_FILE = "Qwen3-Next-80B-A3B-Instruct-UD-Q4_K_XL.gguf"
EMBEDDER_MODEL = "BAAI/bge-small-en-v1.5"
#: What `transformers`' tokenizer path imports at runtime, minus torch.
TOKENIZER_LIGHT_DEPS = ("regex", "filelock", "pyyaml", "requests", "tqdm", "packaging", "numpy", "safetensors")
TOKENIZER_REPO = "Qwen/Qwen3-Next-80B-A3B-Instruct"

PRIMARY_N_CTX, SECONDARY_N_CTX = 262_144, 393_216
YARN_ARGS = "--rope-scaling yarn --rope-scale 2 --yarn-orig-ctx 262144"
GTT_USED = pathlib.Path("/sys/class/drm/card1/device/mem_info_gtt_used")
GTT_CEILING_GIB = 57.5


def _sh(cmd: Sequence[str], check: bool = True, capture: bool = True, **kw) -> subprocess.CompletedProcess:
    """Run a command; on failure, raise with the tail of stderr so the cause is visible."""
    proc = subprocess.run(list(cmd), check=False, capture_output=capture, text=True, **kw)
    if check and proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-1500:]
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}\n{tail}")
    return proc


def _sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_tree(root: pathlib.Path) -> str:
    """sha256 over every file's (relative path + sha256(contents)) in sorted order."""
    h = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        h.update(rel.encode("utf-8") + b"\0" + _sha256_file(path).encode("ascii") + b"\n")
    return h.hexdigest()


def gtt_used_gib() -> float | None:
    try:
        return int(GTT_USED.read_text()) / 2**30
    except OSError:
        return None


# --------------------------------------------------------------------------
# setup
# --------------------------------------------------------------------------


def _resolve_digest(ref: str) -> str:
    out = _sh(["docker", "manifest", "inspect", "-v", ref]).stdout
    data = json.loads(out)
    items = data if isinstance(data, list) else [data]
    for item in items:
        plat = (item.get("Descriptor") or {}).get("platform") or {}
        if plat.get("architecture") == "amd64" and plat.get("os") == "linux":
            return item["Descriptor"]["digest"]
    return items[0]["Descriptor"]["digest"]


def setup(skip_gguf_verify: bool = False, python: pathlib.Path | None = None) -> dict:
    """Pinned installs, image pulls by digest, caches with shas, GGUF verification.

    Idempotent: a second run re-verifies and rewrites the same record.
    """
    # The interpreter actually running this code — a lane worktree has no venv of
    # its own, so REPO_ROOT/.venv would name a path that does not exist.
    py = str(python or pathlib.Path(sys.executable))
    req = COMPOSE_DIR / "requirements-arms849.txt"
    _sh(["uv", "pip", "install", "--python", py, "-r", str(req)])
    # transformers' tokenizer classes need a handful of light deps; torch is
    # not one of them and is asserted absent below (adversarial A2, refined:
    # "no torch", not "no deps" — --no-deps alone leaves `regex` missing).
    _sh(["uv", "pip", "install", "--python", py, "--no-deps", "transformers", "tokenizers", "huggingface-hub"])
    _sh(["uv", "pip", "install", "--python", py, *TOKENIZER_LIGHT_DEPS])
    torch_probe = _sh([py, "-c", "import importlib.util; print(importlib.util.find_spec('torch') is not None)"]).stdout.strip()
    if torch_probe == "True":
        raise RuntimeError("torch is importable after setup; env_clean forbids it (adversarial A2)")

    falkor_digest = _resolve_digest(FALKORDB_TAG)
    falkor_ref = f"falkordb/falkordb@{falkor_digest}"
    digest_note = ("matches the #976 prefix" if falkor_digest.startswith(FALKORDB_DIGEST_PREFIX)
                   else f"DOES NOT match the #976 prefix {FALKORDB_DIGEST_PREFIX}; pinned to {FALKORDB_TAG}'s current digest and recorded here")
    _sh(["docker", "pull", falkor_ref])
    _sh(["docker", "pull", LLAMA_IMAGE])
    _sh(["docker", "build", "-t", RUNNER_IMAGE, "-f", str(COMPOSE_DIR / "runner.Dockerfile"), str(COMPOSE_DIR)])

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # The embedder and the tokenizer: fetched ONCE, here, never at run time.
    _sh([py, "-c", (
        "import os,sys; from fastembed import TextEmbedding; "
        f"TextEmbedding({EMBEDDER_MODEL!r}, cache_dir={str(CACHE_DIR / 'fastembed')!r})")])
    _sh([py, "-c", (
        "from huggingface_hub import snapshot_download; "
        f"snapshot_download({TOKENIZER_REPO!r}, allow_patterns=['tokenizer*', 'vocab*', 'merges*', 'special_tokens_map.json'], "
        f"local_dir={str(CACHE_DIR / 'qwen-tokenizer')!r})")])
    cache_shas = {str(p.relative_to(CACHE_DIR)): _sha256_file(p)
                  for p in sorted(CACHE_DIR.rglob("*")) if p.is_file()}

    gguf = GGUF_DIR / GGUF_FILE
    expected = next((l.split()[0] for l in (GGUF_DIR / "SHA256SUMS").read_text().splitlines() if GGUF_FILE in l), None)
    gguf_sha = "skipped" if skip_gguf_verify else _sha256_file(gguf)
    if not skip_gguf_verify and expected and gguf_sha != expected:
        raise RuntimeError(f"GGUF sha256 {gguf_sha} != SHA256SUMS {expected}")

    record = {
        "recorded_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pins": req.read_text().splitlines(),
        "falkordb_image": falkor_ref, "falkordb_digest_note": digest_note,
        "llama_image": LLAMA_IMAGE, "runner_image": RUNNER_IMAGE,
        "gguf": str(gguf), "gguf_sha256": gguf_sha, "gguf_sha256_expected": expected,
        "cache_dir": str(CACHE_DIR), "cache_shas": cache_shas,
        "embedder_model": EMBEDDER_MODEL, "tokenizer_repo": TOKENIZER_REPO,
    }
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    SETUP_JSON.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def load_setup() -> dict:
    if not SETUP_JSON.exists():
        raise RuntimeError(f"{SETUP_JSON} absent — run `substrate setup` first")
    return json.loads(SETUP_JSON.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# up / health / down
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SubstrateState:
    n_ctx: int
    rope: str
    falkordb_image: str
    llama_image: str
    model_file: str
    falkordb_ok: bool
    llama_ok: bool
    props: dict


def _compose(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return _sh(["docker", "compose", "-p", PROJECT, "-f", str(COMPOSE_DIR / "compose.yaml"), *args],
               env={**os.environ, **(env or {})})


def compose_env(yarn: bool, setup_record: dict) -> dict:
    return {
        "FALKORDB_IMAGE": setup_record["falkordb_image"],
        "LLAMA_IMAGE": setup_record["llama_image"],
        "GGUF_DIR": str(GGUF_DIR),
        "GGUF_FILE": GGUF_FILE,
        "N_CTX": str(SECONDARY_N_CTX if yarn else PRIMARY_N_CTX),
        "ROPE_ARGS": YARN_ARGS if yarn else "",
    }


def up(yarn: bool = False, wait_s: int = 3600) -> SubstrateState:
    env = compose_env(yarn, load_setup())
    _compose("up", "-d", "--wait", "--wait-timeout", str(wait_s), env=env)
    state = health(expect_n_ctx=int(env["N_CTX"]), expect_rope="yarn" if yarn else "none")
    if not (state.falkordb_ok and state.llama_ok):
        raise RuntimeError(f"substrate up but unhealthy: {state}")
    return state


def health(expect_n_ctx: int | None = None, expect_rope: str | None = None) -> SubstrateState:
    """FalkorDB answers GRAPH.LIST; llama /health ok and /props reports what we expect.

    /props on the pinned image: ``default_generation_settings.n_ctx`` and
    ``model_path`` at the top level; any other shape is reported as-is and
    fails the expectation rather than being guessed at.
    """
    falkor_ok = False
    try:
        out = _sh(["docker", "exec", f"{PROJECT}-falkordb-1", "redis-cli", "-p", "6379", "GRAPH.LIST"], check=False)
        falkor_ok = out.returncode == 0
    except OSError:
        pass
    props: dict = {}
    llama_ok = False
    probe_error = ""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{LLAMA_PORT}/health", timeout=10) as r:
            llama_ok = json.loads(r.read().decode())["status"] == "ok"
        with urllib.request.urlopen(f"http://127.0.0.1:{LLAMA_PORT}/props", timeout=10) as r:
            props = json.loads(r.read().decode())
    except Exception as exc:  # noqa: BLE001 — health is a probe; the caller decides
        llama_ok = False
        probe_error = f"{type(exc).__name__}: {exc}"
    gen = props.get("default_generation_settings") or {}
    n_ctx = int(gen.get("n_ctx") or props.get("n_ctx") or 0)
    model_file = str(props.get("model_path") or props.get("model") or "")
    if expect_n_ctx is not None and n_ctx != expect_n_ctx:
        llama_ok = False
    if props and GGUF_FILE not in model_file:
        llama_ok = False
    rope = "yarn" if "yarn" in json.dumps(props).lower() else "none"
    if expect_rope is not None and props and rope != expect_rope:
        llama_ok = False
    if probe_error:
        props = {"probe_error": probe_error}
    setup_record = load_setup() if SETUP_JSON.exists() else {}
    return SubstrateState(n_ctx=n_ctx, rope=rope, falkordb_image=setup_record.get("falkordb_image", ""),
                          llama_image=LLAMA_IMAGE, model_file=model_file, falkordb_ok=falkor_ok,
                          llama_ok=llama_ok, props=props)


def down() -> dict:
    """compose down -v --rmi all, then VERIFY nothing remains (SC-008)."""
    env = compose_env(False, load_setup()) if SETUP_JSON.exists() else {
        "FALKORDB_IMAGE": "x", "LLAMA_IMAGE": "x", "GGUF_DIR": "/", "GGUF_FILE": "x", "N_CTX": "1", "ROPE_ARGS": ""}
    _compose("down", "-v", "--rmi", "all", env=env)
    _sh(["docker", "image", "rm", "-f", RUNNER_IMAGE], check=False)
    leftovers = {
        "containers": _sh(["docker", "ps", "-a", "--format", "{{.Names}}"]).stdout.split(),
        "volumes": _sh(["docker", "volume", "ls", "--format", "{{.Name}}"]).stdout.split(),
        "networks": _sh(["docker", "network", "ls", "--format", "{{.Name}}"]).stdout.split(),
        "images": _sh(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}@{{.Digest}}"]).stdout.split(),
    }
    matched = {k: [x for x in v if any(s in x.lower() for s in (PROJECT, "falkor", "llama"))]
               for k, v in leftovers.items()}
    gtt = gtt_used_gib()
    report = {"leftovers": matched, "gtt_used_gib": gtt, "gguf_intact": (GGUF_DIR / GGUF_FILE).exists(),
              "clean": not any(matched.values()) and (gtt is None or gtt < 2.0)}
    return report


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------


def excluded_prefixes() -> tuple[str, ...]:
    lines = (COMPOSE_DIR / "export-excludes.txt").read_text(encoding="utf-8").splitlines()
    return tuple(l.strip() for l in lines if l.strip() and not l.startswith("#"))


def content_manifest_sha(root: pathlib.Path) -> str:
    return _sha256_tree(root)


def export(commit: str = "HEAD", repo: pathlib.Path = REPO_ROOT, dest: pathlib.Path = EXPORT_DIR) -> dict:
    """git archive <commit> minus the excluded prefixes; refuse a dirty tree."""
    dirty = _sh(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"]).stdout.strip()
    if dirty:
        raise RuntimeError("working tree is dirty; the export must equal a commit:\n" + dirty)
    sha = _sh(["git", "-C", str(repo), "rev-parse", commit]).stdout.strip()
    excludes = excluded_prefixes()
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    with tempfile.NamedTemporaryFile(suffix=".tar", delete=False) as tmp:
        tar_path = pathlib.Path(tmp.name)
    try:
        _sh(["git", "-C", str(repo), "archive", "--format=tar", "-o", str(tar_path), sha])
        with tarfile.open(tar_path) as tar:
            members = [m for m in tar.getmembers()
                       if not any(m.name == p.rstrip("/") or m.name.startswith(p) for p in excludes)]
            tar.extractall(dest, members=members, filter="data")
    finally:
        tar_path.unlink(missing_ok=True)
    for p in excludes:
        if (dest / p.rstrip("/")).exists():
            raise RuntimeError(f"excluded path survived the export: {p}")
    manifest = {"source_commit": sha, "excludes": list(excludes), "content_sha": content_manifest_sha(dest)}
    (dest / ".export-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


# --------------------------------------------------------------------------
# run / self-test
# --------------------------------------------------------------------------


def _ensure_runner_image() -> None:
    """`down --rmi all` removes the runner image (SC-008); rebuild it on demand (cached, fast)."""
    if _sh(["docker", "image", "inspect", RUNNER_IMAGE], check=False).returncode != 0:
        _sh(["docker", "build", "-t", RUNNER_IMAGE, "-f", str(COMPOSE_DIR / "runner.Dockerfile"), str(COMPOSE_DIR)])


def _runner_cmd(extra: Iterable[str], *, entrypoint: str | None = None,
                env_extra: Sequence[tuple[str, str]] = ()) -> list[str]:
    """The ONLY docker-run shape the harness ever executes: allowlisted mounts, compose net."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    _ensure_runner_image()
    cmd = ["docker", "run", "--rm", "--network", NETWORK,
           "-v", f"{EXPORT_DIR}:/work:ro", "-v", f"{CORPUS_DIR}:/corpus:ro",
           "-v", f"{CACHE_DIR}:/cache:ro", "-v", f"{RUNS_DIR}:/runs:rw",
           "-e", "HF_HUB_OFFLINE=1", "-e", "ARMS849_CORPUS=/corpus", "-e", "ARMS849_CACHE=/cache",
           "-e", "ARMS849_LLAMA_HOSTS=llama", "-e", "OPENAI_API_KEY=", "-w", "/work"]
    for k, v in env_extra:
        cmd += ["-e", f"{k}={v}"]
    if entrypoint:
        cmd += ["--entrypoint", entrypoint]
    cmd += [RUNNER_IMAGE, *extra]
    return cmd


SELF_TEST = r"""
import os, socket, sys, json, importlib.util
checks = {}
# The excluded paths come from the same data file the export used; this probe
# never names them itself (the arms package must not).
excl = []
try:
    for line in open("/work/scripts/research/arms849/compose/export-excludes.txt", encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#"):
            excl.append(line.rstrip("/"))
except OSError:
    checks["excludes_file_present"] = False
checks["excludes_file_present"] = bool(excl)
for rel in excl:
    checks["absent:/work/" + rel] = not os.path.exists("/work/" + rel)
# The base image has an empty /home; what must be unreachable is any host home
# CONTENT and the host checkout itself.
checks["home_empty_or_absent"] = (not os.path.exists("/home")) or (os.listdir("/home") == [])
host = os.environ.get("HOST_CHECKOUT", "/host-checkout")
checks["absent:" + host] = not os.path.exists(host)
try:
    open("/work/.probe", "w").write("x"); checks["work_readonly"] = False
except OSError:
    checks["work_readonly"] = True
checks["no_openai_key"] = not os.environ.get("OPENAI_API_KEY")
try:
    socket.create_connection(("1.1.1.1", 80), timeout=3); checks["no_outbound"] = False
except OSError:
    checks["no_outbound"] = True
for name, port in (("llama", 8080), ("falkordb", 6379)):
    try:
        socket.create_connection((name, port), timeout=3).close(); checks["reaches_" + name] = True
    except OSError:
        checks["reaches_" + name] = False
checks["no_torch"] = importlib.util.find_spec("torch") is None
print(json.dumps(checks, indent=2))
sys.exit(0 if all(checks.values()) else 1)
"""


def self_test(host_checkout: pathlib.Path = REPO_ROOT) -> dict:
    """Denied-access test from INSIDE the boundary (contracts/gates.md `boundary`)."""
    cmd = _runner_cmd(["-c", SELF_TEST], entrypoint="python3",
                      env_extra=[("HOST_CHECKOUT", str(host_checkout))])
    proc = _sh(cmd, check=False)
    try:
        checks = json.loads(proc.stdout.strip()) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        checks = {}
    return {"passed": proc.returncode == 0 and bool(checks) and all(checks.values()),
            "checks": checks, "stderr": proc.stderr[-2000:]}


def run(harness_args: Sequence[str]) -> int:
    """Execute the harness inside the runner; the export must exist and be intact."""
    manifest_path = EXPORT_DIR / ".export-manifest.json"
    if not manifest_path.exists():
        raise RuntimeError("no export at build/849-run-env — run `substrate export` first")
    manifest = json.loads(manifest_path.read_text())
    recorded = manifest["content_sha"]
    # Recompute without the manifest file itself (it is not part of what it describes).
    manifest_path.unlink()
    try:
        actual = content_manifest_sha(EXPORT_DIR)
    finally:
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if actual != recorded:
        raise RuntimeError(f"export content sha {actual} != recorded {recorded}; re-export")
    proc = subprocess.run(_runner_cmd(["scripts.research.run_849_harness", *harness_args]), check=False)
    return proc.returncode


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: Sequence[str]) -> int:
    ap = argparse.ArgumentParser(prog="substrate")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup"); s.add_argument("--skip-gguf-verify", action="store_true")
    u = sub.add_parser("up"); u.add_argument("--yarn", action="store_true")
    sub.add_parser("down"); sub.add_parser("health")
    e = sub.add_parser("export"); e.add_argument("--commit", default="HEAD")
    r = sub.add_parser("run"); r.add_argument("--self-test", action="store_true"); r.add_argument("args", nargs=argparse.REMAINDER)
    a = ap.parse_args(argv[1:])
    if a.cmd == "setup":
        print(json.dumps(setup(skip_gguf_verify=a.skip_gguf_verify), indent=2)); return 0
    if a.cmd == "up":
        print(json.dumps(asdict(up(yarn=a.yarn)), indent=2, default=str)); return 0
    if a.cmd == "health":
        st = health(); print(json.dumps(asdict(st), indent=2, default=str)); return 0 if st.falkordb_ok and st.llama_ok else 1
    if a.cmd == "down":
        rep = down(); print(json.dumps(rep, indent=2)); return 0 if rep["clean"] else 1
    if a.cmd == "export":
        print(json.dumps(export(commit=a.commit), indent=2)); return 0
    if a.cmd == "run":
        if a.self_test:
            rep = self_test(); print(json.dumps(rep, indent=2)); return 0 if rep["passed"] else 1
        args = [x for x in a.args if x != "--"]
        return run(args)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
