"""Substrate lifecycle: the static half always runs; the live half needs ARMS849_LIVE=1 (WP02 T010)."""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.research.arms849 import substrate as SUB

live = pytest.mark.skipif(os.environ.get("ARMS849_LIVE") != "1", reason="live substrate tests need ARMS849_LIVE=1")


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
def test_live_up_health_down():
    state = SUB.up(yarn=False)
    assert state.falkordb_ok and state.llama_ok and state.n_ctx == 262_144
    rep = SUB.down()
    assert rep["clean"], rep


@live
def test_live_self_test_passes_and_a_widened_mount_fails(tmp_path):
    SUB.up(yarn=False)
    try:
        rep = SUB.self_test()
        assert rep["passed"], rep
    finally:
        SUB.down()
