"""Mapping an installed-file report to baselines, and fold freshness (#1072 WP04).

Contract: kitty-specs/deploy-runtime-installed-report-01M4ZP8E/contracts/
installed-report.md. The mapper may only widen what the security monitor
tolerates with proof that a repo file landed under a surface's host_paths
(C-002), so every rejection path below is load-bearing.
"""
from __future__ import annotations

import datetime as _dt
import importlib.util
import pathlib
import subprocess
import sys
from unittest.mock import MagicMock

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
FELIX_DEPLOYER_DIR = REPO_ROOT / "scripts" / "deploy" / "felix-deployer"


def _load_rebaseline():
    for p in (REPO_ROOT, FELIX_DEPLOYER_DIR):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    spec = importlib.util.spec_from_file_location(
        "felix_deployer_rebaseline_reported_under_test", FELIX_DEPLOYER_DIR / "rebaseline.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


rbl = _load_rebaseline()

UNIT_BASELINES = [
    "enabled-services.txt",
    "systemd-user-dropins.txt",
    "systemd-user-unit-contents.txt",
    "systemd-user-units.txt",
]


@pytest.fixture
def layout(tmp_path):
    repo = tmp_path / "repo"
    unit = repo / "scripts" / "sync" / "systemd" / "x.timer"
    unit.parent.mkdir(parents=True)
    unit.write_text("[Timer]\n")
    other = repo / "README.md"
    other.write_text("hi\n")
    home = tmp_path / "home"
    unit_dir = home / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True)
    return {"repo": repo, "unit": unit, "other": other, "home": home, "unit_dir": unit_dir, "tmp": tmp_path}


def _report(*pairs):
    return {"entries": [{"source": str(s), "dest": str(d)} for s, d in pairs],
            "rejected": False, "missing": False, "warnings": []}


def _map(report, lay, **kw):
    return rbl.baselines_for_installed_report(report, lay["repo"], lay["home"], **kw)


# --- registry ---------------------------------------------------------------------

def test_registry_declares_host_paths_for_user_units():
    registry, err = rbl.load_audited_surfaces_or_error()
    assert err is None
    surface = next(s for s in registry["audited_surfaces"] if s["id"] == "systemd-user-units")
    assert surface["host_paths"] == ["~/.config/systemd/user/"]


# --- mapper -----------------------------------------------------------------------

def test_the_0029_shape_maps_to_the_unit_baselines(layout):
    res = _map(_report((layout["unit"], layout["unit_dir"] / "x.timer")), layout)
    assert res["rejected"] is False
    assert res["baselines"] == UNIT_BASELINES
    assert res["matched"] == ["scripts/sync/systemd/x.timer"]


def test_scratch_destination_rejects(layout):
    res = _map(_report((layout["unit"], layout["tmp"] / "scratch" / "x.timer")), layout)
    assert res["rejected"] is True and res["baselines"] == []


def test_source_outside_the_repo_rejects(layout):
    outside = layout["tmp"] / "elsewhere" / "scripts" / "sync" / "systemd" / "x.timer"
    res = _map(_report((outside, layout["unit_dir"] / "x.timer")), layout)
    assert res["rejected"] is True and res["baselines"] == []
    assert any("outside the repository" in w for w in res["warnings"])


def test_dotdot_source_escaping_the_repo_rejects(layout):
    sneaky = layout["repo"] / ".." / "evil" / "x.timer"
    res = _map(_report((sneaky, layout["unit_dir"] / "x.timer")), layout)
    assert res["rejected"] is True and res["baselines"] == []


def test_one_bad_entry_rejects_the_whole_report(layout):
    good = (layout["unit"], layout["unit_dir"] / "x.timer")
    bad = (layout["unit"], layout["tmp"] / "scratch" / "x.timer")
    res = _map(_report(good, bad, good), layout)
    assert res["rejected"] is True and res["baselines"] == [] and res["matched"] == []


def test_unmatched_source_contributes_nothing_and_is_not_an_error(layout):
    res = _map(_report((layout["other"], layout["tmp"] / "anywhere")), layout)
    assert res == {"baselines": [], "rejected": False, "matched": [], "warnings": []}


@pytest.mark.parametrize("rel", ["scripts/openclaw/openclaw.json", "requirements.txt"])
@pytest.mark.parametrize("under_host_paths", [False, True])
def test_surface_without_host_paths_contributes_nothing(layout, rel, under_host_paths):
    """C-002 (renata WP04 cycle 1): a surface with no host_paths can never be
    proven installed, so its baselines are never widened by a report, wherever
    the file landed."""
    src = layout["repo"] / rel
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("{}\n")
    dest = (layout["unit_dir"] if under_host_paths else layout["tmp"] / "scratch") / src.name
    res = _map(_report((src, dest)), layout)
    assert res == {"baselines": [], "rejected": False, "matched": [], "warnings": []}


def test_relative_paths_are_rejected_not_resolved_against_cwd(layout):
    res = _map({"entries": [{"source": "scripts/sync/systemd/x.timer", "dest": str(layout["unit_dir"] / "x.timer")}],
                "rejected": False}, layout)
    assert res["rejected"] is True and res["baselines"] == []


def test_symlinked_repo_root_and_home_are_accepted(layout):
    repo_link = layout["tmp"] / "repo-link"
    repo_link.symlink_to(layout["repo"])
    home_link = layout["tmp"] / "home-link"
    home_link.symlink_to(layout["home"])
    res = rbl.baselines_for_installed_report(
        _report((layout["unit"], layout["unit_dir"] / "x.timer")), repo_link, home_link)
    assert res["rejected"] is False and res["baselines"] == UNIT_BASELINES


def test_destination_symlink_leaving_the_host_path_rejects(layout):
    outside = layout["tmp"] / "outside"
    outside.mkdir()
    link = layout["unit_dir"] / "x.timer"
    link.symlink_to(outside / "x.timer")
    res = _map(_report((layout["unit"], link)), layout)
    assert res["rejected"] is True and res["baselines"] == []


def test_unreadable_registry_warns_and_maps_nothing(layout, monkeypatch):
    monkeypatch.setattr(rbl, "load_audited_surfaces_or_error", lambda: (None, "boom"))
    res = _map(_report((layout["unit"], layout["unit_dir"] / "x.timer")), layout)
    assert res["baselines"] == [] and any("boom" in w for w in res["warnings"])


@pytest.mark.parametrize("report", [
    None,
    "nope",
    {"entries": [], "rejected": True, "missing": False, "warnings": ["bad report"]},
    {"entries": [{"source": "/x"}], "rejected": False},  # malformed entry
])
def test_rejected_or_malformed_reports_map_nothing_and_never_raise(layout, report):
    res = _map(report, layout)
    assert res["baselines"] == [] and res["rejected"] is True


def test_missing_report_maps_nothing_without_rejecting(layout):
    res = _map({"entries": [], "rejected": False, "missing": True, "warnings": []}, layout)
    assert res["baselines"] == [] and res["rejected"] is False


# --- fold freshness ---------------------------------------------------------------

def _iso(delta_seconds: float) -> str:
    return (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(seconds=delta_seconds)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _proc(stdout="", returncode=0):
    p = MagicMock(spec=subprocess.CompletedProcess)
    p.stdout, p.stderr, p.returncode = stdout, "", returncode
    return p


def _old_token(pending_since):
    return {
        "schema_version": rbl.SCHEMA_VERSION,
        "pending_since_utc": pending_since,
        "observed_head_sha": "a" * 40,
        "surface_ids": ["openclaw-config"],
        "expected_baselines": ["openclaw-config.txt"],
        "matched_files": ["scripts/openclaw/openclaw.json"],
        "last_check_utc": None,
        "alerts_emitted": [],
        "manifest_names": ["0040-earlier"],
    }


_REGISTRY = {
    "rebaseline_command": "ssh office2-claude 'rm /data/services/security-monitor/baselines/* "
                          "&& sg docker -c /data/services/security-monitor/scripts/audit.sh'",
    "audited_surfaces": [
        {"id": "openclaw-config", "patterns": ["scripts/openclaw/openclaw.json"],
         "affected_baselines": ["openclaw-config.txt"]},
    ],
}


def test_fold_into_an_old_token_gets_a_fresh_grace_window(tmp_path):
    token_path = tmp_path / "token.json"
    rbl.write_token(_old_token(_iso(-3600)), token_path)
    rbl.fold_manifest_baselines({"systemd-user-units.txt"}, observed_head_sha="b" * 40,
                                manifest_names=["0041-reinstall"], token_path=token_path)
    token = rbl.read_token(token_path)
    assert token["last_fold_utc"] and token["manifest_names"] == ["0040-earlier", "0041-reinstall"]
    result = rbl.reconcile(token_path=token_path, registry=_REGISTRY,
                           audit_runner=lambda cmd: _proc("Security audit 2026-10-15: All clear"))
    assert result["outcome"] == rbl.OUTCOME_PENDING_CLEAN
    assert token_path.exists()


def test_without_a_fold_the_old_token_clears(tmp_path):
    """Control for the test above: the fold stamp is what keeps the token."""
    token_path = tmp_path / "token.json"
    rbl.write_token(_old_token(_iso(-3600)), token_path)
    result = rbl.reconcile(token_path=token_path, registry=_REGISTRY,
                           audit_runner=lambda cmd: _proc("Security audit 2026-10-15: All clear"))
    assert result["outcome"] == rbl.OUTCOME_CLEARED_CLEAN


def test_observe_merge_keeps_fold_fields(tmp_path):
    token_path = tmp_path / "token.json"
    rbl.write_token(_old_token(_iso(-3600)), token_path)
    rbl.fold_manifest_baselines({"systemd-user-units.txt"}, observed_head_sha="b" * 40,
                                manifest_names=["0041-reinstall"], token_path=token_path)
    folded = rbl.read_token(token_path)

    def git(args):
        return _proc("scripts/openclaw/openclaw.json\n") if args[0] == "diff" else _proc()

    rbl.observe("a" * 40, "c" * 40, token_path=token_path, git_runner=git, registry=_REGISTRY)
    token = rbl.read_token(token_path)
    assert token["last_fold_utc"] == folded["last_fold_utc"]
    assert token["manifest_names"] == ["0040-earlier", "0041-reinstall"]
    assert "systemd-user-units.txt" in token["expected_baselines"]


def test_stale_still_measures_from_pending_since(tmp_path):
    token_path = tmp_path / "token.json"
    token = _old_token(_iso(-25 * 3600))
    token["last_fold_utc"] = _iso(0)
    rbl.write_token(token, token_path)
    result = rbl.reconcile(token_path=token_path, registry=_REGISTRY, max_age_seconds=86_400,
                           audit_runner=lambda cmd: _proc("garbage", returncode=2))
    assert result.get("stale") is True


def test_fold_tolerates_a_corrupt_names_field(tmp_path):
    token_path = tmp_path / "token.json"
    token = _old_token(_iso(-3600))
    token["manifest_names"] = 7
    rbl.write_token(token, token_path)
    res = rbl.fold_manifest_baselines({"systemd-user-units.txt"}, observed_head_sha="b" * 40,
                                      manifest_names=["0041-reinstall"], token_path=token_path)
    assert res["outcome"] == "merged"
    assert rbl.read_token(token_path)["manifest_names"] == ["0041-reinstall"]
