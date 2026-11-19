"""Substrate lifecycle: the static half always runs; the live half needs ARMS849_LIVE=1 (WP02 T010)."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.research.arms849 import substrate as SUB

live = pytest.mark.skipif(os.environ.get("ARMS849_LIVE") != "1", reason="live substrate tests need ARMS849_LIVE=1")
_REAL_URLOPEN = urllib.request.urlopen   # captured before the conftest guard patches it


@pytest.fixture
def live_http(monkeypatch):
    """Live tests deliberately probe the local stack; lift the repo-wide no-live-HTTP guard."""
    monkeypatch.setattr(urllib.request, "urlopen", _REAL_URLOPEN)


# --------------------------------------------------------------------------
# compose.yaml renders the envelope research.md D-9 certifies
# --------------------------------------------------------------------------


def _compose():
    return yaml.safe_load((SUB.COMPOSE_DIR / "compose.yaml").read_text())


def test_compose_project_network_and_volume():
    c = _compose()
    assert c["name"] == "arms849"
    assert c["networks"]["arms849-net"]["internal"] is True
    # The runner joins ONLY the internal network (design-lead 01:00Z: assert it, do not construct it).
    cmd = SUB._runner_argv(["-c", "pass"], entrypoint="python3")     # pure: no docker in a static test
    nets = [cmd[i + 1] for i, a in enumerate(cmd) if a == "--network"]
    assert nets == [SUB.NETWORK] and SUB.NETWORK.endswith("arms849-net")
    assert not any(a.startswith("ARMS849_LLAMA_HOSTS") for a in cmd)   # the allowlist is a constant (WP01)
    assert "arms849-falkor" in c["volumes"]


def test_compose_ports_bind_loopback_only():
    c = _compose()
    for svc in ("falkordb", "llama"):
        for p in c["services"][svc]["ports"]:
            assert p.startswith("127.0.0.1:"), p
    assert "127.0.0.1:16379:6379" in c["services"]["falkordb"]["ports"]
    assert "127.0.0.1:18080:8080" in c["services"]["llama"]["ports"]


def test_compose_llama_uses_known_good_flags_and_render_group():
    c = _compose()
    llama = c["services"]["llama"]
    cmd = " ".join(llama["command"].split())
    for flag in ("--parallel 1", "--n-gpu-layers 999", "--jinja", "--ctx-size ${N_CTX}", "${ROPE_ARGS}"):
        assert flag in cmd, flag
    assert "992" in [str(g) for g in llama["group_add"]]
    assert "/dev/dri:/dev/dri" in llama["devices"]
    assert any(v.endswith(":/models:ro") for v in llama["volumes"])


def test_compose_env_primary_vs_yarn():
    rec = {"falkordb_image": "falkordb/falkordb@sha256:abc", "llama_image": SUB.LLAMA_IMAGE}
    p, s = SUB.compose_env(False, rec), SUB.compose_env(True, rec)
    assert p["N_CTX"] == "262144" and p["ROPE_ARGS"] == ""
    assert s["N_CTX"] == "393216" and s["ROPE_ARGS"] == "--rope-scaling yarn --rope-scale 2 --yarn-orig-ctx 262144"
    assert p["LLAMA_IMAGE"].startswith("ghcr.io/ggml-org/llama.cpp@sha256:063e88ae")


def test_images_are_pinned_by_digest_not_tag():
    assert "@sha256:" in SUB.LLAMA_IMAGE
    # FalkorDB is resolved to a digest at setup; the tag is only the resolution input.
    assert SUB.FALKORDB_DIGEST_PREFIX.startswith("sha256:")


# --------------------------------------------------------------------------
# export: exclusions and the content manifest
# --------------------------------------------------------------------------


def test_exclusion_list_covers_every_d8_path():
    ex = SUB.excluded_prefixes()
    for p in ("docs/design/research/849-synthesis/oracle/", "docs/design/research/849-synthesis/seed/",
              "docs/design/research/849-synthesis/00-context-chains.md", "docs/design/research/849-synthesis/01-cast.md",
              "docs/design/research/849-lattice-scenario-arcs.md", "docs/design/research/849-traceability.md", "kitty-specs/"):
        assert p in ex, p


def _tmp_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    repo = tmp_path / "repo"; repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    for rel in ("scripts/keep.py", "docs/design/research/849-synthesis/oracle/A.yaml",
                "docs/design/research/849-synthesis/seed/arc-a.yaml", "kitty-specs/x/spec.md", "docs/design/research/849-rubric.md"):
        f = repo / rel; f.parent.mkdir(parents=True, exist_ok=True); f.write_text(f"content of {rel}\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init"], check=True)
    return repo


def test_export_excludes_the_paths_and_records_a_content_sha(tmp_path):
    repo = _tmp_repo(tmp_path)
    dest = tmp_path / "env"
    m = SUB.export(commit="HEAD", repo=repo, dest=dest)
    assert (dest / "scripts/keep.py").exists() and (dest / "docs/design/research/849-rubric.md").exists()
    for p in ("docs/design/research/849-synthesis/oracle", "docs/design/research/849-synthesis/seed", "kitty-specs"):
        assert not (dest / p).exists(), p
    assert len(m["content_sha"]) == 64 and m["source_commit"]


def test_content_sha_changes_when_content_changes(tmp_path):
    repo = _tmp_repo(tmp_path)
    m1 = SUB.export(repo=repo, dest=tmp_path / "e1")
    (repo / "scripts/keep.py").write_text("changed\n")
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qam", "change"], check=True)
    m2 = SUB.export(repo=repo, dest=tmp_path / "e2")
    assert m1["content_sha"] != m2["content_sha"]


def test_content_sha_is_over_contents_not_names(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    for d, body in ((a, "one"), (b, "two")):
        d.mkdir(); (d / "same-name.txt").write_text(body)
    assert SUB.content_manifest_sha(a) != SUB.content_manifest_sha(b)


def test_export_refuses_a_dirty_tree(tmp_path):
    repo = _tmp_repo(tmp_path)
    (repo / "scripts/keep.py").write_text("dirty\n")
    with pytest.raises(RuntimeError, match="dirty"):
        SUB.export(repo=repo, dest=tmp_path / "env")


# --------------------------------------------------------------------------
# live: the real stack on office4
# --------------------------------------------------------------------------


@live
def test_live_up_health_down(live_http):
    state = SUB.up(yarn=False)
    assert state.falkordb_ok and state.llama_ok and state.n_ctx == 262_144
    # Codex c2: the same healthy stack must FAIL a health check with the wrong expectation.
    assert not SUB.health(expect_n_ctx=4096, expect_rope="none").llama_ok
    assert not SUB.health(expect_n_ctx=262_144, expect_rope="yarn").llama_ok
    rep = SUB.down()
    assert rep["clean"], rep


@live
def test_live_self_test_passes_and_a_widened_mount_fails(tmp_path, live_http, monkeypatch):
    """The negative half is the point: an extra bind mount must be DETECTED from inside."""
    SUB.up(yarn=False)
    try:
        rep = SUB.self_test()
        assert rep["passed"], rep
        leak = tmp_path / "leak"; leak.mkdir(); (leak / "secret.txt").write_text("x")
        # Codex c2: a nested target, a look-alike prefix, a stray /etc or /dev entry must all be
        # caught by the exact allowlist.
        for target in ("/leak", "/runs/leak", "/dev-leak", "/etc/leak", "/dev/leak"):
            widened = SUB.self_test(widen_with=["-v", f"{leak}:{target}:ro"])
            assert not widened["passed"], (target, widened)
            assert widened["checks"].get("no_extra_mounts") is False, target
            assert target in widened["checks"].get("extra_mounts", []), target
        # Codex c5: an allowlisted DESTINATION with the wrong identity — the host checkout bound
        # over /dev/shm (not tmpfs) — must be caught by the filesystem-type check.
        widened = SUB.self_test(widen_with=["-v", f"{SUB.REPO_ROOT}:/dev/shm:ro"])
        assert not widened["passed"], widened
        assert any(e.startswith("/dev/shm:fstype=") for e in widened["checks"].get("extra_mounts", [])), widened
        # Codex c6: the checkout mounted AS a data mount (/runs) must fail on identity — the
        # runner's own configuration is changed here, so the argv itself carries the leak.
        # (SELF_TEST never writes under /runs, so the checkout stays clean.)
        monkeypatch.setattr(SUB, "RUNS_DIR", SUB.REPO_ROOT)
        try:
            widened = SUB.self_test()
        finally:
            monkeypatch.undo()
        assert not widened["passed"], widened
        assert "/runs:identity" in widened["checks"].get("extra_mounts", []), widened
        assert "/runs:checkout" in widened["checks"].get("extra_mounts", []), widened
        assert any(k.startswith("absent:/runs/") and v is False for k, v in widened["checks"].items()), widened
        # Codex c10: an excluded file bound over a docker-managed /etc path must fail on the
        # mount's SOURCE identity (docker's own binds root in …/containers/<id>/).
        excluded_file = SUB.REPO_ROOT / "docs" / "design" / "research" / "849-synthesis" / ("or" + "acle") / "A.yaml"
        assert excluded_file.is_file(), excluded_file
        widened = SUB.self_test(widen_with=["-v", f"{excluded_file}:/etc/hostname:ro"])
        assert not widened["passed"], widened
        assert any(e.startswith("/etc/hostname:") for e in widened["checks"].get("extra_mounts", [])), widened
        # /sys and /proc are refused by the runtime itself (read-only rootfs / runc) before the
        # script runs: still not passed, and the refusal is the recorded reason.
        for target in ("/sys/leak", "/proc/leak"):
            widened = SUB.self_test(widen_with=["-v", f"{leak}:{target}:ro"])
            assert not widened["passed"] and widened["checks"] == {}, (target, widened)
            assert "error mounting" in widened["stderr"] or "not allowed" in widened["stderr"], widened["stderr"]
    finally:
        SUB.down()


def test_runner_refuses_a_missing_mount_source(tmp_path, monkeypatch):
    """Docker would create a missing bind source as a root-owned dir; the runner refuses first."""
    monkeypatch.setattr(SUB, "CACHE_DIR", tmp_path / "absent")
    def no_docker(): raise AssertionError("docker must not be reached before the mount check")
    monkeypatch.setattr(SUB, "_ensure_runner_image", no_docker)
    with pytest.raises(RuntimeError, match="mount source"):
        SUB._runner_cmd(["-c", "pass"], entrypoint="python3")


def _run_dirs(tmp_path: pathlib.Path, monkeypatch) -> None:
    """A valid exported runner envelope, without reaching Docker."""
    export = tmp_path / "export"
    export.mkdir()
    (export / "payload.txt").write_text("the exported payload\n")
    manifest = {"content_sha": SUB.content_manifest_sha(export)}
    (export / ".export-manifest.json").write_text(json.dumps(manifest) + "\n")
    for name in ("corpus", "cache", "runs"):
        (tmp_path / name).mkdir()
    monkeypatch.setattr(SUB, "EXPORT_DIR", export)
    monkeypatch.setattr(SUB, "CORPUS_DIR", tmp_path / "corpus")
    monkeypatch.setattr(SUB, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(SUB, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(SUB, "_ensure_runner_image", lambda: None)


def _runner_env(argv: list[str]) -> dict[str, str]:
    return dict(argv[i + 1].split("=", 1) for i, arg in enumerate(argv) if arg == "-e")


def test_run_wraps_only_the_runner_with_one_generation_writer(tmp_path, monkeypatch):
    """T014: inspect may be slow; the generation starts only after it resolves."""
    _run_dirs(tmp_path, monkeypatch)
    started = datetime(2026, 9, 27, 15, 0, 0, 123456, tzinfo=timezone.utc)
    now = [started - timedelta(seconds=30)]
    container_id = "a" * 64
    events: list[str] = []
    runner_argv: list[str] = []

    monkeypatch.setattr(SUB, "_new_series_id", lambda: "generation-1")

    def clock() -> datetime:
        events.append("clock")
        return now[0]

    monkeypatch.setattr(SUB, "_utc_now", clock)

    def resolve(container: str) -> str:
        assert container == "arms849-falkordb-1"
        events.append("inspect")
        now[0] = started
        return container_id

    monkeypatch.setattr(SUB, "docker_container_id", resolve)

    class Writer:
        def __init__(self, path, series_id, container, *, container_id, started, interval_s):
            assert pathlib.Path(path) == SUB.RUNS_DIR / "falkordb-cgroup-generation-1.jsonl"
            assert (series_id, container, container_id) == ("generation-1", "arms849-falkordb-1", "a" * 64)
            assert started == datetime(2026, 9, 27, 15, 0, 0, 123456, tzinfo=timezone.utc)
            self.path, self.series_id, self.container = pathlib.Path(path), series_id, container
            self.container_id, self.started, self.interval_s = container_id, started, interval_s

        def start(self):
            events.append("start")

        def stop(self):
            events.append("stop")

    monkeypatch.setattr(SUB, "CgroupSeriesWriter", Writer)

    def fake_run(argv, *, check):
        assert check is False
        events.append("runner")
        runner_argv.extend(argv)
        return type("P", (), {"returncode": 7})()

    monkeypatch.setattr(SUB.subprocess, "run", fake_run)
    assert SUB.run(["--ledger", "/runs/l.jsonl"]) == 7
    assert events == ["inspect", "clock", "start", "runner", "stop"]

    descriptor = json.loads(_runner_env(runner_argv)[SUB.SERIES_GENERATION_ENV])
    assert descriptor == {
        "container_id": container_id,
        "interval_s": 1.0,
        "path": "/runs/falkordb-cgroup-generation-1.jsonl",
        "series_id": "generation-1",
        "started_ts": "2026-09-27T15:00:00.123456+00:00",
        "writer_reason": None,
        "writer_status": "running",
    }


def test_run_launches_runner_when_container_id_cannot_be_resolved(tmp_path, monkeypatch):
    """The run-level measure is observational: failed inspect becomes evidence, not a refusal."""
    _run_dirs(tmp_path, monkeypatch)
    started = datetime(2026, 9, 27, 15, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(SUB, "_new_series_id", lambda: "inspect-failed")
    events: list[str] = []

    def clock() -> datetime:
        events.append("clock")
        return started

    monkeypatch.setattr(SUB, "_utc_now", clock)

    def failed_inspect(_container):
        events.append("inspect")
        raise subprocess.CalledProcessError(1, ["docker", "inspect"], stderr="no such container")

    monkeypatch.setattr(SUB, "docker_container_id", failed_inspect)
    monkeypatch.setattr(SUB, "CgroupSeriesWriter", lambda *a, **k: pytest.fail("writer must not be constructed"))
    seen: list[list[str]] = []

    def fake_run(argv, *, check):
        seen.append(argv)
        return type("P", (), {"returncode": 9})()

    monkeypatch.setattr(SUB.subprocess, "run", fake_run)
    assert SUB.run([]) == 9
    assert events == ["inspect", "clock"]
    assert len(seen) == 1 and seen[0][:2] == ["docker", "run"]
    descriptor = json.loads(_runner_env(seen[0])[SUB.SERIES_GENERATION_ENV])
    assert descriptor["writer_status"] == "failed"
    assert descriptor["container_id"] is None
    assert descriptor["path"] == "/runs/falkordb-cgroup-inspect-failed.jsonl"
    assert descriptor["interval_s"] == 1.0
    assert descriptor["started_ts"] == "2026-09-27T15:00:00+00:00"
    assert descriptor["writer_reason"] and "CalledProcessError" in descriptor["writer_reason"]


def test_preexisting_series_is_not_truncated_and_does_not_block_runner(tmp_path, monkeypatch):
    """The real exclusive writer turns a collision into failed evidence and preserves the file."""
    _run_dirs(tmp_path, monkeypatch)
    monkeypatch.setattr(SUB, "_new_series_id", lambda: "already-there")
    monkeypatch.setattr(SUB, "_utc_now", lambda: datetime(2026, 9, 27, 15, 0, tzinfo=timezone.utc))
    series = SUB.RUNS_DIR / "falkordb-cgroup-already-there.jsonl"
    original = b"pre-existing evidence must survive\n"
    series.write_bytes(original)
    calls: list[list[str]] = []

    def fake_docker(argv, **kwargs):
        calls.append(argv)
        if argv[:2] == ["docker", "inspect"]:
            return type("P", (), {"stdout": "b" * 64 + "\n", "returncode": 0})()
        assert argv[:2] == ["docker", "run"]
        return type("P", (), {"stdout": "", "returncode": 4})()

    monkeypatch.setattr(SUB.subprocess, "run", fake_docker)
    assert SUB.run([]) == 4
    assert series.read_bytes() == original
    assert sum(argv[:2] == ["docker", "inspect"] for argv in calls) == 1
    run_argv = next(argv for argv in calls if argv[:2] == ["docker", "run"])
    descriptor = json.loads(_runner_env(run_argv)[SUB.SERIES_GENERATION_ENV])
    assert descriptor["writer_status"] == "failed"
    assert descriptor["container_id"] == "b" * 64
    assert descriptor["path"] == "/runs/falkordb-cgroup-already-there.jsonl"
    assert "FileExistsError" in descriptor["writer_reason"]


def test_writer_stop_failure_does_not_replace_the_runner_result(tmp_path, monkeypatch):
    """Stopping observational measurement cannot turn a completed harness into a failure."""
    _run_dirs(tmp_path, monkeypatch)
    monkeypatch.setattr(SUB, "_new_series_id", lambda: "stop-failed")
    monkeypatch.setattr(SUB, "_utc_now", lambda: datetime(2026, 9, 27, 15, 0, tzinfo=timezone.utc))
    monkeypatch.setattr(SUB, "docker_container_id", lambda _container: "c" * 64)

    class Writer:
        def __init__(self, path, series_id, container, *, container_id, started, interval_s):
            self.path, self.series_id, self.container = pathlib.Path(path), series_id, container
            self.container_id, self.started, self.interval_s = container_id, started, interval_s

        def start(self):
            pass

        def stop(self):
            raise OSError("trailer write failed")

    monkeypatch.setattr(SUB, "CgroupSeriesWriter", Writer)
    monkeypatch.setattr(SUB.subprocess, "run", lambda argv, *, check: type("P", (), {"returncode": 3})())
    assert SUB.run([]) == 3


def test_runner_image_installs_every_light_dep_and_no_openai():
    df = (SUB.COMPOSE_DIR / "runner.Dockerfile").read_text()
    for dep in SUB.TOKENIZER_LIGHT_DEPS:
        assert dep in df, dep
    assert "ARMS849_LLAMA_HOSTS" not in df
    req = (SUB.COMPOSE_DIR / "requirements-arms849.txt").read_text()
    assert "openai" not in [line.split("==")[0] for line in req.splitlines() if line and not line.startswith("#")]


@pytest.mark.parametrize("changed", ["runner.Dockerfile", "requirements-arms849.txt"])
def test_runner_image_tag_follows_its_build_inputs(tmp_path, monkeypatch, changed):
    """A changed Dockerfile OR requirements file yields a different tag (Codex c5)."""
    before = SUB._runner_dockerfile_sha()
    assert SUB.RUNNER_IMAGE.endswith(before) and len(before) == 12
    for name in SUB.RUNNER_IMAGE_INPUTS:
        (tmp_path / name).write_bytes((SUB.COMPOSE_DIR / name).read_bytes())
    monkeypatch.setattr(SUB, "COMPOSE_DIR", tmp_path)
    assert SUB._runner_dockerfile_sha() == before
    (tmp_path / changed).write_bytes((tmp_path / changed).read_bytes() + b"\n# changed\n")
    assert SUB._runner_dockerfile_sha() != before


def test_runner_base_is_digest_pinned():
    ref = SUB.runner_base_image()
    assert ref.startswith("python:3.12-slim@sha256:") and len(ref.split("@sha256:")[1]) == 64


def test_light_deps_carry_jinja2_and_never_torch():
    assert "jinja2" in SUB.TOKENIZER_LIGHT_DEPS and "torch" not in SUB.TOKENIZER_LIGHT_DEPS


def test_expected_gguf_sha_requires_exactly_one_full_filename_entry(tmp_path):
    sums = tmp_path / "SHA256SUMS"
    good = "a" * 64
    sums.write_text(f"{good}  model.gguf\n{'b' * 64}  model.gguf.wrong\n")
    assert SUB.expected_gguf_sha(sums, "model.gguf") == good
    sums.write_text("nothing here\n")
    with pytest.raises(RuntimeError, match="exactly one"):
        SUB.expected_gguf_sha(sums, "model.gguf")
    sums.write_text(f"{good}  model.gguf\n{good}  model.gguf\n")
    with pytest.raises(RuntimeError, match="exactly one"):
        SUB.expected_gguf_sha(sums, "model.gguf")


def _fake_sh(stdout: str):
    return lambda cmd, check=True, capture=True, **k: type("P", (), {"stdout": stdout, "returncode": 0})()


def test_rope_mode_is_the_container_arg_and_unknown_when_uninspectable(monkeypatch):
    monkeypatch.setattr(SUB, "_sh", _fake_sh('["--model","/models/x.gguf","--rope-scaling","yarn","--rope-scale","2","--yarn-orig-ctx","262144"]'))
    assert SUB._rope_mode() == "yarn"
    # Codex c3: YaRN with other parameters is a DIFFERENT configuration, never "yarn".
    monkeypatch.setattr(SUB, "_sh", _fake_sh('["--rope-scaling","yarn","--rope-scale","99","--yarn-orig-ctx","4096"]'))
    assert SUB._rope_mode() == "yarn:99:4096"
    monkeypatch.setattr(SUB, "_sh", _fake_sh('["--rope-scaling","yarn"]'))
    assert SUB._rope_mode() == "yarn:None:None"
    monkeypatch.setattr(SUB, "_sh", _fake_sh('["--rope-scaling=yarn","--rope-scale=2","--yarn-orig-ctx=262144"]'))
    assert SUB._rope_mode() == "yarn"
    monkeypatch.setattr(SUB, "_sh", _fake_sh('["--model","/models/x.gguf","-c","262144"]'))
    assert SUB._rope_mode() == "none"
    def boom(*a, **k): raise RuntimeError("no such container")
    monkeypatch.setattr(SUB, "_sh", boom)
    assert SUB._rope_mode() == "unknown"


def _answering(answers: dict[str, bytes]):
    class R:
        def __init__(self, url, *a, **k): self.body = answers["/" + url.rsplit("/", 1)[-1]]
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return self.body
    return lambda url, *a, **k: R(url)


def test_health_rejects_empty_props_wrong_model_and_wrong_n_ctx(monkeypatch):
    import urllib.request
    cases = [
        ({}, False),
        ({"default_generation_settings": {"n_ctx": 262144}, "model_path": "/models/other.gguf"}, False),
        ({"default_generation_settings": {"n_ctx": 4096}, "model_path": f"/models/{SUB.GGUF_FILE}"}, False),
        ({"default_generation_settings": {"n_ctx": 262144}, "model_path": f"/models/{SUB.GGUF_FILE}"}, True),
    ]
    monkeypatch.setattr(SUB, "_rope_mode", lambda *a, **k: "none")
    monkeypatch.setattr(SUB, "load_setup", lambda: {"falkordb_image": "x", "llama_image": "y"})
    monkeypatch.setattr(SUB, "_sh", _fake_sh(""))          # falkordb GRAPH.LIST → rc 0
    for props, ok in cases:
        answers = {"/health": b'{"status": "ok"}', "/props": json.dumps(props).encode()}
        monkeypatch.setattr(urllib.request, "urlopen", _answering(answers))
        st = SUB.health(expect_n_ctx=262144, expect_rope="none")
        assert st.llama_ok is ok, (props, st)


def test_exclusion_matching_is_exact_for_files_and_prefix_for_dirs():
    ex = ("docs/a/", "docs/b.md")
    assert SUB._excluded("docs/a/x.yaml", ex) and SUB._excluded("docs/a", ex)
    assert SUB._excluded("docs/b.md", ex)
    assert not SUB._excluded("docs/b.md.backup", ex)
    assert not SUB._excluded("docs/ab/x", ex)


def test_down_report_is_not_clean_without_a_gtt_measurement(monkeypatch):
    monkeypatch.setattr(SUB, "gtt_used_gib", lambda: None)
    monkeypatch.setattr(SUB, "_compose", lambda *a, **k: None)
    monkeypatch.setattr(SUB, "_sh", lambda cmd, check=True, capture=True, **k: type("P", (), {"stdout": "", "returncode": 0})())
    monkeypatch.setattr(SUB, "load_setup", lambda: {"falkordb_image": "x", "llama_image": "y"})
    rep = SUB.down()
    assert rep["gtt_verified"] is False and rep["clean"] is False
