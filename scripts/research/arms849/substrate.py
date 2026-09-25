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
import re
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


RUNNER_IMAGE_INPUTS = ("runner.Dockerfile", "requirements-arms849.txt")


def _runner_dockerfile_sha() -> str:
    """Identity of everything the image build reads: the Dockerfile AND the pinned
    requirements it copies in (Codex WP02 c5: a pin change must change the tag)."""
    h = hashlib.sha256()
    for name in RUNNER_IMAGE_INPUTS:
        h.update(name.encode()); h.update(b"\0"); h.update((COMPOSE_DIR / name).read_bytes()); h.update(b"\0")
    return h.hexdigest()[:12]


#: Tagged by the Dockerfile's content: a changed Dockerfile can never reuse a stale
#: image, and `down` removes every `<project>-runner:*` tag (Codex WP02 c3).
RUNNER_IMAGE = f"{PROJECT}-runner:{_runner_dockerfile_sha()}"
FALKOR_PORT, LLAMA_PORT = 16379, 18080

#: SOURCE.md's known-good serving image, by digest.
LLAMA_IMAGE = ("ghcr.io/ggml-org/llama.cpp@sha256:"
               "063e88aef1c168cf4a0a4b3a7983604561f96870a3c4953bd1fad908b4e41716")
#: #974 (the spike) ran FalkorDB 4.20.1 and recorded only this digest prefix. ``setup`` resolves
#: the full digest from this tag and records it — and says so if the prefix differs.
FALKORDB_TAG = "falkordb/falkordb:v4.20.1"
FALKORDB_DIGEST_PREFIX = "sha256:9042fdc4"

GGUF_DIR = pathlib.Path.home() / "models" / "gguf" / "unsloth" / "Qwen3-Next-80B-A3B-Instruct-GGUF"
GGUF_FILE = "Qwen3-Next-80B-A3B-Instruct-UD-Q4_K_XL.gguf"
EMBEDDER_MODEL = "BAAI/bge-small-en-v1.5"
#: What `transformers`' tokenizer path imports at runtime, minus torch.
TOKENIZER_LIGHT_DEPS = ("regex", "filelock", "pyyaml", "requests", "tqdm", "packaging", "numpy", "safetensors",
                        "jinja2")   # jinja2: apply_chat_template (rubric 939d9b29)
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


def runner_base_image() -> str:
    """The digest-pinned FROM line of the runner image, read from the Dockerfile (never a tag)."""
    for line in (COMPOSE_DIR / "runner.Dockerfile").read_text(encoding="utf-8").splitlines():
        if line.startswith("FROM "):
            ref = line.split()[1]
            if "@sha256:" not in ref:
                raise RuntimeError(f"runner base image is not digest-pinned: {ref}")
            return ref
    raise RuntimeError("runner.Dockerfile has no FROM line")


def expected_gguf_sha(sums_path: pathlib.Path, filename: str) -> str:
    """Exactly ONE SHA256SUMS entry whose filename field equals `filename`; anything else refuses.

    A missing entry used to make the comparison conditional and setup succeeded
    without verifying anything (Codex, WP02 cycle 1).
    """
    entries = []
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].lstrip("*") == filename and re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            entries.append(parts[0])
    if len(entries) != 1:
        raise RuntimeError(f"SHA256SUMS must carry exactly one entry for {filename}; found {len(entries)}")
    return entries[0]


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
    digest_note = ("matches the #974 prefix" if falkor_digest.startswith(FALKORDB_DIGEST_PREFIX)
                   else f"DOES NOT match the #974 prefix {FALKORDB_DIGEST_PREFIX}; pinned to {FALKORDB_TAG}'s current digest and recorded here")
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
    expected = expected_gguf_sha(GGUF_DIR / "SHA256SUMS", GGUF_FILE)
    gguf_sha = "skipped" if skip_gguf_verify else _sha256_file(gguf)
    if not skip_gguf_verify and gguf_sha != expected:
        raise RuntimeError(f"GGUF sha256 {gguf_sha} != SHA256SUMS {expected}")

    record = {
        "recorded_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pins": req.read_text().splitlines(),
        "falkordb_image": falkor_ref, "falkordb_digest_note": digest_note,
        "llama_image": LLAMA_IMAGE,
        "runner_base": runner_base_image(), "runner_image": RUNNER_IMAGE,
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


YARN_EXPECTED = {"rope_scale": "2", "yarn_orig_ctx": "262144"}      # D-YaRN secondary (research.md D-6)


def _llama_args(container: str = "arms849-llama-1") -> list[str] | None:
    """The llama.cpp container's start arguments, or None when it cannot be inspected."""
    try:
        out = _sh(["docker", "inspect", "--format", "{{json .Args}}", container], capture=True).stdout
        args = json.loads(out or "[]")
        return [str(a) for a in args]
    except Exception:  # noqa: BLE001 — could-not-check is its own answer
        return None


def _arg_value(args: list[str], flag: str) -> str | None:
    for i, a in enumerate(args):
        if a == flag and i + 1 < len(args):
            return args[i + 1].lower()
        if a.startswith(flag + "="):
            return a.split("=", 1)[1].lower()
    return None


def _rope_mode(container: str = "arms849-llama-1") -> str:
    """The rope configuration the server was actually STARTED with, from the container's args.

    llama.cpp's /props exposes no rope field (verified 2026-09-25 against the live
    server: only n_ctx under default_generation_settings), so the configured
    setting is read from the process arguments; the effective n_ctx in /props is
    the runtime evidence that it took. Returns 'none', 'yarn' (only when
    --rope-scaling yarn AND --rope-scale 2 AND --yarn-orig-ctx 262144 are all
    present — a YaRN with other parameters is a different serving configuration
    and reports 'yarn:<scale>:<orig>'), or 'unknown' when the container cannot be
    inspected, which never satisfies an expectation.
    """
    args = _llama_args(container)
    if args is None:
        return "unknown"
    scaling = _arg_value(args, "--rope-scaling")
    if scaling is None or scaling == "none":
        return "none"
    if scaling != "yarn":
        return f"{scaling}"
    scale, orig = _arg_value(args, "--rope-scale"), _arg_value(args, "--yarn-orig-ctx")
    if scale == YARN_EXPECTED["rope_scale"] and orig == YARN_EXPECTED["yarn_orig_ctx"]:
        return "yarn"
    return f"yarn:{scale}:{orig}"


def health(expect_n_ctx: int, expect_rope: str) -> SubstrateState:
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
    n_ctx = int(gen.get("n_ctx") or 0)
    model_file = str(props.get("model_path") or "")
    # Health means VERIFIED, not merely answering: props must be present and
    # name the exact model basename and the expected context; rope comes from
    # the container's start arguments (/props has no rope field), never from a
    # substring of the whole payload.
    if not props or not gen or not model_file:
        llama_ok = False
    if pathlib.PurePosixPath(model_file).name != GGUF_FILE:
        llama_ok = False
    if n_ctx != expect_n_ctx:
        llama_ok = False
    rope = _rope_mode()
    if rope != expect_rope:          # 'unknown' (uninspectable) never satisfies
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
    stale = _sh(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}", f"{PROJECT}-runner"], check=False).stdout.split()
    for ref in sorted(set(stale) | {RUNNER_IMAGE}):
        _sh(["docker", "image", "rm", "-f", ref], check=False)
    leftovers = {
        "containers": _sh(["docker", "ps", "-a", "--format", "{{.Names}}"]).stdout.split(),
        "volumes": _sh(["docker", "volume", "ls", "--format", "{{.Name}}"]).stdout.split(),
        "networks": _sh(["docker", "network", "ls", "--format", "{{.Name}}"]).stdout.split(),
        "images": _sh(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}@{{.Digest}}"]).stdout.split(),
    }
    matched = {k: [x for x in v if any(s in x.lower() for s in (PROJECT, "falkor", "llama"))]
               for k, v in leftovers.items()}
    gtt = gtt_used_gib()
    # SC-008 is a VERIFICATION: an unreadable GTT counter is "could not check", never "clean".
    report = {"leftovers": matched, "gtt_used_gib": gtt, "gguf_intact": (GGUF_DIR / GGUF_FILE).exists(),
              "gtt_verified": gtt is not None,
              "clean": not any(matched.values()) and gtt is not None and gtt < 2.0}
    return report


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------


def excluded_prefixes() -> tuple[str, ...]:
    lines = (COMPOSE_DIR / "export-excludes.txt").read_text(encoding="utf-8").splitlines()
    return tuple(l.strip() for l in lines if l.strip() and not l.startswith("#"))


def _excluded(name: str, prefixes: Sequence[str]) -> bool:
    """Directory entries (trailing slash) match by slash-delimited prefix; file entries match exactly."""
    for p in prefixes:
        if p.endswith("/"):
            if name == p.rstrip("/") or name.startswith(p):
                return True
        elif name == p:
            return True
    return False


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
            members = [m for m in tar.getmembers() if not _excluded(m.name, excludes)]
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


def _assert_mount_sources(*dirs: pathlib.Path) -> None:
    """Every bind-mount source must already exist as OUR directory. Docker creates a
    missing source as a root-owned empty dir (seen 2026-09-25: an empty root-owned
    build/849-cache that then broke setup with PermissionError); refuse instead."""
    for d in dirs:
        if not d.is_dir():
            raise RuntimeError(f"mount source {d} does not exist; run setup (never let docker create it)")
        if not os.access(d, os.W_OK if d in (RUNS_DIR,) else os.R_OK):
            raise RuntimeError(f"mount source {d} is not accessible by this user (owner {d.stat().st_uid})")


def _runner_argv(extra: Iterable[str], *, entrypoint: str | None = None,
                 env_extra: Sequence[tuple[str, str]] = ()) -> list[str]:
    """The ONLY docker-run shape the harness ever executes — pure: no docker, no filesystem.

    Static tests assert on this; :func:`_runner_cmd` adds the side effects.
    """
    cmd = ["docker", "run", "--rm", "--network", NETWORK,
           "-v", f"{EXPORT_DIR}:/work:ro", "-v", f"{CORPUS_DIR}:/corpus:ro",
           "-v", f"{CACHE_DIR}:/cache:ro", "-v", f"{RUNS_DIR}:/runs:rw",
           "-e", "HF_HUB_OFFLINE=1", "-e", "ARMS849_CORPUS=/corpus", "-e", "ARMS849_CACHE=/cache",
           "-e", "OPENAI_API_KEY=", "-w", "/work"]
    for k, v in env_extra:
        cmd += ["-e", f"{k}={v}"]
    if entrypoint:
        cmd += ["--entrypoint", entrypoint]
    cmd += [RUNNER_IMAGE, *extra]
    return cmd


def _runner_cmd(extra: Iterable[str], *, entrypoint: str | None = None,
                env_extra: Sequence[tuple[str, str]] = ()) -> list[str]:
    """:func:`_runner_argv` after the preconditions: mount sources exist and are ours
    (checked BEFORE anything touches docker), then the runner image exists for this
    Dockerfile."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    _assert_mount_sources(EXPORT_DIR, CORPUS_DIR, CACHE_DIR, RUNS_DIR)
    _ensure_runner_image()
    return _runner_argv(extra, entrypoint=entrypoint, env_extra=env_extra)


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
# Excluded material must be absent under EVERY data mount, not only /work — a
# checkout bound at /runs would otherwise carry it in unchecked (Codex WP02 c6).
for rel in excl:
    for mnt in ("/work", "/corpus", "/cache", "/runs"):
        checks["absent:" + mnt + "/" + rel] = not os.path.exists(mnt + "/" + rel)
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
# Rubric 939d9b29: the arms apply the chat template inside this container, so jinja2
# and the cached tokenizer must render it here — not only on the host.
try:
    import transformers
    _t = transformers.AutoTokenizer.from_pretrained("/cache/qwen-tokenizer")
    _s = _t.apply_chat_template([{"role": "user", "content": "probe"}], add_generation_prompt=True, tokenize=False)
    checks["chat_template_renders"] = isinstance(_s, str) and "<|im_start|>user" in _s and "probe" in _s
except Exception as exc:  # noqa: BLE001
    checks["chat_template_renders"] = False
    checks["chat_template_error"] = f"{type(exc).__name__}: {exc}"[:300]
# Every bind mount must be one of the four the runner is allowed; an extra mount
# is a widened boundary and fails the test (it is not enough that it is unused).
# Every mount target must be EXACTLY one the runner is allowed — the four data
# mounts, docker's own /etc files, /dev tmpfs and its three standard submounts,
# the enumerated /sys entries — or a /proc/ masked path (runc refuses user
# mounts inside /proc). A nested target (/runs/leak), a look-alike (/dev-leak)
# or a stray /sys entry is a widened boundary and fails the test.
# Every mount target must be EXACTLY an allowed one AND of the filesystem type
# that target legitimately has: a bind of the host checkout over /dev/shm sits
# at an allowed path but is not tmpfs (Codex WP02 c5). The four data mounts are
# host binds whose identity is checked by content below.
expected_fstype = {
    "/dev": ("tmpfs",), "/dev/mqueue": ("mqueue",), "/dev/pts": ("devpts",), "/dev/shm": ("tmpfs",),
    "/proc": ("proc",), "/sys": ("sysfs",), "/sys/fs/cgroup": ("cgroup2", "cgroup"),
    "/sys/firmware": ("tmpfs",), "/sys/devices/virtual/powercap": ("tmpfs",),
}
data_mounts = {"/work", "/corpus", "/cache", "/runs"}
docker_etc = {"/etc/hostname", "/etc/hosts", "/etc/resolv.conf"}
extra = []
seen = {}
for line in open("/proc/self/mounts", encoding="utf-8"):
    parts = line.split()
    if len(parts) < 3:
        continue
    target, fstype = parts[1], parts[2]
    seen[target] = fstype
    if target == "/" or target in data_mounts or target in docker_etc:
        continue
    if target in expected_fstype:
        if fstype not in expected_fstype[target]:
            extra.append(f"{target}:fstype={fstype}")
        continue
    if target.startswith("/proc/") and fstype in ("proc", "tmpfs"):
        continue
    extra.append(target)
# The data mounts must be OUR data, not a checkout wearing the right path.
if not os.path.isfile("/work/scripts/research/arms849/compose/export-excludes.txt") or os.path.exists("/work/.git"):
    extra.append("/work:identity")
if not os.path.isfile("/corpus/stream.jsonl") or not os.path.isfile("/corpus/entities.json"):
    extra.append("/corpus:identity")
if not os.path.isdir("/cache/qwen-tokenizer"):
    extra.append("/cache:identity")
if not os.path.isfile("/runs/setup.json") or os.path.exists("/runs/.git"):
    extra.append("/runs:identity")
for mnt in ("/work", "/corpus", "/cache", "/runs"):
    if os.path.exists(mnt + "/.git"):
        extra.append(mnt + ":checkout")
checks["no_extra_mounts"] = not extra
if extra:
    checks["extra_mounts"] = extra
print(json.dumps(checks, indent=2))
sys.exit(0 if all(checks.values()) else 1)
"""


def self_test(host_checkout: pathlib.Path = REPO_ROOT, widen_with: Sequence[str] = ()) -> dict:
    """Denied-access test from INSIDE the boundary (contracts/gates.md `boundary`).

    `widen_with` exists for the NEGATIVE test only: extra `docker run` args (an
    extra bind mount) that must make the self-test FAIL.
    """
    cmd = _runner_cmd(["-c", SELF_TEST], entrypoint="python3",
                      env_extra=[("HOST_CHECKOUT", str(host_checkout))])
    if widen_with:
        idx = cmd.index(RUNNER_IMAGE)
        cmd = cmd[:idx] + list(widen_with) + cmd[idx:]
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
    sub.add_parser("down")
    sub.add_parser("health").add_argument("--yarn", action="store_true", help="expect the D-YaRN secondary configuration")
    e = sub.add_parser("export"); e.add_argument("--commit", default="HEAD")
    r = sub.add_parser("run"); r.add_argument("--self-test", action="store_true"); r.add_argument("args", nargs=argparse.REMAINDER)
    a = ap.parse_args(argv[1:])
    if a.cmd == "setup":
        print(json.dumps(setup(skip_gguf_verify=a.skip_gguf_verify), indent=2)); return 0
    if a.cmd == "up":
        print(json.dumps(asdict(up(yarn=a.yarn)), indent=2, default=str)); return 0
    if a.cmd == "health":
        env = compose_env(a.yarn, load_setup())
        st = health(expect_n_ctx=int(env["N_CTX"]), expect_rope="yarn" if a.yarn else "none")
        print(json.dumps(asdict(st), indent=2, default=str)); return 0 if st.falkordb_ok and st.llama_ok else 1
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
