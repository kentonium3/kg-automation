"""Substrate lifecycle: the static half always runs; the live half needs ARMS849_LIVE=1 (WP02 T010)."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import urllib.request

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
    rep = SUB.down()
    assert rep["clean"], rep


@live
def test_live_self_test_passes_and_a_widened_mount_fails(tmp_path, live_http):
    """The negative half is the point: an extra bind mount must be DETECTED from inside."""
    SUB.up(yarn=False)
    try:
        rep = SUB.self_test()
        assert rep["passed"], rep
        leak = tmp_path / "leak"; leak.mkdir(); (leak / "secret.txt").write_text("x")
        widened = SUB.self_test(widen_with=["-v", f"{leak}:/leak:ro"])
        assert not widened["passed"], widened
        assert widened["checks"].get("no_extra_mounts") is False
        assert "/leak" in widened["checks"].get("extra_mounts", [])
    finally:
        SUB.down()


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
    monkeypatch.setattr(SUB, "_sh", _fake_sh('["--model","/models/x.gguf","--rope-scaling","yarn","--yarn-orig-ctx","262144"]'))
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
