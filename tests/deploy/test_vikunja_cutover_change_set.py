"""Historical Compose contract and phase-aware repeat cutover; see #1095.

History is explicitly 0033/0034 with the frozen first-cutover identities
(see #1087). STAGE retains deployed inventory; ACTIVATE promotes it. A broken
queued manifest cannot be masked by applied history or a valid applied release.
The historical Compose reversal hash also works in shallow CI checkouts.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import subprocess
import shutil
import sys
from pathlib import Path

import pytest
import yaml

from scripts.deploy.lib import manifest as manifest_lib
from scripts.deploy.vikunja_release import baseline, core

_ROOT = Path(__file__).resolve().parents[2]
_COMPOSE = _ROOT / "services" / "vikunja" / "docker-compose.yml"
_INVENTORY_JSON = _ROOT / "docs" / "design" / "architecture" / "data" / "service-inventory.json"
_INVENTORY_MD = _ROOT / "docs" / "design" / "architecture" / "service-inventory.md"
_ENTRY_REL = "scripts/deploy/deploy-vikunja-release-activate.py"
_HISTORICAL_ACTIVATE = "0034-vikunja-release-activate.yaml"
_HISTORICAL_STAGE = "0033-vikunja-release-stage.yaml"
_FROZEN = _ROOT / "tests/deploy/fixtures/vikunja_first_cutover_release.json"

#: The mission base on origin/main, and the sha256 of its Compose file.
BASE_COMMIT = "93f40d4a"
BASE_COMPOSE_SHA256 = "ae5c779b6acd8bde58c2de3f9f0377948b23511e3d6aac8504cd221c8197cd7b"
OLD_LINE = "    image: vikunja/vikunja:2.4.0\n"
NEW_LINES = "    image: office2.local/vikunja:active\n    pull_policy: never\n"

#: Historical first-cutover set; repeat ACTIVATE has just the three WP07 paths.
HISTORICAL_CUTOVER_PATHS = frozenset({
    "services/vikunja/docker-compose.yml",
    "deploys/queued/vikunja-release-activate.yaml",
    "docs/design/architecture/data/service-inventory.json",
    "docs/design/architecture/service-inventory.md",
    "tests/deploy/test_vikunja_cutover_change_set.py",
})
CUTOVER_PATHS = frozenset({
    "deploys/queued/vikunja-release-activate.yaml",
    "docs/design/architecture/data/service-inventory.json",
    "docs/design/architecture/service-inventory.md",
})
#: Paths the cutover depends on that must ship EARLIER, in the STAGE merge:
#: the inert ACTIVATE code, the release record and the STAGE manifest.
STAGE_MERGE_PREREQUISITES = frozenset({
    "scripts/deploy/deploy-vikunja-release-activate.py",
    "services/vikunja/release.json",
    "deploys/queued/vikunja-release-stage.yaml",
    "scripts/deploy/vikunja_release/core.py",
})


def _release(root: Path = _ROOT) -> dict:
    return core.load_release(root / "services/vikunja/release.json")


def _manifest(path: Path) -> dict:
    result = manifest_lib.validate_manifest_file(path)
    assert result.ok, result.details
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _historical_release(root: Path) -> dict:
    rec = json.loads(_FROZEN.read_text(encoding="utf-8"))
    # The frozen fixture sanitizes service locations. Derive the historical
    # public endpoint from unchanged Compose, independently of release.json.
    service = yaml.safe_load((root / "services/vikunja/docker-compose.yml").read_text())["services"]["vikunja"]
    rec["service"]["container"] = service["container_name"]
    rec["service"]["info_url"] = "http://" + service["ports"][0].rsplit(":", 1)[0] + "/api/v1/info"
    return rec


# ---------------------------------------------------------------------------
# T033 — the two-line Compose change
# ---------------------------------------------------------------------------


def two_line_change_problems(text: str) -> list[str]:
    """Why *text* is not exactly the base plus the two-line change ([] = ok)."""
    problems = []
    if text.count(NEW_LINES) != 1:
        problems.append("the new image line with pull_policy directly under it appears != 1 time")
        return problems
    base = text.replace(NEW_LINES, OLD_LINE)
    if hashlib.sha256(base.encode("utf-8")).hexdigest() != BASE_COMPOSE_SHA256:
        problems.append("reversing the two lines does not give the base file byte for byte")
    removed = [l for l in difflib.ndiff(base.splitlines(True), text.splitlines(True)) if l.startswith("- ")]
    added = [l for l in difflib.ndiff(base.splitlines(True), text.splitlines(True)) if l.startswith("+ ")]
    if removed != ["- " + OLD_LINE] or added != ["+ " + l + "\n" for l in NEW_LINES.splitlines()]:
        problems.append("the diff is not exactly -image/+image/+pull_policy")
    return problems


def test_historical_compose_is_the_base_plus_exactly_two_lines():
    text = _COMPOSE.read_text(encoding="utf-8")
    assert two_line_change_problems(text) == []
    svc = yaml.safe_load(text)["services"]["vikunja"]
    base_svc = yaml.safe_load(text.replace(NEW_LINES, OLD_LINE))["services"]["vikunja"]
    assert svc["image"] == _release()["tags"]["active"] == "office2.local/vikunja:active"
    assert svc["pull_policy"] == "never"
    assert {k: v for k, v in svc.items() if k not in ("image", "pull_policy")} == \
        {k: v for k, v in base_svc.items() if k != "image"}
    # The fields FR-007 names, unchanged:
    assert svc["container_name"] == "vikunja" and svc["restart"] == "unless-stopped"
    assert svc["ports"] == ["100.92.197.90:3456:3456"]
    assert svc["volumes"] == ["/data/services/vikunja/data:/app/vikunja/files"]
    assert svc["environment"]["VIKUNJA_DATABASE_PATH"] == "/app/vikunja/files/vikunja.db"


@pytest.mark.parametrize("mutate", [
    lambda t: t.replace("100.92.197.90:3456:3456", "0.0.0.0:3456:3456"),
    lambda t: t.replace("/app/vikunja/files/vikunja.db", "/db/vikunja.db"),
    lambda t: t.replace("restart: unless-stopped", "restart: always"),
    lambda t: t.replace(NEW_LINES, "    image: office2.local/vikunja:active\n"),  # pull_policy missing
    lambda t: t.replace(NEW_LINES, "    pull_policy: never\n    image: office2.local/vikunja:active\n"),
    lambda t: t.replace("# Vikunja Task Manager", "# Vikunja task manager"),  # header comment
    lambda t: t + "\n",
], ids=["bind", "db-path", "restart", "no-pull-policy", "order", "header", "trailing-newline"])
def test_any_other_change_is_detected(mutate):
    text = _COMPOSE.read_text(encoding="utf-8")
    assert two_line_change_problems(text) == []  # positive control on the same text
    assert two_line_change_problems(mutate(text)) != []


def test_base_pin_matches_the_mission_base_commit():
    try:
        base = subprocess.run(["git", "show", f"{BASE_COMMIT}:services/vikunja/docker-compose.yml"],
                              cwd=_ROOT, capture_output=True, check=True, timeout=30).stdout
    except (subprocess.CalledProcessError, OSError) as exc:  # shallow CI clone
        pytest.skip(f"mission base {BASE_COMMIT} not in this clone: {type(exc).__name__}")
    assert hashlib.sha256(base).hexdigest() == BASE_COMPOSE_SHA256
    assert base.decode("utf-8").count(OLD_LINE) == 1


# ---------------------------------------------------------------------------
# T034 — the ACTIVATE manifest
# ---------------------------------------------------------------------------


def expected_post_checks(rec: dict) -> list[str]:
    """The release-exact reconcile (R-12), built from the release record."""
    svc = rec["service"]
    return [
        f"docker inspect {svc['container']} --format '{{{{.Image}}}}' | grep -qx {rec['image']['config_digest']}",
        f"curl -fsS --max-time 5 {svc['info_url']} | jq -e '.version == \"{rec['release_version']}\"'",
    ]


def _expected_stage_checks(rec: dict) -> list[str]:
    return [
        f"docker image inspect --format '{{{{.Id}}}}' {rec['tags']['release']} | grep -qx {rec['image']['config_digest']}",
        f"docker image inspect --format '{{{{.Id}}}}' {rec['rollback']['ref']} | grep -qx {rec['rollback']['image_id']}",
    ]


def _check_manifest(root: Path, path: Path, rec: dict, kind: str, issue: str) -> dict:
    m = _manifest(path)
    entry = f"scripts/deploy/deploy-vikunja-release-{kind}.py"
    assert m["schema_version"] == "v1"
    assert m["name"] == f"vikunja-release-{kind}"
    assert m["issue"] == f"kentonium3/kg-automation#{issue}"
    assert m["tier"] == 2 and m["audited_surface"] is True
    assert m["entrypoint"] == entry and (root / entry).is_file()
    assert m["expected_baselines"] == ["docker-images.txt"]
    assert manifest_lib.validate_expected_baselines_only(m).ok
    assert m["created_by"] and m["created_at"]
    assert 0 < len(m["notes"]) <= 2000
    assert m["verification"]["pre"] == [f"{entry} --dry-run"]
    expected = expected_post_checks(rec) if kind == "activate" else _expected_stage_checks(rec)
    assert m["verification"]["post"] == expected
    return m


def _manifest_issue(path: Path) -> str:
    issue = _manifest(path)["issue"]
    assert re.fullmatch(r"kentonium3/kg-automation#[1-9][0-9]*", issue)
    return issue.rsplit("#", 1)[1]


def _predecessor(root: Path, rec: dict) -> dict:
    version = baseline.previous_version(rec)
    matches = [value for path in sorted((root / "services/vikunja/releases").glob("*.json"))
               if (value := json.loads(path.read_text()))["release_version"] == version]
    assert len(matches) == 1, "missing or ambiguous predecessor"
    [previous] = matches
    assert rec["rollback"]["image_id"] == previous["image"]["config_digest"]
    assert {k: rec["rollback"]["archive"][k] for k in ("sha256", "size")} == previous["archive"]
    return previous


def _resolve_manifest_path(root: Path, rec: dict, kind: str, issue: str | None = None) -> Path | None:
    """A queued manifest is authoritative even when malformed or stale."""
    queued = root / f"deploys/queued/vikunja-release-{kind}.yaml"
    if queued.exists():
        _check_manifest(root, queued, rec, kind, issue or _manifest_issue(queued))
        return queued
    matches = []
    for path in sorted((root / "deploys/applied").glob(f"*-vikunja-release-{kind}.yaml")):
        if path.name in (_HISTORICAL_ACTIVATE, _HISTORICAL_STAGE):
            continue
        m = _manifest(path)
        expected = expected_post_checks(rec) if kind == "activate" else _expected_stage_checks(rec)
        if m["verification"]["post"] == expected:
            _check_manifest(root, path, rec, kind, issue or _manifest_issue(path))
            matches.append(path)
        else:
            # An applied record naming the current version/tag with broken
            # checks is invalid, rather than an excuse to select history.
            identity = rec["release_version"] if kind == "activate" else rec["tags"]["release"]
            assert identity not in "\n".join(m["verification"]["post"])
    assert len(matches) <= 1, "ambiguous current manifests"
    return matches[0] if matches else None


def _check_inventory(root: Path, rec: dict, historical: dict, phase: str, issue: str) -> None:
    data = json.loads((root / _INVENTORY_JSON.relative_to(_ROOT)).read_text())
    [entry] = [s for s in data["services"] if s.get("name") == "vikunja"]
    compose = yaml.safe_load((root / _COMPOSE.relative_to(_ROOT)).read_text())["services"]["vikunja"]
    assert compose["image"] == rec["tags"]["active"] == entry["image"]
    assert compose["pull_policy"] == "never"
    deployed = rec if phase == "ACTIVATE" else historical
    assert entry["updated_by"] == issue
    assert issue in data["updated_by"]
    for value in (deployed["release_version"], deployed["source_revision"],
                  deployed["archive"]["sha256"], deployed["image"]["config_digest"],
                  deployed["rollback"]["image_id"]):
        assert value in entry["notes"]
    md = (root / _INVENTORY_MD.relative_to(_ROOT)).read_text()
    rows = [line for line in md.splitlines() if line.startswith("| Vikunja |")]
    assert len(rows) == 1
    assert deployed["release_version"] in rows[0] and rec["tags"]["active"] in rows[0]
    assert "`pull_policy: never`" in md
    if phase == "STAGE":
        assert rec["rollback"]["image_id"] == historical["image"]["config_digest"]
        tag = rec["rollback"]["ref"].rsplit(":", 1)[1]
        assert (tag if tag.startswith("v") else "v" + tag) == historical["release_version"]
        assert rec["release_version"] not in entry["notes"]
        assert rec["image"]["config_digest"] not in entry["notes"]
        assert rec["release_version"] not in rows[0]


def check_tree(root: Path) -> str:
    """Validate history in every phase, then the current release and inventory."""
    historical = _historical_release(root)
    applied = root / "deploys/applied"
    _check_manifest(root, applied / _HISTORICAL_STAGE, historical, "stage", "1087")
    m = _check_manifest(root, applied / _HISTORICAL_ACTIVATE, historical, "activate", "1087")
    assert m["created_by"] == "claude-code-1087"
    for needle in ("R-21", "Cancel (R-17)", "ACTIVATE_ROLLED_BACK_REMOVE_QUEUED_MANIFEST",
                   "Retry (R-24)", "retired.json"):
        assert needle in m["notes"]
    rec = _release(root)
    if rec["release_version"] == historical["release_version"]:
        # The original tree has no repeat-release manifests.
        assert not list((root / "deploys/queued").glob("vikunja-release-*.yaml"))
        assert rec["image"] == historical["image"]
        phase = "historical"
    else:
        baseline.load_bound(rec, root)
        previous = _predecessor(root, rec)
        stage = _resolve_manifest_path(root, rec, "stage")
        assert stage is not None, "current STAGE missing"
        issue = _manifest_issue(stage)
        phase = "ACTIVATE" if _resolve_manifest_path(root, rec, "activate", issue) else "STAGE"
        _check_inventory(root, rec, previous, phase,
                         "#" + issue if phase == "ACTIVATE" else previous["activate_issue"])
        return phase
    _check_inventory(root, rec, historical, phase, "#1087")
    return phase


def test_current_tree():
    assert check_tree(_ROOT) in {"historical", "STAGE", "ACTIVATE"}


def test_release_history_matches_released_records():
    for rec, issue in ((_historical_release(_ROOT), "#1087"), (_release(), None)):
        if not (_ROOT / "services/vikunja/releases" / (rec["release_version"] + ".json")).exists():
            # A newly staged release has no applied history entry yet.
            assert issue is None
            continue
        history = json.loads((_ROOT / "services/vikunja/releases" / (rec["release_version"] + ".json")).read_text())
        assert set(history) == {"release_version", "source_revision", "archive", "image", "rollback",
                                "stage_issue", "activate_issue"}
        for key in ("release_version", "source_revision"):
            assert history[key] == rec[key]
        assert history["archive"] == {k: rec["archive"][k] for k in ("sha256", "size")}
        assert history["image"] == {k: rec["image"][k] for k in ("config_digest", "index_digest")}
        assert history["rollback"] == {
            "ref": rec["rollback"]["ref"], "image_id": rec["rollback"]["image_id"],
            "archive": {k: rec["rollback"]["archive"][k] for k in ("sha256", "size")},
        }
        if issue is not None:
            assert history["stage_issue"] == history["activate_issue"] == issue
        for kind in ("stage", "activate"):
            path = _resolve_manifest_path(_ROOT, rec, kind) if issue is None else (
                _ROOT / "deploys/applied" / (_HISTORICAL_STAGE if kind == "stage" else _HISTORICAL_ACTIVATE))
            assert path is not None
            assert history[kind + "_issue"] == "#" + _manifest_issue(path)


def test_historical_manifest_schema_controls():
    m = _manifest(_ROOT / "deploys/applied" / _HISTORICAL_ACTIVATE)
    assert not manifest_lib.validate_manifest(dict(m, surprise=True)).ok
    assert not manifest_lib.validate_expected_baselines_only(dict(m, expected_baselines=["nope.txt"])).ok
    assert not manifest_lib.validate_expected_baselines_only(dict(m, audited_surface=False)).ok


def test_cutover_path_sets():
    assert CUTOVER_PATHS == {
        "deploys/queued/vikunja-release-activate.yaml",
        "docs/design/architecture/data/service-inventory.json",
        "docs/design/architecture/service-inventory.md",
    }
    assert HISTORICAL_CUTOVER_PATHS == CUTOVER_PATHS | {
        "services/vikunja/docker-compose.yml",
        "tests/deploy/test_vikunja_cutover_change_set.py",
    }
    assert CUTOVER_PATHS.isdisjoint(STAGE_MERGE_PREREQUISITES)
    assert _ENTRY_REL in STAGE_MERGE_PREREQUISITES
    for path in STAGE_MERGE_PREREQUISITES - {"deploys/queued/vikunja-release-stage.yaml"}:
        assert (_ROOT / path).is_file()


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) if not isinstance(value, str) else value, encoding="utf-8")


def _promote(root: Path, rec: dict, issue: str = "#1095") -> None:
    _write(root / _INVENTORY_JSON.relative_to(_ROOT), {
        "updated_by": issue, "services": [{
            "name": "vikunja", "image": rec["tags"]["active"], "updated_by": issue,
            "notes": " ".join((rec["release_version"], rec["source_revision"], rec["archive"]["sha256"],
                               rec["image"]["config_digest"], rec["rollback"]["image_id"])),
        }],
    })
    _write(root / _INVENTORY_MD.relative_to(_ROOT),
           f"| Vikunja | `{rec['tags']['active']}` | {rec['release_version']} |\n`pull_policy: never`\n")


@pytest.fixture
def phase_tree(tmp_path):
    for path in (_ROOT / "services/vikunja/releases").glob("*.json"):
        _write(tmp_path / "services/vikunja/releases" / path.name, json.loads(path.read_text()))
    for rel in (
        _COMPOSE.relative_to(_ROOT), _INVENTORY_JSON.relative_to(_ROOT), _INVENTORY_MD.relative_to(_ROOT),
        Path("deploys/applied") / _HISTORICAL_STAGE, Path("deploys/applied") / _HISTORICAL_ACTIVATE,
        Path(_ENTRY_REL), Path("scripts/deploy/deploy-vikunja-release-stage.py"),
    ):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_ROOT / rel, target)
    historical = _historical_release(tmp_path)
    _promote(tmp_path, historical, "#1087")
    _write(tmp_path / "services/vikunja/release.json", historical)
    assert check_tree(tmp_path) == "historical"
    rec = json.loads(json.dumps(historical))
    rec["release_version"] = "v3.0.0-rrule.1"
    rec["source_revision"] = "a" * 40
    rec["image"]["config_digest"] = "sha256:" + "b" * 64
    rec["archive"]["sha256"] = "c" * 64
    rec["tags"]["release"] = "office2.local/vikunja:" + rec["release_version"]
    rec["rollback"]["ref"] = historical["tags"]["release"]
    rec["rollback"]["image_id"] = historical["image"]["config_digest"]
    rec["rollback"]["archive"] = historical["archive"].copy()
    facts = {
        "schema_version": 1, "previous_version": historical["release_version"],
        "previous_image_config": rec["rollback"]["image_id"],
        "pre_upgrade_migration_ids": ["10", "SCHEMA_INIT"],
        "added_migration_ids": [str(i) for i in range(20, 30)],
        "schema_identity": {"algorithm": "sqlite-master-sha256-v1",
                            "pre_upgrade": "d" * 64, "target": "e" * 64},
    }
    rel = "services/vikunja/baselines/synthetic.json"
    _write(tmp_path / rel, facts)
    rec["baseline"] = {"path": rel, "sha256": hashlib.sha256((tmp_path / rel).read_bytes()).hexdigest()}
    _write(tmp_path / "services/vikunja/release.json", rec)
    for kind, name in (("stage", _HISTORICAL_STAGE), ("activate", _HISTORICAL_ACTIVATE)):
        m = _manifest(tmp_path / "deploys/applied" / name)
        for key in ("apply_mode", "applied_at", "rebaseline"):
            m.pop(key)
        m.update(issue="kentonium3/kg-automation#1095", created_by="synthetic-implementer",
                 notes="Synthetic repeat cutover; see #1095.")
        m["verification"]["post"] = _expected_stage_checks(rec) if kind == "stage" else expected_post_checks(rec)
        _write(tmp_path / f"deploys/queued/vikunja-release-{kind}.yaml", m)
    activate_path = tmp_path / "deploys/queued/vikunja-release-activate.yaml"
    activate_manifest = _manifest(activate_path)
    activate_path.unlink()
    assert check_tree(tmp_path) == "STAGE"
    return tmp_path, rec, activate_manifest


@pytest.fixture
def next_release_tree(phase_tree):
    root, rec, activate = phase_tree
    previous = json.loads((root / "services/vikunja/releases/v2.8.0-rrule.2.json").read_text())
    previous["tags"] = {"release": "office2.local/vikunja:" + previous["release_version"],
                        "active": rec["tags"]["active"]}
    previous["archive"]["path"] = rec["archive"]["path"]
    rec["rollback"] = {"ref": previous["tags"]["release"],
                       "image_id": previous["image"]["config_digest"],
                       "archive": previous["archive"].copy()}
    path = root / rec["baseline"]["path"]
    facts = json.loads(path.read_text())
    facts.update(previous_version=previous["release_version"],
                 previous_image_config=previous["image"]["config_digest"])
    _write(path, facts)
    rec["baseline"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    _write(root / "services/vikunja/release.json", rec)
    stage_path = root / "deploys/queued/vikunja-release-stage.yaml"
    stage = _manifest(stage_path)
    stage["issue"] = activate["issue"] = "kentonium3/kg-automation#1200"
    stage["verification"]["post"] = _expected_stage_checks(rec)
    activate["verification"]["post"] = expected_post_checks(rec)
    _write(stage_path, stage)
    _promote(root, previous)
    return root, rec, activate


def test_next_release_uses_applied_predecessor_and_new_issue(next_release_tree):
    root, rec, activate = next_release_tree
    assert check_tree(root) == "STAGE"
    _write(root / "deploys/queued/vikunja-release-activate.yaml", activate)
    _promote(root, rec, "#1200")
    assert check_tree(root) == "ACTIVATE"


@pytest.mark.parametrize("fault", ["digest", "archive-hash", "archive-size", "missing", "duplicate", "older"])
def test_next_release_predecessor_refusals(next_release_tree, fault):
    root, rec, _ = next_release_tree
    assert check_tree(root) == "STAGE"
    history = root / "services/vikunja/releases/v2.8.0-rrule.2.json"
    if fault == "missing":
        history.unlink()
    elif fault == "duplicate":
        _write(history.with_name("duplicate.json"), json.loads(history.read_text()))
    elif fault == "digest":
        rec["rollback"]["image_id"] = "sha256:" + "0" * 64
    elif fault == "archive-hash":
        rec["rollback"]["archive"]["sha256"] = "0" * 64
    elif fault == "archive-size":
        rec["rollback"]["archive"]["size"] += 1
    else:
        older = _historical_release(root)
        rec["rollback"] = {"ref": older["tags"]["release"],
                           "image_id": older["image"]["config_digest"], "archive": older["archive"]}
        path = root / rec["baseline"]["path"]
        facts = json.loads(path.read_text())
        facts.update(previous_version=older["release_version"],
                     previous_image_config=older["image"]["config_digest"])
        _write(path, facts)
        rec["baseline"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    if fault in {"digest", "older"}:
        path = root / "deploys/queued/vikunja-release-stage.yaml"
        stage = _manifest(path)
        stage["verification"]["post"] = _expected_stage_checks(rec)
        _write(path, stage)
    _write(root / "services/vikunja/release.json", rec)
    with pytest.raises((AssertionError, core.Fail)):
        check_tree(root)


@pytest.mark.parametrize("stage_applied", [False, True])
@pytest.mark.parametrize("activate_form", ["absent", "queued", "applied"])
def test_phase_matrix(phase_tree, stage_applied, activate_form):
    root, rec, m = phase_tree
    if stage_applied:
        (root / "deploys/queued/vikunja-release-stage.yaml").rename(
            root / "deploys/applied/0040-vikunja-release-stage.yaml")
    if activate_form != "absent":
        path = ("deploys/queued/vikunja-release-activate.yaml" if activate_form == "queued"
                else "deploys/applied/0041-vikunja-release-activate.yaml")
        _write(root / path, m)
        _promote(root, rec)
    assert check_tree(root) == ("STAGE" if activate_form == "absent" else "ACTIVATE")


@pytest.mark.parametrize("fault", [
    "yaml", "wrong-release", "missing-post", "wrong-image", "audit", "baselines",
    "issue", "entrypoint", "pre", "tier", "creator",
])
@pytest.mark.parametrize("stage_applied", [False, True])
def test_invalid_queued_activate_never_falls_back(phase_tree, fault, stage_applied):
    root, rec, m = phase_tree
    if stage_applied:
        (root / "deploys/queued/vikunja-release-stage.yaml").rename(
            root / "deploys/applied/0040-vikunja-release-stage.yaml")
    queued = root / "deploys/queued/vikunja-release-activate.yaml"
    # A valid applied current record and history cannot mask a broken queue.
    _write(root / "deploys/applied/0041-vikunja-release-activate.yaml", m)
    _write(queued, m)
    _promote(root, rec)
    assert check_tree(root) == "ACTIVATE"
    if fault == "wrong-release":
        m["verification"]["post"][1] = "echo stale-release"
    elif fault == "missing-post":
        m["verification"]["post"] = []
    elif fault == "wrong-image":
        m["verification"]["post"][0] = "echo wrong-image"
    elif fault == "audit":
        m["audited_surface"] = False
    elif fault == "baselines":
        m["expected_baselines"] = []
    elif fault == "issue":
        m["issue"] = "kentonium3/kg-automation#1087"
    elif fault == "entrypoint":
        m["entrypoint"] = "scripts/deploy/deploy-vikunja-release-stage.py"
    elif fault == "pre":
        m["verification"]["pre"] = []
    elif fault == "tier":
        m["tier"] = 1
    elif fault == "creator":
        m["created_by"] = ""
    _write(queued, "[" if fault == "yaml" else m)
    with pytest.raises(AssertionError):
        check_tree(root)


@pytest.mark.parametrize("fault", [
    "binding-missing", "binding-hash", "baseline-missing", "stage-missing", "stage-stale",
    "inventory-premature", "inventory-json", "inventory-md", "applied-post",
])
def test_phase_refusals(phase_tree, fault):
    root, rec, m = phase_tree
    assert check_tree(root) == "STAGE"
    if fault == "binding-missing":
        rec.pop("baseline")
    elif fault == "binding-hash":
        rec["baseline"]["sha256"] = "0" * 64
    elif fault == "baseline-missing":
        (root / rec["baseline"]["path"]).unlink()
    elif fault.startswith("stage-"):
        path = root / "deploys/queued/vikunja-release-stage.yaml"
        if fault == "stage-missing":
            path.unlink()
        else:
            value = _manifest(path)
            value["verification"]["post"] = _expected_stage_checks(_historical_release(root))
            _write(path, value)
    elif fault == "inventory-premature":
        _promote(root, rec)
    else:
        _write(root / "deploys/applied/0041-vikunja-release-activate.yaml", m)
        _promote(root, rec)
        assert check_tree(root) == "ACTIVATE"
        if fault == "inventory-json":
            path = root / _INVENTORY_JSON.relative_to(_ROOT)
            value = json.loads(path.read_text())
            value["services"][0]["notes"] = "stale inventory"
            _write(path, value)
        elif fault == "inventory-md":
            path = root / _INVENTORY_MD.relative_to(_ROOT)
            _write(path, path.read_text().replace(rec["release_version"], "v0.0.0"))
        else:
            m["verification"]["post"][0] = "echo broken-current-image"
            _write(root / "deploys/applied/0041-vikunja-release-activate.yaml", m)
    _write(root / "services/vikunja/release.json", rec)
    with pytest.raises((AssertionError, core.Fail)):
        check_tree(root)


def test_stale_applied_activate_does_not_promote_inventory(phase_tree):
    root, rec, m = phase_tree
    historical = _historical_release(root)
    m["verification"]["post"] = expected_post_checks(historical)
    _write(root / "deploys/applied/9999-vikunja-release-activate.yaml", m)
    assert check_tree(root) == "STAGE"


@pytest.mark.parametrize("fault", ["issue", "post", "stage-post", "unexpected-queue"])
def test_frozen_history_refusals(phase_tree, fault):
    root, _, queued = phase_tree
    historical = _historical_release(root)
    _write(root / "services/vikunja/release.json", historical)
    (root / "deploys/queued/vikunja-release-stage.yaml").unlink()
    _promote(root, historical, "#1087")
    assert check_tree(root) == "historical"
    path = root / "deploys/applied" / (_HISTORICAL_STAGE if fault == "stage-post" else _HISTORICAL_ACTIVATE)
    m = _manifest(path)
    if fault == "unexpected-queue":
        _write(root / "deploys/queued/vikunja-release-activate.yaml", queued)
    else:
        if fault == "issue":
            m["issue"] = "kentonium3/kg-automation#1095"
        else:
            m["verification"]["post"][0] = "echo wrong historical image"
        _write(path, m)
    with pytest.raises(AssertionError):
        check_tree(root)


def test_invalid_queued_stage_is_not_masked_by_applied_current(phase_tree):
    root, _, _ = phase_tree
    path = root / "deploys/queued/vikunja-release-stage.yaml"
    m = _manifest(path)
    _write(root / "deploys/applied/0040-vikunja-release-stage.yaml", m)
    assert check_tree(root) == "STAGE"
    m["verification"]["post"] = _expected_stage_checks(_historical_release(root))
    _write(path, m)
    with pytest.raises(AssertionError):
        check_tree(root)


@pytest.mark.parametrize("wal", [False, True])
def test_documented_b3_keeps_stable_db_and_wal_without_shm(tmp_path, wal):
    text = (_ROOT / "docs/runbooks/vikunja-release-cutover.md").read_text()
    script = text.split("python3 - <<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
    source = tmp_path / "data"
    source.mkdir()
    (source / "vikunja.db").write_bytes(b"synthetic database bytes")
    (source / "vikunja.db-shm").write_bytes(b"synthetic index bytes")
    if wal:
        (source / "vikunja.db-wal").write_bytes(b"synthetic WAL bytes")
    private = tmp_path / "copies"
    private.mkdir(mode=0o700)
    _write(tmp_path / "services/vikunja/release.json", {
        "service": {"data_dir": str(source)}, "roots": {"private_logs": str(private)},
    })
    result = subprocess.run([sys.executable, "-c", script], cwd=tmp_path, capture_output=True,
                            text=True, timeout=10, check=True)
    copy = Path(result.stdout.strip())
    assert copy.parent.parent == private
    assert copy.read_bytes() == (source / "vikunja.db").read_bytes()
    assert not copy.with_name("vikunja.db-shm").exists()
    assert copy.with_name("vikunja.db-wal").exists() is wal
    if wal:
        assert copy.with_name("vikunja.db-wal").read_bytes() == (source / "vikunja.db-wal").read_bytes()
    assert list(private.iterdir()) == [copy.parent]
    assert copy.parent.stat().st_mode & 0o777 == 0o700


def test_candidate_archive_includes_repeat_dependencies():
    text = (_ROOT / "docs/runbooks/vikunja-release-cutover.md").read_text()
    archive = text.split('git -C "$REPO" archive --format=tar "$CAND"', 1)[1].split("| ssh", 1)[0]
    for rel in (
        "scripts/deploy/deploy-vikunja-release-stage.py",
        "scripts/deploy/deploy-vikunja-release-activate.py",
        "scripts/deploy/vikunja_release", "scripts/deploy/lib",
        "scripts/vikunja/preflight_release_baseline.py",
        "scripts/vikunja/verify_release_upgrade.py",
        "scripts/vikunja/build_release_baseline.py",
        "scripts/vikunja/rollback_release.py",
        "services/vikunja/release.json", "services/vikunja/baselines",
    ):
        assert rel in archive
        if rel != "services/vikunja/baselines" or "baseline" in _release():
            assert (_ROOT / rel).exists()
    assert (_ROOT / "scripts/deploy/vikunja_release/baseline.py").is_file()
    rec = _release()
    if "baseline" in rec:
        assert Path(rec["baseline"]["path"]).is_relative_to("services/vikunja/baselines")
